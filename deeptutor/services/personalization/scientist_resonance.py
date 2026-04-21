from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from deeptutor.services.config import get_env_store
from deeptutor.services.llm import complete, get_llm_config
from deeptutor.services.llm.config import LLMConfig
from deeptutor.services.memory import MemoryService, get_memory_service
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, get_sqlite_session_store

RECENT_WINDOW = 12
RECENT_MIN_MESSAGES = 4
PORTRAIT_PREFIX = "/scientist-portraits"
SCIENTIST_RESONANCE_ENV_KEYS = {
    "binding": "SCIENTIST_RESONANCE_LLM_BINDING",
    "model": "SCIENTIST_RESONANCE_LLM_MODEL",
    "api_key": "SCIENTIST_RESONANCE_LLM_API_KEY",
    "host": "SCIENTIST_RESONANCE_LLM_HOST",
    "api_version": "SCIENTIST_RESONANCE_LLM_API_VERSION",
    "reasoning_effort": "SCIENTIST_RESONANCE_REASONING_EFFORT",
}


@dataclass(frozen=True)
class ScientistRecord:
    slug: str
    name: str
    quote_en: str
    quote_zh: str
    core_traits: str
    thinking_style: str
    temperament_tags: str
    temperament_summary: str

    def pool_payload(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "core_traits": self.core_traits,
            "thinking_style": self.thinking_style,
            "temperament_tags": self.temperament_tags,
            "temperament_summary": self.temperament_summary,
        }

    def card_payload(self, *, reason: str, resonance_axes: list[str], confidence_style: str) -> dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "portrait_url": f"{PORTRAIT_PREFIX}/{self.slug}.jpg",
            "hook": self.temperament_summary,
            "quote_zh": self.quote_zh,
            "quote_en": self.quote_en,
            "reason": reason.strip(),
            "resonance_axes": resonance_axes[:4],
            "confidence_style": confidence_style,
        }


@lru_cache(maxsize=1)
def load_scientist_pool() -> dict[str, ScientistRecord]:
    root = Path(__file__).resolve().parents[3]
    tsv_path = root / "assets" / "scientist_portraits_bw" / "quotes_bilingual.tsv"
    pool: dict[str, ScientistRecord] = {}
    with tsv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            slug = str(row.get("slug") or "").strip()
            if not slug:
                continue
            pool[slug] = ScientistRecord(
                slug=slug,
                name=str(row.get("name_en") or slug).strip(),
                quote_en=str(row.get("quote_en") or "").strip(),
                quote_zh=str(row.get("quote_zh") or "").strip(),
                core_traits=str(row.get("core_traits") or "").strip(),
                thinking_style=str(row.get("thinking_style") or "").strip(),
                temperament_tags=str(row.get("temperament_tags") or "").strip(),
                temperament_summary=str(row.get("temperament_summary") or "").strip(),
            )
    return pool


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


def _strip_env_value(value: str) -> str:
    return str(value or "").strip().strip("\"'")


def get_scientist_resonance_llm_config() -> LLMConfig:
    base_config = get_llm_config()
    env_store = get_env_store()

    binding = _strip_env_value(env_store.get(SCIENTIST_RESONANCE_ENV_KEYS["binding"]))
    model = _strip_env_value(env_store.get(SCIENTIST_RESONANCE_ENV_KEYS["model"]))
    api_key = _strip_env_value(env_store.get(SCIENTIST_RESONANCE_ENV_KEYS["api_key"]))
    host = _strip_env_value(env_store.get(SCIENTIST_RESONANCE_ENV_KEYS["host"]))
    api_version = _strip_env_value(env_store.get(SCIENTIST_RESONANCE_ENV_KEYS["api_version"]))
    reasoning_effort = _strip_env_value(
        env_store.get(SCIENTIST_RESONANCE_ENV_KEYS["reasoning_effort"])
    )

    updates: dict[str, Any] = {}
    if binding:
        updates["binding"] = binding
    if model:
        updates["model"] = model
    if api_key:
        updates["api_key"] = api_key
    if host:
        updates["base_url"] = host
        updates["effective_url"] = host
    if api_version:
        updates["api_version"] = api_version
    if reasoning_effort:
        updates["reasoning_effort"] = reasoning_effort

    if not updates:
        return base_config
    return base_config.model_copy(updates)


def _clean_profile_text(profile_text: str) -> str:
    text = str(profile_text or "").strip()
    if not text:
        return ""
    pattern = re.compile(r"(^##\s*Scientist Resonance\s*$.*?)(?=^##\s+|\Z)", re.M | re.S)
    return pattern.sub("", text).strip()


