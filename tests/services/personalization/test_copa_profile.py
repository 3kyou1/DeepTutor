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

    def get_copa_state_file(self) -> Path:
        return self.root / "data" / "user" / "memory" / "copa_state.json"


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


@pytest.mark.asyncio
async def test_list_global_raw_user_messages_returns_only_user_messages_in_order(
    store: SQLiteSessionStore,
) -> None:
    await store.create_session(session_id="s1")
    await store.create_session(session_id="s2")
    await store.add_message(session_id="s1", role="user", content="first")
    await store.add_message(session_id="s1", role="assistant", content="ignore me")
    await store.add_message(session_id="s2", role="user", content="second")

    rows = await store.list_global_raw_user_messages()

    assert [row["content"] for row in rows] == ["first", "second"]


def test_write_copa_section_preserves_manual_profile_content(tmp_path: Path) -> None:
    svc = make_memory_service(
        tmp_path,
        profile_text="## Preferences\nManual notes",
    )

    svc.write_copa_section("## CoPA Factors\nnew block")

    content = svc.read_profile()
    assert "## Preferences\nManual notes" in content
    assert "## CoPA Factors\nnew block" in content


def test_read_copa_section_returns_empty_when_missing(tmp_path: Path) -> None:
    svc = make_memory_service(
        tmp_path,
        profile_text="## Preferences\nManual notes",
    )

    assert svc.read_copa_section() == ""


def test_filter_messages_keeps_only_raw_user_inputs() -> None:
    from deeptutor.services.personalization.copa_profile import filter_raw_user_inputs

    rows = [
        {"content": "How should I learn calculus?", "role": "user"},
        {"content": "[Quiz Performance]\nScore: 3/5", "role": "user"},
        {"content": "Assistant reply", "role": "assistant"},
    ]

    kept = filter_raw_user_inputs(rows)

    assert [item["content"] for item in kept] == ["How should I learn calculus?"]


def test_should_refresh_when_15_new_messages_accumulated() -> None:
    from deeptutor.services.personalization.copa_profile import should_refresh

    state = {"messages_consumed": 30, "refresh_threshold": 15}
    assert (
        should_refresh(
            total_user_messages=45,
            consumed=state["messages_consumed"],
            threshold=state["refresh_threshold"],
        )
        is True
    )


def test_should_not_refresh_before_threshold() -> None:
    from deeptutor.services.personalization.copa_profile import should_refresh

    assert should_refresh(total_user_messages=44, consumed=30, threshold=15) is False


@pytest.mark.asyncio
async def test_infer_copa_profile_normalizes_llm_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.personalization.copa_profile import infer_copa_profile

    async def fake_complete(*args, **kwargs):
        return """{
          "factors": {
            "CT": {
              "user_profile_description": "该用户偏好有依据、可信、可解释的回答。",
              "response_strategy": ["先给结论，再补依据", "显式说明限制条件"]
            },
            "SA": {
              "user_profile_description": "该用户偏好贴合当前任务场景的回答。",
              "response_strategy": ["优先回应当前任务", "给出直接可执行的下一步"]
            },
            "SC": {
              "user_profile_description": "该用户倾向于接受与既有表述一致的解释。",
              "response_strategy": ["沿用用户术语", "避免无必要范式切换"]
            },
            "CLM": {
              "user_profile_description": "该用户偏好分层、结构清晰的信息组织方式。",
              "response_strategy": ["先给最小可用答案", "控制单轮信息密度"]
            },
            "MS": {
              "user_profile_description": "该用户希望得到步骤支架与判断框架。",
              "response_strategy": ["给出步骤顺序", "提供验证方法"]
            },
            "AMR": {
              "user_profile_description": "该用户偏好务实、克制、具推进感的语气。",
              "response_strategy": ["保持直接语气", "减少空泛鼓励"]
            }
          }
        }"""

    monkeypatch.setattr(
        "deeptutor.services.personalization.copa_profile.complete",
        fake_complete,
    )

    result = await infer_copa_profile(["msg 1", "msg 2"])

    assert (
        result["factors"]["CT"]["user_profile_description"]
        == "该用户偏好有依据、可信、可解释的回答。"
    )
    assert result["factors"]["CT"]["response_strategy"][0] == "先给结论，再补依据"


