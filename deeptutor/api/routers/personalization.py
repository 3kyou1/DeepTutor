from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.services.personalization import (
    get_cold_start_service,
    get_scientist_resonance_service,
)

router = APIRouter()


class ColdStartSubmitRequest(BaseModel):
    language: str = "zh"
    answers: dict[str, int] = Field(default_factory=dict)


class ScientistResonanceRegenerateRequest(BaseModel):
    language: str = "zh"
    mode: str = "both"


async def _resolve(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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


@router.get("/scientist-resonance")
async def get_scientist_resonance(language: str = Query(default="zh")):
    service = get_scientist_resonance_service()
    return await _resolve(service.get_resonance(language=language))


@router.post("/scientist-resonance/regenerate")
async def regenerate_scientist_resonance(payload: ScientistResonanceRegenerateRequest):
    service = get_scientist_resonance_service()
    return await _resolve(service.regenerate(language=payload.language, mode=payload.mode))
