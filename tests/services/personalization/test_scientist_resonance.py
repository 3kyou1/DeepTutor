from __future__ import annotations

import json
from pathlib import Path

import pytest

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
