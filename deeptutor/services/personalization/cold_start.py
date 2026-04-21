from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from deeptutor.services.memory import MemoryService, get_memory_service
from deeptutor.services.path_service import PathService, get_path_service
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, get_sqlite_session_store

from .copa_profile import REFRESH_THRESHOLD, filter_raw_user_inputs, render_copa_markdown


@dataclass(frozen=True)
class ColdStartQuestion:
    id: str
    factor: str
    prompt_zh: str
    prompt_en: str
    order: int


COLD_START_QUESTIONS: list[ColdStartQuestion] = [
    ColdStartQuestion(
        id="CT_1",
        factor="CT",
        prompt_zh="当一个回答给出明确依据、限制条件和推理链时，我会更信任它。",
        prompt_en="I trust an answer more when it states evidence, limits, and the reasoning path clearly.",
        order=1,
    ),
    ColdStartQuestion(
        id="CT_2",
        factor="CT",
        prompt_zh="如果一个建议没有说明为什么这样做，我通常不会完全放心地采纳。",
        prompt_en="If a suggestion does not explain why it should work, I usually do not feel fully comfortable adopting it.",
        order=2,
    ),
    ColdStartQuestion(
        id="SA_1",
        factor="SA",
        prompt_zh="相比通用解释，我更希望回答直接贴合我当前手头的问题和约束。",
        prompt_en="Compared with general explanations, I prefer answers that directly fit my current task and constraints.",
        order=3,
    ),
    ColdStartQuestion(
        id="SA_2",
        factor="SA",
        prompt_zh="我更看重“现在这个具体场景下该怎么做”，而不是先展开大量背景知识。",
        prompt_en="I care more about what to do in my current situation than about a long background explanation first.",
        order=4,
    ),
    ColdStartQuestion(
        id="SC_1",
        factor="SC",
        prompt_zh="如果回答沿用我已经在使用的术语和理解方式，我会更容易接受。",
        prompt_en="I find an answer easier to accept when it uses the terminology and framing I am already using.",
        order=5,
    ),
    ColdStartQuestion(
        id="SC_2",
        factor="SC",
        prompt_zh="学习新内容时，我更喜欢别人先从我现有的理解出发，再逐步扩展。",
        prompt_en="When learning something new, I prefer others to start from what I already understand and then extend it gradually.",
        order=6,
    ),
    ColdStartQuestion(
        id="CLM_1",
        factor="CLM",
        prompt_zh="我更喜欢先得到简洁可执行的答案，再决定要不要看更多细节。",
        prompt_en="I prefer getting a concise, usable answer first, and then deciding whether I want more detail.",
        order=7,
    ),
    ColdStartQuestion(
        id="CLM_2",
        factor="CLM",
        prompt_zh="当信息很多时，分步骤、分层次的表达会让我更容易理解。",
        prompt_en="When there is a lot of information, step-by-step and layered explanations help me understand better.",
        order=8,
    ),
    ColdStartQuestion(
        id="MS_1",
        factor="MS",
        prompt_zh="除了答案本身，我也希望知道应该按什么顺序思考、排查或验证。",
        prompt_en="Besides the answer itself, I want to know the order in which I should think, troubleshoot, or verify.",
        order=9,
    ),
    ColdStartQuestion(
        id="MS_2",
        factor="MS",
        prompt_zh="我希望回答能帮助我形成以后也能复用的判断框架，而不只是解决当前一次问题。",
        prompt_en="I want answers that help me build a reusable judgment framework, not just solve this one problem.",
        order=10,
    ),
    ColdStartQuestion(
        id="AMR_1",
        factor="AMR",
        prompt_zh="当我卡住时，我更喜欢直接、稳定、不过度煽情的支持方式。",
        prompt_en="When I get stuck, I prefer support that is direct, steady, and not overly emotional.",
        order=11,
    ),
    ColdStartQuestion(
        id="AMR_2",
        factor="AMR",
        prompt_zh="相比鼓励性的话语，我更希望回答优先给我一个最容易执行的下一步。",
        prompt_en="Compared with encouraging words, I would rather get the easiest next step to execute first.",
        order=12,
    ),
]

QUESTION_BY_ID = {question.id: question for question in COLD_START_QUESTIONS}
QUESTION_IDS = set(QUESTION_BY_ID)
QUESTION_FACTORS = ("CT", "SA", "SC", "CLM", "MS", "AMR")
QUESTION_SCALE = {
    "zh": [
        {"value": 1, "label": "非常不同意"},
        {"value": 2, "label": "不同意"},
        {"value": 3, "label": "一般"},
        {"value": 4, "label": "同意"},
        {"value": 5, "label": "非常同意"},
    ],
    "en": [
        {"value": 1, "label": "Strongly Disagree"},
        {"value": 2, "label": "Disagree"},
        {"value": 3, "label": "Neutral"},
        {"value": 4, "label": "Agree"},
        {"value": 5, "label": "Strongly Agree"},
    ],
}

