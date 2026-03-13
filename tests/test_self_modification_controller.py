from orchestration.self_modification_controller import (
    build_autonomous_self_modification_candidates,
    evaluate_self_modification_controller,
)


def test_build_candidates_skips_reserved_and_orders_by_priority():
    suggestions = [
        {
            "id": 1,
            "type": "routing",
            "target": "research",
            "finding": "research confidence drift",
            "suggestion": "Prompt verbessern",
            "confidence": 0.9,
            "severity": "high",
        },
        {
            "id": 2,
            "type": "tool",
            "target": "open_url",
            "finding": "browser workflow drift",
            "suggestion": "Selector verbessern",
            "confidence": 0.6,
            "severity": "low",
        },
        {
            "id": 3,
            "type": "routing",
            "target": "unknown",
            "finding": "ignore",
            "suggestion": "ignore",
            "confidence": 0.8,
            "severity": "medium",
        },
    ]

    candidates = build_autonomous_self_modification_candidates(
        suggestions,
        reserved_source_ids=("2",),
    )

    assert [candidate.source_id for candidate in candidates] == ["1"]
    assert candidates[0].file_path == "agent/prompts.py"


def test_controller_warn_mode_allows_two_when_only_gate_warns():
    decision = evaluate_self_modification_controller(
        stability_gate_state="warn",
        ops_gate_state="pass",
        e2e_gate_state="pass",
        strict_force_off=False,
        pending_approvals=0,
        rollback_count_recent=0,
        regression_count_recent=0,
        configured_max_per_cycle=3,
        max_pending_approvals=4,
    )

    assert decision.state == "warn"
    assert decision.allow_autonomous_apply is True
    assert decision.max_apply_count == 2


def test_controller_warn_mode_caps_to_one_under_soft_pressure():
    decision = evaluate_self_modification_controller(
        stability_gate_state="pass",
        ops_gate_state="warn",
        e2e_gate_state="pass",
        strict_force_off=False,
        pending_approvals=1,
        rollback_count_recent=0,
        regression_count_recent=0,
        configured_max_per_cycle=3,
        max_pending_approvals=4,
    )

    assert decision.state == "warn"
    assert decision.allow_autonomous_apply is True
    assert decision.max_apply_count == 1


def test_controller_blocks_on_strict_force_off():
    decision = evaluate_self_modification_controller(
        stability_gate_state="pass",
        ops_gate_state="pass",
        e2e_gate_state="pass",
        strict_force_off=True,
        pending_approvals=0,
        rollback_count_recent=0,
        regression_count_recent=0,
        configured_max_per_cycle=3,
        max_pending_approvals=4,
    )

    assert decision.state == "blocked"
    assert decision.allow_autonomous_apply is False
    assert decision.max_apply_count == 0
