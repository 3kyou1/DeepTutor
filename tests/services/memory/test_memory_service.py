from __future__ import annotations

from deeptutor.services.memory.service import MemoryService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


def _make_service(tmp_path):
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    return MemoryService(
        path_service=type(
            "PathServiceStub",
            (),
            {"get_memory_dir": lambda self: tmp_path / "memory"},
        )(),
        store=store,
    )


def test_memory_service_snapshot_is_empty_without_file(tmp_path) -> None:
    service = _make_service(tmp_path)
    snapshot = service.read_snapshot()

    assert snapshot.summary == ""
    assert snapshot.profile == ""
    assert snapshot.summary_updated_at is None
    assert snapshot.profile_updated_at is None


async def _no_change_stream(**_kwargs):
    yield "NO_CHANGE"


async def _rewrite_stream(**_kwargs):
    yield "## Preferences\n- Prefer concise answers.\n\n## Context\n- Working on DeepTutor memory."


def test_memory_service_refresh_turn_writes_rewritten_document(monkeypatch, tmp_path) -> None:
    service = _make_service(tmp_path)
    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", _rewrite_stream)

    import asyncio

    result = asyncio.run(
        service.refresh_from_turn(
            user_message="Please remember that I like concise answers.",
            assistant_message="Sure, I'll keep answers concise.",
            session_id="s1",
            capability="chat",
            language="en",
        )
    )

    assert result.changed is True
    assert "concise answers" in result.content
    assert service._path("profile").exists() or service._path("summary").exists()


def test_memory_service_refresh_turn_skips_when_model_returns_no_change(
    monkeypatch,
    tmp_path,
) -> None:
    service = _make_service(tmp_path)
    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", _no_change_stream)

    import asyncio

    result = asyncio.run(
        service.refresh_from_turn(
            user_message="What is 2+2?",
            assistant_message="4",
            session_id="s1",
            capability="chat",
            language="en",
        )
    )

    assert result.changed is False
    assert result.content == ""
    assert not service._path("profile").exists()
    assert not service._path("summary").exists()


def test_memory_service_reads_and_writes_profile_summary_section(tmp_path) -> None:
    service = _make_service(tmp_path)

    service.write_profile_summary_section("## Profile Summary\n- summary bullet")

    assert service.read_profile_summary_section() == "## Profile Summary\n- summary bullet"
    assert "## Profile Summary\n- summary bullet" in service.read_profile()


def test_memory_service_rewrite_profile_generated_sections_preserves_manual_content(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.write_file(
        "profile",
        "## Preferences\nManual notes\n\n## CoPA Factors\nold copa\n\n## Identity\nDo not remove",
    )

    service.rewrite_profile_generated_sections(
        copa_markdown="## CoPA Factors\nnew copa",
        summary_markdown="## Profile Summary\n- new summary",
        metadata_markdown="## Profile Metadata\n- source: history_import",
    )

    profile = service.read_profile()
    assert "## Preferences\nManual notes" in profile
    assert "## Identity\nDo not remove" in profile
    assert "## CoPA Factors\nnew copa" in profile
    assert "## Profile Summary\n- new summary" in profile
    assert "## Profile Metadata\n- source: history_import" in profile