_BAND_LABELS = (
    (4.3, "high"),
    (3.5, "medium-high"),
    (3.0, "medium"),
    (2.1, "medium-low"),
    (0.0, "low"),
)

_FACTOR_TEXT: dict[str, dict[str, dict[str, Any]]] = {
    "CT": {
        "high": {
            "description": "该用户明显重视依据充分、可信且可解释的回答，对结论的论证质量要求较高。",
            "strategy": ["先给结论，再补依据与限制条件。", "关键判断尽量说明为什么成立。"],
        },
        "medium": {
            "description": "该用户希望回答有基本依据，同时也接受较直接的结论表达。",
            "strategy": ["优先给清晰结论，再补必要依据。", "只在关键处展开推理链。"],
        },
        "low": {
            "description": "该用户对显式依据的要求相对较低，更偏好先拿到直接可用的建议。",
            "strategy": ["先给直接答案和下一步。", "仅在必要时补充详细论证。"],
        },
    },
    "SA": {
        "high": {
            "description": "该用户更在意回答是否紧贴当前任务、约束和即时目标。",
            "strategy": ["优先回应当前场景，不先展开泛化背景。", "建议中显式绑定用户当前约束。"],
        },
        "medium": {
            "description": "该用户既接受背景解释，也希望答案和当前问题保持明确关联。",
            "strategy": ["先回应当前任务，再补少量通用背景。", "给出可直接执行的下一步。"],
        },
        "low": {
            "description": "该用户对场景锚定的要求相对较弱，也能接受更一般性的解释。",
            "strategy": ["在给出通用解释时保留一个场景化结论。", "避免过度依赖任务细节。"],
        },
    },
    "SC": {
        "high": {
            "description": "该用户更容易接受沿用其现有术语、理解路径和表达框架的解释。",
            "strategy": ["优先沿用用户当前术语和 framing。", "新概念先挂接到用户已有理解上。"],
        },
        "medium": {
            "description": "该用户希望解释与已有理解保持连续，但也接受适度的新表述。",
            "strategy": ["尽量沿用用户术语，再补必要的新命名。", "控制范式切换频率。"],
        },
        "low": {
            "description": "该用户对表述切换的敏感度较低，可以接受更独立的解释方式。",
            "strategy": ["在保持清晰的前提下可直接采用标准表述。", "仅在必要时回接用户原术语。"],
        },
    },
    "CLM": {
        "high": {
            "description": "该用户明显偏好结构化、分步且信息密度可控的回答。",
            "strategy": ["先给最小可用答案，再补扩展。", "用编号和分层结构组织内容。"],
        },
        "medium": {
            "description": "该用户希望回答清晰有层次，但可以接受适中的信息密度。",
            "strategy": ["保持答案结构清晰。", "在一个回复里控制并列分支数量。"],
        },
        "low": {
            "description": "该用户对信息密度较为耐受，可以接受更紧凑的表达方式。",
            "strategy": ["保持清晰即可，不必过度拆分。", "必要时可适度压缩步骤层级。"],
        },
    },
    "MS": {
        "high": {
            "description": "该用户不仅要答案，也重视可复用的思考顺序、判断节点与验证框架。",
            "strategy": ["给出步骤顺序和判断节点。", "补充可复用的检查或验证方法。"],
        },
        "medium": {
            "description": "该用户希望在关键处获得步骤支架，但不需要每次都展开完整框架。",
            "strategy": ["在复杂问题上补充思路顺序。", "必要时说明为什么先做这个。"],
        },
        "low": {
            "description": "该用户更偏向直接拿到结论，只有在需要时才希望看到完整支架。",
            "strategy": ["默认先给答案，按需再展开方法论。", "仅在复杂卡点时提供完整排查框架。"],
        },
    },
    "AMR": {
        "high": {
            "description": "该用户偏好稳、准、直接且具推进感的支持方式，不希望过度情绪化表达。",
            "strategy": ["保持克制直接的语气。", "少空泛鼓励，多给可执行下一步。"],
        },
        "medium": {
            "description": "该用户接受适度鼓励，但更看重回答是否能帮助自己继续推进。",
            "strategy": ["在支持语气和推进感之间保持平衡。", "优先给具体下一步。"],
        },
        "low": {
            "description": "该用户对情绪调节型表达的需求较高，除结论外也希望被稳定承接。",
            "strategy": ["在给出建议前先简短承接用户状态。", "结论保持温和、支持性更强。"],
        },
    },
}


def validate_cold_start_answers(answers: dict[str, int]) -> str | None:
    if set(answers) - QUESTION_IDS:
        return "unknown_question"
    if set(answers) != QUESTION_IDS:
        return "missing_answers"
    if any(not isinstance(value, int) or value < 1 or value > 5 for value in answers.values()):
        return "invalid_scale"
    return None


