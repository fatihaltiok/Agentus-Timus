from __future__ import annotations

import deal

from agent.agents.meta import MetaAgent


@deal.post(lambda r: isinstance(r, bool))
def _contract_should_execute_optional_stage(chain: list[str], optional: bool, agent: str) -> bool:
    return MetaAgent._should_execute_optional_recipe_stage(
        {"recommended_agent_chain": chain},
        {"optional": optional, "agent": agent},
    )


def test_optional_stage_requires_agent_in_chain():
    assert _contract_should_execute_optional_stage(["meta", "visual"], True, "document") is False
    assert _contract_should_execute_optional_stage(["meta", "document"], True, "document") is True
    assert _contract_should_execute_optional_stage(["meta"], False, "document") is True
