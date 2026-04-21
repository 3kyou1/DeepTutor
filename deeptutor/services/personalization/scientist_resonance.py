from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from deeptutor.services.config import get_env_store
from deeptutor.services.llm import complete, get_llm_config
from deeptutor.services.llm.config import LLMConfig
from deeptutor.services.memory import MemoryService, get_memory_service
from deeptutor.services.path_service import get_path_service
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, get_sqlite_session_store

RECENT_WINDOW = 12
RECENT_MIN_MESSAGES = 4
PORTRAIT_PREFIX = "/scientist-portraits"
logger = logging.getLogger(__name__)
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
    loading_copy_zh: str
    loading_copy_en: str
    bio_zh: str
    bio_en: str
    achievements_zh: str
    achievements_en: str

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
            "loading_copy_zh": self.loading_copy_zh,
            "loading_copy_en": self.loading_copy_en,
            "bio_zh": self.bio_zh,
            "bio_en": self.bio_en,
            "achievements_zh": _split_achievement_items(self.achievements_zh),
            "achievements_en": _split_achievement_items(self.achievements_en),
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
                loading_copy_zh=str(row.get("loading_copy_zh") or "").strip(),
                loading_copy_en=str(row.get("loading_copy_en") or "").strip(),
                bio_zh=str(row.get("bio_zh") or "").strip(),
                bio_en=str(row.get("bio_en") or "").strip(),
                achievements_zh=str(row.get("achievements_zh") or "").strip(),
                achievements_en=str(row.get("achievements_en") or "").strip(),
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