def compute_factor_scores(answers: dict[str, int]) -> dict[str, float]:
    grouped: dict[str, list[int]] = {factor: [] for factor in QUESTION_FACTORS}
    for question in COLD_START_QUESTIONS:
        grouped[question.factor].append(int(answers[question.id]))
    return {
        factor: round(sum(values) / len(values), 2) if values else 0.0
        for factor, values in grouped.items()
    }


def _score_band(score: float) -> str:
    for threshold, label in _BAND_LABELS:
        if score >= threshold:
            return label
    return "low"


def _band_bucket(label: str) -> str:
    if label in {"high", "medium-high"}:
        return "high"
    if label in {"medium", "medium-low"}:
        return "medium"
    return "low"


def build_cold_start_profile_payload(factor_scores: dict[str, float]) -> dict[str, Any]:
    payload: dict[str, dict[str, Any]] = {}
    for factor in QUESTION_FACTORS:
        score = float(factor_scores.get(factor, 3.0))
        text = _FACTOR_TEXT[factor][_band_bucket(_score_band(score))]
        payload[factor] = {
            "user_profile_description": text["description"],
            "response_strategy": list(text["strategy"]),
        }
    return {"factors": payload}


def build_cold_start_profile_markdown(factor_scores: dict[str, float]) -> str:
    return render_copa_markdown(build_cold_start_profile_payload(factor_scores))


class CoPAColdStartService:
    def __init__(
        self,
        path_service: PathService | None = None,
        store: SQLiteSessionStore | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._path_service = path_service or get_path_service()
        self._store = store or get_sqlite_session_store()
        self._memory_service = memory_service or get_memory_service()

    @property
    def _state_path(self) -> Path:
        return self._path_service.get_copa_state_file()

    def _read_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, state: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_cold_start_questions(self, language: str = "zh") -> dict[str, Any]:
        lang = "zh" if str(language or "").lower().startswith("zh") else "en"
        questions = [
            {
                "id": question.id,
                "factor": question.factor,
                "order": question.order,
                "prompt": question.prompt_zh if lang == "zh" else question.prompt_en,
            }
            for question in sorted(COLD_START_QUESTIONS, key=lambda item: item.order)
        ]
        return {
            "questions": questions,
            "scale": QUESTION_SCALE[lang],
            "question_count": len(questions),
        }

    async def get_cold_start_status(self) -> dict[str, Any]:
        state = self._read_state()
        all_rows = await self._store.list_global_raw_user_messages()
        raw_messages = filter_raw_user_inputs(all_rows)
        cold_start = state.get("cold_start") if isinstance(state.get("cold_start"), dict) else {}
        return {
            "profile_source": state.get("profile_source"),
            "has_cold_start_profile": bool(cold_start),
            "live_rebuild_threshold": int(state.get("live_rebuild_threshold") or REFRESH_THRESHOLD),
            "real_user_messages": len(raw_messages),
            "completed_at": cold_start.get("completed_at"),
            "can_reinitialize": True,
        }

    async def submit_cold_start_answers(
        self,
        answers: dict[str, int],
        *,
        language: str = "zh",
    ) -> dict[str, Any]:
        error = validate_cold_start_answers(answers)
        if error:
            raise ValueError(error)

        factor_scores = compute_factor_scores(answers)
        markdown = build_cold_start_profile_markdown(factor_scores)
        self._memory_service.write_copa_section(markdown)

        all_rows = await self._store.list_global_raw_user_messages()
        raw_messages = filter_raw_user_inputs(all_rows)
        state = self._read_state()
        completed_at = datetime.now().astimezone().isoformat()
        state.update(
            {
                "messages_consumed": len(raw_messages),
                "refresh_threshold": int(state.get("refresh_threshold") or REFRESH_THRESHOLD),
                "last_updated_at": completed_at,
                "profile_source": "cold_start",
                "live_rebuild_threshold": int(
                    state.get("live_rebuild_threshold") or REFRESH_THRESHOLD
                ),
                "cold_start": {
                    "version": "v1",
                    "completed_at": completed_at,
                    "answers": {key: int(value) for key, value in answers.items()},
                    "factor_scores": factor_scores,
                },
            }
        )
        self._write_state(state)
        return {
            "profile_source": "cold_start",
            "profile_updated": True,
            "completed_at": completed_at,
            "factor_scores": factor_scores,
            "profile_preview": markdown,
        }


_cold_start_service: CoPAColdStartService | None = None


def get_cold_start_service() -> CoPAColdStartService:
    global _cold_start_service
    if _cold_start_service is None:
        _cold_start_service = CoPAColdStartService()
    return _cold_start_service
