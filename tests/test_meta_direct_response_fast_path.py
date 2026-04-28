import json

import pytest

from agent.agents.meta import MetaAgent


@pytest.mark.asyncio
async def test_meta_agent_returns_exact_direct_response_without_llm():
    task = (
        f"{MetaAgent._META_HANDOFF_HEADER}\n"
        "meta_clarity_contract_json: "
        + json.dumps(
            {
                "request_kind": "direct_response",
                "answer_obligation": "answer_exactly_as_requested",
                "completion_condition": "requested_direct_response_returned",
                "direct_answer_required": True,
            }
        )
        + "\n"
        f"{MetaAgent._ORIGINAL_TASK_HEADER}\n"
        "führe aus: antworte exakt nur mit KIMI_CHAT_OK"
    )
    agent = MetaAgent.__new__(MetaAgent)

    result = await MetaAgent.run(agent, task)

    assert result == "KIMI_CHAT_OK"
