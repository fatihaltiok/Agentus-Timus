import deal

from orchestration.self_modification_policy import evaluate_self_modification_policy
from orchestration.self_modification_risk import classify_self_modification_risk


@deal.post(lambda r: r.risk_level in {"low", "medium", "high"})
@deal.post(lambda r: r.score >= 0)
@deal.post(lambda r: r.changed_lines >= 0)
def _risk_result(path: str, original: str, modified: str):
    return classify_self_modification_risk(
        file_path=path,
        change_description="contract",
        original_code=original,
        modified_code=modified,
        policy=evaluate_self_modification_policy(path),
    )


def test_risk_contract_docs_path():
    result = _risk_result("docs/report.md", "# a\n", "# b\n")
    assert result.risk_level == "low"