def _split_achievement_items(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[｜|]+", str(value or "")) if item.strip()]


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


def _scientist_signature(scientist: ScientistRecord) -> set[str]:
    parts = re.split(r"[、,，;/｜|\s]+", f"{scientist.core_traits}、{scientist.temperament_tags}")
    return {part.strip().lower() for part in parts if part.strip()}


def _candidate_similarity(left: ScientistRecord, right: ScientistRecord) -> float:
    left_sig = _scientist_signature(left)
    right_sig = _scientist_signature(right)
    if not left_sig or not right_sig:
        return 0.0
    shared = left_sig & right_sig
    universe = left_sig | right_sig
    if not universe:
        return 0.0
    return len(shared) / len(universe)


def _build_card_payload(
    scientist: ScientistRecord,
    *,
    reason: str,
    resonance_axes: list[Any],
    confidence_style: str,
) -> dict[str, Any]:
    normalized_axes = _unique_axes(resonance_axes)
    if not normalized_axes:
        normalized_axes = _unique_axes(
            scientist.core_traits.split("、")[:2] + scientist.temperament_tags.split("、")[:1]
        )
    return scientist.card_payload(
        reason=str(reason or "").strip() or scientist.thinking_style,
        resonance_axes=normalized_axes,
        confidence_style=confidence_style,
    )


def _normalize_card_payload(payload: Any, pool: dict[str, ScientistRecord], *, confidence_style: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    slug = str(payload.get("slug") or "").strip()
    scientist = pool.get(slug)
    if scientist is None:
        return None
    axes = payload.get("resonance_axes") if isinstance(payload.get("resonance_axes"), list) else []
    return _build_card_payload(
        scientist,
        reason=str(payload.get("reason") or "").strip() or scientist.thinking_style,
        resonance_axes=axes,
        confidence_style=confidence_style,
    )


def _normalize_long_term_payload(payload: Any, pool: dict[str, ScientistRecord]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    primary_payload = payload.get("primary") if isinstance(payload.get("primary"), dict) else payload
    primary = _normalize_card_payload(primary_payload, pool, confidence_style="strong_resonance")
    if primary is None:
        return None

    secondary_payloads = payload.get("secondary") if isinstance(payload.get("secondary"), list) else []
    secondary: list[dict[str, Any]] = []
    seen = {primary["slug"]}
    for item in secondary_payloads:
        normalized = _normalize_card_payload(item, pool, confidence_style="strong_resonance")
        if normalized is None or normalized["slug"] in seen:
            continue
        seen.add(normalized["slug"])
        secondary.append(normalized)
        if len(secondary) >= 2:
            break

    return {
        "primary": primary,
        "secondary": secondary,
    }


def _default_reason(scientist: ScientistRecord, *, mode: str, language: str = "zh") -> str:
    if str(language or "").lower().startswith("zh"):
        prefix = "你长期更像" if mode == "long_term" else "你最近这段时间更像"
        return f"{prefix}{scientist.name}式研究者：{scientist.thinking_style}"
    prefix = "Your long-term archetype feels closest to" if mode == "long_term" else "Your recent state feels closest to"
    return f"{prefix} {scientist.name}: {scientist.thinking_style}"


def _score_scientist(signal_text: str, scientist: ScientistRecord) -> tuple[int, list[str]]:
    signal = str(signal_text or "").lower()
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
    return score, _unique_axes(matched_axes)


def _heuristic_candidates(
    signal_text: str,
    pool: dict[str, ScientistRecord],
    *,
    language: str = "zh",
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for scientist in pool.values():
        score, axes = _score_scientist(signal_text, scientist)
        candidates.append(
            {
                "slug": scientist.slug,
                "score": score,
                "reason": _default_reason(scientist, mode="long_term", language=language),
                "resonance_axes": axes or _unique_axes(scientist.core_traits.split("、")[:2]),
            }
        )
    return sorted(
        candidates,
        key=lambda item: (int(item.get("score") or 0), len(item.get("resonance_axes") or [])),
        reverse=True,
    )


def _pick_secondary_candidates(
    *,
    primary_slug: str,
    candidates: list[dict[str, Any]],
    pool: dict[str, ScientistRecord],
    limit: int = 2,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    primary = pool.get(primary_slug)
    if primary is None:
        return selected

    for candidate in candidates:
        slug = str(candidate.get("slug") or "").strip()
        if not slug or slug == primary_slug or slug not in pool:
            continue
        scientist = pool[slug]
        too_close_to_primary = _candidate_similarity(primary, scientist) >= 0.45
        too_close_to_selected = any(
            _candidate_similarity(pool[item["slug"]], scientist) >= 0.45 for item in selected if item["slug"] in pool
        )
        if too_close_to_primary or too_close_to_selected:
            skipped.append(candidate)
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            return selected

    for candidate in skipped:
        slug = str(candidate.get("slug") or "").strip()
        if not slug or any(item["slug"] == slug for item in selected):
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def _heuristic_match(
    signal_text: str,
    pool: dict[str, ScientistRecord],
    *,
    mode: str,
    language: str = "zh",
) -> dict[str, Any]:
    candidates = _heuristic_candidates(signal_text, pool, language=language)
    chosen_payload = candidates[0] if candidates else None
    chosen = pool.get(str(chosen_payload.get("slug") or "")) if chosen_payload else None
    if chosen is None:
        chosen = next(iter(pool.values()))
        chosen_payload = {
            "slug": chosen.slug,
            "score": 0,
            "reason": _default_reason(chosen, mode=mode, language=language),
            "resonance_axes": _unique_axes(chosen.core_traits.split("、")[:2]),
        }

    primary_card = _build_card_payload(
        chosen,
        reason=str(chosen_payload.get("reason") or _default_reason(chosen, mode=mode, language=language)),
        resonance_axes=list(chosen_payload.get("resonance_axes") or []),
        confidence_style="strong_resonance" if mode == "long_term" else "phase_resonance",
    )

    if mode != "long_term":
        return primary_card

    secondary = []
    for candidate in _pick_secondary_candidates(primary_slug=chosen.slug, candidates=candidates[1:], pool=pool):
        scientist = pool.get(str(candidate.get("slug") or ""))
        if scientist is None:
            continue
        secondary.append(
            _build_card_payload(
                scientist,
                reason=str(candidate.get("reason") or scientist.thinking_style),
                resonance_axes=list(candidate.get("resonance_axes") or []),
                confidence_style="strong_resonance",
            )
        )

    return {
        "primary": primary_card,
        "secondary": secondary,
    }


def _enrich_long_term_with_secondary(
    long_term: dict[str, Any] | None,
    *,
    signal_text: str,
    pool: dict[str, ScientistRecord],
    language: str = "zh",
) -> dict[str, Any]:
    if not isinstance(long_term, dict) or not isinstance(long_term.get("primary"), dict):
        return _heuristic_match(signal_text, pool, mode="long_term", language=language)

    primary = long_term["primary"]
    secondary = [item for item in long_term.get("secondary", []) if isinstance(item, dict)]
    if len(secondary) >= 2:
        return {"primary": primary, "secondary": secondary[:2]}

    candidates = _heuristic_candidates(signal_text, pool, language=language)
    for candidate in _pick_secondary_candidates(
        primary_slug=str(primary.get("slug") or ""),
        candidates=candidates,
        pool=pool,
        limit=2,
    ):
        scientist = pool.get(str(candidate.get("slug") or ""))
        if scientist is None:
            continue
        if any(item.get("slug") == scientist.slug for item in secondary):
            continue
        secondary.append(
            _build_card_payload(
                scientist,
                reason=str(candidate.get("reason") or scientist.thinking_style),
                resonance_axes=list(candidate.get("resonance_axes") or []),
                confidence_style="strong_resonance",
            )
        )
        if len(secondary) >= 2:
            break

    return {
        "primary": primary,
        "secondary": secondary[:2],
    }


def _default_resonance_cache_path() -> Path:
    return get_path_service().get_settings_file("scientist_resonance_cache")


def _normalize_cached_payload(payload: Any, pool: dict[str, ScientistRecord]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    long_term = _normalize_long_term_payload(payload.get("long_term"), pool)
    recent_state = _normalize_card_payload(payload.get("recent_state"), pool, confidence_style="phase_resonance")
    if long_term is None:
        return None
    return {
        "long_term": long_term,
        "recent_state": recent_state,
    }


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
    logger.info(
        "Scientist Resonance requesting LLM: model=%s binding=%s base_url=%s recent_messages=%s allow_recent=%s",
        llm_config.model,
        llm_config.binding,
        llm_config.effective_url or llm_config.base_url,
        len(recent_messages),
        allow_recent,
    )

    if str(language or "").lower().startswith("zh"):
        system_prompt = (
            "你正在为 DeepTutor 生成 Scientist Resonance 结果。\n"
            "任务不是判断用户像不像名人，而是根据研究方式、人格气质与学习表达偏好，"
            "从固定科学家库中找出最强共振人物镜像。\n"
            "规则：\n"
            "1. 优先依据思维方式判断；\n"
            "2. 人格气质只用于确认或区分相近候选；\n"
            "3. 学习表达偏好只作弱辅助；\n"
            "4. 长期主原型需要给出 1 个 primary 和 2 个 secondary；\n"
            "5. secondary 要尽量和 primary、彼此之间拉开气质差异，不要只给同类变体；\n"
            "6. 输出严格 JSON；\n"
            "7. 长期主原型与最近状态原型都只能从给定 slug 中选择。"
        )
        user_prompt = (
            "请根据以下用户画像与最近用户消息，在给定科学家库中生成 Scientist Resonance。\n\n"
            f"<profile>\n{profile_text or '(empty)'}\n</profile>\n\n"
            f"<recent_messages>\n{json.dumps(recent_messages, ensure_ascii=False)}\n</recent_messages>\n\n"
            f"<allow_recent_state>\n{json.dumps(allow_recent)}\n</allow_recent_state>\n\n"
            f"<scientist_pool>\n{json.dumps(scientist_pool, ensure_ascii=False)}\n</scientist_pool>\n\n"
            "返回 JSON，格式必须为：\n"
            "{\n"
            '  "long_term": {\n'
            '    "primary": {"slug": "...", "reason": "...", "resonance_axes": ["..."]},\n'
            '    "secondary": [\n'
            '      {"slug": "...", "reason": "...", "resonance_axes": ["..."]},\n'
            '      {"slug": "...", "reason": "...", "resonance_axes": ["..."]}\n'
            "    ]\n"
            "  },\n"
            '  "recent_state": {"slug": "...", "reason": "...", "resonance_axes": ["..."]} | null\n'
            "}\n"
            "要求：\n"
            "- long_term.primary 必须存在；\n"
            "- long_term.secondary 尽量返回 2 个，若实在不合适可少于 2 个；\n"
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
            "For long_term, return one primary scientist plus two secondary scientists with deliberately different temperaments. "
            "Return strict JSON only."
        )
        user_prompt = (
            "Generate a Scientist Resonance result from the given profile and recent user messages.\n\n"
            f"<profile>\n{profile_text or '(empty)'}\n</profile>\n\n"
            f"<recent_messages>\n{json.dumps(recent_messages, ensure_ascii=False)}\n</recent_messages>\n\n"
            f"<allow_recent_state>\n{json.dumps(allow_recent)}\n</allow_recent_state>\n\n"
            f"<scientist_pool>\n{json.dumps(scientist_pool, ensure_ascii=False)}\n</scientist_pool>\n\n"
            "Return JSON with keys long_term and recent_state. "
            "long_term must include primary and secondary. recent_state may be null."
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
    logger.info("Scientist Resonance LLM returned payload (%s chars)", len(raw))
    parsed = json.loads(_strip_code_fence(raw))
    return {
        "long_term": _enrich_long_term_with_secondary(
            _normalize_long_term_payload(parsed.get("long_term"), pool),
            signal_text=signal_text,
            pool=pool,
            language=language,
        ),
        "recent_state": _normalize_card_payload(parsed.get("recent_state"), pool, confidence_style="phase_resonance") if allow_recent else None,
    }


class ScientistResonanceService:
    def __init__(
        self,
        *,
        memory_service: MemoryService | None = None,
        store: SQLiteSessionStore | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self._memory_service = memory_service or get_memory_service()
        self._store = store or get_sqlite_session_store()
        self._cache_path = cache_path or _default_resonance_cache_path()

    def _read_cache(self, *, language: str, pool: dict[str, ScientistRecord]) -> dict[str, Any] | None:
        if not self._cache_path.exists():
            return None
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Scientist Resonance cache is unreadable; ignoring cache", exc_info=True)
            return None

        normalized_language = "zh" if str(language or "").lower().startswith("zh") else "en"
        cached = raw.get(normalized_language) if isinstance(raw, dict) else None
        result = _normalize_cached_payload(cached, pool)
        if result is None:
            return None
        logger.info("Scientist Resonance cache hit for language=%s", normalized_language)
        return result

    def _write_cache(self, *, language: str, payload: dict[str, Any]) -> None:
        normalized_language = "zh" if str(language or "").lower().startswith("zh") else "en"
        cache: dict[str, Any] = {}
        if self._cache_path.exists():
            try:
                cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
                if not isinstance(cache, dict):
                    cache = {}
            except Exception:
                logger.warning("Scientist Resonance cache could not be loaded; overwriting cache", exc_info=True)
                cache = {}

        cache[normalized_language] = payload
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _build_live_result(
        self,
        *,
        profile_text: str,
        recent_messages: list[str],
        language: str,
        pool: dict[str, ScientistRecord],
        signal_text: str,
    ) -> dict[str, Any]:
        try:
            result = await infer_scientist_resonance(
                profile_text=profile_text,
                recent_messages=recent_messages,
                language=language,
            )
        except Exception:
            logger.warning(
                "Scientist Resonance LLM inference failed; falling back to heuristic match",
                exc_info=True,
            )
            result = {
                "long_term": _heuristic_match(signal_text, pool, mode="long_term", language=language),
                "recent_state": _heuristic_match(
                    "\n".join(recent_messages[-RECENT_WINDOW:]),
                    pool,
                    mode="recent_state",
                    language=language,
                )
                if len(recent_messages) >= RECENT_MIN_MESSAGES
                else None,
            }

        if not result.get("long_term"):
            result["long_term"] = _heuristic_match(signal_text, pool, mode="long_term", language=language)
        if len(recent_messages) < RECENT_MIN_MESSAGES:
            result["recent_state"] = None
        elif result.get("recent_state") is None:
            result["recent_state"] = _heuristic_match(
                "\n".join(recent_messages[-RECENT_WINDOW:]),
                pool,
                mode="recent_state",
                language=language,
            )
        return result

    def _build_bootstrap_result(
        self,
        *,
        signal_text: str,
        recent_messages: list[str],
        pool: dict[str, ScientistRecord],
        language: str,
    ) -> dict[str, Any]:
        logger.info("Scientist Resonance cache miss; bootstrapping from heuristic snapshot")
        return {
            "long_term": _heuristic_match(signal_text, pool, mode="long_term", language=language),
            "recent_state": _heuristic_match(
                "\n".join(recent_messages[-RECENT_WINDOW:]),
                pool,
                mode="recent_state",
                language=language,
            )
            if len(recent_messages) >= RECENT_MIN_MESSAGES
            else None,
        }

    async def get_resonance(self, *, language: str = "zh") -> dict[str, Any]:
        profile_text = _clean_profile_text(self._memory_service.read_profile())
        recent_rows = await self._store.list_global_raw_user_messages()
        recent_messages = _extract_recent_messages(recent_rows)
        pool = load_scientist_pool()
        signal_text = _collect_signal_text(profile_text, recent_messages)
        cached = self._read_cache(language=language, pool=pool)
        if cached is not None:
            return cached

        result = self._build_bootstrap_result(
            signal_text=signal_text,
            recent_messages=recent_messages,
            pool=pool,
            language=language,
        )
        self._write_cache(language=language, payload=result)
        return result

    async def regenerate(self, *, language: str = "zh", mode: str = "both") -> dict[str, Any]:
        profile_text = _clean_profile_text(self._memory_service.read_profile())
        recent_rows = await self._store.list_global_raw_user_messages()
        recent_messages = _extract_recent_messages(recent_rows)
        pool = load_scientist_pool()
        signal_text = _collect_signal_text(profile_text, recent_messages)
        cached = self._read_cache(language=language, pool=pool)
        live = await self._build_live_result(
            profile_text=profile_text,
            recent_messages=recent_messages,
            language=language,
            pool=pool,
            signal_text=signal_text,
        )

        if mode == "long_term" and cached is not None:
            live["recent_state"] = cached.get("recent_state")
        elif mode == "recent_state" and cached is not None:
            live["long_term"] = cached.get("long_term") or live.get("long_term")

        self._write_cache(language=language, payload=live)
        return live


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
