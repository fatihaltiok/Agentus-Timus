from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import re
from typing import Any, Iterable, Mapping, Protocol, TypeVar
import uuid

from memory.memory_system import MemoryItem, memory_manager
from orchestration.autonomy_observation import record_autonomy_observation
from orchestration.conversation_recall_eval import (
    ConversationRecallEvalCase,
    summarize_conversation_recall_evals,
)
from utils.stable_hash import stable_text_digest


ARCHIVE_CATEGORY_PREFIX = "archived::"
SUMMARY_CATEGORY = "summarized_memory"
_SUMMARY_SOURCE = "memory_curation"
_STABLE_CATEGORIES = {"user_profile", "relationships", "self_model", "preference_memory"}
_TOPIC_BOUND_CATEGORIES = {"patterns", "decisions", "extracted", "summarized", SUMMARY_CATEGORY}
_EPHEMERAL_CATEGORIES = {"working_memory", "scratchpad", "session_memory"}
_ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE = 64
_T = TypeVar("_T")
_AUTONOMY_STATE_KEY = "memory_curation_autonomy"
_DEFAULT_AUTONOMY_ALLOWED_CATEGORIES = ("decisions", "patterns", "working_memory", "extracted", "test")
_DEFAULT_AUTONOMY_ALLOWED_ACTIONS = ("summarize", "archive", "devalue")
_RETRIEVAL_PROBE_STOPWORDS = {
    "aber",
    "alle",
    "auch",
    "auf",
    "aus",
    "bei",
    "damit",
    "dann",
    "dass",
    "deine",
    "deiner",
    "deinem",
    "deinen",
    "dein",
    "dieser",
    "dieses",
    "eine",
    "einer",
    "einem",
    "einen",
    "eines",
    "euch",
    "fuer",
    "have",
    "hier",
    "ihnen",
    "ihnen",
    "ihrer",
    "ihres",
    "ihre",
    "ihren",
    "ihr",
    "mehr",
    "mein",
    "meine",
    "meinem",
    "meinen",
    "meiner",
    "noch",
    "oder",
    "schon",
    "seine",
    "seiner",
    "seinem",
    "seinen",
    "sein",
    "sowie",
    "that",
    "their",
    "there",
    "these",
    "this",
    "ueber",
    "unter",
    "user",
    "value",
    "werden",
    "wieder",
    "with",
}
_RETRIEVAL_MIN_AVG_SCORE_DELTA = -0.05
_RETRIEVAL_MIN_HIT_AT_3_DELTA = -0.2
_RETRIEVAL_MIN_USEFUL_RATE_DELTA = -0.2
_RETRIEVAL_MAX_WRONG_TOP1_INCREASE = 0.2
_RETRIEVAL_MAX_FORBIDDEN_TOP1_INCREASE = 0.2
_DEFAULT_RETRIEVAL_BACKPRESSURE_LOOKBACK_RUNS = 6
_DEFAULT_RETRIEVAL_BACKPRESSURE_MIN_EVALUATED_RUNS = 3
_DEFAULT_RETRIEVAL_BACKPRESSURE_MIN_PASS_RATE = 0.67
_DEFAULT_RETRIEVAL_BACKPRESSURE_MAX_FAILED_RUNS = 1
_DEFAULT_RETRIEVAL_BACKPRESSURE_MAX_ROLLED_BACK_RUNS = 1


class MemoryCurationManagerLike(Protocol):
    persistent: Any
    semantic_store: Any

    def get_last_working_memory_stats(self) -> dict[str, Any]:
        ...

    def unified_recall(
        self,
        query: str,
        n_results: int = 5,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class MemoryCurationCandidate:
    candidate_id: str
    action: str
    tier: str
    category: str
    source: str
    reason: str
    item_keys: tuple[str, ...]
    item_count: int
    last_used_age_days: int
    average_importance: float


@dataclass(frozen=True)
class MemoryCurationRetrievalProbe:
    probe_id: str
    label: str
    query: str
    expected_markers: tuple[str, ...]
    forbidden_markers: tuple[str, ...]
    action: str
    category: str
    item_keys: tuple[str, ...]


def _normalize_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "true" if default else "false")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: Iterable[str]) -> list[str]:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return [str(value).strip().lower() for value in default if str(value).strip()]
    values = []
    for part in raw.split(","):
        clean = str(part or "").strip().lower()
        if clean and clean not in values:
            values.append(clean)
    return values


def _now() -> datetime:
    return datetime.now()


def _days_since(value: datetime, now: datetime) -> int:
    return max(0, int((now - value).days))


def _cooldown_active(updated_at: str, *, now: datetime, minutes: int) -> tuple[bool, str]:
    safe_minutes = max(0, _normalize_int(minutes, default=0))
    if safe_minutes <= 0:
        return False, ""
    try:
        parsed = datetime.fromisoformat(str(updated_at or "").strip())
    except Exception:
        return False, ""
    cooldown_until = parsed + timedelta(minutes=safe_minutes)
    return now < cooldown_until, cooldown_until.isoformat()


def _value_preview(value: Any, *, limit: int = 120) -> str:
    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def classify_memory_curation_tier(
    category: str,
    importance: float,
    confidence: float,
    source: str = "",
) -> str:
    normalized_category = str(category or "").strip().lower()
    normalized_source = str(source or "").strip().lower()
    normalized_importance = max(0.0, min(1.0, _normalize_float(importance, default=0.5)))
    normalized_confidence = max(0.0, min(1.0, _normalize_float(confidence, default=1.0)))

    if normalized_category.startswith(ARCHIVE_CATEGORY_PREFIX):
        return "archived"
    if normalized_category in _STABLE_CATEGORIES or normalized_source in {"self_model", "meta_preference_memory"}:
        return "stable"
    if normalized_category in _EPHEMERAL_CATEGORIES:
        return "ephemeral"
    if normalized_category in _TOPIC_BOUND_CATEGORIES:
        return "topic_bound"
    if normalized_importance >= 0.88 and normalized_confidence >= 0.85:
        return "stable"
    if normalized_importance <= 0.45 and normalized_confidence <= 0.75:
        return "ephemeral"
    return "topic_bound"


def decide_memory_curation_action(
    tier: str,
    *,
    last_used_age_days: int,
    importance: float,
    group_size: int,
) -> str:
    normalized_tier = str(tier or "").strip().lower()
    safe_age = max(0, _normalize_int(last_used_age_days))
    normalized_importance = max(0.0, min(1.0, _normalize_float(importance, default=0.5)))
    safe_group_size = max(0, _normalize_int(group_size))

    if normalized_tier in {"stable", "archived"}:
        return "keep"
    if safe_group_size >= 2 and safe_age >= 14:
        return "summarize"
    if normalized_tier == "ephemeral" and safe_age >= 30 and normalized_importance <= 0.55:
        return "archive"
    if normalized_tier == "topic_bound" and safe_age >= 30 and normalized_importance <= 0.75:
        return "devalue"
    return "keep"


def verify_memory_curation_outcome(
    *,
    before_active_items: int,
    after_active_items: int,
    before_stale_active_items: int,
    after_stale_active_items: int,
    before_stable_items: int,
    after_stable_items: int,
) -> bool:
    return (
        after_stale_active_items <= before_stale_active_items
        and after_stable_items >= before_stable_items
        and after_active_items <= (before_active_items + 1)
    )


def _manager(manager: MemoryCurationManagerLike | None = None) -> MemoryCurationManagerLike:
    return manager or memory_manager


def _active_items(items: Iterable[MemoryItem]) -> list[MemoryItem]:
    return [item for item in items if not str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX)]


def _active_average_importance(items: Iterable[MemoryItem]) -> float:
    materialized = list(items)
    if not materialized:
        return 0.0
    return round(sum(float(item.importance or 0.0) for item in materialized) / len(materialized), 3)


def _normalize_allowed_set(values: Iterable[str] | None) -> set[str]:
    normalized: set[str] = set()
    for value in values or []:
        clean = str(value or "").strip().lower()
        if clean:
            normalized.add(clean)
    return normalized


def _normalize_ratio(value: Any, *, default: float = 0.0) -> float:
    return max(0.0, min(1.0, _normalize_float(value, default=default)))


