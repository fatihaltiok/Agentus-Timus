import deal

from orchestration.self_modification_canary import SelfModificationCanaryResult, CanaryCheckResult


@deal.pre(lambda state: state in {"passed", "failed"})
@deal.post(lambda r: r.state in {"passed", "failed"})
@deal.post(lambda r: isinstance(r.summary, str))
def _canary_result(state: str):
    return SelfModificationCanaryResult(
        state=state,
        checks=(CanaryCheckResult(name="production_gates", status=state),),
        rollback_required=(state == "failed"),
    )


def test_canary_contract_passed_summary() -> None:
    result = _canary_result("passed")
    assert "production_gates:passed" in result.summary