@pytest.mark.asyncio
async def test_refresh_profile_writes_markdown_and_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    from deeptutor.services.personalization.copa_profile import CoPAProfileService

    async def fake_complete(*args, **kwargs):
        return json.dumps(
            {
                "factors": {
                    code: {
                        "user_profile_description": f"{code} description",
                        "response_strategy": [f"{code} strategy 1", f"{code} strategy 2"],
                    }
                    for code in ("CT", "SA", "SC", "CLM", "MS", "AMR")
                }
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "deeptutor.services.personalization.copa_profile.complete",
        fake_complete,
    )

    await store.create_session(session_id="s1")
    for idx in range(15):
        await store.add_message(session_id="s1", role="user", content=f"user message {idx}")

    memory_service = make_memory_service(
        tmp_path,
        store=store,
        profile_text="## Preferences\nManual notes",
    )
    service = CoPAProfileService(
        path_service=_PathServiceStub(tmp_path),
        store=store,
        memory_service=memory_service,
    )

    result = await service.refresh_profile(language="zh")

    assert result.refreshed is True
    profile = memory_service.read_profile()
    assert "## Preferences\nManual notes" in profile
    assert "## CoPA Factors" in profile
    assert "### Prompt Summary" in profile

    state = json.loads(_PathServiceStub(tmp_path).get_copa_state_file().read_text(encoding="utf-8"))
    assert state["messages_consumed"] == 15
    assert state["refresh_threshold"] == 15
    assert state["last_updated_at"]


@pytest.mark.asyncio
async def test_refresh_profile_skips_before_threshold(
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    from deeptutor.services.personalization.copa_profile import CoPAProfileService

    await store.create_session(session_id="s1")
    for idx in range(14):
        await store.add_message(session_id="s1", role="user", content=f"user message {idx}")

    memory_service = make_memory_service(tmp_path, store=store)
    service = CoPAProfileService(
        path_service=_PathServiceStub(tmp_path),
        store=store,
        memory_service=memory_service,
    )

    result = await service.refresh_profile(language="zh")

    assert result.refreshed is False
    assert memory_service.read_copa_section() == ""
    assert not _PathServiceStub(tmp_path).get_copa_state_file().exists()


def test_build_memory_context_includes_copa_factors_from_profile(tmp_path: Path) -> None:
    svc = make_memory_service(
        tmp_path,
        profile_text=(
            "## CoPA Factors\n"
            "\n"
            "### Prompt Summary\n"
            "Prompt Summary content."
        ),
    )

    context = svc.build_memory_context()

    assert "CoPA Factors" in context
    assert "Prompt Summary" in context


@pytest.mark.asyncio
async def test_refresh_profile_rebuilds_live_after_cold_start_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: SQLiteSessionStore,
) -> None:
    from deeptutor.services.personalization.copa_profile import CoPAProfileService

    async def fake_infer(
        new_raw_user_messages: list[str],
        *,
        existing_copa_profile: str = "",
        language: str = "zh",
    ) -> dict[str, object]:
        assert existing_copa_profile == ""
        assert len(new_raw_user_messages) == 15
        return {
            "factors": {
                code: {
                    "user_profile_description": f"{code} from live messages",
                    "response_strategy": [f"{code} live strategy"],
                }
                for code in ("CT", "SA", "SC", "CLM", "MS", "AMR")
            }
        }

    monkeypatch.setattr(
        "deeptutor.services.personalization.copa_profile.infer_copa_profile",
        fake_infer,
    )

    await store.create_session(session_id="s1")
    for idx in range(15):
        await store.add_message(session_id="s1", role="user", content=f"user message {idx}")

    memory_service = make_memory_service(
        tmp_path,
        store=store,
        profile_text="## CoPA Factors\n旧冷启动画像",
    )
    state_path = _PathServiceStub(tmp_path).get_copa_state_file()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "messages_consumed": 1,
                "refresh_threshold": 15,
                "last_updated_at": "2026-04-21T12:00:00+08:00",
                "profile_source": "cold_start",
                "live_rebuild_threshold": 15,
                "cold_start": {
                    "version": "v1",
                    "completed_at": "2026-04-21T12:00:00+08:00",
                    "answers": {"CT_1": 4},
                    "factor_scores": {"CT": 4.0},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = CoPAProfileService(
        path_service=_PathServiceStub(tmp_path),
        store=store,
        memory_service=memory_service,
    )

    result = await service.refresh_profile(language="zh")

    assert result.refreshed is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["profile_source"] == "live"
    assert state["messages_consumed"] == 15
    assert "CT from live messages" in memory_service.read_profile()