def _flatten_memory_value_segments(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Mapping):
        ordered_keys: list[str] = []
        for preferred in ("summary", "original_value", "value", "source_category", "source", "original_key"):
            if preferred in value:
                ordered_keys.append(preferred)
        for key in value.keys():
            key_text = str(key or "")
            if key_text not in ordered_keys:
                ordered_keys.append(key_text)
        segments: list[str] = []
        for key in ordered_keys:
            segments.extend(_flatten_memory_value_segments(value.get(key)))
        return segments
    if isinstance(value, (list, tuple, set)):
        segments: list[str] = []
        for item in value:
            segments.extend(_flatten_memory_value_segments(item))
        return segments
    text = str(value).strip()
    return [text] if text else []


def _memory_item_probe_text(item: MemoryItem) -> str:
    parts = _flatten_memory_value_segments(item.value)
    joined = " | ".join(part for part in parts if part).strip()
    return _value_preview(joined, limit=220)


def _extract_retrieval_probe_terms(text: str, *, limit: int = 4) -> list[str]:
    normalized = str(text or "").lower()
    terms: list[str] = []
    for token in re.findall(r"[a-z0-9äöüß_-]{4,}", normalized):
        clean = token.strip("_-")
        if not clean or clean in _RETRIEVAL_PROBE_STOPWORDS or clean in terms:
            continue
        terms.append(clean)
        if len(terms) >= limit:
            break
    return terms


def _build_retrieval_probe_for_item(
    *,
    item: MemoryItem,
    action: str,
    category: str,
    item_keys: tuple[str, ...],
) -> MemoryCurationRetrievalProbe | None:
    raw_text = _memory_item_probe_text(item)
    probe_terms = _extract_retrieval_probe_terms(raw_text, limit=4)
    if not raw_text or not probe_terms:
        return None
    expected_markers = tuple(probe_terms[:2]) or (raw_text.lower(),)
    return MemoryCurationRetrievalProbe(
        probe_id=f"{action}:{category}:{item.key}",
        label=f"{action}:{category}:{item.key}",
        query=" ".join(probe_terms[:3]),
        expected_markers=expected_markers,
        forbidden_markers=(),
        action=action,
        category=category,
        item_keys=item_keys,
    )


def build_memory_curation_retrieval_probes(
    *,
    items: Iterable[MemoryItem],
    candidates: Iterable[Mapping[str, Any]],
    max_probes: int = 6,
) -> list[dict[str, Any]]:
    item_map = {(item.category, item.key): item for item in items}
    safe_limit = max(1, _normalize_int(max_probes, default=6))
    probes: list[MemoryCurationRetrievalProbe] = []
    seen_probe_ids: set[str] = set()

    for candidate in candidates:
        action = str(candidate.get("action") or "").strip().lower()
        category = str(candidate.get("category") or "").strip()
        keys = tuple(str(key) for key in (candidate.get("item_keys") or []) if str(key))
        if not action or not category or not keys or action == "archive":
            continue

        if action == "summarize":
            probe_items = [
                item_map[(category, key)]
                for key in keys
                if (category, key) in item_map
            ][:2]
        else:
            item = item_map.get((category, keys[0]))
            probe_items = [item] if item is not None else []

        for item in probe_items:
            probe = _build_retrieval_probe_for_item(
                item=item,
                action=action,
                category=category,
                item_keys=keys,
            )
            if probe is None or probe.probe_id in seen_probe_ids:
                continue
            seen_probe_ids.add(probe.probe_id)
            probes.append(probe)
            if len(probes) >= safe_limit:
                break
        if len(probes) >= safe_limit:
            break

    return [
        {
            "probe_id": probe.probe_id,
            "label": probe.label,
            "query": probe.query,
            "expected_markers": list(probe.expected_markers),
            "forbidden_markers": list(probe.forbidden_markers),
            "action": probe.action,
            "category": probe.category,
            "item_keys": list(probe.item_keys),
        }
        for probe in probes
    ]


