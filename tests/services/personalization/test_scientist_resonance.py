from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.llm.config import LLMConfig
from deeptutor.services.memory.service import MemoryService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get_memory_dir(self) -> Path:
        return self.root / "memory"


def make_memory_service(
    tmp_path: Path,
    *,
    store: SQLiteSessionStore | None = None,
    profile_text: str = "",
) -> MemoryService:
    service = MemoryService(
        path_service=_PathServiceStub(tmp_path),
        store=store or SQLiteSessionStore(tmp_path / "chat_history.db"),
    )
    if profile_text:
        service.write_file("profile", profile_text)
    return service


def make_resonance_service(
    tmp_path: Path,
    *,
    store: SQLiteSessionStore,
    profile_text: str = "",
):
    from deeptutor.services.personalization.scientist_resonance import ScientistResonanceService

    return ScientistResonanceService(
        memory_service=make_memory_service(tmp_path, store=store, profile_text=profile_text),
        store=store,
        cache_path=tmp_path / "scientist_resonance_cache.json",
    )


@pytest.fixture
def store(tmp_path: Path) -> SQLiteSessionStore:
    return SQLiteSessionStore(tmp_path / "chat_history.db")


def test_load_scientist_pool_reads_extended_fields() -> None:
    from deeptutor.services.personalization.scientist_resonance import load_scientist_pool

    pool = load_scientist_pool()

    assert "ramanujan" in pool
    assert pool["ramanujan"].core_traits
    assert pool["ramanujan"].thinking_style
    assert pool["ramanujan"].temperament_summary
    assert pool["ramanujan"].loading_copy_zh
    assert pool["ramanujan"].bio_zh
    assert pool["ramanujan"].achievements_zh
    assert all(item.loading_copy_zh and item.bio_zh and item.achievements_zh for item in pool.values())
    assert all(item.loading_copy_en and item.bio_en and item.achievements_en for item in pool.values())


def test_load_scientist_pool_includes_selected_chinese_scientists() -> None:
    from deeptutor.services.personalization.scientist_resonance import load_scientist_pool

    pool = load_scientist_pool()
    public_portraits = Path("web/public/scientist-portraits")

    expected = [
        "yang_zhenning",
        "qian_xuesen",
        "hua_luogeng",
        "deng_jiaxian",
    ]

    for slug in expected:
        assert slug in pool
        assert (public_portraits / f"{slug}.jpg").exists()


def test_selected_chinese_scientists_have_english_descriptions() -> None:
    from deeptutor.services.personalization.scientist_resonance import load_scientist_pool

    pool = load_scientist_pool()

    for slug in ["yang_zhenning", "qian_xuesen", "hua_luogeng", "deng_jiaxian"]:
        scientist = pool[slug]
        assert scientist.loading_copy_en
        assert scientist.bio_en
        assert scientist.achievements_en


def test_get_scientist_resonance_llm_config_defaults_to_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.personalization import scientist_resonance as module

    base_config = LLMConfig(
        model="global-model",
        api_key="global-key",
        base_url="https://global.example/v1",
        binding="openai",
        api_version="2025-01-01",
        reasoning_effort="medium",
        extra_headers={"X-Test": "1"},
    )

    class _EnvStoreStub:
        def get(self, key: str, default: str = "") -> str:
            return default

    monkeypatch.setattr(module, "get_llm_config", lambda: base_config)
    monkeypatch.setattr(module, "get_env_store", lambda: _EnvStoreStub())

    resolved = module.get_scientist_resonance_llm_config()

    assert resolved.model == "global-model"
    assert resolved.api_key == "global-key"
    assert resolved.base_url == "https://global.example/v1"
    assert resolved.binding == "openai"
    assert resolved.api_version == "2025-01-01"
    assert resolved.reasoning_effort == "medium"
    assert resolved.extra_headers == {"X-Test": "1"}


def test_get_scientist_resonance_llm_config_allows_partial_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.personalization import scientist_resonance as module

    base_config = LLMConfig(
        model="global-model",
        api_key="global-key",
        base_url="https://global.example/v1",
        binding="openai",
        api_version="2025-01-01",
        reasoning_effort="medium",
    )
    env_values = {
        "SCIENTIST_RESONANCE_LLM_MODEL": "resonance-model",
        "SCIENTIST_RESONANCE_LLM_HOST": "https://resonance.example/v1",
        "SCIENTIST_RESONANCE_REASONING_EFFORT": "high",
    }

    class _EnvStoreStub:
        def get(self, key: str, default: str = "") -> str:
            return env_values.get(key, default)

    monkeypatch.setattr(module, "get_llm_config", lambda: base_config)
    monkeypatch.setattr(module, "get_env_store", lambda: _EnvStoreStub())

    resolved = module.get_scientist_resonance_llm_config()

    assert resolved.model == "resonance-model"
    assert resolved.base_url == "https://resonance.example/v1"
    assert resolved.effective_url == "https://resonance.example/v1"
    assert resolved.reasoning_effort == "high"
    assert resolved.binding == "openai"
    assert resolved.api_key == "global-key"


