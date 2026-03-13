import deal

from orchestration.self_modification_policy import evaluate_self_modification_policy


@deal.post(lambda r: isinstance(r.allowed, bool))
@deal.post(lambda r: isinstance(r.zone_id, str))
@deal.post(lambda r: isinstance(r.reason, str))
def _policy_result(path: str):
    return evaluate_self_modification_policy(path)


def test_policy_contract_prompt_file():
    result = _policy_result("agent/prompts.py")
    assert result.allowed is True


def test_policy_contract_blocked_file():
    result = _policy_result("agent/agents/meta.py")
    assert result.allowed is False