def evaluate_memory_curation_retrieval_probes(
    *,
    manager: MemoryCurationManagerLike | None = None,
    probes: Iterable[Mapping[str, Any]],
    n_results: int = 5,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    safe_results = max(1, min(8, _normalize_int(n_results, default=5)))
    materialized_probes = [dict(probe) for probe in probes]
    cases: list[ConversationRecallEvalCase] = []

    for probe in materialized_probes:
        recall_payload = active_manager.unified_recall(
            str(probe.get("query") or "").strip(),
            n_results=safe_results,
        )
        recalled_items = list((recall_payload or {}).get("memories") or [])
        cases.append(
            ConversationRecallEvalCase(
                query=str(probe.get("query") or ""),
                recalled_items=recalled_items,
                expected_markers=list(probe.get("expected_markers") or []),
                forbidden_markers=list(probe.get("forbidden_markers") or []),
                label=str(probe.get("label") or probe.get("probe_id") or ""),
            )
        )

    summary = summarize_conversation_recall_evals(cases)
    summary["probe_count"] = len(materialized_probes)
    summary["probe_labels"] = [str(probe.get("label") or probe.get("probe_id") or "") for probe in materialized_probes]
    summary["probes"] = materialized_probes
    return summary


def verify_memory_curation_retrieval_quality(
    *,
    before_summary: Mapping[str, Any],
    after_summary: Mapping[str, Any],
    min_avg_score_delta: float = _RETRIEVAL_MIN_AVG_SCORE_DELTA,
    min_hit_rate_at_3_delta: float = _RETRIEVAL_MIN_HIT_AT_3_DELTA,
    min_useful_rate_delta: float = _RETRIEVAL_MIN_USEFUL_RATE_DELTA,
    max_wrong_top1_increase: float = _RETRIEVAL_MAX_WRONG_TOP1_INCREASE,
    max_forbidden_top1_increase: float = _RETRIEVAL_MAX_FORBIDDEN_TOP1_INCREASE,
) -> bool:
    before_total = _normalize_int(before_summary.get("total_cases"), default=0)
    after_total = _normalize_int(after_summary.get("total_cases"), default=0)
    if before_total <= 0 or after_total <= 0:
        return True

    avg_score_delta = _normalize_float(after_summary.get("avg_score")) - _normalize_float(before_summary.get("avg_score"))
    hit_at_3_delta = _normalize_float(after_summary.get("hit_rate_at_3")) - _normalize_float(before_summary.get("hit_rate_at_3"))
    useful_rate_delta = _normalize_float(after_summary.get("useful_rate")) - _normalize_float(before_summary.get("useful_rate"))
    wrong_top1_increase = _normalize_float(after_summary.get("wrong_top1_rate")) - _normalize_float(before_summary.get("wrong_top1_rate"))
    forbidden_top1_increase = _normalize_float(after_summary.get("forbidden_top1_rate")) - _normalize_float(before_summary.get("forbidden_top1_rate"))

    return (
        avg_score_delta >= float(min_avg_score_delta)
        and hit_at_3_delta >= float(min_hit_rate_at_3_delta)
        and useful_rate_delta >= float(min_useful_rate_delta)
        and wrong_top1_increase <= float(max_wrong_top1_increase)
        and forbidden_top1_increase <= float(max_forbidden_top1_increase)
    )


def build_memory_curation_retrieval_quality_verdict(
    *,
    before_summary: Mapping[str, Any],
    after_summary: Mapping[str, Any],
) -> dict[str, Any]:
    before_total = _normalize_int(before_summary.get("total_cases"), default=0)
    after_total = _normalize_int(after_summary.get("total_cases"), default=0)
    if before_total <= 0 or after_total <= 0:
        return {
            "passed": True,
            "reason": "no_retrieval_probes",
            "probe_count": max(before_total, after_total),
            "avg_score_delta": 0.0,
            "hit_rate_at_3_delta": 0.0,
            "useful_rate_delta": 0.0,
            "wrong_top1_increase": 0.0,
            "forbidden_top1_increase": 0.0,
        }

    avg_score_delta = round(
        _normalize_float(after_summary.get("avg_score")) - _normalize_float(before_summary.get("avg_score")),
        3,
    )
    hit_rate_at_3_delta = round(
        _normalize_float(after_summary.get("hit_rate_at_3")) - _normalize_float(before_summary.get("hit_rate_at_3")),
        3,
    )
    useful_rate_delta = round(
        _normalize_float(after_summary.get("useful_rate")) - _normalize_float(before_summary.get("useful_rate")),
        3,
    )
    wrong_top1_increase = round(
        _normalize_float(after_summary.get("wrong_top1_rate")) - _normalize_float(before_summary.get("wrong_top1_rate")),
        3,
    )
    forbidden_top1_increase = round(
        _normalize_float(after_summary.get("forbidden_top1_rate")) - _normalize_float(before_summary.get("forbidden_top1_rate")),
        3,
    )
    passed = verify_memory_curation_retrieval_quality(
        before_summary=before_summary,
        after_summary=after_summary,
    )

    return {
        "passed": passed,
        "reason": "retrieval_quality_stable" if passed else "retrieval_quality_regressed",
        "probe_count": min(before_total, after_total),
        "avg_score_delta": avg_score_delta,
        "hit_rate_at_3_delta": hit_rate_at_3_delta,
        "useful_rate_delta": useful_rate_delta,
        "wrong_top1_increase": wrong_top1_increase,
        "forbidden_top1_increase": forbidden_top1_increase,
    }


def summarize_memory_curation_quality_history(
    snapshots: Iterable[Mapping[str, Any]],
    *,
    lookback_runs: int = _DEFAULT_RETRIEVAL_BACKPRESSURE_LOOKBACK_RUNS,
) -> dict[str, Any]:
    safe_lookback = max(1, _normalize_int(lookback_runs, default=_DEFAULT_RETRIEVAL_BACKPRESSURE_LOOKBACK_RUNS))
    recent_snapshots = [dict(snapshot) for snapshot in list(snapshots)[:safe_lookback]]

    evaluated_runs = 0
    passed_runs = 0
    failed_runs = 0
    rolled_back_runs = 0
    retrieval_regression_runs = 0
    snapshot_ids: list[str] = []

    for snapshot in recent_snapshots:
        snapshot_ids.append(str(snapshot.get("snapshot_id") or ""))
        status = str(snapshot.get("status") or "").strip().lower()
        metadata = dict(snapshot.get("metadata") or {})
        retrieval_quality = dict(metadata.get("retrieval_quality") or {})
        verdict = dict(retrieval_quality.get("verdict") or {})

        if verdict:
            evaluated_runs += 1
            if bool(verdict.get("passed")):
                passed_runs += 1
            else:
                failed_runs += 1
            if str(verdict.get("reason") or "").strip().lower() == "retrieval_quality_regressed":
                retrieval_regression_runs += 1
        if status == "rolled_back":
            rolled_back_runs += 1

    pass_rate = round(passed_runs / evaluated_runs, 3) if evaluated_runs > 0 else 1.0
    return {
        "lookback_runs": safe_lookback,
        "recent_snapshot_count": len(recent_snapshots),
        "evaluated_runs": evaluated_runs,
        "passed_runs": passed_runs,
        "failed_runs": failed_runs,
        "rolled_back_runs": rolled_back_runs,
        "retrieval_regression_runs": retrieval_regression_runs,
        "pass_rate": pass_rate,
        "recent_snapshot_ids": [snapshot_id for snapshot_id in snapshot_ids if snapshot_id],
    }


def should_block_memory_curation_retrieval_backpressure(
    *,
    evaluated_runs: int,
    pass_rate: float,
    failed_runs: int,
    rolled_back_runs: int,
    min_evaluated_runs: int,
    min_pass_rate: float,
    max_failed_runs: int,
    max_rolled_back_runs: int,
) -> bool:
    safe_evaluated_runs = max(0, _normalize_int(evaluated_runs, default=0))
    safe_failed_runs = max(0, _normalize_int(failed_runs, default=0))
    safe_rolled_back_runs = max(0, _normalize_int(rolled_back_runs, default=0))
    safe_min_runs = max(1, _normalize_int(min_evaluated_runs, default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MIN_EVALUATED_RUNS))
    safe_pass_rate = _normalize_ratio(pass_rate, default=1.0)
    safe_min_pass_rate = _normalize_ratio(min_pass_rate, default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MIN_PASS_RATE)
    safe_max_failed_runs = max(0, _normalize_int(max_failed_runs, default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MAX_FAILED_RUNS))
    safe_max_rolled_back_runs = max(0, _normalize_int(max_rolled_back_runs, default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MAX_ROLLED_BACK_RUNS))

    if safe_evaluated_runs < safe_min_runs:
        return False

    negative_budget_exhausted = (
        safe_failed_runs > safe_max_failed_runs
        or safe_rolled_back_runs > safe_max_rolled_back_runs
    )
    return negative_budget_exhausted and safe_pass_rate < safe_min_pass_rate


def build_memory_curation_retrieval_backpressure_governance(
    snapshots: Iterable[Mapping[str, Any]],
    *,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings_payload = dict(settings or {})
    backpressure_settings = {
        "enabled": bool(settings_payload.get("retrieval_backpressure_enabled", True)),
        "lookback_runs": max(
            1,
            _normalize_int(
                settings_payload.get("retrieval_backpressure_lookback_runs"),
                default=_DEFAULT_RETRIEVAL_BACKPRESSURE_LOOKBACK_RUNS,
            ),
        ),
        "min_evaluated_runs": max(
            1,
            _normalize_int(
                settings_payload.get("retrieval_backpressure_min_evaluated_runs"),
                default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MIN_EVALUATED_RUNS,
            ),
        ),
        "min_pass_rate": _normalize_ratio(
            settings_payload.get("retrieval_backpressure_min_pass_rate"),
            default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MIN_PASS_RATE,
        ),
        "max_failed_runs": max(
            0,
            _normalize_int(
                settings_payload.get("retrieval_backpressure_max_failed_runs"),
                default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MAX_FAILED_RUNS,
            ),
        ),
        "max_rolled_back_runs": max(
            0,
            _normalize_int(
                settings_payload.get("retrieval_backpressure_max_rolled_back_runs"),
                default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MAX_ROLLED_BACK_RUNS,
            ),
        ),
    }
    summary = summarize_memory_curation_quality_history(
        snapshots,
        lookback_runs=int(backpressure_settings["lookback_runs"]),
    )

    state = "allow"
    blocked = False
    reasons: list[str] = []
    if not bool(backpressure_settings["enabled"]):
        state = "disabled"
    elif int(summary["evaluated_runs"]) < int(backpressure_settings["min_evaluated_runs"]):
        state = "insufficient_history"
        reasons.append(
            f"evaluated_runs={summary['evaluated_runs']}/{backpressure_settings['min_evaluated_runs']}"
        )
    else:
        blocked = should_block_memory_curation_retrieval_backpressure(
            evaluated_runs=int(summary["evaluated_runs"]),
            pass_rate=float(summary["pass_rate"]),
            failed_runs=int(summary["failed_runs"]),
            rolled_back_runs=int(summary["rolled_back_runs"]),
            min_evaluated_runs=int(backpressure_settings["min_evaluated_runs"]),
            min_pass_rate=float(backpressure_settings["min_pass_rate"]),
            max_failed_runs=int(backpressure_settings["max_failed_runs"]),
            max_rolled_back_runs=int(backpressure_settings["max_rolled_back_runs"]),
        )
        if blocked:
            state = "retrieval_backpressure"
            reasons.extend(
                [
                    f"pass_rate={summary['pass_rate']}",
                    f"failed_runs={summary['failed_runs']}",
                    f"rolled_back_runs={summary['rolled_back_runs']}",
                ]
            )

    return {
        "state": state,
        "blocked": blocked,
        "reasons": reasons,
        "settings": backpressure_settings,
        "summary": summary,
    }


def build_memory_curation_metrics(
    items: Iterable[MemoryItem],
    *,
    manager: MemoryCurationManagerLike | None = None,
    stale_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _now()
    safe_stale_days = max(1, _normalize_int(stale_days, default=30))
    all_items = list(items)
    active_items = _active_items(all_items)
    archived_items = [item for item in all_items if str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX)]
    summary_items = [item for item in active_items if str(item.category or "") == SUMMARY_CATEGORY]

    tier_counts: dict[str, int] = {"stable": 0, "topic_bound": 0, "ephemeral": 0, "archived": 0}
    stale_active_items = 0
    stable_active_items = 0
    for item in all_items:
        tier = classify_memory_curation_tier(item.category, item.importance, item.confidence, item.source)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if tier == "stable" and not str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX):
            stable_active_items += 1
        if tier not in {"stable", "archived"} and not str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX):
            if _days_since(item.last_used, current) >= safe_stale_days:
                stale_active_items += 1

    working_stats = {}
    if manager is not None:
        try:
            working_stats = dict(manager.get_last_working_memory_stats() or {})
        except Exception:
            working_stats = {}

    return {
        "total_items": len(all_items),
        "active_items": len(active_items),
        "archived_items": len(archived_items),
        "summary_items": len(summary_items),
        "stale_active_items": stale_active_items,
        "stable_active_items": stable_active_items,
        "active_average_importance": _active_average_importance(active_items),
        "tier_counts": tier_counts,
        "working_memory_last_stats": working_stats,
        "stale_days": safe_stale_days,
    }


