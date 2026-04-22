from __future__ import annotations

from pathlib import Path

from .base import ProviderImportResult, ProviderSegment, load_json_line, normalize_text


_DEF_WARN = "provider_history_empty"


def load_codex_history(folder_path: Path) -> ProviderImportResult:
    sessions_dir = folder_path / "sessions"
    archived_dir = folder_path / "archived_sessions"
    if not sessions_dir.is_dir() and not archived_dir.is_dir():
        raise ValueError("invalid_provider_root")

    rollout_files = sorted(sessions_dir.rglob("rollout-*.jsonl")) if sessions_dir.is_dir() else []
    if archived_dir.is_dir():
        rollout_files += sorted(archived_dir.rglob("rollout-*.jsonl"))

    segments: list[ProviderSegment] = []
    for rollout_path in rollout_files:
        for raw in rollout_path.read_text(encoding="utf-8").splitlines():
            record = load_json_line(raw)
            if not record or record.get("type") != "response_item":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "message":
                continue
            role = str(payload.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = normalize_text(payload.get("content"))
            if not content:
                continue
            segments.append(
                ProviderSegment(
                    role=role,  # type: ignore[arg-type]
                    content=content,
                    source=str(rollout_path),
                    confidence="high",
                )
            )

    warnings = [] if rollout_files and segments else [_DEF_WARN]
    return ProviderImportResult(
        provider="codex",
        segments=segments,
        scanned_session_count=len(rollout_files),
        warnings=warnings,
    )
