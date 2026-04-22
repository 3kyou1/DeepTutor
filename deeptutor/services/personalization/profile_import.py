from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
import tempfile
from typing import Literal

from deeptutor.services.llm import complete
from deeptutor.services.memory import MemoryService, get_memory_service

from .copa_profile import CoPAProfileService, infer_copa_profile, render_copa_markdown
from .history_import.providers import load_provider_history

ImportMode = Literal["create", "merge", "overwrite"]
ImportSourceType = Literal["folder", "pasted_text"]
ImportProvider = Literal["codex", "claude_code", "cursor"]
ImportRole = Literal["user", "assistant", "unknown"]

_ROLE_PATTERNS: tuple[tuple[re.Pattern[str], ImportRole], ...] = (
    (re.compile(r"^\s*(?:user|human)\s*[:：]\s*(.*)$", re.IGNORECASE), "user"),
    (re.compile(r"^\s*(?:用户)\s*[:：]\s*(.*)$", re.IGNORECASE), "user"),
    (re.compile(r"^\s*(?:assistant|ai|chatgpt|claude)\s*[:：]\s*(.*)$", re.IGNORECASE), "assistant"),
    (re.compile(r"^\s*(?:助手|模型)\s*[:：]\s*(.*)$", re.IGNORECASE), "assistant"),
)
_STOP_PHRASES = {"谢谢", "继续", "下一题", "收到", "好的", "ok", "thanks", "thank you"}


@dataclass(frozen=True)
class ImportSegment:
    role: ImportRole
    content: str
    turn_index: int
    source: str
    confidence: str


@dataclass(frozen=True)
class UploadedImportFile:
    relative_path: str
    content_bytes: bytes


@dataclass(frozen=True)
class ImportParseResult:
    source_type: ImportSourceType
    provider: ImportProvider | None
    folder_path: str | None
    segments: list[ImportSegment]
    detected_turns: int
    user_segment_count: int
    assistant_segment_count: int
    warnings: list[str]
    scanned_session_count: int = 0
    truncated: bool = False


@dataclass(frozen=True)
class ProfileImportPreview:
    mode: ImportMode
    source_type: ImportSourceType
    provider: ImportProvider | None
    detected_turns: int
    extracted_user_messages: list[str]
    effective_signal_count: int
    warnings: list[str]
    generated_copa_markdown: str
    generated_summary_markdown: str
    will_update_sections: list[str]
    can_apply: bool
    scanned_session_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProfileImportApplyResult:
    applied: bool
    mode: ImportMode
    warnings: list[str]
    updated_sections: list[str]
    profile_updated_at: str | None
    profile: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalize_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_normalize_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "value"):
            text = _normalize_text(value.get(key))
            if text:
                return text
        return ""
    return ""