def build_memory_curation_candidates(
    *,
    manager: MemoryCurationManagerLike | None = None,
    stale_days: int = 30,
    max_candidates: int = 12,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    active_manager = _manager(manager)
    current = now or _now()
    safe_limit = max(1, _normalize_int(max_candidates, default=12))
    safe_stale_days = max(1, _normalize_int(stale_days, default=30))
    items = active_manager.persistent.get_all_memory_items()

    group_map: dict[tuple[str, str, str], list[tuple[MemoryItem, int]]] = {}
    consumed_ids: set[tuple[str, str]] = set()
    candidates: list[MemoryCurationCandidate] = []

    for item in items:
        tier = classify_memory_curation_tier(item.category, item.importance, item.confidence, item.source)
        if tier in {"stable", "archived"}:
            continue
        if str(item.category or "") == SUMMARY_CATEGORY:
            continue
        age = _days_since(item.last_used, current)
        if age < max(14, safe_stale_days // 2):
            continue
        key = (tier, str(item.category or ""), str(item.source or ""))
        group_map.setdefault(key, []).append((item, age))

    for (tier, category, source), grouped_items in group_map.items():
        if len(grouped_items) < 2:
            continue
        grouped_items.sort(key=lambda entry: (-entry[1], str(entry[0].key or "")))
        items_only = [entry[0] for entry in grouped_items[:5]]
        avg_importance = round(
            sum(float(item.importance or 0.0) for item in items_only) / max(1, len(items_only)),
            3,
        )
        max_age = max(_days_since(item.last_used, current) for item in items_only)
        digest = stable_text_digest("|".join(f"{item.category}:{item.key}" for item in items_only), hex_chars=10)
        candidates.append(
            MemoryCurationCandidate(
                candidate_id=f"summarize:{category}:{digest}",
                action="summarize",
                tier=tier,
                category=category,
                source=source,
                reason=f"group:{category}:{source or 'unknown'}",
                item_keys=tuple(item.key for item in items_only),
                item_count=len(items_only),
                last_used_age_days=max_age,
                average_importance=avg_importance,
            )
        )
        consumed_ids.update((item.category, item.key) for item in items_only)

    for item in items:
        item_ref = (item.category, item.key)
        if item_ref in consumed_ids:
            continue
        tier = classify_memory_curation_tier(item.category, item.importance, item.confidence, item.source)
        age = _days_since(item.last_used, current)
        action = decide_memory_curation_action(
            tier,
            last_used_age_days=age,
            importance=float(item.importance or 0.0),
            group_size=1,
        )
        if action == "keep":
            continue
        candidates.append(
            MemoryCurationCandidate(
                candidate_id=f"{action}:{item.category}:{item.key}",
                action=action,
                tier=tier,
                category=item.category,
                source=item.source,
                reason=f"stale:{age}d",
                item_keys=(item.key,),
                item_count=1,
                last_used_age_days=age,
                average_importance=round(float(item.importance or 0.0), 3),
            )
        )

    action_priority = {"summarize": 0, "archive": 1, "devalue": 2}
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            action_priority.get(candidate.action, 9),
            -candidate.item_count,
            -candidate.last_used_age_days,
            candidate.candidate_id,
        ),
    )

    result: list[dict[str, Any]] = []
    for candidate in ordered[:safe_limit]:
        result.append(
            {
                "candidate_id": candidate.candidate_id,
                "action": candidate.action,
                "tier": candidate.tier,
                "category": candidate.category,
                "source": candidate.source,
                "reason": candidate.reason,
                "item_keys": list(candidate.item_keys),
                "item_count": candidate.item_count,
                "last_used_age_days": candidate.last_used_age_days,
                "average_importance": candidate.average_importance,
            }
        )
    return result


def filter_memory_curation_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    allowed_actions: Iterable[str] | None = None,
    allowed_categories: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    action_allow = _normalize_allowed_set(allowed_actions)
    category_allow = _normalize_allowed_set(allowed_categories)
    safe_limit = None if limit is None else max(1, _normalize_int(limit, default=1))

    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        action = str(candidate.get("action") or "").strip().lower()
        category = str(candidate.get("category") or "").strip().lower()
        if action_allow and action not in action_allow:
            continue
        if category_allow and category not in category_allow:
            continue
        filtered.append(dict(candidate))
        if safe_limit is not None and len(filtered) >= safe_limit:
            break
    return filtered


def _store_active_item(manager: MemoryCurationManagerLike, item: MemoryItem) -> None:
    manager.persistent.store_memory_item(item)
    semantic_store = getattr(manager, "semantic_store", None)
    if semantic_store and hasattr(semantic_store, "is_available") and semantic_store.is_available():
        semantic_store.store_embedding(item)


def _delete_active_item(manager: MemoryCurationManagerLike, category: str, key: str) -> None:
    manager.persistent.delete_memory_item(category, key)
    semantic_store = getattr(manager, "semantic_store", None)
    if semantic_store and hasattr(semantic_store, "is_available") and semantic_store.is_available():
        semantic_store.delete_embedding(category, key)


def _archive_item(
    manager: MemoryCurationManagerLike,
    item: MemoryItem,
    *,
    archived_at: datetime,
    reason: str,
) -> MemoryItem:
    archived_item = MemoryItem(
        category=f"{ARCHIVE_CATEGORY_PREFIX}{item.category}",
        key=item.key,
        value={
            "original_category": item.category,
            "original_key": item.key,
            "original_value": item.value,
            "archived_at": archived_at.isoformat(),
            "archived_reason": reason,
            "original_importance": item.importance,
            "original_confidence": item.confidence,
            "original_source": item.source,
        },
        importance=item.importance,
        confidence=item.confidence,
        reason=f"memory_curation_archive:{reason}",
        source=_SUMMARY_SOURCE,
        created_at=item.created_at,
        last_used=archived_at,
    )
    manager.persistent.store_memory_item(archived_item)
    _delete_active_item(manager, item.category, item.key)
    return archived_item


def _apply_devalue_item(
    manager: MemoryCurationManagerLike,
    item: MemoryItem,
    *,
    reason: str,
) -> MemoryItem:
    devalued_item = MemoryItem(
        category=item.category,
        key=item.key,
        value=item.value,
        importance=max(0.1, round(float(item.importance or 0.0) - 0.2, 3)),
        confidence=max(0.1, round(float(item.confidence or 0.0) - 0.1, 3)),
        reason=f"{item.reason}; memory_curation_devalue:{reason}".strip("; "),
        source=item.source,
        created_at=item.created_at,
        last_used=item.last_used,
    )
    _store_active_item(manager, devalued_item)
    return devalued_item


def _build_summary_item(
    items: list[MemoryItem],
    *,
    category: str,
    source: str,
    now: datetime,
) -> MemoryItem:
    previews = [_value_preview(item.value, limit=90) for item in items]
    summary_text = " | ".join(preview for preview in previews if preview)[:320]
    digest = stable_text_digest("|".join(f"{item.category}:{item.key}" for item in items), hex_chars=10)
    return MemoryItem(
        category=SUMMARY_CATEGORY,
        key=f"summary_{digest}",
        value={
            "summary": summary_text,
            "source_category": category,
            "source": source,
            "source_keys": [item.key for item in items],
            "original_count": len(items),
        },
        importance=max(0.55, round(sum(float(item.importance or 0.0) for item in items) / max(1, len(items)), 3)),
        confidence=max(0.6, round(sum(float(item.confidence or 0.0) for item in items) / max(1, len(items)), 3)),
        reason="memory_curation_summary",
        source=_SUMMARY_SOURCE,
        created_at=now,
        last_used=now,
    )


