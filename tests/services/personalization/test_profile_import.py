from __future__ import annotations

import json
import logging
import sqlite3
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
    profile_text: str = "",
) -> MemoryService:
    service = MemoryService(
        path_service=_PathServiceStub(tmp_path),
        store=SQLiteSessionStore(tmp_path / "chat_history.db"),
    )
    if profile_text:
        service.write_file("profile", profile_text)
    return service


def _state_path(tmp_path: Path) -> Path:
    return _PathServiceStub(tmp_path).get_copa_state_file()


def _fake_copa_payload() -> dict[str, object]:
    return {
        "factors": {
            code: {
                "user_profile_description": f"{code} description",
                "response_strategy": [f"{code} strategy 1", f"{code} strategy 2"],
            }
            for code in ("CT", "SA", "SC", "CLM", "MS", "AMR")
        }
    }


async def _fake_complete(*args, **kwargs):
    prompt = kwargs.get("prompt", "")
    if "最终只返回严格 JSON" in prompt or "Return strict JSON only." in prompt:
        return json.dumps(_fake_copa_payload(), ensure_ascii=False)
    return (
        "## Profile Summary\n\n"
        "- 回答偏好：更喜欢先给结论，再按需展开。\n"
        "- 系统适配建议：默认给最小可用答案，再补依据。\n"
    )


