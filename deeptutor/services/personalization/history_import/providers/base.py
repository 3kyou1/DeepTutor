from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

ImportRole = Literal["user", "assistant", "unknown"]
ProviderName = Literal["codex", "claude_code", "cursor"]


@dataclass(frozen=True)
class ProviderSegment:
    role: ImportRole
    content: str
    source: str
    confidence: str = "high"


@dataclass(frozen=True)
class ProviderImportResult:
    provider: ProviderName
    segments: list[ProviderSegment]
    scanned_session_count: int
    warnings: list[str] = field(default_factory=list)


def normalize_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [normalize_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "value"):
            text = normalize_text(value.get(key))
            if text:
                return text
        return ""
    return ""


def load_json_line(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def sanitize_json_blob(data: str) -> str:
    return "".join(
        " " if ch.isascii() and ord(ch) < 32 and ch not in "\n\r\t" else ch
        for ch in data
    )