@pytest.mark.asyncio
async def test_infer_scientist_resonance_passes_dedicated_llm_config(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from deeptutor.services.personalization import scientist_resonance as module

    llm_config = LLMConfig(
        model="resonance-model",
        api_key="resonance-key",
        base_url="https://resonance.example/v1",
        binding="custom",
        api_version="2025-02-02",
        reasoning_effort="high",
        extra_headers={"X-Resonance": "1"},
    )
    captured: dict[str, object] = {}

    async def fake_complete(*args, **kwargs):
        captured.update(kwargs)
        return json.dumps(
            {
                "long_term": {
                    "primary": {
                        "slug": "ramanujan",
                        "reason": "你会先抓模式，再补表达。",
                        "resonance_axes": ["模式敏感", "直觉跳跃"],
                    },
                    "secondary": [
                        {
                            "slug": "turing",
                            "reason": "你也会把问题切到结构骨架。",
                            "resonance_axes": ["结构化", "本质导向"],
                        },
                        {
                            "slug": "feynman",
                            "reason": "你也保留了强烈的解释冲动。",
                            "resonance_axes": ["解释冲动", "问题驱动"],
                        },
                    ],
                },
                "recent_state": None,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(module, "get_scientist_resonance_llm_config", lambda: llm_config)
    monkeypatch.setattr(module, "complete", fake_complete)

    with caplog.at_level("INFO"):
        result = await module.infer_scientist_resonance(
            profile_text="偏模式敏感",
            recent_messages=["最近在反复比较不同解法"],
            language="zh",
        )

    assert captured["model"] == "resonance-model"
    assert captured["api_key"] == "resonance-key"
    assert captured["base_url"] == "https://resonance.example/v1"
    assert captured["binding"] == "custom"
    assert captured["api_version"] == "2025-02-02"
    assert captured["reasoning_effort"] == "high"
    assert captured["extra_headers"] == {"X-Resonance": "1"}
    assert result["long_term"]["primary"]["slug"] == "ramanujan"
    assert len(result["long_term"]["secondary"]) == 2
    assert "Scientist Resonance requesting LLM" in caplog.text
    assert "model=resonance-model" in caplog.text


@pytest.mark.asyncio
async def test_regenerate_returns_structured_cards(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    from deeptutor.services.personalization.scientist_resonance import ScientistResonanceService

    async def fake_complete(*args, **kwargs):
        return json.dumps(
            {
                "long_term": {
                    "primary": {
                        "slug": "ramanujan",
                        "reason": "你会先抓模式，再回头补表达。",
                        "resonance_axes": ["直觉跳跃", "模式敏感", "非标准路径"],
                    },
                    "secondary": [
                        {
                            "slug": "turing",
                            "reason": "你也会把问题切到本质结构。",
                            "resonance_axes": ["本质导向", "结构感"],
                        },
                        {
                            "slug": "feynman",
                            "reason": "你也保留了很强的讲透冲动。",
                            "resonance_axes": ["解释冲动", "问题驱动"],
                        },
                    ],
                },
                "recent_state": {
                    "slug": "feynman",
                    "reason": "你最近更像费曼：总想亲手把问题讲透。",
                    "resonance_axes": ["问题驱动", "解释冲动", "推进感"],
                },
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "deeptutor.services.personalization.scientist_resonance.complete",
        fake_complete,
    )

    await store.create_session(session_id="s1")
    for idx in range(5):
        await store.add_message(session_id="s1", role="user", content=f"user message {idx}")

    service = make_resonance_service(
        tmp_path,
        store=store,
        profile_text="## CoPA Factors\n- 偏直觉、模式敏感、非标准路径",
    )

    result = await service.regenerate(language="zh", mode="long_term")

    assert result["long_term"]["primary"]["slug"] == "ramanujan"
    assert result["long_term"]["primary"]["quote_zh"]
    assert result["long_term"]["primary"]["quote_en"]
    assert result["long_term"]["primary"]["loading_copy_zh"]
    assert result["long_term"]["primary"]["loading_copy_en"]
    assert result["long_term"]["primary"]["bio_zh"]
    assert result["long_term"]["primary"]["bio_en"]
    assert result["long_term"]["primary"]["achievements_zh"]
    assert result["long_term"]["primary"]["achievements_en"]
    assert [item["slug"] for item in result["long_term"]["secondary"]] == ["turing", "feynman"]
    assert result["recent_state"]["slug"] == "feynman"
    assert result["recent_state"]["portrait_url"].endswith("/feynman.jpg")


@pytest.mark.asyncio
async def test_get_resonance_returns_null_recent_state_when_not_enough_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    from deeptutor.services.personalization.scientist_resonance import ScientistResonanceService

    async def fake_complete(*args, **kwargs):
        return json.dumps(
            {
                "long_term": {
                    "primary": {
                        "slug": "turing",
                        "reason": "你会把问题切到本质层。",
                        "resonance_axes": ["本质导向", "非标准路径"],
                    },
                    "secondary": [],
                },
                "recent_state": None,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "deeptutor.services.personalization.scientist_resonance.complete",
        fake_complete,
    )

    await store.create_session(session_id="s1")
    await store.add_message(session_id="s1", role="user", content="only one message")

    service = make_resonance_service(
        tmp_path,
        store=store,
        profile_text="## Preferences\n- 偏本质导向",
    )

    result = await service.get_resonance(language="zh")

    assert result["long_term"]["primary"]["slug"] == "turing"
    assert len(result["long_term"]["secondary"]) == 2
    assert result["recent_state"] is None


@pytest.mark.asyncio
async def test_get_resonance_bootstrap_uses_english_reason_when_language_is_en(
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    service = make_resonance_service(
        tmp_path,
        store=store,
        profile_text="## Preferences\n- pattern sensitive and intuitive",
    )

    result = await service.get_resonance(language="en")

    assert result["long_term"] is not None
    assert result["long_term"]["primary"]["quote_en"]
    assert result["long_term"]["primary"]["bio_en"]
    assert result["long_term"]["primary"]["achievements_en"]
    assert result["long_term"]["primary"]["reason"].startswith("Your long-term archetype feels closest to ")


def test_pick_secondary_candidates_prefers_diversity_over_adjacent_duplicates() -> None:
    from deeptutor.services.personalization.scientist_resonance import (
        ScientistRecord,
        _pick_secondary_candidates,
    )

    pool = {
        "ramanujan": ScientistRecord(
            slug="ramanujan",
            name="Ramanujan",
            quote_en="",
            quote_zh="",
            core_traits="直觉跳跃、模式敏感",
            thinking_style="",
            temperament_tags="孤峰式、非标准路径",
            temperament_summary="",
            loading_copy_zh="",
            loading_copy_en="",
            bio_zh="",
            bio_en="",
            achievements_zh="",
            achievements_en="",
        ),
        "godel": ScientistRecord(
            slug="godel",
            name="Godel",
            quote_en="",
            quote_zh="",
            core_traits="直觉跳跃、模式敏感",
            thinking_style="",
            temperament_tags="孤峰式、内倾沉思",
            temperament_summary="",
            loading_copy_zh="",
            loading_copy_en="",
            bio_zh="",
            bio_en="",
            achievements_zh="",
            achievements_en="",
        ),
        "turing": ScientistRecord(
            slug="turing",
            name="Turing",
            quote_en="",
            quote_zh="",
            core_traits="结构化、抽象建模",
            thinking_style="",
            temperament_tags="冷静、系统构造",
            temperament_summary="",
            loading_copy_zh="",
            loading_copy_en="",
            bio_zh="",
            bio_en="",
            achievements_zh="",
            achievements_en="",
        ),
        "feynman": ScientistRecord(
            slug="feynman",
            name="Feynman",
            quote_en="",
            quote_zh="",
            core_traits="问题驱动、解释冲动",
            thinking_style="",
            temperament_tags="外放、实验感",
            temperament_summary="",
            loading_copy_zh="",
            loading_copy_en="",
            bio_zh="",
            bio_en="",
            achievements_zh="",
            achievements_en="",
        ),
    }

    secondary = _pick_secondary_candidates(
        primary_slug="ramanujan",
        candidates=[
            {"slug": "ramanujan", "score": 10, "reason": "primary", "resonance_axes": ["直觉跳跃"]},
            {"slug": "godel", "score": 9, "reason": "too similar", "resonance_axes": ["模式敏感"]},
            {"slug": "turing", "score": 8, "reason": "different structure", "resonance_axes": ["结构化"]},
            {"slug": "feynman", "score": 7, "reason": "different energy", "resonance_axes": ["问题驱动"]},
        ],
        pool=pool,
        limit=2,
    )

    assert [item["slug"] for item in secondary] == ["turing", "feynman"]


@pytest.mark.asyncio
async def test_regenerate_logs_fallback_reason(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from deeptutor.services.personalization.scientist_resonance import ScientistResonanceService

    async def failing_complete(*args, **kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(
        "deeptutor.services.personalization.scientist_resonance.complete",
        failing_complete,
    )

    await store.create_session(session_id="s1")
    for idx in range(4):
        await store.add_message(session_id="s1", role="user", content=f"user message {idx}")

    service = make_resonance_service(
        tmp_path,
        store=store,
        profile_text="## Preferences\n- 偏本质导向",
    )

    with caplog.at_level("WARNING"):
        result = await service.regenerate(language="zh", mode="both")

    assert result["long_term"] is not None
    assert "Scientist Resonance LLM inference failed; falling back to heuristic match" in caplog.text
    assert "llm unavailable" in caplog.text


@pytest.mark.asyncio
async def test_regenerate_backfills_secondary_candidates_when_llm_only_returns_primary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    from deeptutor.services.personalization.scientist_resonance import ScientistResonanceService

    async def fake_complete(*args, **kwargs):
        return json.dumps(
            {
                "long_term": {
                    "primary": {
                        "slug": "ramanujan",
                        "reason": "你会先抓模式。",
                        "resonance_axes": ["模式敏感", "直觉跳跃"],
                    },
                    "secondary": [],
                },
                "recent_state": None,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "deeptutor.services.personalization.scientist_resonance.complete",
        fake_complete,
    )

    await store.create_session(session_id="s1")
    for idx in range(5):
        await store.add_message(
            session_id="s1",
            role="user",
            content=f"我最近更关注结构化抽象建模，也很在意如何把问题讲透 {idx}",
        )

    service = make_resonance_service(
        tmp_path,
        store=store,
        profile_text="## Preferences\n- 偏直觉、模式敏感，也在意结构化与解释能力",
    )

    result = await service.regenerate(language="zh", mode="long_term")

    assert result["long_term"]["primary"]["slug"] == "ramanujan"
    assert len(result["long_term"]["secondary"]) == 2


@pytest.mark.asyncio
async def test_get_resonance_returns_cached_payload_without_calling_llm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    service = make_resonance_service(
        tmp_path,
        store=store,
        profile_text="## Preferences\n- 偏结构化，也会解释复杂问题",
    )
    cached_payload = {
        "zh": {
            "long_term": {
                "primary": {
                    "name": "Alan Turing",
                    "slug": "turing",
                    "portrait_url": "/scientist-portraits/turing.jpg",
                    "hook": "缓存主卡",
                    "quote_zh": "缓存中文",
                    "quote_en": "cached english",
                    "reason": "缓存结果",
                    "resonance_axes": ["结构化"],
                    "confidence_style": "strong_resonance",
                },
                "secondary": [],
            },
            "recent_state": None,
        }
    }
    service._cache_path.write_text(json.dumps(cached_payload, ensure_ascii=False), encoding="utf-8")

    async def failing_complete(*args, **kwargs):
        raise AssertionError("get_resonance should not call LLM when cache exists")

    monkeypatch.setattr(
        "deeptutor.services.personalization.scientist_resonance.complete",
        failing_complete,
    )

    result = await service.get_resonance(language="zh")

    assert result["long_term"]["primary"]["slug"] == "turing"
    assert result["long_term"]["primary"]["reason"] == "缓存结果"


@pytest.mark.asyncio
async def test_regenerate_refreshes_cache_and_get_resonance_then_uses_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    service = make_resonance_service(
        tmp_path,
        store=store,
        profile_text="## Preferences\n- 偏模式敏感，也会解释复杂问题",
    )

    await store.create_session(session_id="s1")
    for idx in range(5):
        await store.add_message(session_id="s1", role="user", content=f"user message {idx}")

    async def fake_complete(*args, **kwargs):
        return json.dumps(
            {
                "long_term": {
                    "primary": {
                        "slug": "ramanujan",
                        "reason": "新生成的主原型",
                        "resonance_axes": ["模式敏感", "直觉跳跃"],
                    },
                    "secondary": [
                        {
                            "slug": "turing",
                            "reason": "新生成的次原型 A",
                            "resonance_axes": ["结构化"],
                        },
                        {
                            "slug": "feynman",
                            "reason": "新生成的次原型 B",
                            "resonance_axes": ["解释冲动"],
                        },
                    ],
                },
                "recent_state": None,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "deeptutor.services.personalization.scientist_resonance.complete",
        fake_complete,
    )

    regenerated = await service.regenerate(language="zh", mode="long_term")

    assert regenerated["long_term"]["primary"]["reason"] == "新生成的主原型"

    async def failing_complete(*args, **kwargs):
        raise AssertionError("cached get_resonance should not call LLM after regenerate")

    monkeypatch.setattr(
        "deeptutor.services.personalization.scientist_resonance.complete",
        failing_complete,
    )

    cached = await service.get_resonance(language="zh")

    assert cached["long_term"]["primary"]["reason"] == "新生成的主原型"
