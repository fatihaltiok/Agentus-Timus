"""Advisory adaptive planner for goal-first orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class AdaptivePlanCandidate:
    chain: Tuple[str, ...]
    score: float
    reason: str
    recipe_hint: str | None
    learned_bias: float = 0.0
    learned_evidence: int = 0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["chain"] = list(self.chain)
        payload["score"] = round(float(self.score), 2)
        payload["learned_bias"] = round(float(self.learned_bias), 2)
        return payload


def _dedupe_chain(chain: Iterable[str]) -> Tuple[str, ...]:
    cleaned: List[str] = []
    for item in chain:
        agent = str(item or "").strip().lower()
        if agent and agent not in cleaned:
            cleaned.append(agent)
    return tuple(cleaned)


def _maybe_prefix_meta(chain: Sequence[str]) -> Tuple[str, ...]:
    normalized = _dedupe_chain(chain)
    if not normalized:
        return ("meta",)
    if normalized[0] == "meta":
        return normalized
    return ("meta",) + normalized


def _derive_recipe_hint(
    chain: Sequence[str],
    goal_spec: Dict[str, Any],
    classification: Dict[str, Any],
) -> str | None:
    normalized = tuple(chain)
    task_type = str(classification.get("task_type") or "").strip().lower()
    output_mode = str(goal_spec.get("output_mode") or "").strip().lower()
    freshness = str(goal_spec.get("freshness") or "").strip().lower()
    current_hint = str(classification.get("recommended_recipe_id") or "").strip() or None
    if normalized == ("meta", "executor", "document") and freshness == "live" and output_mode in {"artifact", "table"}:
        return "simple_live_lookup_document"
    if normalized == ("meta", "executor") and freshness == "live":
        return "simple_live_lookup"
    if "research" in normalized and task_type == "knowledge_research":
        return current_hint or "knowledge_research"
    return current_hint


def _normalize_learned_chain_stats(
    learned_chain_stats: Sequence[Mapping[str, Any]] | None,
) -> Dict[Tuple[str, ...], Dict[str, Any]]:
    normalized: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for item in learned_chain_stats or []:
        chain = _dedupe_chain(item.get("chain") or [])
        if not chain:
            continue
        normalized[chain] = {
            "learned_bias": float(item.get("learned_bias") or 0.0),
            "evidence_count": max(0, int(item.get("evidence_count") or 0)),
            "learned_confidence": float(item.get("learned_confidence") or 0.0),
        }
    return normalized


def _learned_chain_adjustment(
    chain: Sequence[str],
    learned_chain_stats: Mapping[Tuple[str, ...], Mapping[str, Any]],
) -> Tuple[float, int]:
    learned = learned_chain_stats.get(tuple(chain))
    if not learned:
        return 0.0, 0
    evidence = max(0, int(learned.get("evidence_count") or 0))
    bias = max(-0.25, min(0.25, float(learned.get("learned_bias") or 0.0)))
    confidence = max(0.0, min(1.0, float(learned.get("learned_confidence") or 0.0)))
    return bias * confidence, evidence


def _score_chain(
    chain: Sequence[str],
    goal_spec: Dict[str, Any],
    goal_gaps: Sequence[str],
    learned_chain_stats: Mapping[Tuple[str, ...], Mapping[str, Any]] | None = None,
) -> Tuple[float, float, int]:
    normalized = tuple(chain)
    score = 0.55
    if str(goal_spec.get("freshness") or "").strip().lower() == "live" and "executor" in normalized:
        score += 0.12
    if str(goal_spec.get("evidence_level") or "").strip().lower() in {"verified", "deep"} and any(
        agent in normalized for agent in ("research", "system")
    ):
        score += 0.12
    if str(goal_spec.get("output_mode") or "").strip().lower() in {"artifact", "table"} and "document" in normalized:
        score += 0.12
    if goal_spec.get("delivery_required") and "communication" in normalized:
        score += 0.08
    if goal_spec.get("uses_location") and "executor" in normalized:
        score += 0.08
    score -= 0.03 * max(len(normalized) - 3, 0)
    score += 0.04 * len([gap for gap in goal_gaps if _covers_gap(gap, normalized)])
    learned_adjustment, learned_evidence = _learned_chain_adjustment(normalized, learned_chain_stats or {})
    score += learned_adjustment
    return max(0.0, min(0.99, score)), learned_adjustment, learned_evidence


def _covers_gap(gap: str, chain: Sequence[str]) -> bool:
    normalized = tuple(chain)
    if gap in {"live_lookup_stage_missing", "location_context_stage_missing"}:
        return "executor" in normalized
    if gap in {"artifact_output_stage_missing", "structured_table_stage_missing"}:
        return "document" in normalized
    if gap == "delivery_stage_missing":
        return "communication" in normalized
    if gap == "verification_stage_missing":
        return any(agent in normalized for agent in ("research", "system"))
    return False


def _candidate_reason(
    current: Sequence[str],
    proposed: Sequence[str],
    goal_gaps: Sequence[str],
    *,
    learned_bias: float = 0.0,
    learned_evidence: int = 0,
) -> str:
    if (
        tuple(current) != tuple(proposed)
        and learned_bias >= 0.05
        and learned_evidence >= 2
    ):
        return "learned_chain_preference"
    if tuple(current) == tuple(proposed):
        return "current_chain_satisfies_goal" if not goal_gaps else "current_chain_retained"
    if goal_gaps:
        return "goal_gap_extension"
    return "goal_first_alternative"


def build_adaptive_plan(
    goal_spec: Dict[str, Any],
    capability_graph: Dict[str, Any],
    classification: Dict[str, Any],
    *,
    learned_chain_stats: Sequence[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    current_chain = _maybe_prefix_meta(classification.get("recommended_agent_chain") or [])
    goal_gaps = list(capability_graph.get("goal_gaps") or [])
    learned_stats_by_chain = _normalize_learned_chain_stats(learned_chain_stats)
    candidates: List[Tuple[str, ...]] = [current_chain]

    if str(goal_spec.get("freshness") or "").strip().lower() == "live" and "executor" not in current_chain:
        candidates.append(_maybe_prefix_meta(list(current_chain) + ["executor"]))
    if str(goal_spec.get("evidence_level") or "").strip().lower() in {"verified", "deep"} and not any(
        agent in current_chain for agent in ("research", "system")
    ):
        candidates.append(_maybe_prefix_meta(list(current_chain) + ["research"]))
    if str(goal_spec.get("output_mode") or "").strip().lower() in {"artifact", "table"} and "document" not in current_chain:
        candidates.append(_maybe_prefix_meta(list(current_chain) + ["document"]))
    if goal_spec.get("delivery_required") and "communication" not in current_chain:
        candidates.append(_maybe_prefix_meta(list(current_chain) + ["communication"]))

    unique_candidates: List[Tuple[str, ...]] = []
    for chain in candidates:
        deduped = _dedupe_chain(chain)
        if deduped not in unique_candidates:
            unique_candidates.append(deduped)

    candidate_payloads: List[AdaptivePlanCandidate] = []
    for chain in unique_candidates:
        score, learned_bias, learned_evidence = _score_chain(
            chain,
            goal_spec,
            goal_gaps,
            learned_chain_stats=learned_stats_by_chain,
        )
        candidate_payloads.append(
            AdaptivePlanCandidate(
                chain=chain,
                score=score,
                reason=_candidate_reason(
                    current_chain,
                    chain,
                    goal_gaps,
                    learned_bias=learned_bias,
                    learned_evidence=learned_evidence,
                ),
                recipe_hint=_derive_recipe_hint(chain, goal_spec, classification),
                learned_bias=learned_bias,
                learned_evidence=learned_evidence,
            )
        )

    candidate_payloads.sort(key=lambda item: (-item.score, len(item.chain), item.chain))
    recommended = candidate_payloads[0]
    return {
        "planner_mode": "advisory",
        "advisory_only": True,
        "goal_signature": str(goal_spec.get("goal_signature") or ""),
        "current_chain": list(current_chain),
        "recommended_chain": list(recommended.chain),
        "recommended_recipe_hint": recommended.recipe_hint,
        "confidence": round(float(recommended.score), 2),
        "reason": recommended.reason,
        "goal_gaps": goal_gaps,
        "learned_chain_stats": list(learned_chain_stats or [])[:6],
        "candidate_chains": [item.to_dict() for item in candidate_payloads[:4]],
    }
