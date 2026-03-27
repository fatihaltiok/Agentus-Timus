"""Advisory capability graph for goal-first orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class CapabilityGraphNode:
    actor: str
    score: int
    matched_capabilities: Tuple[str, ...]
    matched_outputs: Tuple[str, ...]
    matched_strengths: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


@dataclass(frozen=True)
class CapabilityGraphEdge:
    source: str
    target: str
    reason: str
    advisory_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _needed_capabilities(goal_spec: Dict[str, Any], required_capabilities: Sequence[str]) -> List[str]:
    needed = [str(item).strip().lower() for item in required_capabilities if str(item).strip()]
    output_mode = str(goal_spec.get("output_mode") or "").strip().lower()
    evidence_level = str(goal_spec.get("evidence_level") or "").strip().lower()
    freshness = str(goal_spec.get("freshness") or "").strip().lower()
    if freshness == "live":
        _append_unique(needed, "live_lookup")
    if goal_spec.get("uses_location"):
        _append_unique(needed, "location_context")
    if output_mode in {"table", "artifact"}:
        _append_unique(needed, "structured_exports")
    if output_mode == "report":
        _append_unique(needed, "report_synthesis")
    if goal_spec.get("delivery_required"):
        _append_unique(needed, "message_delivery")
    if evidence_level in {"verified", "deep"}:
        _append_unique(needed, "source_research")
    return needed


def _agent_supports_need(profile: Dict[str, Any], need: str) -> bool:
    capabilities = {str(item).strip().lower() for item in profile.get("capabilities") or []}
    strengths = {str(item).strip().lower() for item in profile.get("strengths") or []}
    outputs = {str(item).strip().lower() for item in profile.get("typical_outputs") or []}
    if need in capabilities:
        return True
    alias_map = {
        "location_context": {"location_aware_lookup"},
        "local_maps_search": {"location_aware_lookup", "live_lookup"},
        "route_planning": {"location_aware_lookup", "live_lookup"},
        "structured_exports": {"structured_exports", "xlsx", "pdf", "docx"},
        "document_creation": {"pdf_creation", "docx_creation", "structured_exports", "xlsx", "pdf", "docx"},
        "report_synthesis": {"report_synthesis", "report", "summary"},
        "message_delivery": {"delivery", "message", "delivery_status"},
        "source_research": {"fact_verification", "content_extraction", "source_comparison"},
        "live_lookup": {"light_search", "fast_search_flows"},
        "light_search": {"light_search", "fast_search_flows"},
        "browser_navigation": {"browser_navigation", "ui_interaction", "multi_step_web_flows", "site_interaction"},
        "content_extraction": {"content_extraction", "summary", "report", "reports"},
        "diagnostics": {"diagnostics", "incident_triage", "health_analysis"},
        "terminal_execution": {"terminal_execution", "command_execution", "controlled_runtime_actions"},
    }
    aliases = alias_map.get(need, set())
    return bool(capabilities & aliases or strengths & aliases or outputs & aliases)


def _match_outputs(profile: Dict[str, Any], output_mode: str) -> Tuple[str, ...]:
    outputs = [str(item).strip().lower() for item in profile.get("typical_outputs") or []]
    matched: List[str] = []
    if output_mode == "table" and "xlsx" in outputs:
        matched.append("xlsx")
    if output_mode == "artifact":
        for item in ("pdf", "docx", "xlsx"):
            if item in outputs:
                matched.append(item)
    if output_mode in {"answer", "list"}:
        for item in ("quick_summary", "summary", "top_results", "source_urls"):
            if item in outputs:
                matched.append(item)
    if output_mode == "report":
        for item in ("report", "summary", "pdf", "docx"):
            if item in outputs:
                matched.append(item)
    if output_mode == "message":
        for item in ("message", "email_body", "delivery_status"):
            if item in outputs:
                matched.append(item)
    return tuple(matched)


def _match_strengths(profile: Dict[str, Any], goal_spec: Dict[str, Any]) -> Tuple[str, ...]:
    strengths = [str(item).strip().lower() for item in profile.get("strengths") or []]
    matched: List[str] = []
    freshness = str(goal_spec.get("freshness") or "").strip().lower()
    evidence_level = str(goal_spec.get("evidence_level") or "").strip().lower()
    uses_location = bool(goal_spec.get("uses_location"))
    if freshness == "live":
        for item in ("fast_search_flows", "casual_requests", "location_aware_lookup"):
            if item in strengths:
                matched.append(item)
    if evidence_level in {"verified", "deep"}:
        for item in ("source_comparison", "reports", "incident_triage"):
            if item in strengths:
                matched.append(item)
    if uses_location and "location_aware_lookup" in strengths:
        matched.append("location_aware_lookup")
    return tuple(dict.fromkeys(matched))


def _build_goal_gaps(goal_spec: Dict[str, Any], current_chain: Sequence[str], missing_capabilities: Sequence[str]) -> List[str]:
    chain = [str(item).strip().lower() for item in current_chain if str(item).strip()]
    gaps: List[str] = []
    output_mode = str(goal_spec.get("output_mode") or "").strip().lower()
    if str(goal_spec.get("freshness") or "").strip().lower() == "live" and "executor" not in chain:
        gaps.append("live_lookup_stage_missing")
    if goal_spec.get("uses_location") and "executor" not in chain:
        gaps.append("location_context_stage_missing")
    if output_mode == "artifact" and "document" not in chain:
        gaps.append("artifact_output_stage_missing")
    if output_mode == "table" and "document" not in chain and "structured_exports" in missing_capabilities:
        gaps.append("structured_table_stage_missing")
    if goal_spec.get("delivery_required") and "communication" not in chain:
        gaps.append("delivery_stage_missing")
    if str(goal_spec.get("evidence_level") or "").strip().lower() in {"verified", "deep"} and not any(
        agent in chain for agent in ("research", "system")
    ):
        gaps.append("verification_stage_missing")
    return gaps


def build_capability_graph(
    goal_spec: Dict[str, Any],
    agent_capability_map: Dict[str, Dict[str, Any]],
    *,
    current_chain: Sequence[str],
    required_capabilities: Sequence[str],
) -> Dict[str, Any]:
    needed_capabilities = _needed_capabilities(goal_spec, required_capabilities)
    current_chain_clean = [str(item).strip().lower() for item in current_chain if str(item).strip()]

    nodes: List[CapabilityGraphNode] = []
    covered_capabilities: List[str] = []
    for agent, profile in agent_capability_map.items():
        matched_caps = tuple(need for need in needed_capabilities if _agent_supports_need(profile, need))
        matched_outputs = _match_outputs(profile, str(goal_spec.get("output_mode") or "").strip().lower())
        matched_strengths = _match_strengths(profile, goal_spec)
        score = (len(matched_caps) * 3) + (len(matched_outputs) * 2) + len(matched_strengths)
        if score > 0 or agent in current_chain_clean:
            nodes.append(
                CapabilityGraphNode(
                    actor=agent,
                    score=score,
                    matched_capabilities=matched_caps,
                    matched_outputs=matched_outputs,
                    matched_strengths=matched_strengths,
                )
            )
        if agent in current_chain_clean:
            for need in matched_caps:
                _append_unique(covered_capabilities, need)

    missing_capabilities = [need for need in needed_capabilities if need not in covered_capabilities]
    goal_gaps = _build_goal_gaps(goal_spec, current_chain_clean, missing_capabilities)

    edges: List[CapabilityGraphEdge] = []
    for left, right in zip(current_chain_clean, current_chain_clean[1:]):
        edges.append(CapabilityGraphEdge(source=left, target=right, reason="current_chain"))
    if str(goal_spec.get("output_mode") or "").strip().lower() in {"artifact", "table"} and "document" not in current_chain_clean:
        source = "research" if "research" in current_chain_clean else "executor" if "executor" in current_chain_clean else "meta"
        edges.append(CapabilityGraphEdge(source=source, target="document", reason="structured_output_gap"))
    if goal_spec.get("delivery_required") and "communication" not in current_chain_clean:
        source = "document" if "document" in current_chain_clean else (current_chain_clean[-1] if current_chain_clean else "meta")
        edges.append(CapabilityGraphEdge(source=source, target="communication", reason="delivery_gap"))

    nodes_sorted = sorted(nodes, key=lambda item: (-item.score, item.actor))
    return {
        "goal_signature": str(goal_spec.get("goal_signature") or ""),
        "current_chain": current_chain_clean,
        "needed_capabilities": needed_capabilities,
        "covered_capabilities": covered_capabilities,
        "missing_capabilities": missing_capabilities,
        "goal_gaps": goal_gaps,
        "matching_nodes": [node.to_dict() for node in nodes_sorted[:6]],
        "suggested_edges": [edge.to_dict() for edge in edges[:6]],
    }
