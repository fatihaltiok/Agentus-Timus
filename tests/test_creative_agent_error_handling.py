import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.agents.creative import CreativeAgent


@pytest.mark.asyncio
async def test_creative_agent_reports_status_error():
    agent = CreativeAgent.__new__(CreativeAgent)
    agent._handle_file_artifacts = lambda observation: None

    async def _fake_prompt(_task: str) -> str:
        return "cinematic hero on rooftop"

    async def _fake_exec(_prompt: str, size: str = "1024x1024", quality: str = "high"):
        return {
            "status": "error",
            "message": "moderation blocked",
            "error_code": "moderation_blocked",
        }

    agent._generate_image_prompt_with_gpt = _fake_prompt
    agent._execute_with_nemotron = _fake_exec

    result = await CreativeAgent.run(agent, "male ein bild von einem helden")
    assert "Fehler bei der Bildgenerierung" in result
    assert "moderation blocked" in result.lower()


@pytest.mark.asyncio
async def test_creative_agent_retries_once_on_moderation_and_succeeds():
    agent = CreativeAgent.__new__(CreativeAgent)
    agent._handle_file_artifacts = lambda observation: None
    calls = {"n": 0, "prompts": []}

    async def _fake_prompt(_task: str) -> str:
        return "cinematic superhero scene"

    async def _fake_exec(prompt: str, size: str = "1024x1024", quality: str = "high"):
        calls["n"] += 1
        calls["prompts"].append(prompt)
        if calls["n"] == 1:
            return {
                "status": "error",
                "error": "blocked by moderation",
                "error_code": "moderation_blocked",
            }
        return {
            "status": "success",
            "saved_as": "results/hero.png",
            "message": "ok",
        }

    agent._generate_image_prompt_with_gpt = _fake_prompt
    agent._execute_with_nemotron = _fake_exec

    result = await CreativeAgent.run(agent, "male ein bild von einem helden")

    assert calls["n"] == 2
    assert "copyrighted" in calls["prompts"][1].lower()
    assert "erfolgreich generiert" in result.lower()
    assert "results/hero.png" in result

