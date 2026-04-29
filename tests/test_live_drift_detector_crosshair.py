from __future__ import annotations

import deal

from orchestration.live_drift_detector import detect_live_drifts


def _has_type(drift_type: str, signals: object) -> bool:
    return any(getattr(signal, "drift_type", "") == drift_type for signal in signals)  # type: ignore[arg-type]


@deal.post(lambda result: _has_type("execute_blocked_by_mode", result))
def _contract_execute_block_is_detected() -> tuple[object, ...]:
    return detect_live_drifts(
        query="erstelle die pdf aus /tmp/test.odt",
        reply="Interaktionsmodus blockiert, keine Toolnutzung erlaubt.",
        response_mode="execute",
    )


@deal.post(lambda result: _has_type("false_context_empty_claim", result))
def _contract_false_context_empty_claim_is_detected() -> tuple[object, ...]:
    return detect_live_drifts(
        query="worueber hatte ich dich eben gebeten",
        reply="Ich sehe keinen vorherigen Kontext.",
        dominant_turn_type="followup",
        conversation_state={"active_goal": "KI-Startup-Beratung"},
    )


def test_contract_execute_block_is_detected() -> None:
    assert _has_type("execute_blocked_by_mode", _contract_execute_block_is_detected())


def test_contract_false_context_empty_claim_is_detected() -> None:
    assert _has_type("false_context_empty_claim", _contract_false_context_empty_claim_is_detected())
