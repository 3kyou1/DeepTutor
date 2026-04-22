from __future__ import annotations

import inspect
import logging
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from deeptutor.services.personalization import (
    get_cold_start_service,
    get_profile_import_service,
    get_scientist_resonance_service,
)
from deeptutor.services.personalization.profile_import import UploadedImportFile

router = APIRouter()
logger = logging.getLogger(__name__)


class ColdStartSubmitRequest(BaseModel):
    language: str = "zh"
    answers: dict[str, int] = Field(default_factory=dict)


class ScientistResonanceRegenerateRequest(BaseModel):
    language: str = "zh"
    mode: str = "both"


class ProfileImportRequest(BaseModel):
    mode: Literal["create", "merge", "overwrite"] = "merge"
    language: str = "zh"
    source_type: Literal["folder", "pasted_text"] = "pasted_text"
    provider: Literal["codex", "claude_code", "cursor"] | None = None
    folder_path: str | None = None
    text: str = ""


async def _resolve(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _read_uploaded_import_files(
    files: list[UploadFile],
    relative_paths: list[str],
) -> list[UploadedImportFile]:
    if len(files) != len(relative_paths):
        raise HTTPException(status_code=400, detail="uploaded_file_count_mismatch")
    uploaded_files: list[UploadedImportFile] = []
    for file, relative_path in zip(files, relative_paths):
        uploaded_files.append(
            UploadedImportFile(
                relative_path=relative_path,
                content_bytes=await file.read(),
            )
        )
    if not uploaded_files:
        raise HTTPException(status_code=400, detail="uploaded_files_required")
    return uploaded_files


def _uploaded_total_bytes(uploaded_files: list[UploadedImportFile]) -> int:
    return sum(len(item.content_bytes) for item in uploaded_files)


@router.get("/cold-start/questions")
async def list_cold_start_questions(language: str = Query(default="zh")):
    service = get_cold_start_service()
    return await _resolve(service.list_cold_start_questions(language=language))


@router.get("/cold-start/status")
async def get_cold_start_status():
    service = get_cold_start_service()
    return await _resolve(service.get_cold_start_status())


@router.post("/cold-start/submit")
async def submit_cold_start_answers(payload: ColdStartSubmitRequest):
    service = get_cold_start_service()
    try:
        return await _resolve(
            service.submit_cold_start_answers(payload.answers, language=payload.language)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(
            status_code=500,
            detail="failed_to_write_cold_start_profile",
        ) from exc


@router.post("/profile-import/preview")
async def preview_profile_import(payload: ProfileImportRequest):
    service = get_profile_import_service()
    logger.info(
        "profile import preview request source_type=%s provider=%s mode=%s has_folder=%s text_length=%d",
        payload.source_type,
        payload.provider,
        payload.mode,
        bool(payload.folder_path),
        len(payload.text or ""),
    )
    try:
        result = await _resolve(
            service.preview_import(
                source_type=payload.source_type,
                provider=payload.provider,
                folder_path=payload.folder_path,
                text=payload.text,
                mode=payload.mode,
                language=payload.language,
            )
        )
        return result.to_dict() if hasattr(result, "to_dict") else result
    except ValueError as exc:
        logger.warning("profile import preview rejected detail=%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        logger.exception("profile import preview failed")
        raise HTTPException(
            status_code=500,
            detail="failed_to_generate_import_profile",
        ) from exc


@router.post("/profile-import/apply")
async def apply_profile_import(payload: ProfileImportRequest):
    service = get_profile_import_service()
    logger.info(
        "profile import apply request source_type=%s provider=%s mode=%s has_folder=%s text_length=%d",
        payload.source_type,
        payload.provider,
        payload.mode,
        bool(payload.folder_path),
        len(payload.text or ""),
    )
    try:
        result = await _resolve(
            service.apply_import(
                source_type=payload.source_type,
                provider=payload.provider,
                folder_path=payload.folder_path,
                text=payload.text,
                mode=payload.mode,
                language=payload.language,
            )
        )
        return result.to_dict() if hasattr(result, "to_dict") else result
    except ValueError as exc:
        logger.warning("profile import apply rejected detail=%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        logger.exception("profile import apply failed")
        raise HTTPException(
            status_code=500,
            detail="failed_to_write_import_profile",
        ) from exc


@router.post("/profile-import/preview-upload")
async def preview_profile_import_upload(
    mode: Literal["create", "merge", "overwrite"] = Form(default="merge"),
    language: str = Form(default="zh"),
    provider: Literal["codex", "claude_code", "cursor"] = Form(...),
    relative_paths: list[str] = Form(...),
    files: list[UploadFile] = File(...),
):
    service = get_profile_import_service()
    uploaded_files = await _read_uploaded_import_files(files, relative_paths)
    logger.info(
        "profile import preview-upload request provider=%s mode=%s uploaded_file_count=%d uploaded_total_bytes=%d",
        provider,
        mode,
        len(uploaded_files),
        _uploaded_total_bytes(uploaded_files),
    )
    try:
        result = await _resolve(
            service.preview_import(
                source_type="folder",
                provider=provider,
                folder_path=None,
                text="",
                mode=mode,
                language=language,
                uploaded_files=uploaded_files,
            )
        )
        return result.to_dict() if hasattr(result, "to_dict") else result
    except ValueError as exc:
        logger.warning("profile import preview-upload rejected detail=%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        logger.exception("profile import preview-upload failed")
        raise HTTPException(
            status_code=500,
            detail="failed_to_generate_import_profile",
        ) from exc


@router.post("/profile-import/apply-upload")
async def apply_profile_import_upload(
    mode: Literal["create", "merge", "overwrite"] = Form(default="merge"),
    language: str = Form(default="zh"),
    provider: Literal["codex", "claude_code", "cursor"] = Form(...),
    relative_paths: list[str] = Form(...),
    files: list[UploadFile] = File(...),
):
    service = get_profile_import_service()
    uploaded_files = await _read_uploaded_import_files(files, relative_paths)
    logger.info(
        "profile import apply-upload request provider=%s mode=%s uploaded_file_count=%d uploaded_total_bytes=%d",
        provider,
        mode,
        len(uploaded_files),
        _uploaded_total_bytes(uploaded_files),
    )
    try:
        result = await _resolve(
            service.apply_import(
                source_type="folder",
                provider=provider,
                folder_path=None,
                text="",
                mode=mode,
                language=language,
                uploaded_files=uploaded_files,
            )
        )
        return result.to_dict() if hasattr(result, "to_dict") else result
    except ValueError as exc:
        logger.warning("profile import apply-upload rejected detail=%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive path
        logger.exception("profile import apply-upload failed")
        raise HTTPException(
            status_code=500,
            detail="failed_to_write_import_profile",
        ) from exc


@router.get("/scientist-resonance")
async def get_scientist_resonance(language: str = Query(default="zh")):
    service = get_scientist_resonance_service()
    return await _resolve(service.get_resonance(language=language))


@router.post("/scientist-resonance/regenerate")
async def regenerate_scientist_resonance(payload: ScientistResonanceRegenerateRequest):
    service = get_scientist_resonance_service()
    return await _resolve(service.regenerate(language=payload.language, mode=payload.mode))
