from __future__ import annotations

from pathlib import Path
from typing import Literal

from .base import ProviderImportResult, ProviderName, ProviderSegment
from .claude_code import load_claude_code_history
from .codex import load_codex_history
from .cursor import load_cursor_history


ProviderLiteral = Literal["codex", "claude_code", "cursor"]


def load_provider_history(provider: ProviderLiteral, folder_path: Path) -> ProviderImportResult:
    if provider == "codex":
        return load_codex_history(folder_path)
    if provider == "claude_code":
        return load_claude_code_history(folder_path)
    if provider == "cursor":
        return load_cursor_history(folder_path)
    raise ValueError("unsupported_provider")


__all__ = [
    "ProviderImportResult",
    "ProviderLiteral",
    "ProviderName",
    "ProviderSegment",
    "load_provider_history",
]
