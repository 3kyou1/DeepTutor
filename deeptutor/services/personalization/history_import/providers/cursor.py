from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .base import ProviderImportResult, ProviderSegment, normalize_text, sanitize_json_blob


_DEF_WARN = "provider_history_empty"


def load_cursor_history(folder_path: Path) -> ProviderImportResult:
    workspace_root = folder_path / "workspaceStorage"
    global_db_path = folder_path / "globalStorage" / "state.vscdb"
    if not workspace_root.is_dir() or not global_db_path.is_file():
        raise ValueError("invalid_provider_root")

    scanned_session_count = 0
    segments: list[ProviderSegment] = []
    warnings: list[str] = []

    global_conn = sqlite3.connect(global_db_path)
    global_conn.row_factory = sqlite3.Row
    try:
        for workspace_dir in sorted(p for p in workspace_root.iterdir() if p.is_dir()):
            workspace_db_path = workspace_dir / "state.vscdb"
            if not workspace_db_path.is_file():
                continue
            composer_ids = _read_composer_ids(workspace_db_path)
            for composer_id in composer_ids:
                scanned_session_count += 1
                segments.extend(_read_composer_segments(global_conn, composer_id))
    finally:
        global_conn.close()

    if scanned_session_count == 0 or not segments:
        warnings.append(_DEF_WARN)
    return ProviderImportResult(
        provider="cursor",
        segments=segments,
        scanned_session_count=scanned_session_count,
        warnings=warnings,
    )


def _read_composer_ids(workspace_db_path: Path) -> list[str]:
    conn = sqlite3.connect(workspace_db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = 'composer.composerData'"
        ).fetchone()
        if row is None:
            return []
        payload = _parse_json_blob(row[0])
        composers = payload.get("allComposers") if isinstance(payload, dict) else None
        if not isinstance(composers, list):
            return []
        result: list[str] = []
        for item in composers:
            if not isinstance(item, dict):
                continue
            if bool(item.get("isArchived")):
                continue
            composer_id = str(item.get("composerId") or "").strip()
            if composer_id:
                result.append(composer_id)
        return result
    finally:
        conn.close()


def _read_composer_segments(global_conn: sqlite3.Connection, composer_id: str) -> list[ProviderSegment]:
    row = global_conn.execute(
        "SELECT value FROM cursorDiskKV WHERE key = ?",
        (f"composerData:{composer_id}",),
    ).fetchone()
    if row is None:
        return []
    payload = _parse_json_blob(row[0])
    headers = payload.get("fullConversationHeadersOnly") if isinstance(payload, dict) else None
    if not isinstance(headers, list):
        return []

    segments: list[ProviderSegment] = []
    for header in headers:
        if not isinstance(header, dict):
            continue
        bubble_id = str(header.get("bubbleId") or "").strip()
        bubble_type = int(header.get("type") or 0)
        if not bubble_id or bubble_type not in {1, 2}:
            continue
        bubble_row = global_conn.execute(
            "SELECT value FROM cursorDiskKV WHERE key = ?",
            (f"bubbleId:{composer_id}:{bubble_id}",),
        ).fetchone()
        if bubble_row is None:
            continue
        bubble = _parse_json_blob(bubble_row[0])
        content = normalize_text(bubble.get("text") if isinstance(bubble, dict) else "")
        if not content:
            continue
        role = "user" if bubble_type == 1 else "assistant"
        segments.append(
            ProviderSegment(
                role=role,
                content=content,
                source=f"cursor://{composer_id}/{bubble_id}",
                confidence="high",
            )
        )
    return segments


def _parse_json_blob(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(sanitize_json_blob(raw))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
