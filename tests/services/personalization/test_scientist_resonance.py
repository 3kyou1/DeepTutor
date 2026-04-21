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
                    "slug": "ramanujan",
                    "reason": "你会先抓模式，再补表达。",
                    "resonance_axes": ["模式敏感", "直觉跳跃"],
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
    assert result["long_term"]["slug"] == "ramanujan"
    assert "Scientist Resonance requesting LLM" in caplog.text
    assert "model=resonance-model" in caplog.text


@pytest.mark.asyncio
async def test_get_resonance_returns_structured_cards(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    from deeptutor.services.personalization.scientist_resonance import ScientistResonanceService

    async def fake_complete(*args, **kwargs):
        return json.dumps(
            {
                "long_term": {
                    "slug": "ramanujan",
                    "reason": "你会先抓模式，再回头补表达。",
                    "resonance_axes": ["直觉跳跃", "模式敏感", "非标准路径"],
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

    memory_service = make_memory_service(tmp_path, store=store, profile_text="## CoPA Factors\n- 偏直觉、模式敏感、非标准路径")
    service = ScientistResonanceService(memory_service=memory_service, store=store)

    result = await service.get_resonance(language="zh")

    assert result["long_term"]["slug"] == "ramanujan"
    assert result["long_term"]["quote_zh"]
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
                    "slug": "turing",
                    "reason": "你会把问题切到本质层。",
                    "resonance_axes": ["本质导向", "非标准路径"],
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

    memory_service = make_memory_service(tmp_path, store=store, profile_text="## Preferences\n- 偏本质导向")
    service = ScientistResonanceService(memory_service=memory_service, store=store)

    result = await service.get_resonance(language="zh")

    assert result["long_term"]["slug"] == "turing"
    assert result["recent_state"] is None


@pytest.mark.asyncio
async def test_get_resonance_logs_fallback_reason(
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

    memory_service = make_memory_service(tmp_path, store=store, profile_text="## Preferences\n- 偏本质导向")
    service = ScientistResonanceService(memory_service=memory_service, store=store)

    with caplog.at_level("WARNING"):
        result = await service.get_resonance(language="zh")

    assert result["long_term"] is not None
    assert "Scientist Resonance LLM inference failed; falling back to heuristic match" in caplog.text
    assert "llm unavailable" in caplog.text
