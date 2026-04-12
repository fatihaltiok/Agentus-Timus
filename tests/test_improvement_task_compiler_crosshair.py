from __future__ import annotations

import deal

from orchestration.improvement_task_compiler import (
    _likely_root_cause,
    compile_improvement_task,
    compile_improvement_tasks,
)


_CATEGORIES = {"routing", "context", "policy", "runtime", "tool", "specialist", "memory", "ux_handoff"}
_TASK_KINDS = {"developer_task", "shell_task", "config_change_candidate", "test_gap", "verification_needed", "do_not_autofix"}
_EXECUTION_HINTS = {"developer_task", "observe_only", "human_only"}
_FRESHNESS_STATES = {"", "fresh", "aging", "stale"}
_ROLLBACK_RISKS = {"low", "medium", "high"}


@deal.post(lambda r: r is True)
def _contract_verified_dispatcher_path_maps_to_specific_root_cause() -> bool:
    return (
        _likely_root_cause(
            {
                "category": "routing",
                "verified_paths": ["main_dispatcher.py"],
            },
            set(),
        )
        == "dispatcher_routing_path_verified"
    )


@deal.post(lambda r: r is True)
def _contract_send_email_failed_maps_to_specific_root_cause() -> bool:
    return (
        _likely_root_cause(
            {
                "category": "runtime",
                "event_type": "send_email_failed",
                "components": ["communication"],
                "signals": ["smtp_error"],
            },
            {"email", "smtp"},
        )
        == "communication_backend_or_delivery_gap"
    )


@deal.post(lambda r: r is True)
def _contract_verified_paths_are_preferred_for_target_files() -> bool:
    compiled = compile_improvement_task(
        {
            "candidate_id": "crosshair:verified-paths",
            "category": "runtime",
            "problem": "MCP path regressed",
            "proposed_action": "Repair runtime path selection",
            "verified_paths": ["server/mcp_server.py"],
        }
    )
    return compiled["target_files"] == ["server/mcp_server.py"]


@deal.pre(lambda category, *_: category in _CATEGORIES)
@deal.pre(lambda _, __, ___, ____, source_count, freshness_state, _____: source_count >= 1 and freshness_state in _FRESHNESS_STATES)
@deal.post(lambda r: r in _TASK_KINDS)
def _contract_task_kind(
    category: str,
    target: str,
    problem: str,
    action: str,
    source_count: int,
    freshness_state: str,
    event_type: str,
) -> str:
    return compile_improvement_task(
        {
            "candidate_id": "crosshair:kind",
            "category": category,
            "target": target,
            "problem": problem,
            "proposed_action": action,
            "source_count": source_count,
            "freshness_state": freshness_state,
            "event_type": event_type,
        }
    )["task_kind"]


@deal.pre(lambda category, *_: category in _CATEGORIES)
@deal.post(lambda r: 0 <= r <= 4)
def _contract_target_file_count(
    category: str,
    target: str,
    problem: str,
    action: str,
) -> int:
    return len(
        compile_improvement_task(
            {
                "candidate_id": "crosshair:files",
                "category": category,
                "target": target,
                "problem": problem,
                "proposed_action": action,
            }
        )["target_files"]
    )


@deal.pre(lambda left, right: left >= 0.0 and right >= 0.0)
@deal.post(lambda r: r in {0, 1})
def _contract_priority_order(left: float, right: float) -> int:
    compiled = compile_improvement_tasks(
        [
            {"candidate_id": "left", "category": "runtime", "problem": "A", "proposed_action": "B", "priority_score": left},
            {"candidate_id": "right", "category": "runtime", "problem": "C", "proposed_action": "D", "priority_score": right},
        ]
    )
    return 1 if float(compiled[0].get("priority_score") or 0.0) >= float(compiled[1].get("priority_score") or 0.0) else 0


@deal.pre(lambda category, *_: category in _CATEGORIES)
@deal.post(lambda r: r in _EXECUTION_HINTS)
def _contract_execution_hint(category: str, problem: str, action: str) -> str:
    return compile_improvement_task(
        {
            "candidate_id": "crosshair:hint",
            "category": category,
            "problem": problem,
            "proposed_action": action,
        }
    )["execution_mode_hint"]


@deal.pre(lambda category, *_: category in _CATEGORIES)
@deal.post(lambda r: r in _ROLLBACK_RISKS)
def _contract_rollback_risk(category: str, problem: str, action: str) -> str:
    return compile_improvement_task(
        {
            "candidate_id": "crosshair:risk",
            "category": category,
            "problem": problem,
            "proposed_action": action,
        }
    )["rollback_risk"]