def _iter_chunks(values: list[_T], chunk_size: int) -> Iterable[list[_T]]:
    safe_chunk_size = max(1, _normalize_int(chunk_size, default=_ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE))
    for index in range(0, len(values), safe_chunk_size):
        yield values[index:index + safe_chunk_size]


def _semantic_item_signature(item: MemoryItem) -> str:
    payload = {
        "category": item.category,
        "key": item.key,
        "value": item.value,
        "importance": round(float(item.importance or 0.0), 6),
        "confidence": round(float(item.confidence or 0.0), 6),
        "reason": str(item.reason or ""),
        "source": str(item.source or ""),
        "created_at": item.created_at.isoformat(),
    }
    return stable_text_digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str), hex_chars=16)


def _build_active_item_map(items: Iterable[MemoryItem]) -> dict[tuple[str, str], MemoryItem]:
    return {
        (item.category, item.key): item
        for item in items
        if not str(item.category or "").startswith(ARCHIVE_CATEGORY_PREFIX)
    }


def _build_semantic_sync_plan(
    *,
    previous_items: list[MemoryItem],
    restored_items: list[MemoryItem],
) -> tuple[list[tuple[str, str]], list[MemoryItem]]:
    previous_active = _build_active_item_map(previous_items)
    restored_active = _build_active_item_map(restored_items)

    delete_refs = sorted(previous_active.keys() - restored_active.keys())
    upsert_items: list[MemoryItem] = []
    for ref, item in restored_active.items():
        previous_item = previous_active.get(ref)
        if previous_item is None or _semantic_item_signature(previous_item) != _semantic_item_signature(item):
            upsert_items.append(item)
    return delete_refs, upsert_items


def _record_memory_curation_progress(
    event_type: str,
    *,
    snapshot_id: str,
    stage: str,
    processed: int,
    total: int,
    chunk_size: int,
) -> None:
    try:
        record_autonomy_observation(
            event_type,
            {
                "snapshot_id": snapshot_id,
                "stage": stage,
                "processed": processed,
                "total": total,
                "chunk_size": chunk_size,
            },
        )
    except Exception:
        pass


def _memory_curation_runtime_state(queue) -> dict[str, Any]:
    if queue is None or not hasattr(queue, "get_policy_runtime_state"):
        return {}
    state = queue.get_policy_runtime_state(_AUTONOMY_STATE_KEY) or {}
    return dict(state)


def _set_memory_curation_runtime_state(queue, state_value: str, *, metadata_update: dict[str, Any], observed_at: str | None = None) -> dict[str, Any]:
    if queue is None or not hasattr(queue, "set_policy_runtime_state"):
        return {}
    return queue.set_policy_runtime_state(
        _AUTONOMY_STATE_KEY,
        state_value,
        metadata_update=metadata_update,
        observed_at=observed_at,
    )


def get_memory_curation_autonomy_settings() -> dict[str, Any]:
    enabled = _env_bool("AUTONOMY_MEMORY_CURATION_ENABLED", False) and not _env_bool("AUTONOMY_COMPAT_MODE", True)
    return {
        "enabled": enabled,
        "interval_heartbeats": max(1, _normalize_int(os.getenv("AUTONOMY_MEMORY_CURATION_INTERVAL_HEARTBEATS"), default=12)),
        "stale_days": max(7, _normalize_int(os.getenv("AUTONOMY_MEMORY_CURATION_STALE_DAYS"), default=30)),
        "candidate_limit": max(1, _normalize_int(os.getenv("AUTONOMY_MEMORY_CURATION_CANDIDATE_LIMIT"), default=5)),
        "max_actions": max(1, _normalize_int(os.getenv("AUTONOMY_MEMORY_CURATION_MAX_ACTIONS"), default=1)),
        "cooldown_minutes": max(0, _normalize_int(os.getenv("AUTONOMY_MEMORY_CURATION_COOLDOWN_MINUTES"), default=180)),
        "rollback_cooldown_minutes": max(0, _normalize_int(os.getenv("AUTONOMY_MEMORY_CURATION_ROLLBACK_COOLDOWN_MINUTES"), default=720)),
        "verification_failure_cooldown_minutes": max(0, _normalize_int(os.getenv("AUTONOMY_MEMORY_CURATION_VERIFICATION_FAILURE_COOLDOWN_MINUTES"), default=720)),
        "require_semantic_store": _env_bool("AUTONOMY_MEMORY_CURATION_REQUIRE_SEMANTIC_STORE", True),
        "allowed_categories": _env_csv("AUTONOMY_MEMORY_CURATION_ALLOWED_CATEGORIES", _DEFAULT_AUTONOMY_ALLOWED_CATEGORIES),
        "allowed_actions": _env_csv("AUTONOMY_MEMORY_CURATION_ALLOWED_ACTIONS", _DEFAULT_AUTONOMY_ALLOWED_ACTIONS),
        "retrieval_backpressure_enabled": _env_bool("AUTONOMY_MEMORY_CURATION_RETRIEVAL_BACKPRESSURE_ENABLED", True),
        "retrieval_backpressure_lookback_runs": max(
            1,
            _normalize_int(
                os.getenv("AUTONOMY_MEMORY_CURATION_RETRIEVAL_BACKPRESSURE_LOOKBACK_RUNS"),
                default=_DEFAULT_RETRIEVAL_BACKPRESSURE_LOOKBACK_RUNS,
            ),
        ),
        "retrieval_backpressure_min_evaluated_runs": max(
            1,
            _normalize_int(
                os.getenv("AUTONOMY_MEMORY_CURATION_RETRIEVAL_BACKPRESSURE_MIN_EVALUATED_RUNS"),
                default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MIN_EVALUATED_RUNS,
            ),
        ),
        "retrieval_backpressure_min_pass_rate": _normalize_ratio(
            os.getenv("AUTONOMY_MEMORY_CURATION_RETRIEVAL_BACKPRESSURE_MIN_PASS_RATE"),
            default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MIN_PASS_RATE,
        ),
        "retrieval_backpressure_max_failed_runs": max(
            0,
            _normalize_int(
                os.getenv("AUTONOMY_MEMORY_CURATION_RETRIEVAL_BACKPRESSURE_MAX_FAILED_RUNS"),
                default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MAX_FAILED_RUNS,
            ),
        ),
        "retrieval_backpressure_max_rolled_back_runs": max(
            0,
            _normalize_int(
                os.getenv("AUTONOMY_MEMORY_CURATION_RETRIEVAL_BACKPRESSURE_MAX_ROLLED_BACK_RUNS"),
                default=_DEFAULT_RETRIEVAL_BACKPRESSURE_MAX_ROLLED_BACK_RUNS,
            ),
        ),
    }