def _extract_recent_messages(rows: list[dict[str, Any]], *, limit: int = RECENT_WINDOW) -> list[str]:
    cleaned: list[str] = []
    for row in rows:
        if str(row.get("role") or "") != "user":
            continue
        content = str(row.get("content") or "").strip()
        if not content or content.startswith("[Quiz Performance]"):
            continue
        cleaned.append(content)
    return cleaned[-limit:]


def _collect_signal_text(profile_text: str, recent_messages: list[str]) -> str:
    chunks = [profile_text.strip()] if profile_text.strip() else []
    if recent_messages:
        chunks.append("\n".join(f"- {item}" for item in recent_messages[-8:]))
    return "\n\n".join(chunks).strip()


def _unique_axes(values: list[Any]) -> list[str]:
    axes: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in axes:
            axes.append(item)
    return axes


def _normalize_card_payload(payload: Any, pool: dict[str, ScientistRecord], *, confidence_style: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    slug = str(payload.get("slug") or "").strip()
    scientist = pool.get(slug)
    if scientist is None:
        return None
    reason = str(payload.get("reason") or "").strip() or scientist.thinking_style
    axes = payload.get("resonance_axes") if isinstance(payload.get("resonance_axes"), list) else []
    normalized_axes = _unique_axes(axes)
    if not normalized_axes:
        normalized_axes = _unique_axes(
            scientist.core_traits.split("、")[:2] + scientist.temperament_tags.split("、")[:1]
        )
    return scientist.card_payload(
        reason=reason,
        resonance_axes=normalized_axes,
        confidence_style=confidence_style,
    )


def _default_reason(scientist: ScientistRecord, *, mode: str) -> str:
    prefix = "你长期更像" if mode == "long_term" else "你最近这段时间更像"
    return f"{prefix}{scientist.name}式研究者：{scientist.thinking_style}"


def _heuristic_match(signal_text: str, pool: dict[str, ScientistRecord], *, mode: str) -> dict[str, Any]:
    signal = str(signal_text or "").lower()
    best: ScientistRecord | None = None
    best_score = -1
    best_axes: list[str] = []
    for scientist in pool.values():
        fields = [scientist.core_traits, scientist.temperament_tags]
        score = 0
        matched_axes: list[str] = []
        for field in fields:
            for raw in field.split("、"):
                axis = raw.strip()
                if not axis:
                    continue
                if axis.lower() in signal:
                    score += 2
                    matched_axes.append(axis)
                elif len(axis) >= 2 and any(part and part in signal for part in re.split(r"[/-]", axis)):
                    score += 1
                    matched_axes.append(axis)
        if score > best_score:
            best = scientist
            best_score = score
            best_axes = _unique_axes(matched_axes)
    chosen = best or next(iter(pool.values()))
    if not best_axes:
        best_axes = _unique_axes(chosen.core_traits.split("、")[:2])
    return chosen.card_payload(
        reason=_default_reason(chosen, mode=mode),
        resonance_axes=best_axes,
        confidence_style="strong_resonance" if mode == "long_term" else "phase_resonance",
    )


async def infer_scientist_resonance(
    *,
    profile_text: str,
    recent_messages: list[str],
    language: str = "zh",
) -> dict[str, Any]:
    pool = load_scientist_pool()
    scientist_pool = [item.pool_payload() for item in pool.values()]
    signal_text = _collect_signal_text(profile_text, recent_messages)
    allow_recent = len(recent_messages) >= RECENT_MIN_MESSAGES
    llm_config = get_scientist_resonance_llm_config()

    if str(language or "").lower().startswith("zh"):
        system_prompt = (
            "你正在为 DeepTutor 生成 Scientist Resonance 结果。\n"
            "任务不是判断用户像不像名人，而是根据研究方式、人格气质与学习表达偏好，"
            "从固定科学家库中找出最强共振人物镜像。\n"
            "规则：\n"
            "1. 优先依据思维方式判断；\n"
            "2. 人格气质只用于确认或区分相近候选；\n"
            "3. 学习表达偏好只作弱辅助；\n"
            "4. 输出严格 JSON；\n"
            "5. 长期主原型与最近状态原型都只能从给定 slug 中选择。"
        )
        user_prompt = (
            "请根据以下用户画像与最近用户消息，在给定科学家库中生成 Scientist Resonance。\n\n"
            f"<profile>\n{profile_text or '(empty)'}\n</profile>\n\n"
            f"<recent_messages>\n{json.dumps(recent_messages, ensure_ascii=False)}\n</recent_messages>\n\n"
            f"<allow_recent_state>\n{json.dumps(allow_recent)}\n</allow_recent_state>\n\n"
            f"<scientist_pool>\n{json.dumps(scientist_pool, ensure_ascii=False)}\n</scientist_pool>\n\n"
            "返回 JSON，格式必须为：\n"
            "{\n"
            '  "long_term": {"slug": "...", "reason": "...", "resonance_axes": ["..."]},\n'
            '  "recent_state": {"slug": "...", "reason": "...", "resonance_axes": ["..."]} | null\n'
            "}\n"
            "要求：\n"
            "- long_term 必须存在；\n"
            "- recent_state 只有在 allow_recent_state 为 true 时才允许返回对象；\n"
            "- reason 必须是面向用户的中文解释，1-2 句；\n"
            "- resonance_axes 只保留 2-4 个短标签；\n"
            "- 不要输出库外人物；\n"
            "- 只返回 JSON。"
        )
    else:
        system_prompt = (
            "You are generating Scientist Resonance for DeepTutor. "
            "Choose resonance scientists from a fixed pool based on thinking style first, temperament second, learning style last. "
            "Return strict JSON only."
        )
        user_prompt = (
            "Generate a Scientist Resonance result from the given profile and recent user messages.\n\n"
            f"<profile>\n{profile_text or '(empty)'}\n</profile>\n\n"
            f"<recent_messages>\n{json.dumps(recent_messages, ensure_ascii=False)}\n</recent_messages>\n\n"
            f"<allow_recent_state>\n{json.dumps(allow_recent)}\n</allow_recent_state>\n\n"
            f"<scientist_pool>\n{json.dumps(scientist_pool, ensure_ascii=False)}\n</scientist_pool>\n\n"
            "Return JSON with keys long_term and recent_state. long_term must exist. recent_state may be null."
        )

    raw = await complete(
        prompt=user_prompt,
        system_prompt=system_prompt,
        model=llm_config.model,
        api_key=llm_config.api_key,
        base_url=llm_config.effective_url or llm_config.base_url,
        api_version=llm_config.api_version,
        binding=llm_config.binding,
        reasoning_effort=llm_config.reasoning_effort,
        extra_headers=llm_config.extra_headers,
        temperature=0.3,
        max_tokens=1600,
    )
    parsed = json.loads(_strip_code_fence(raw))
    return {
        "long_term": _normalize_card_payload(parsed.get("long_term"), pool, confidence_style="strong_resonance"),
        "recent_state": _normalize_card_payload(parsed.get("recent_state"), pool, confidence_style="phase_resonance") if allow_recent else None,
    }


class ScientistResonanceService:
    def __init__(
        self,
        *,
        memory_service: MemoryService | None = None,
        store: SQLiteSessionStore | None = None,
    ) -> None:
        self._memory_service = memory_service or get_memory_service()
        self._store = store or get_sqlite_session_store()

    async def get_resonance(self, *, language: str = "zh") -> dict[str, Any]:
        profile_text = _clean_profile_text(self._memory_service.read_profile())
        recent_rows = await self._store.list_global_raw_user_messages()
        recent_messages = _extract_recent_messages(recent_rows)
        pool = load_scientist_pool()
        signal_text = _collect_signal_text(profile_text, recent_messages)

        try:
            result = await infer_scientist_resonance(
                profile_text=profile_text,
                recent_messages=recent_messages,
                language=language,
            )
        except Exception:
            result = {
                "long_term": _heuristic_match(signal_text, pool, mode="long_term"),
                "recent_state": _heuristic_match("\n".join(recent_messages[-RECENT_WINDOW:]), pool, mode="recent_state")
                if len(recent_messages) >= RECENT_MIN_MESSAGES
                else None,
            }

        if not result.get("long_term"):
            result["long_term"] = _heuristic_match(signal_text, pool, mode="long_term")
        if len(recent_messages) < RECENT_MIN_MESSAGES:
            result["recent_state"] = None
        elif result.get("recent_state") is None:
            result["recent_state"] = _heuristic_match("\n".join(recent_messages[-RECENT_WINDOW:]), pool, mode="recent_state")
        return result

    async def regenerate(self, *, language: str = "zh", mode: str = "both") -> dict[str, Any]:
        # MVP: regenerate simply recomputes the structured payload from current profile + recent messages.
        return await self.get_resonance(language=language)


_scientist_resonance_service: ScientistResonanceService | None = None


def get_scientist_resonance_service() -> ScientistResonanceService:
    global _scientist_resonance_service
    if _scientist_resonance_service is None:
        _scientist_resonance_service = ScientistResonanceService()
    return _scientist_resonance_service


__all__ = [
    "ScientistRecord",
    "ScientistResonanceService",
    "get_scientist_resonance_llm_config",
    "get_scientist_resonance_service",
    "infer_scientist_resonance",
    "load_scientist_pool",
]
