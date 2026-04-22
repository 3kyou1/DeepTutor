from __future__ import annotations

import io
from pathlib import Path

from typer.testing import CliRunner

from deeptutor_cli.main import app

runner = CliRunner()



def test_memory_import_command_uses_provider_and_path(monkeypatch, tmp_path: Path) -> None:
    codex_root = tmp_path / ".codex"
    codex_root.mkdir()
    calls: list[tuple[str, dict]] = []

    class FakeService:
        async def preview_import(self, **kwargs):
            calls.append(("preview", kwargs))
            return {
                "mode": "merge",
                "source_type": "folder",
                "provider": "codex",
                "detected_turns": 1,
                "extracted_user_messages": ["我喜欢先给结论"],
                "effective_signal_count": 1,
                "warnings": [],
                "generated_copa_markdown": "## CoPA Factors\npreview",
                "generated_summary_markdown": "## Profile Summary\n- preview",
                "will_update_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "can_apply": True,
                "scanned_session_count": 1,
            }

        async def apply_import(self, **kwargs):
            calls.append(("apply", kwargs))
            return {
                "applied": True,
                "mode": "merge",
                "warnings": [],
                "updated_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "profile_updated_at": "2026-04-21T12:00:00+08:00",
                "profile": "## CoPA Factors\napplied",
            }

    monkeypatch.setattr(
        "deeptutor_cli.memory.get_profile_import_service",
        lambda: FakeService(),
    )

    result = runner.invoke(
        app,
        [
            "memory",
            "import",
            "--provider",
            "codex",
            "--path",
            str(codex_root),
            "--mode",
            "merge",
        ],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert [name for name, _ in calls] == ["preview", "apply"]
    assert calls[0][1]["source_type"] == "folder"
    assert calls[0][1]["provider"] == "codex"
    assert calls[0][1]["folder_path"] == str(codex_root)



def test_memory_import_command_supports_paste(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeService:
        async def preview_import(self, **kwargs):
            calls.append(("preview", kwargs))
            return {
                "mode": "merge",
                "source_type": "pasted_text",
                "provider": None,
                "detected_turns": 1,
                "extracted_user_messages": ["我喜欢结构化答案"],
                "effective_signal_count": 1,
                "warnings": [],
                "generated_copa_markdown": "## CoPA Factors\npreview",
                "generated_summary_markdown": "## Profile Summary\n- preview",
                "will_update_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "can_apply": True,
                "scanned_session_count": 0,
            }

        async def apply_import(self, **kwargs):
            calls.append(("apply", kwargs))
            return {
                "applied": True,
                "mode": "merge",
                "warnings": [],
                "updated_sections": ["CoPA Factors", "Profile Summary", "Profile Metadata"],
                "profile_updated_at": "2026-04-21T12:00:00+08:00",
                "profile": "## CoPA Factors\napplied",
            }

    monkeypatch.setattr(
        "deeptutor_cli.memory.get_profile_import_service",
        lambda: FakeService(),
    )
    monkeypatch.setattr(
        "deeptutor_cli.memory.typer.get_text_stream",
        lambda *_args, **_kwargs: io.StringIO("User: 我喜欢结构化答案"),
    )
    monkeypatch.setattr("deeptutor_cli.memory.typer.confirm", lambda *_args, **_kwargs: True)

    result = runner.invoke(
        app,
        ["memory", "import", "--paste", "--mode", "merge"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0][1]["source_type"] == "pasted_text"
    assert calls[0][1]["text"].strip() == "User: 我喜欢结构化答案"
