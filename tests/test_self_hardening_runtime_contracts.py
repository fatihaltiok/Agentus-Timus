from __future__ import annotations

import deal

from orchestration.self_hardening_runtime import classify_self_hardening_runtime_state


@deal.post(lambda r: r in {"critical", "warn", "ok", "idle"})
def _contract_classify_self_hardening_runtime_state(last_status: str, last_stage: str) -> str:
    return classify_self_hardening_runtime_state(last_status=last_status, last_stage=last_stage)


def test_contract_classify_self_hardening_runtime_state_error_is_critical() -> None:
    assert _contract_classify_self_hardening_runtime_state("error", "self_modify_finished") == "critical"