def _write_codex_history(root: Path) -> None:
    session_dir = root / "sessions" / "2026" / "04" / "22"
    session_dir.mkdir(parents=True, exist_ok=True)
    rollout = session_dir / "rollout-2026-04-22T10-00-00.jsonl"
    rollout.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-04-22T10:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "sess-1", "cwd": "/tmp/project"},
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-04-22T10:00:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "我喜欢先给结论"}],
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "timestamp": "2026-04-22T10:00:02Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "好的"}],
                        },
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_claude_history(root: Path) -> None:
    project_dir = root / "projects" / "-Users-test-project"
    project_dir.mkdir(parents=True, exist_ok=True)
    session_file = project_dir / "session-1.jsonl"
    session_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "parentUuid": None,
                        "isSidechain": False,
                        "userType": "external",
                        "cwd": "/tmp/project",
                        "sessionId": "session-1",
                        "type": "user",
                        "message": {"role": "user", "content": "如果能说明限制条件我会更信任"},
                        "uuid": "u1",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "parentUuid": "u1",
                        "isSidechain": False,
                        "userType": "external",
                        "cwd": "/tmp/project",
                        "sessionId": "session-1",
                        "type": "assistant",
                        "message": {"role": "assistant", "content": "收到"},
                        "uuid": "a1",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_cursor_history(root: Path) -> None:
    global_dir = root / "globalStorage"
    workspace_dir = root / "workspaceStorage" / "ws-1"
    global_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    (workspace_dir / "workspace.json").write_text(
        json.dumps({"folder": "file:///Users/test/project"}, ensure_ascii=False),
        encoding="utf-8",
    )

    ws_conn = sqlite3.connect(workspace_dir / "state.vscdb")
    ws_conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    ws_conn.execute(
        "INSERT INTO ItemTable(key, value) VALUES (?, ?)",
        (
            "composer.composerData",
            json.dumps(
                {
                    "allComposers": [
                        {
                            "composerId": "composer-1",
                            "name": "Test Composer",
                            "createdAt": 1710000000000,
                            "lastUpdatedAt": 1710000001000,
                            "unifiedMode": "chat",
                            "isArchived": False,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        ),
    )
    ws_conn.commit()
    ws_conn.close()

    global_conn = sqlite3.connect(global_dir / "state.vscdb")
    global_conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    global_conn.execute(
        "INSERT INTO cursorDiskKV(key, value) VALUES (?, ?)",
        (
            "composerData:composer-1",
            json.dumps(
                {
                    "fullConversationHeadersOnly": [
                        {"bubbleId": "bubble-user-1", "type": 1},
                        {"bubbleId": "bubble-assistant-1", "type": 2},
                    ]
                },
                ensure_ascii=False,
            ),
        ),
    )
    global_conn.execute(
        "INSERT INTO cursorDiskKV(key, value) VALUES (?, ?)",
        (
            "bubbleId:composer-1:bubble-user-1",
            json.dumps(
                {"bubbleId": "bubble-user-1", "text": "我喜欢结构化答案"},
                ensure_ascii=False,
            ),
        ),
    )
    global_conn.execute(
        "INSERT INTO cursorDiskKV(key, value) VALUES (?, ?)",
        (
            "bubbleId:composer-1:bubble-assistant-1",
            json.dumps(
                {"bubbleId": "bubble-assistant-1", "text": "收到"},
                ensure_ascii=False,
            ),
        ),
    )
    global_conn.commit()
    global_conn.close()


def _uploaded_files_from_root(root: Path) -> list[tuple[str, bytes]]:
    result: list[tuple[str, bytes]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        result.append((str(path.relative_to(root)).replace("\\", "/"), path.read_bytes()))
    return result


@pytest.mark.asyncio
async def test_preview_import_from_pasted_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    service = ProfileImportService(memory_service=make_memory_service(tmp_path))
    preview = await service.preview_import(
        source_type="pasted_text",
        provider=None,
        folder_path=None,
        text="User: 我更喜欢先给结论\nAssistant: 好的\nUser: 如果能补依据更好",
        mode="merge",
        language="zh",
    )

    assert preview.source_type == "pasted_text"
    assert preview.provider is None
    assert preview.effective_signal_count == 2
    assert preview.can_apply is True
    assert preview.scanned_session_count == 0


@pytest.mark.asyncio
async def test_preview_import_from_codex_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    codex_root = tmp_path / ".codex"
    _write_codex_history(codex_root)
    service = ProfileImportService(memory_service=make_memory_service(tmp_path))

    preview = await service.preview_import(
        source_type="folder",
        provider="codex",
        folder_path=str(codex_root),
        text="",
        mode="merge",
        language="zh",
    )

    assert preview.provider == "codex"
    assert preview.scanned_session_count == 1
    assert preview.extracted_user_messages == ["我喜欢先给结论"]


@pytest.mark.asyncio
async def test_preview_import_logs_parse_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    codex_root = tmp_path / ".codex"
    _write_codex_history(codex_root)
    service = ProfileImportService(memory_service=make_memory_service(tmp_path))

    with caplog.at_level(logging.INFO, logger="deeptutor.services.personalization.profile_import"):
        preview = await service.preview_import(
            source_type="folder",
            provider="codex",
            folder_path=str(codex_root),
            text="",
            mode="merge",
            language="zh",
        )

    assert preview.provider == "codex"
    assert "profile import parsed input" in caplog.text
    assert "provider=codex" in caplog.text
    assert "scanned_session_count=1" in caplog.text
    assert "effective_signal_count=1" in caplog.text


@pytest.mark.asyncio
async def test_preview_import_from_claude_code_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    claude_root = tmp_path / ".claude"
    _write_claude_history(claude_root)
    service = ProfileImportService(memory_service=make_memory_service(tmp_path))

    preview = await service.preview_import(
        source_type="folder",
        provider="claude_code",
        folder_path=str(claude_root),
        text="",
        mode="merge",
        language="zh",
    )

    assert preview.provider == "claude_code"
    assert preview.scanned_session_count == 1
    assert preview.extracted_user_messages == ["如果能说明限制条件我会更信任"]


@pytest.mark.asyncio
async def test_preview_import_from_cursor_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    cursor_root = tmp_path / "CursorUser"
    _write_cursor_history(cursor_root)
    service = ProfileImportService(memory_service=make_memory_service(tmp_path))

    preview = await service.preview_import(
        source_type="folder",
        provider="cursor",
        folder_path=str(cursor_root),
        text="",
        mode="merge",
        language="zh",
    )

    assert preview.provider == "cursor"
    assert preview.scanned_session_count == 1
    assert preview.extracted_user_messages == ["我喜欢结构化答案"]


@pytest.mark.asyncio
async def test_preview_import_from_uploaded_codex_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService, UploadedImportFile

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    codex_root = tmp_path / ".codex"
    _write_codex_history(codex_root)
    uploaded_files = [
        UploadedImportFile(relative_path=relative_path, content_bytes=content_bytes)
        for relative_path, content_bytes in _uploaded_files_from_root(codex_root)
    ]
    service = ProfileImportService(memory_service=make_memory_service(tmp_path))

    preview = await service.preview_import(
        source_type="folder",
        provider="codex",
        folder_path=None,
        text="",
        mode="merge",
        language="zh",
        uploaded_files=uploaded_files,
    )

    assert preview.provider == "codex"
    assert preview.scanned_session_count == 1
    assert preview.extracted_user_messages == ["我喜欢先给结论"]


@pytest.mark.asyncio
async def test_preview_import_from_uploaded_claude_code_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService, UploadedImportFile

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    claude_root = tmp_path / ".claude"
    _write_claude_history(claude_root)
    uploaded_files = [
        UploadedImportFile(relative_path=relative_path, content_bytes=content_bytes)
        for relative_path, content_bytes in _uploaded_files_from_root(claude_root)
    ]
    service = ProfileImportService(memory_service=make_memory_service(tmp_path))

    preview = await service.preview_import(
        source_type="folder",
        provider="claude_code",
        folder_path=None,
        text="",
        mode="merge",
        language="zh",
        uploaded_files=uploaded_files,
    )

    assert preview.provider == "claude_code"
    assert preview.scanned_session_count == 1
    assert preview.extracted_user_messages == ["如果能说明限制条件我会更信任"]


@pytest.mark.asyncio
async def test_preview_import_from_uploaded_cursor_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService, UploadedImportFile

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    cursor_root = tmp_path / "CursorUser"
    _write_cursor_history(cursor_root)
    uploaded_files = [
        UploadedImportFile(relative_path=relative_path, content_bytes=content_bytes)
        for relative_path, content_bytes in _uploaded_files_from_root(cursor_root)
    ]
    service = ProfileImportService(memory_service=make_memory_service(tmp_path))

    preview = await service.preview_import(
        source_type="folder",
        provider="cursor",
        folder_path=None,
        text="",
        mode="merge",
        language="zh",
        uploaded_files=uploaded_files,
    )

    assert preview.provider == "cursor"
    assert preview.scanned_session_count == 1
    assert preview.extracted_user_messages == ["我喜欢结构化答案"]


@pytest.mark.asyncio
async def test_apply_import_writes_profile_and_marks_history_import(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService

    monkeypatch.setattr("deeptutor.services.personalization.copa_profile.complete", _fake_complete)
    monkeypatch.setattr("deeptutor.services.personalization.profile_import.complete", _fake_complete)

    state_file = _state_path(tmp_path)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "messages_consumed": 12,
                "refresh_threshold": 15,
                "last_updated_at": None,
                "profile_source": "live",
                "live_rebuild_threshold": 15,
                "cold_start": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    codex_root = tmp_path / ".codex"
    _write_codex_history(codex_root)
    memory_service = make_memory_service(
        tmp_path,
        profile_text="## Preferences\nManual notes\n\n## CoPA Factors\nold block",
    )
    service = ProfileImportService(memory_service=memory_service)

    result = await service.apply_import(
        source_type="folder",
        provider="codex",
        folder_path=str(codex_root),
        text="",
        mode="overwrite",
        language="zh",
    )

    profile = memory_service.read_profile()
    assert result.applied is True
    assert "## Preferences\nManual notes" in profile
    assert "## CoPA Factors" in profile
    assert "## Profile Summary" in profile
    assert "## Profile Metadata" in profile

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["messages_consumed"] == 12
    assert state["profile_source"] == "history_import"
    assert state["history_import_provider"] == "codex"
    assert state["history_import_signal_count"] == 1


@pytest.mark.asyncio
async def test_preview_import_requires_provider_for_folder(tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService

    service = ProfileImportService(memory_service=make_memory_service(tmp_path))

    with pytest.raises(ValueError, match="provider_required_for_folder_import"):
        await service.preview_import(
            source_type="folder",
            provider=None,
            folder_path=str(tmp_path),
            text="",
            mode="merge",
            language="zh",
        )


@pytest.mark.asyncio
async def test_preview_import_rejects_invalid_provider_root(tmp_path: Path) -> None:
    from deeptutor.services.personalization.profile_import import ProfileImportService

    service = ProfileImportService(memory_service=make_memory_service(tmp_path))
    bad_root = tmp_path / "not-codex"
    bad_root.mkdir()

    with pytest.raises(ValueError, match="invalid_provider_root"):
        await service.preview_import(
            source_type="folder",
            provider="codex",
            folder_path=str(bad_root),
            text="",
            mode="merge",
            language="zh",
        )
