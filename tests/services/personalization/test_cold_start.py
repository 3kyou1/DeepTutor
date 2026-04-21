from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.memory.service import MemoryService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get_memory_dir(self) -> Path:
        return self.root / "memory"

    def get_copa_state_file(self) -> Path:
        return self.root / "data" / "user" / "memory" / "copa_state.json"


def make_memory_service(
    tmp_path: Path,
    *,
    store: SQLiteSessionStore | None = None,
    profile_text: str = "",
) -> MemoryService:
    service = MemoryService(
        path_service=_PathServiceStub(tmp_path),
        store=store or SQLiteSessionStore(tmp_path / "chat_history.db"),
    )
    if profile_text:
        service.write_file("profile", profile_text)
    return service


def test_cold_start_questions_cover_all_six_factors() -> None:
    from deeptutor.services.personalization.cold_start import COLD_START_QUESTIONS

    factors = [question.factor for question in COLD_START_QUESTIONS]
    assert len(COLD_START_QUESTIONS) == 12
    assert sorted(set(factors)) == ["AMR", "CLM", "CT", "MS", "SA", "SC"]
    for factor in {"CT", "SA", "SC", "CLM", "MS", "AMR"}:
        assert factors.count(factor) == 2


def test_validate_cold_start_answers_rejects_missing_question() -> None:
    from deeptutor.services.personalization.cold_start import (
        COLD_START_QUESTIONS,
        validate_cold_start_answers,
    )

    answers = {question.id: 3 for question in COLD_START_QUESTIONS[:-1]}
    error = validate_cold_start_answers(answers)
    assert error == "missing_answers"


def test_validate_cold_start_answers_rejects_invalid_scale() -> None:
    from deeptutor.services.personalization.cold_start import (
        COLD_START_QUESTIONS,
        validate_cold_start_answers,
    )

    answers = {question.id: 3 for question in COLD_START_QUESTIONS}
    answers["CT_1"] = 6
    error = validate_cold_start_answers(answers)
    assert error == "invalid_scale"


def test_compute_factor_scores_returns_average_score_per_factor() -> None:
    from deeptutor.services.personalization.cold_start import compute_factor_scores

    answers = {
        "CT_1": 4, "CT_2": 5,
        "SA_1": 3, "SA_2": 4,
        "SC_1": 2, "SC_2": 3,
        "CLM_1": 3, "CLM_2": 3,
        "MS_1": 5, "MS_2": 4,
        "AMR_1": 2, "AMR_2": 3,
    }

    scores = compute_factor_scores(answers)

    assert scores["CT"] == 4.5
    assert scores["MS"] == 4.5
    assert scores["AMR"] == 2.5


def test_build_cold_start_profile_markdown_uses_standard_copa_block() -> None:
    from deeptutor.services.personalization.cold_start import build_cold_start_profile_markdown

    profile = build_cold_start_profile_markdown(
        factor_scores={"CT": 4.5, "SA": 4.0, "SC": 3.5, "CLM": 3.0, "MS": 4.5, "AMR": 2.5}
    )

    assert "## CoPA Factors" in profile
    assert "### Cognitive Trust (CT)｜认知信任" in profile
    assert "- 因子定义：" in profile
    assert "- 用户画像描述：" in profile
    assert "- 回答策略：" in profile


@pytest.mark.asyncio
async def test_submit_cold_start_answers_writes_profile_and_state(tmp_path: Path) -> None:
    from deeptutor.services.personalization.cold_start import (
        COLD_START_QUESTIONS,
        CoPAColdStartService,
    )

    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    await store.create_session(session_id="s1")
    await store.add_message(session_id="s1", role="user", content="help me learn")

    memory_service = make_memory_service(
        tmp_path,
        store=store,
        profile_text="## Preferences\nManual notes",
    )
    service = CoPAColdStartService(
        path_service=_PathServiceStub(tmp_path),
        store=store,
        memory_service=memory_service,
    )

    answers = {question.id: 4 for question in COLD_START_QUESTIONS}
    result = await service.submit_cold_start_answers(answers, language="zh")

    assert result["profile_source"] == "cold_start"
    assert result["profile_updated"] is True
    assert "## CoPA Factors" in result["profile_preview"]
    profile = memory_service.read_profile()
    assert "## Preferences\nManual notes" in profile
    assert "## CoPA Factors" in profile

    state = json.loads(_PathServiceStub(tmp_path).get_copa_state_file().read_text(encoding="utf-8"))
    assert state["profile_source"] == "cold_start"
    assert state["cold_start"]["answers"]["CT_1"] == 4
    assert state["cold_start"]["factor_scores"]["CT"] == 4.0
    assert state["messages_consumed"] == 1
