from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from deeptutor.services.llm import complete
from deeptutor.services.memory import MemoryService, get_memory_service
from deeptutor.services.path_service import PathService, get_path_service
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, get_sqlite_session_store

REFRESH_THRESHOLD = 15
FACTOR_ORDER = ("CT", "SA", "SC", "CLM", "MS", "AMR")
FACTOR_SPECS: dict[str, dict[str, str]] = {
    "CT": {
        "title": "Cognitive Trust (CT)｜认知信任",
        "definition": "用户对回答可信度、证据充分性、来源可靠性与论证严谨度的偏好阈值。",
    },
    "SA": {
        "title": "Situational Anchoring (SA)｜情境锚定",
        "definition": "回答是否紧贴用户当前任务、即时目标、实际限制与具体使用场景。",
    },
    "SC": {
        "title": "Schema Consistency (SC)｜认知图式一致性",
        "definition": "回答是否与用户已有知识结构、术语习惯、理解路径和心智模型保持一致。",
    },
    "CLM": {
        "title": "Cognitive Load Management (CLM)｜认知负荷管理",
        "definition": "回答复杂度、信息密度、步骤数与抽象程度是否匹配用户当前处理能力。",
    },
    "MS": {
        "title": "Metacognitive Scaffolding (MS)｜元认知支架",
        "definition": "回答是否帮助用户建立判断框架、排错顺序、思考路径和自我校验能力。",
    },
    "AMR": {
        "title": "Affective and Motivational Resonance (AMR)｜情感与动机共振",
        "definition": "回答的语气、支持方式与用户当前情绪状态、动机强度、行动倾向是否匹配。",
    },
}


@dataclass
class CoPARefreshResult:
    refreshed: bool
    total_messages: int
    consumed_messages: int
    markdown: str = ""


def filter_raw_user_inputs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("role") or "") != "user":
            continue
        content = str(row.get("content") or "").strip()
        if not content or content.startswith("[Quiz Performance]"):
            continue
        filtered.append({**row, "content": content})
    return filtered


def should_refresh(total_user_messages: int, consumed: int, threshold: int = REFRESH_THRESHOLD) -> bool:
    return max(0, int(total_user_messages) - int(consumed)) >= int(threshold)


def _strip_code_fence(content: str) -> str:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _default_factor_payload(code: str) -> dict[str, Any]:
    title = FACTOR_SPECS[code]["title"]
    zh_name = title.split("｜", 1)[-1]
    return {
        "user_profile_description": f"该用户在{zh_name}上暂无足够新信号，保持现有稳定偏好判断。",
        "response_strategy": [
            "优先延续现有回答风格。",
            "仅在用户给出明确信号时再调整策略。",
        ],
    }


def _normalize_factor_payload(code: str, payload: Any) -> dict[str, Any]:
    default = _default_factor_payload(code)
    if not isinstance(payload, dict):
        return default

    description = str(payload.get("user_profile_description") or "").strip()
    if not description:
        description = default["user_profile_description"]

    raw_strategy = payload.get("response_strategy")
    if isinstance(raw_strategy, list):
        strategy = [str(item).strip() for item in raw_strategy if str(item).strip()]
    else:
        strategy = []
    if not strategy:
        strategy = list(default["response_strategy"])
    return {
        "user_profile_description": description,
        "response_strategy": strategy[:4],
    }


def _normalize_inference_payload(payload: Any) -> dict[str, Any]:
    factors = payload.get("factors") if isinstance(payload, dict) else None
    normalized = {}
    for code in FACTOR_ORDER:
        normalized[code] = _normalize_factor_payload(
            code,
            factors.get(code) if isinstance(factors, dict) else None,
        )
    return {"factors": normalized}


