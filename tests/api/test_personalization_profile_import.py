from __future__ import annotations

import importlib
import logging

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
router = importlib.import_module("deeptutor.api.routers.personalization").router



def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/personalization")
    return app



def test_profile_import_preview_accepts_folder_source(monkeypatch) -> None:
    class FakeService:
        async def preview_import(self, **kwargs):
            assert kwargs["source_type"] == "folder"
            assert kwargs["provider"] == "codex"
            assert kwargs["folder_path"] == "/tmp/.codex"
            return {
                "mode": "merge",
                "source_type": "folder",
                "provider": "codex",
                "detected_turns": 2,
                "extracted_user_messages": ["a", "b"],
                "effective_signal_count": 2,
                "warnings": [],
                "generated_copa_markdown": "## CoPA Factors\n...",
                "generated_summary_markdown": "## Profile Summary\n...",
                "will_update_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "can_apply": True,
                "scanned_session_count": 1,
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_profile_import_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/personalization/profile-import/preview",
            json={
                "mode": "merge",
                "language": "zh",
                "source_type": "folder",
                "provider": "codex",
                "folder_path": "/tmp/.codex",
                "text": "",
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "codex"
    assert response.json()["scanned_session_count"] == 1



def test_profile_import_apply_accepts_pasted_text(monkeypatch) -> None:
    class FakeService:
        async def apply_import(self, **kwargs):
            assert kwargs["source_type"] == "pasted_text"
            assert kwargs["provider"] is None
            assert kwargs["text"] == "User: hi"
            return {
                "applied": True,
                "mode": "overwrite",
                "warnings": [],
                "updated_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "profile_updated_at": "2026-04-21T12:00:00+08:00",
                "profile": "## CoPA Factors\n...",
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_profile_import_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/personalization/profile-import/apply",
            json={
                "mode": "overwrite",
                "language": "zh",
                "source_type": "pasted_text",
                "provider": None,
                "folder_path": None,
                "text": "User: hi",
            },
        )

    assert response.status_code == 200
    assert response.json()["applied"] is True



def test_profile_import_preview_maps_value_error(monkeypatch) -> None:
    class FakeService:
        async def preview_import(self, **kwargs):
            raise ValueError("provider_required_for_folder_import")

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_profile_import_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/personalization/profile-import/preview",
            json={
                "mode": "merge",
                "language": "zh",
                "source_type": "folder",
                "provider": None,
                "folder_path": "/tmp/whatever",
                "text": "",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "provider_required_for_folder_import"


def test_profile_import_preview_upload_accepts_folder_files(monkeypatch) -> None:
    class FakeService:
        async def preview_import(self, **kwargs):
            assert kwargs["source_type"] == "folder"
            assert kwargs["provider"] == "codex"
            assert kwargs["folder_path"] is None
            assert kwargs["text"] == ""
            uploaded_files = kwargs["uploaded_files"]
            assert len(uploaded_files) == 1
            assert uploaded_files[0].relative_path == "sessions/2026/04/22/rollout-1.jsonl"
            assert uploaded_files[0].content_bytes == b'{"type":"response_item"}\n'
            return {
                "mode": "merge",
                "source_type": "folder",
                "provider": "codex",
                "detected_turns": 1,
                "extracted_user_messages": ["a"],
                "effective_signal_count": 1,
                "warnings": [],
                "generated_copa_markdown": "## CoPA Factors\n...",
                "generated_summary_markdown": "## Profile Summary\n...",
                "will_update_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "can_apply": True,
                "scanned_session_count": 1,
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_profile_import_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/personalization/profile-import/preview-upload",
            data={
                "mode": "merge",
                "language": "zh",
                "provider": "codex",
                "relative_paths": "sessions/2026/04/22/rollout-1.jsonl",
            },
            files=[
                (
                    "files",
                    ("rollout-1.jsonl", b'{"type":"response_item"}\n', "application/json"),
                )
            ],
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "codex"


def test_profile_import_preview_upload_logs_request_summary(monkeypatch, caplog) -> None:
    class FakeService:
        async def preview_import(self, **kwargs):
            return {
                "mode": "merge",
                "source_type": "folder",
                "provider": "codex",
                "detected_turns": 1,
                "extracted_user_messages": ["a"],
                "effective_signal_count": 1,
                "warnings": [],
                "generated_copa_markdown": "## CoPA Factors\n...",
                "generated_summary_markdown": "## Profile Summary\n...",
                "will_update_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "can_apply": True,
                "scanned_session_count": 1,
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_profile_import_service",
        lambda: FakeService(),
    )

    with caplog.at_level(logging.INFO, logger="deeptutor.api.routers.personalization"):
        with TestClient(_build_app()) as client:
            response = client.post(
                "/api/v1/personalization/profile-import/preview-upload",
                data={
                    "mode": "merge",
                    "language": "zh",
                    "provider": "codex",
                    "relative_paths": "sessions/2026/04/22/rollout-1.jsonl",
                },
                files=[
                    (
                        "files",
                        ("rollout-1.jsonl", b'{"type":"response_item"}\n', "application/json"),
                    )
                ],
            )

    assert response.status_code == 200
    assert "profile import preview-upload request" in caplog.text
    assert "provider=codex" in caplog.text
    assert "uploaded_file_count=1" in caplog.text


def test_profile_import_apply_upload_accepts_folder_files(monkeypatch) -> None:
    class FakeService:
        async def apply_import(self, **kwargs):
            assert kwargs["source_type"] == "folder"
            assert kwargs["provider"] == "claude_code"
            assert kwargs["folder_path"] is None
            uploaded_files = kwargs["uploaded_files"]
            assert len(uploaded_files) == 1
            assert uploaded_files[0].relative_path == "projects/demo/session-1.jsonl"
            return {
                "applied": True,
                "mode": "merge",
                "warnings": [],
                "updated_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "profile_updated_at": "2026-04-21T12:00:00+08:00",
                "profile": "## CoPA Factors\n...",
            }

    monkeypatch.setattr(
        "deeptutor.api.routers.personalization.get_profile_import_service",
        lambda: FakeService(),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/personalization/profile-import/apply-upload",
            data={
                "mode": "merge",
                "language": "zh",
                "provider": "claude_code",
                "relative_paths": "projects/demo/session-1.jsonl",
            },
            files=[
                (
                    "files",
                    ("session-1.jsonl", b'{"type":"user"}\n', "application/json"),
                )
            ],
        )

    assert response.status_code == 200
    assert response.json()["applied"] is True
