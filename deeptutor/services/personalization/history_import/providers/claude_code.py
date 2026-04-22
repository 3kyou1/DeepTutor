from __future__ import annotations

from pathlib import Path

from .base import ProviderImportResult, ProviderSegment, load_json_line, normalize_text


_DEF_WARN = "provider_history_empty"


def load_claude_code_history(folder_path: Path) -> ProviderImportResult:
    projects_dir = folder_path / "projects"
    if not projects_dir.is_dir():
        raise ValueError("invalid_provider_root")

    session_files = sorted(projects_dir.rglob("*.jsonl"))
    segments: list[ProviderSegment] = []
    for session_path in session_files:
        for raw in session_path.read_text(encoding="utf-8").splitlines():
            record = load_json_line(raw)
            if not record:
                continue
            if bool(record.get("isSidechain")):
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or record.get("type") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = normalize_text(message.get("content"))
            if not content:
                continue
            segments.append(
                ProviderSegment(
                    role=role,  # type: ignore[arg-type]
                    content=content,
                    source=str(session_path),
                    confidence="high",
                )
            )

    warnings = [] if session_files and segments else [_DEF_WARN]
    return ProviderImportResult(
        provider="claude_code",
        segments=segments,
        scanned_session_count=len(session_files),
        warnings=warnings,
    )
