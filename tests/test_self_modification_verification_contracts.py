import deal

from orchestration.self_modification_verification import SelfModificationVerificationResult, VerificationCheckResult


@deal.pre(lambda status: status in {"passed", "failed"})
@deal.post(lambda r: r.status in {"passed", "failed"})
@deal.post(lambda r: isinstance(r.summary, str))
def _verification_result(status: str):
    return SelfModificationVerificationResult(
        status=status,
        checks=(VerificationCheckResult(name="py_compile", status=status),),
    )


def test_verification_contract_passed_summary() -> None:
    result = _verification_result("passed")
    assert "py_compile:passed" in result.summary
