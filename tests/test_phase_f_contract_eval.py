from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_run_phase_f_contract_eval_reports_expected_contracts() -> None:
    from orchestration.phase_f_contract_eval import (
        PHASE_F_CONTRACT_REPORT_VERSION,
        run_phase_f_contract_eval,
    )

    report = run_phase_f_contract_eval()

    assert report["contract_version"] == PHASE_F_CONTRACT_REPORT_VERSION
    assert report["summary"]["state"] == "pass"
    assert report["summary"]["total"] == 4
    assert report["summary"]["passed"] == 4
    assert report["summary"]["failed"] == 0
    assert report["summary"]["failed_contracts"] == []
    assert {item["contract_id"] for item in report["results"]} == {
        "phase_d_approval_auth_workflow",
        "longrunner_user_visible_transport",
        "typed_handoff_and_preflight",
        "runtime_lane_operator_surface",
    }


def test_typed_handoff_contract_reports_blocked_preflight_under_pressure() -> None:
    from orchestration.phase_f_contract_eval import evaluate_typed_handoff_contract

    result = evaluate_typed_handoff_contract()

    assert result["passed"] is True
    assert result["reason"] == "ok"
    assert result["area"] == "handoff"
    assert result["evidence"]["request_chars"] >= 6000
    assert result["evidence"]["handoff_chars"] >= 5000
    assert "request_chars_hard_limit" in result["evidence"]["preflight_issues"]


def test_runtime_lane_contract_uses_phase_e_operator_surface() -> None:
    from orchestration.phase_f_contract_eval import evaluate_runtime_lane_contract

    result = evaluate_runtime_lane_contract()

    assert result["passed"] is True
    assert result["area"] == "runtime_lanes"
    assert result["evidence"]["governance_state"] == "strict_force_off"
    assert result["evidence"]["governance_action"] == "freeze"
    assert result["evidence"]["blocked_lanes"] == ["improvement", "memory_curation"]
    assert result["evidence"]["approval_pending_count"] == 1
