import deal

from orchestration.self_modification_controller import evaluate_self_modification_controller


@deal.pre(
    lambda stability_gate_state,
    ops_gate_state,
    e2e_gate_state,
    strict_force_off,
    pending_approvals,
    rollback_count_recent,
    regression_count_recent,
    configured_max_per_cycle,
    max_pending_approvals: configured_max_per_cycle >= 1
)
@deal.pre(
    lambda stability_gate_state,
    ops_gate_state,
    e2e_gate_state,
    strict_force_off,
    pending_approvals,
    rollback_count_recent,
    regression_count_recent,
    configured_max_per_cycle,
    max_pending_approvals: max_pending_approvals >= 1
)
@deal.post(lambda r: r.state in {"pass", "warn", "blocked"})
@deal.post(lambda r: isinstance(r.allow_autonomous_apply, bool))
@deal.post(lambda r: r.max_apply_count >= 0)
@deal.post(lambda r: (r.state == "blocked") == (r.allow_autonomous_apply is False and r.max_apply_count == 0))
def _controller_result(
    stability_gate_state: str,
    ops_gate_state: str,
    e2e_gate_state: str,
    strict_force_off: bool,
    pending_approvals: int,
    rollback_count_recent: int,
    regression_count_recent: int,
    configured_max_per_cycle: int,
    max_pending_approvals: int,
):
    return evaluate_self_modification_controller(
        stability_gate_state=stability_gate_state,
        ops_gate_state=ops_gate_state,
        e2e_gate_state=e2e_gate_state,
        strict_force_off=strict_force_off,
        pending_approvals=pending_approvals,
        rollback_count_recent=rollback_count_recent,
        regression_count_recent=regression_count_recent,
        configured_max_per_cycle=configured_max_per_cycle,
        max_pending_approvals=max_pending_approvals,
    )


def test_controller_contract_pass_case():
    result = _controller_result(
        "pass",
        "pass",
        "pass",
        False,
        0,
        0,
        0,
        3,
        4,
    )
    assert result.max_apply_count == 3