class ProfileImportService:
    def __init__(self, memory_service: MemoryService | None = None) -> None:
        self._memory_service = memory_service or get_memory_service()
        self._copa_profile_service = CoPAProfileService(
            path_service=getattr(self._memory_service, "_path_service", None),
            memory_service=self._memory_service,
        )

    def parse_import_input(
        self,
        *,
        source_type: ImportSourceType,
        provider: ImportProvider | None,
        folder_path: str | None,
        text: str,
        uploaded_files: list[UploadedImportFile] | None = None,
    ) -> ImportParseResult:
        if source_type == "pasted_text":
            normalized = str(text or "").replace("\r\n", "\n").strip()
            if not normalized:
                raise ValueError("empty_import_input")
            return self._parse_text_input(normalized)

        if source_type != "folder":
            raise ValueError("unsupported_import_source")
        if provider is None:
            raise ValueError("provider_required_for_folder_import")
        if uploaded_files is not None:
            if not uploaded_files:
                raise ValueError("uploaded_files_required")
            provider_result = self._load_provider_history_from_uploaded_files(
                provider=provider,
                uploaded_files=uploaded_files,
            )
            return self._provider_result_to_parse_result(
                provider=provider,
                provider_result=provider_result,
                folder_path=None,
            )
        if not folder_path:
            raise ValueError("folder_path_required")

        folder = Path(folder_path).expanduser()
        if not folder.exists() or not folder.is_dir():
            raise ValueError("import_folder_not_found")

        provider_result = load_provider_history(provider, folder)
        return self._provider_result_to_parse_result(
            provider=provider,
            provider_result=provider_result,
            folder_path=str(folder),
        )

    def _provider_result_to_parse_result(
        self,
        *,
        provider: ImportProvider,
        provider_result,
        folder_path: str | None,
    ) -> ImportParseResult:
        segments = [
            ImportSegment(
                role=item.role,
                content=item.content,
                turn_index=index,
                source=item.source,
                confidence=item.confidence,
            )
            for index, item in enumerate(provider_result.segments)
        ]
        return ImportParseResult(
            source_type="folder",
            provider=provider,
            folder_path=folder_path,
            segments=segments,
            detected_turns=len(segments),
            user_segment_count=sum(1 for item in segments if item.role == "user"),
            assistant_segment_count=sum(1 for item in segments if item.role == "assistant"),
            warnings=list(provider_result.warnings),
            scanned_session_count=provider_result.scanned_session_count,
        )

    def _load_provider_history_from_uploaded_files(
        self,
        *,
        provider: ImportProvider,
        uploaded_files: list[UploadedImportFile],
    ):
        with tempfile.TemporaryDirectory(prefix="deeptutor-history-import-") as tmp_dir:
            root = Path(tmp_dir)
            for item in uploaded_files:
                relative_path = self._safe_uploaded_relative_path(item.relative_path)
                target = root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(item.content_bytes)
            return load_provider_history(provider, root)

    def _safe_uploaded_relative_path(self, value: str) -> Path:
        normalized = str(value or "").strip().replace("\\", "/").lstrip("/")
        if not normalized:
            raise ValueError("invalid_uploaded_relative_path")
        relative_path = Path(normalized)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("invalid_uploaded_relative_path")
        return relative_path

    def extract_raw_user_inputs(
        self,
        parse_result: ImportParseResult,
    ) -> tuple[list[str], list[str]]:
        messages: list[str] = []
        warnings = list(parse_result.warnings)
        for segment in parse_result.segments:
            if segment.role not in {"user", "unknown"}:
                continue
            content = segment.content.strip()
            if not content or content.lower() in _STOP_PHRASES or content in _STOP_PHRASES:
                continue
            if len(content) < 4:
                continue
            messages.append(content)
        if not messages and "too_few_effective_signals" not in warnings:
            warnings.append("too_few_effective_signals")
        return messages, warnings

    async def preview_import(
        self,
        *,
        source_type: ImportSourceType,
        provider: ImportProvider | None,
        folder_path: str | None,
        text: str,
        mode: ImportMode,
        language: str = "zh",
        uploaded_files: list[UploadedImportFile] | None = None,
    ) -> ProfileImportPreview:
        parse_result = self.parse_import_input(
            source_type=source_type,
            provider=provider,
            folder_path=folder_path,
            text=text,
            uploaded_files=uploaded_files,
        )
        messages, warnings = self.extract_raw_user_inputs(parse_result)
        inferred = await infer_copa_profile(
            messages,
            existing_copa_profile=self._existing_copa_profile(mode),
            language=language,
        )
        copa_markdown = render_copa_markdown(inferred)
        summary_markdown = await self.generate_profile_summary(
            copa_markdown=copa_markdown,
            language=language,
        )
        return ProfileImportPreview(
            mode=mode,
            source_type=source_type,
            provider=provider,
            detected_turns=parse_result.detected_turns,
            extracted_user_messages=messages[:10],
            effective_signal_count=len(messages),
            warnings=warnings,
            generated_copa_markdown=copa_markdown,
            generated_summary_markdown=summary_markdown,
            will_update_sections=["CoPA Factors", "Profile Summary", "Profile Metadata"],
            can_apply=bool(messages),
            scanned_session_count=parse_result.scanned_session_count,
        )

    async def apply_import(
        self,
        *,
        source_type: ImportSourceType,
        provider: ImportProvider | None,
        folder_path: str | None,
        text: str,
        mode: ImportMode,
        language: str = "zh",
        uploaded_files: list[UploadedImportFile] | None = None,
    ) -> ProfileImportApplyResult:
        preview = await self.preview_import(
            source_type=source_type,
            provider=provider,
            folder_path=folder_path,
            text=text,
            mode=mode,
            language=language,
            uploaded_files=uploaded_files,
        )
        metadata_markdown = self.build_profile_metadata_section(
            mode=mode,
            source_type=source_type,
            provider=provider,
            folder_path=folder_path,
            effective_signal_count=preview.effective_signal_count,
            scanned_session_count=preview.scanned_session_count,
        )
        snapshot = self._memory_service.rewrite_profile_generated_sections(
            copa_markdown=preview.generated_copa_markdown,
            summary_markdown=preview.generated_summary_markdown,
            metadata_markdown=metadata_markdown,
        )
        self._copa_profile_service.mark_profile_refreshed(
            profile_source="history_import",
            history_import_provider=provider,
            history_import_signal_count=preview.effective_signal_count,
        )
        return ProfileImportApplyResult(
            applied=True,
            mode=mode,
            warnings=preview.warnings,
            updated_sections=preview.will_update_sections,
            profile_updated_at=snapshot.profile_updated_at,
            profile=snapshot.profile,
        )

    async def generate_profile_summary(
        self,
        *,
        copa_markdown: str,
        language: str,
    ) -> str:
        zh = str(language).lower().startswith("zh")
        system_prompt = (
            "你是 DeepTutor 的画像总结器。请基于 CoPA 画像生成简洁、克制、可读的 markdown 总结，只输出 markdown。"
            if zh
            else "You summarize a DeepTutor CoPA profile into concise markdown. Return markdown only."
        )
        prompt = (
            "请根据以下 CoPA 画像生成 `## Profile Summary` 区块，使用 3-4 条项目符号，只描述稳定偏好与系统适配建议。\n\n"
            f"{copa_markdown}"
            if zh
            else f"Generate a `## Profile Summary` section with 3-4 bullets based on:\n\n{copa_markdown}"
        )
        return str(
            await complete(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.2,
                max_tokens=300,
            )
        ).strip()

    def _existing_copa_profile(self, mode: ImportMode) -> str:
        if mode == "merge":
            return self._memory_service.read_copa_section()
        return ""

    def build_profile_metadata_section(
        self,
        *,
        mode: ImportMode,
        source_type: ImportSourceType,
        provider: ImportProvider | None,
        folder_path: str | None,
        effective_signal_count: int,
        scanned_session_count: int,
    ) -> str:
        lines = [
            "## Profile Metadata",
            "- source: history_import",
            f"- mode: {mode}",
            f"- source_type: {source_type}",
            f"- provider: {provider or 'none'}",
            f"- effective_signals: {effective_signal_count}",
            f"- scanned_sessions: {scanned_session_count}",
        ]
        if folder_path:
            lines.append(f"- folder: {folder_path}")
        return "\n".join(lines)

    def _parse_text_input(self, text: str) -> ImportParseResult:
        segments: list[ImportSegment] = []
        current_role: ImportRole | None = None
        current_lines: list[str] = []
        turn_index = 0
        warnings: list[str] = []

        def flush() -> None:
            nonlocal turn_index
            if current_role is None:
                return
            content = "\n".join(line for line in current_lines if line.strip()).strip()
            if not content:
                return
            segments.append(
                ImportSegment(
                    role=current_role,
                    content=content,
                    turn_index=turn_index,
                    source="pasted_text",
                    confidence="high" if current_role != "unknown" else "low",
                )
            )
            turn_index += 1

        for raw_line in text.splitlines():
            matched = False
            for pattern, role in _ROLE_PATTERNS:
                match = pattern.match(raw_line)
                if match:
                    flush()
                    current_role = role
                    current_lines = [match.group(1).strip()]
                    matched = True
                    break
            if matched:
                continue
            if current_role is None:
                current_role = "unknown"
            current_lines.append(raw_line)
        flush()

        if segments and all(segment.role == "unknown" for segment in segments):
            warnings.append("large_pasted_block_fallback")
        return ImportParseResult(
            source_type="pasted_text",
            provider=None,
            folder_path=None,
            segments=segments,
            detected_turns=len(segments),
            user_segment_count=sum(1 for item in segments if item.role == "user"),
            assistant_segment_count=sum(1 for item in segments if item.role == "assistant"),
            warnings=warnings,
            scanned_session_count=0,
        )


_default_service: ProfileImportService | None = None


def get_profile_import_service() -> ProfileImportService:
    global _default_service
    if _default_service is None:
        _default_service = ProfileImportService()
    return _default_service