def build_memory_curation_autonomy_governance(
    *,
    queue=None,
    manager: MemoryCurationManagerLike | None = None,
    heartbeat_count: int | None = None,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    queue_state = _memory_curation_runtime_state(queue)
    current = _now()
    settings_payload = dict(settings or get_memory_curation_autonomy_settings())
    recent_snapshots = list(
        active_manager.persistent.list_memory_curation_snapshots(
            limit=max(
                5,
                int(settings_payload.get("retrieval_backpressure_lookback_runs") or _DEFAULT_RETRIEVAL_BACKPRESSURE_LOOKBACK_RUNS),
            ),
        )
    )
    latest_snapshot = next(iter(recent_snapshots), None)
    retrieval_backpressure = build_memory_curation_retrieval_backpressure_governance(
        recent_snapshots,
        settings=settings_payload,
    )
    candidate_limit = int(settings_payload.get("candidate_limit") or 5)
    raw_candidates = build_memory_curation_candidates(
        manager=active_manager,
        stale_days=int(settings_payload.get("stale_days") or 30),
        max_candidates=max(candidate_limit * 3, candidate_limit),
        now=current,
    )
    filtered_candidates = filter_memory_curation_candidates(
        raw_candidates,
        allowed_actions=settings_payload.get("allowed_actions"),
        allowed_categories=settings_payload.get("allowed_categories"),
        limit=candidate_limit,
    )

    state = "allow"
    blocked = False
    reasons: list[str] = []
    cooldown_until = ""

    if not bool(settings_payload.get("enabled")):
        state = "disabled"
        blocked = True
        reasons.append("feature_disabled")
    elif heartbeat_count is not None and heartbeat_count > 0:
        interval = max(1, int(settings_payload.get("interval_heartbeats") or 1))
        if heartbeat_count % interval != 0:
            state = "cadence_skip"
            blocked = True
            reasons.append(f"heartbeat:{heartbeat_count}/{interval}")

    semantic_store = getattr(active_manager, "semantic_store", None)
    semantic_available = bool(semantic_store and hasattr(semantic_store, "is_available") and semantic_store.is_available())
    if not blocked and bool(settings_payload.get("require_semantic_store")) and not semantic_available:
        state = "storage_degraded"
        blocked = True
        reasons.append("semantic_store_unavailable")

    latest_status = str((latest_snapshot or {}).get("status") or "").strip().lower()
    if not blocked and latest_status in {"started", "rolling_back"}:
        state = "memory_curation_busy"
        blocked = True
        reasons.append(f"latest_snapshot_status:{latest_status}")

    degrade_state = queue.get_self_healing_runtime_state("degrade_mode") if queue and hasattr(queue, "get_self_healing_runtime_state") else None
    degrade_value = str((degrade_state or {}).get("state_value") or "normal").strip().lower()
    if not blocked and degrade_value in {"degraded", "emergency"}:
        state = "runtime_degraded"
        blocked = True
        reasons.append(f"degrade_mode={degrade_value}")

    if not blocked and latest_snapshot:
        snapshot_status = str(latest_snapshot.get("status") or "").strip().lower()
        updated_at = str(latest_snapshot.get("updated_at") or latest_snapshot.get("created_at") or "")
        if snapshot_status == "rolled_back":
            active, until = _cooldown_active(
                updated_at,
                now=current,
                minutes=int(settings_payload.get("rollback_cooldown_minutes") or 0),
            )
            if active:
                state = "rollback_cooldown"
                blocked = True
                reasons.append("recent_rollback")
                cooldown_until = until
        elif snapshot_status == "verification_failed":
            active, until = _cooldown_active(
                updated_at,
                now=current,
                minutes=int(settings_payload.get("verification_failure_cooldown_minutes") or 0),
            )
            if active:
                state = "verification_failure_cooldown"
                blocked = True
                reasons.append("recent_verification_failure")
                cooldown_until = until
        if not blocked and snapshot_status in {"completed", "rolled_back", "verification_failed"}:
            active, until = _cooldown_active(
                updated_at,
                now=current,
                minutes=int(settings_payload.get("cooldown_minutes") or 0),
            )
            if active:
                state = "cooldown_active"
                blocked = True
                reasons.append("recent_memory_curation_run")
                cooldown_until = until

    if not blocked and bool(retrieval_backpressure.get("blocked")):
        state = str(retrieval_backpressure.get("state") or "retrieval_backpressure")
        blocked = True
        reasons.extend(list(retrieval_backpressure.get("reasons") or []))

    if not blocked and not filtered_candidates:
        state = "no_candidates"
        blocked = True
        reasons.append("no_allowed_candidates")

    return {
        "state": state,
        "blocked": blocked,
        "reasons": reasons,
        "cooldown_until": cooldown_until,
        "heartbeat_count": int(heartbeat_count or 0),
        "settings": settings_payload,
        "semantic_store_available": semantic_available,
        "degrade_mode": degrade_value,
        "runtime_state": queue_state,
        "latest_snapshot": latest_snapshot or {},
        "retrieval_backpressure": retrieval_backpressure,
        "raw_candidate_count": len(raw_candidates),
        "filtered_candidate_count": len(filtered_candidates),
        "filtered_candidates": filtered_candidates,
    }


async def run_memory_curation_autonomy_cycle(
    *,
    queue=None,
    manager: MemoryCurationManagerLike | None = None,
    heartbeat_count: int = 0,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    settings = get_memory_curation_autonomy_settings()
    governance = build_memory_curation_autonomy_governance(
        queue=queue,
        manager=active_manager,
        heartbeat_count=heartbeat_count,
        settings=settings,
    )
    latest_snapshot = dict(governance.get("latest_snapshot") or {})
    filtered_candidates = list(governance.get("filtered_candidates") or [])
    runtime_state = dict(governance.get("runtime_state") or {})
    now_iso = _now().isoformat()

    if governance.get("blocked"):
        _set_memory_curation_runtime_state(
            queue,
            str(governance.get("state") or "blocked"),
            metadata_update={
                "last_guard_state": governance.get("state", ""),
                "last_guard_reasons": list(governance.get("reasons") or []),
                "last_snapshot_id": latest_snapshot.get("snapshot_id", ""),
                "last_snapshot_status": latest_snapshot.get("status", ""),
                "last_candidate_count": int(governance.get("filtered_candidate_count") or 0),
                "cooldown_until": governance.get("cooldown_until", ""),
                "last_heartbeat_count": int(heartbeat_count or 0),
            },
            observed_at=now_iso,
        )
        previous_state = str(runtime_state.get("state_value") or "").strip().lower()
        current_state = str(governance.get("state") or "").strip().lower()
        should_emit_blocked = current_state not in {"disabled", "cadence_skip", "no_candidates"} and current_state != previous_state
        if should_emit_blocked:
            try:
                record_autonomy_observation(
                    "memory_curation_autonomy_blocked",
                    {
                        "state": governance.get("state", ""),
                        "reasons": list(governance.get("reasons") or []),
                        "snapshot_id": latest_snapshot.get("snapshot_id", ""),
                        "candidate_count": int(governance.get("filtered_candidate_count") or 0),
                    },
                )
            except Exception:
                pass
        return {
            "status": "blocked",
            "state": governance.get("state", ""),
            "reasons": list(governance.get("reasons") or []),
            "candidate_count": int(governance.get("filtered_candidate_count") or 0),
            "cooldown_until": governance.get("cooldown_until", ""),
        }

    try:
        record_autonomy_observation(
            "memory_curation_autonomy_started",
            {
                "candidate_count": int(governance.get("filtered_candidate_count") or 0),
                "heartbeat_count": int(heartbeat_count or 0),
                "max_actions": int(settings.get("max_actions") or 1),
            },
        )
    except Exception:
        pass

    result = await asyncio.to_thread(
        run_memory_curation_mvp,
        manager=active_manager,
        stale_days=int(settings.get("stale_days") or 30),
        max_actions=int(settings.get("max_actions") or 1),
        dry_run=False,
        allowed_actions=settings.get("allowed_actions"),
        allowed_categories=settings.get("allowed_categories"),
    )

    state_value = str(result.get("status") or "completed")
    _set_memory_curation_runtime_state(
        queue,
        state_value,
        metadata_update={
            "last_guard_state": "allow",
            "last_guard_reasons": [],
            "last_snapshot_id": result.get("snapshot_id", ""),
            "last_snapshot_status": result.get("status", ""),
            "last_candidate_count": int(result.get("candidate_count") or 0),
            "last_action_count": len(result.get("actions_applied") or []),
            "last_heartbeat_count": int(heartbeat_count or 0),
            "cooldown_until": "",
        },
        observed_at=now_iso,
    )
    try:
        record_autonomy_observation(
            "memory_curation_autonomy_completed",
            {
                "status": state_value,
                "snapshot_id": result.get("snapshot_id", ""),
                "candidate_count": int(result.get("candidate_count") or 0),
                "action_count": len(result.get("actions_applied") or []),
                "verification_passed": bool((result.get("verification") or {}).get("passed")),
            },
        )
    except Exception:
        pass
    return {
        "status": state_value,
        "snapshot_id": result.get("snapshot_id", ""),
        "candidate_count": int(result.get("candidate_count") or 0),
        "action_count": len(result.get("actions_applied") or []),
        "verification": dict(result.get("verification") or {}),
        "actions_applied": list(result.get("actions_applied") or []),
    }


def _sync_semantic_store_diff(
    manager: MemoryCurationManagerLike,
    *,
    previous_items: list[MemoryItem],
    restored_items: list[MemoryItem],
    snapshot_id: str,
    chunk_size: int = _ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE,
) -> dict[str, int]:
    semantic_store = getattr(manager, "semantic_store", None)
    if not semantic_store or not hasattr(semantic_store, "is_available") or not semantic_store.is_available():
        return {"delete_count": 0, "upsert_count": 0, "chunk_count": 0}

    delete_refs, upsert_items = _build_semantic_sync_plan(
        previous_items=previous_items,
        restored_items=restored_items,
    )
    safe_chunk_size = max(1, _normalize_int(chunk_size, default=_ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE))
    total_operations = len(delete_refs) + len(upsert_items)
    processed = 0
    chunk_count = 0

    if total_operations:
        _record_memory_curation_progress(
            "memory_curation_rollback_progress",
            snapshot_id=snapshot_id,
            stage="semantic_sync_started",
            processed=0,
            total=total_operations,
            chunk_size=safe_chunk_size,
        )

    for chunk in _iter_chunks(delete_refs, safe_chunk_size):
        for category, key in chunk:
            semantic_store.delete_embedding(category, key)
        processed += len(chunk)
        chunk_count += 1
        _record_memory_curation_progress(
            "memory_curation_rollback_progress",
            snapshot_id=snapshot_id,
            stage="semantic_delete",
            processed=processed,
            total=total_operations,
            chunk_size=safe_chunk_size,
        )

    for chunk in _iter_chunks(upsert_items, safe_chunk_size):
        for item in chunk:
            semantic_store.store_embedding(item)
        processed += len(chunk)
        chunk_count += 1
        _record_memory_curation_progress(
            "memory_curation_rollback_progress",
            snapshot_id=snapshot_id,
            stage="semantic_upsert",
            processed=processed,
            total=total_operations,
            chunk_size=safe_chunk_size,
        )

    if total_operations:
        _record_memory_curation_progress(
            "memory_curation_rollback_progress",
            snapshot_id=snapshot_id,
            stage="semantic_sync_completed",
            processed=processed,
            total=total_operations,
            chunk_size=safe_chunk_size,
        )
    return {
        "delete_count": len(delete_refs),
        "upsert_count": len(upsert_items),
        "chunk_count": chunk_count,
    }


def get_memory_curation_status(
    *,
    manager: MemoryCurationManagerLike | None = None,
    queue=None,
    stale_days: int = 30,
    limit: int = 5,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    items = active_manager.persistent.get_all_memory_items()
    pending_candidates = build_memory_curation_candidates(
        manager=active_manager,
        stale_days=stale_days,
        max_candidates=limit,
    )
    pending_retrieval_probes = build_memory_curation_retrieval_probes(
        items=items,
        candidates=pending_candidates,
        max_probes=max(1, limit * 2),
    )
    last_snapshots = active_manager.persistent.list_memory_curation_snapshots(limit=limit)
    latest_snapshot = next(iter(last_snapshots), {})
    runtime_queue = queue
    if runtime_queue is None:
        try:
            from orchestration.task_queue import get_queue
            runtime_queue = get_queue()
        except Exception:
            runtime_queue = None
    return {
        "status": "ok",
        "current_metrics": build_memory_curation_metrics(
            items,
            manager=active_manager,
            stale_days=stale_days,
        ),
        "last_snapshots": last_snapshots,
        "latest_retrieval_quality": dict((latest_snapshot.get("metadata") or {}).get("retrieval_quality") or {}),
        "pending_candidates": pending_candidates,
        "pending_retrieval_probes": pending_retrieval_probes,
        "autonomy_settings": get_memory_curation_autonomy_settings(),
        "autonomy_governance": build_memory_curation_autonomy_governance(
            queue=runtime_queue,
            manager=active_manager,
        ),
        "quality_governance": build_memory_curation_retrieval_backpressure_governance(
            last_snapshots,
            settings=get_memory_curation_autonomy_settings(),
        ),
    }


def run_memory_curation_mvp(
    *,
    manager: MemoryCurationManagerLike | None = None,
    stale_days: int = 30,
    max_actions: int = 12,
    dry_run: bool = False,
    allowed_actions: Iterable[str] | None = None,
    allowed_categories: Iterable[str] | None = None,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    current = _now()
    safe_stale_days = max(1, _normalize_int(stale_days, default=30))
    safe_max_actions = max(1, _normalize_int(max_actions, default=12))

    before_items = active_manager.persistent.get_all_memory_items()
    metrics_before = build_memory_curation_metrics(
        before_items,
        manager=active_manager,
        stale_days=safe_stale_days,
        now=current,
    )
    candidates = build_memory_curation_candidates(
        manager=active_manager,
        stale_days=safe_stale_days,
        max_candidates=safe_max_actions,
        now=current,
    )
    candidates = filter_memory_curation_candidates(
        candidates,
        allowed_actions=allowed_actions,
        allowed_categories=allowed_categories,
        limit=safe_max_actions,
    )
    retrieval_probes = build_memory_curation_retrieval_probes(
        items=before_items,
        candidates=candidates,
        max_probes=max(1, safe_max_actions * 2),
    )
    retrieval_before = evaluate_memory_curation_retrieval_probes(
        manager=active_manager,
        probes=retrieval_probes,
    )

    if dry_run or not candidates:
        return {
            "status": "dry_run" if dry_run else "no_candidates",
            "dry_run": bool(dry_run),
            "snapshot_id": "",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "metrics_before": metrics_before,
            "metrics_after": metrics_before,
            "retrieval_quality": {
                "before": retrieval_before,
                "after": retrieval_before,
                "verdict": {
                    "passed": True,
                    "reason": "no_mutation",
                    "probe_count": int(retrieval_before.get("probe_count") or 0),
                    "avg_score_delta": 0.0,
                    "hit_rate_at_3_delta": 0.0,
                    "useful_rate_delta": 0.0,
                    "wrong_top1_increase": 0.0,
                    "forbidden_top1_increase": 0.0,
                },
            },
            "verification": {
                "passed": True,
                "reason": "no_mutation",
            },
            "actions_applied": [],
        }

    snapshot_id = uuid.uuid4().hex[:12]
    active_manager.persistent.store_memory_curation_snapshot(
        snapshot_id=snapshot_id,
        status="started",
        before_items=before_items,
        metrics_before=metrics_before,
        metadata={
            "stale_days": safe_stale_days,
            "max_actions": safe_max_actions,
            "candidate_count": len(candidates),
            "retrieval_probe_count": int(retrieval_before.get("probe_count") or 0),
        },
    )
    try:
        record_autonomy_observation(
            "memory_curation_started",
            {
                "snapshot_id": snapshot_id,
                "candidate_count": len(candidates),
                "stale_days": safe_stale_days,
                "max_actions": safe_max_actions,
            },
        )
    except Exception:
        pass

    actions_applied: list[dict[str, Any]] = []
    items_by_ref = {(item.category, item.key): item for item in before_items}

    for candidate in candidates[:safe_max_actions]:
        action = str(candidate.get("action") or "")
        keys = [str(key) for key in (candidate.get("item_keys") or []) if str(key)]
        category = str(candidate.get("category") or "")
        source = str(candidate.get("source") or "")
        reason = str(candidate.get("reason") or "")
        if action == "summarize":
            grouped_items = [
                items_by_ref[(category, key)]
                for key in keys
                if (category, key) in items_by_ref
            ]
            if len(grouped_items) < 2:
                continue
            summary_item = _build_summary_item(grouped_items, category=category, source=source, now=current)
            _store_active_item(active_manager, summary_item)
            for item in grouped_items:
                _archive_item(active_manager, item, archived_at=current, reason=reason)
            actions_applied.append(
                {
                    "action": "summarize",
                    "summary_key": summary_item.key,
                    "source_category": category,
                    "source_keys": keys,
                    "archived_count": len(grouped_items),
                }
            )
            try:
                record_autonomy_observation(
                    "memory_summarized",
                    {
                        "snapshot_id": snapshot_id,
                        "summary_key": summary_item.key,
                        "source_category": category,
                        "source_count": len(grouped_items),
                    },
                )
            except Exception:
                pass
        elif action == "archive" and len(keys) == 1:
            item = items_by_ref.get((category, keys[0]))
            if not item:
                continue
            archived_item = _archive_item(active_manager, item, archived_at=current, reason=reason)
            actions_applied.append(
                {
                    "action": "archive",
                    "archived_key": archived_item.key,
                    "source_category": category,
                }
            )
            try:
                record_autonomy_observation(
                    "memory_archived",
                    {
                        "snapshot_id": snapshot_id,
                        "archived_category": archived_item.category,
                        "archived_key": archived_item.key,
                        "source_category": category,
                    },
                )
            except Exception:
                pass
        elif action == "devalue" and len(keys) == 1:
            item = items_by_ref.get((category, keys[0]))
            if not item:
                continue
            devalued = _apply_devalue_item(active_manager, item, reason=reason)
            actions_applied.append(
                {
                    "action": "devalue",
                    "key": devalued.key,
                    "category": devalued.category,
                    "importance": devalued.importance,
                    "confidence": devalued.confidence,
                }
            )
            try:
                record_autonomy_observation(
                    "memory_devalued",
                    {
                        "snapshot_id": snapshot_id,
                        "category": devalued.category,
                        "key": devalued.key,
                        "importance": devalued.importance,
                        "confidence": devalued.confidence,
                    },
                )
            except Exception:
                pass

    after_items = active_manager.persistent.get_all_memory_items()
    metrics_after = build_memory_curation_metrics(
        after_items,
        manager=active_manager,
        stale_days=safe_stale_days,
        now=current,
    )
    metrics_gate_passed = verify_memory_curation_outcome(
        before_active_items=int(metrics_before.get("active_items") or 0),
        after_active_items=int(metrics_after.get("active_items") or 0),
        before_stale_active_items=int(metrics_before.get("stale_active_items") or 0),
        after_stale_active_items=int(metrics_after.get("stale_active_items") or 0),
        before_stable_items=int(metrics_before.get("stable_active_items") or 0),
        after_stable_items=int(metrics_after.get("stable_active_items") or 0),
    )
    retrieval_after = evaluate_memory_curation_retrieval_probes(
        manager=active_manager,
        probes=retrieval_probes,
    )
    retrieval_verdict = build_memory_curation_retrieval_quality_verdict(
        before_summary=retrieval_before,
        after_summary=retrieval_after,
    )
    verification_passed = metrics_gate_passed and bool(retrieval_verdict.get("passed"))
    verification = {
        "passed": verification_passed,
        "reason": (
            "metrics_and_retrieval_stable"
            if verification_passed
            else (
                "retrieval_quality_regression"
                if not retrieval_verdict.get("passed")
                else "stale_or_stable_regression"
            )
        ),
        "metrics_gate_passed": metrics_gate_passed,
        "retrieval_gate_passed": bool(retrieval_verdict.get("passed")),
        "rollback_recommended": not verification_passed,
    }
    retrieval_quality = {
        "before": retrieval_before,
        "after": retrieval_after,
        "verdict": retrieval_verdict,
    }
    try:
        record_autonomy_observation(
            "memory_curation_retrieval_quality",
            {
                "snapshot_id": snapshot_id,
                "probe_count": int(retrieval_verdict.get("probe_count") or 0),
                "passed": bool(retrieval_verdict.get("passed")),
                "avg_score_delta": float(retrieval_verdict.get("avg_score_delta") or 0.0),
                "hit_rate_at_3_delta": float(retrieval_verdict.get("hit_rate_at_3_delta") or 0.0),
                "useful_rate_delta": float(retrieval_verdict.get("useful_rate_delta") or 0.0),
                "wrong_top1_increase": float(retrieval_verdict.get("wrong_top1_increase") or 0.0),
            },
        )
    except Exception:
        pass

    active_manager.persistent.store_memory_curation_snapshot(
        snapshot_id=snapshot_id,
        status="completed" if verification_passed else "verification_failed",
        before_items=before_items,
        metrics_before=metrics_before,
        metadata={
            "stale_days": safe_stale_days,
            "max_actions": safe_max_actions,
            "candidate_count": len(candidates),
            "actions_applied": actions_applied,
            "retrieval_quality": retrieval_quality,
            "verification": verification,
        },
        after_items=after_items,
        metrics_after=metrics_after,
    )
    rollback_result: dict[str, Any] = {}
    final_status = "complete"
    final_metrics_after = metrics_after
    if not verification_passed:
        rollback_result = rollback_memory_curation(snapshot_id, manager=active_manager)
        if rollback_result.get("status") == "rolled_back":
            final_status = "rolled_back"
            final_metrics_after = dict(rollback_result.get("metrics_after") or metrics_after)
            verification["rollback_performed"] = True
            verification["rollback_snapshot_status"] = "rolled_back"
        else:
            final_status = "verification_failed"
            verification["rollback_performed"] = False
            verification["rollback_snapshot_status"] = str(rollback_result.get("status") or "")
    try:
        record_autonomy_observation(
            "memory_curation_completed",
            {
                "snapshot_id": snapshot_id,
                "actions_applied": len(actions_applied),
                "verification_passed": verification_passed,
                "final_status": final_status,
            },
        )
    except Exception:
        pass

    return {
        "status": final_status,
        "dry_run": False,
        "snapshot_id": snapshot_id,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "actions_applied": actions_applied,
        "metrics_before": metrics_before,
        "metrics_after": final_metrics_after,
        "metrics_after_mutation": metrics_after,
        "retrieval_quality": retrieval_quality,
        "verification": verification,
        "rollback": rollback_result,
    }


def rollback_memory_curation(
    snapshot_id: str,
    *,
    manager: MemoryCurationManagerLike | None = None,
) -> dict[str, Any]:
    active_manager = _manager(manager)
    snapshot = active_manager.persistent.get_memory_curation_snapshot(snapshot_id)
    if not snapshot:
        return {
            "status": "missing_snapshot",
            "snapshot_id": snapshot_id,
        }

    before_items = list(snapshot.get("before_items") or [])
    current_items = active_manager.persistent.get_all_memory_items()
    current_metrics = build_memory_curation_metrics(
        current_items,
        manager=active_manager,
        stale_days=int((snapshot.get("metrics_before") or {}).get("stale_days") or 30),
    )
    active_manager.persistent.store_memory_curation_snapshot(
        snapshot_id=snapshot_id,
        status="rolling_back",
        before_items=before_items,
        metrics_before=dict(snapshot.get("metrics_before") or {}),
        metadata={
            **dict(snapshot.get("metadata") or {}),
            "rollback_started_at": _now().isoformat(),
        },
        after_items=current_items,
        metrics_after=current_metrics,
    )
    _record_memory_curation_progress(
        "memory_curation_rollback_started",
        snapshot_id=snapshot_id,
        stage="rollback_started",
        processed=0,
        total=max(1, len(current_items)),
        chunk_size=_ROLLBACK_SEMANTIC_SYNC_CHUNK_SIZE,
    )
    active_manager.persistent.replace_all_memory_items(before_items)
    semantic_sync = _sync_semantic_store_diff(
        active_manager,
        previous_items=current_items,
        restored_items=before_items,
        snapshot_id=snapshot_id,
    )

    metrics_after = build_memory_curation_metrics(
        before_items,
        manager=active_manager,
        stale_days=int((snapshot.get("metrics_before") or {}).get("stale_days") or 30),
    )
    active_manager.persistent.store_memory_curation_snapshot(
        snapshot_id=snapshot_id,
        status="rolled_back",
        before_items=before_items,
        metrics_before=dict(snapshot.get("metrics_before") or {}),
        metadata={
            **dict(snapshot.get("metadata") or {}),
            "rollback_started_at": dict(snapshot.get("metadata") or {}).get("rollback_started_at", ""),
            "semantic_sync": semantic_sync,
        },
        after_items=current_items,
        metrics_after=metrics_after,
    )
    try:
        record_autonomy_observation(
            "memory_curation_rollback",
            {
                "snapshot_id": snapshot_id,
                "restored_items": len(before_items),
                "semantic_sync": semantic_sync,
            },
        )
    except Exception:
        pass
    return {
        "status": "rolled_back",
        "snapshot_id": snapshot_id,
        "restored_items": len(before_items),
        "metrics_after": metrics_after,
        "semantic_sync": semantic_sync,
    }