async def infer_copa_profile(
    new_raw_user_messages: list[str],
    *,
    existing_copa_profile: str = "",
    language: str = "zh",
) -> dict[str, Any]:
    joined_messages = "\n".join(
        f"- {str(message).strip()}"
        for message in new_raw_user_messages
        if str(message).strip()
    )
    if str(language or "").lower().startswith("zh"):
        system_prompt = (
            "你是 DeepTutor 的长期个性化画像维护器。\n\n"
            "你的任务是：基于已有画像做“增量更新”，而不是从零重建画像。\n\n"
            "你将获得两类输入：\n"
            "1. 现有的因子画像；\n"
            "2. 新增的用户原始输入。\n\n"
            "必须严格遵守以下规则：\n"
            "- 更新规则：当新消息对某个因子提供了明确的新信号时，调整该因子。\n"
            "- 画像应保持跨会话的全局稳定性。\n"
            "- 不要重写因子定义；因子定义会在系统外部固定维护。\n"
            "- 模型只允许输出 6 个因子画像内容。\n"
            "- 顶层输出只允许包含一个字段：`factors`。\n"
            "- 最终只能返回严格 JSON，不能带解释性前后缀。"
        )
        user_prompt = (
            "请基于已有画像，对该用户的 CoPA 个性化画像做一次增量更新。\n\n"
            "<existing_copa_profile>\n"
            f"{existing_copa_profile or '(empty)'}\n"
            "</existing_copa_profile>\n\n"
            "<new_raw_user_messages>\n"
            f"{joined_messages or '(empty)'}\n"
            "</new_raw_user_messages>\n\n"
            "要求：\n"
            "- 根据新增用户输入来修正画像。\n"
            "- 如果某个因子没有被新消息明确影响，就尽量保持原画像不变。\n"
            "- 每条 response_strategy 都要简短、可执行，并且面向“后续回答生成”。\n"
            "- 返回的 JSON 只能包含上面定义的 `factors` 对象。\n\n"
            "最终只返回严格 JSON。"
        )
    else:
        system_prompt = (
            "You maintain a long-term CoPA personalization profile for DeepTutor.\n\n"
            "Your task is to UPDATE an existing global profile incrementally, not rebuild it from scratch.\n\n"
            "You are given:\n"
            "1. The existing CoPA profile.\n"
            "2. Newly added raw user messages.\n\n"
            "Important rules:\n"
            "- Update rule: adjust a factor only when the new messages provide a clear new signal for that factor.\n"
            "- Keep the profile globally stable across sessions.\n"
            "- Do NOT rewrite factor definitions. They are fixed outside your output.\n"
            "- Your output schema contains only one top-level field: `factors`.\n\n"
            "Return STRICT JSON only, matching the required schema exactly."
        )
        user_prompt = (
            "Please incrementally update the user's CoPA profile.\n\n"
            "<existing_copa_profile>\n"
            f"{existing_copa_profile or '(empty)'}\n"
            "</existing_copa_profile>\n\n"
            "<new_raw_user_messages>\n"
            f"{joined_messages or '(empty)'}\n"
            "</new_raw_user_messages>\n\n"
            "Requirements:\n"
            "- Adjust the profile according to the newly added raw user messages.\n"
            "- If a factor is not clearly affected by the new messages, keep it close to the previous profile.\n"
            "- Keep each response_strategy short, actionable, and generation-oriented.\n"
            "- The returned JSON must contain only the `factors` object defined in the schema above.\n\n"
            "Return strict JSON only."
        )

    raw = await complete(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.2,
        max_tokens=1400,
    )
    try:
        parsed = json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError:
        parsed = {}
    return _normalize_inference_payload(parsed)


def render_copa_markdown(profile: dict[str, Any]) -> str:
    factors = profile.get("factors") if isinstance(profile, dict) else {}
    sections = [
        "## CoPA Factors",
        "",
        "- 画像范围：全局稳定画像（仅基于用户原始输入）",
        "",
    ]
    for code in FACTOR_ORDER:
        factor = _normalize_factor_payload(code, factors.get(code) if isinstance(factors, dict) else None)
        sections.extend(
            [
                f"### {FACTOR_SPECS[code]['title']}",
                f"- 因子定义：{FACTOR_SPECS[code]['definition']}",
                f"- 用户画像描述：{factor['user_profile_description']}",
                "- 回答策略：",
            ]
        )
        sections.extend(f"  - {item}" for item in factor["response_strategy"])
        sections.append("")

    sections.extend(
        [
            "### Prompt Summary",
            _build_prompt_summary(
                {
                    code: _normalize_factor_payload(
                        code,
                        factors.get(code) if isinstance(factors, dict) else None,
                    )
                    for code in FACTOR_ORDER
                }
            ),
        ]
    )
    return "\n".join(sections).strip()


def _build_prompt_summary(factors: dict[str, dict[str, Any]]) -> str:
    prompt_bits: list[str] = []
    for code in ("SA", "CLM", "SC", "MS", "CT", "AMR"):
        strategy = factors[code]["response_strategy"][0]
        prompt_bits.append(strategy.rstrip("。.;；"))
    joined = "、".join(prompt_bits[:6])
    return f"该用户整体偏好：{joined}。"


class CoPAProfileService:
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
            return {
                "messages_consumed": 0,
                "refresh_threshold": REFRESH_THRESHOLD,
                "last_updated_at": None,
            }
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        return {
            "messages_consumed": int(payload.get("messages_consumed") or 0),
            "refresh_threshold": int(payload.get("refresh_threshold") or REFRESH_THRESHOLD),
            "last_updated_at": payload.get("last_updated_at"),
        }

    def _write_state(self, *, messages_consumed: int, threshold: int) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(
                {
                    "messages_consumed": int(messages_consumed),
                    "refresh_threshold": int(threshold),
                    "last_updated_at": datetime.now().astimezone().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    async def refresh_profile(self, *, language: str = "zh") -> CoPARefreshResult:
        all_rows = await self._store.list_global_raw_user_messages()
        raw_messages = filter_raw_user_inputs(all_rows)
        state = self._read_state()
        consumed = int(state["messages_consumed"])
        threshold = int(state["refresh_threshold"])
        total = len(raw_messages)

        if not should_refresh(total, consumed, threshold):
            return CoPARefreshResult(
                refreshed=False,
                total_messages=total,
                consumed_messages=consumed,
            )

        pending_messages = [row["content"] for row in raw_messages[consumed:]]
        existing_profile = self._memory_service.read_copa_section()
        inferred = await infer_copa_profile(
            pending_messages,
            existing_copa_profile=existing_profile,
            language=language,
        )
        markdown = render_copa_markdown(inferred)
        self._memory_service.write_copa_section(markdown)
        self._write_state(messages_consumed=total, threshold=threshold)
        return CoPARefreshResult(
            refreshed=True,
            total_messages=total,
            consumed_messages=total,
            markdown=markdown,
        )


_copa_profile_service: CoPAProfileService | None = None


def get_copa_profile_service() -> CoPAProfileService:
    global _copa_profile_service
    if _copa_profile_service is None:
        _copa_profile_service = CoPAProfileService()
    return _copa_profile_service
