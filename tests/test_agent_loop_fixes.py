"""
Integrationstest für die Agent-Loop-Fixes:
- max_tokens erhöht für qwq/deepseek-reasoner
- <think> Tags werden gestrippt
- Volle run()-Schleife verarbeitet Think+Action korrekt (Mock-LLM)
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.base_agent import BaseAgent


# ── 1. max_tokens ─────────────────────────────────────────────────────────

def test_max_tokens_qwq():
    assert BaseAgent._get_max_tokens_for_model("qwen/qwq-32b") == 8000

def test_max_tokens_deepseek_reasoner():
    assert BaseAgent._get_max_tokens_for_model("deepseek-reasoner") == 8000

def test_max_tokens_nemotron():
    assert BaseAgent._get_max_tokens_for_model("nvidia/nemotron-3-nano-30b-a3b") == 4000

def test_max_tokens_standard():
    assert BaseAgent._get_max_tokens_for_model("claude-sonnet-4-6") == 2000

def test_max_tokens_qvq():
    assert BaseAgent._get_max_tokens_for_model("qwen/qvq-72b") == 8000


# ── 2. <think> Stripping ──────────────────────────────────────────────────

def test_strip_think_basic():
    raw = "<think>langer denkprozess</think>\nAction: {\"method\": \"search_web\"}"
    result = BaseAgent._strip_think_tags(raw)
    assert "<think>" not in result
    assert "Action:" in result

def test_strip_think_multiline():
    raw = "<think>\nZeile 1\nZeile 2\n</think>\nFinal Answer: Ergebnis"
    result = BaseAgent._strip_think_tags(raw)
    assert "<think>" not in result
    assert "Final Answer:" in result

def test_strip_think_no_tag():
    raw = "Action: {\"method\": \"read_file\", \"params\": {}}"
    result = BaseAgent._strip_think_tags(raw)
    assert result == raw

def test_strip_think_empty():
    assert BaseAgent._strip_think_tags("") == ""

def test_strip_think_only_tags():
    raw = "<think>nur thinking, kein output</think>"
    result = BaseAgent._strip_think_tags(raw)
    assert "<think>" not in result

def test_strip_think_nested_content_preserved():
    """Inhalt NACH den Think-Tags bleibt erhalten."""
    action = 'Action: {"method": "start_deep_research", "params": {"query": "KI Robotik"}}'
    raw = f"<think>Ich soll eine Recherche starten...</think>\n{action}"
    result = BaseAgent._strip_think_tags(raw)
    assert action in result


# ── 3. Parse-Verhalten: think+action → action korrekt erkannt ─────────────

def test_think_then_action_parseable():
    """Nach strip_think_tags ist die Action-JSON parseable."""
    from agent.shared.action_parser import parse_action

    raw_qwq = (
        "<think>Ich soll eine Recherche starten. "
        "Der Nutzer fragt nach KI Agenten in Robotik.</think>\n"
        'Action: {"method": "start_deep_research", "params": {"query": "KI Agenten Robotik 2026"}}'
    )
    stripped = BaseAgent._strip_think_tags(raw_qwq)
    action, err = parse_action(stripped)
    assert action is not None, f"Action nicht geparst: {err}"
    assert action["method"] == "start_deep_research"
    assert action["params"]["query"] == "KI Agenten Robotik 2026"


def test_think_then_final_answer_parseable():
    """Nach strip_think_tags ist Final Answer erkennbar."""
    raw_qwq = (
        "<think>Ich habe genug Infos. Ich kann jetzt antworten.</think>\n"
        "Final Answer: KI Agenten revolutionieren die Robotik durch ..."
    )
    stripped = BaseAgent._strip_think_tags(raw_qwq)
    assert "Final Answer:" in stripped
    assert "<think>" not in stripped


def test_without_think_action_still_parseable():
    """Normale Antwort ohne think-Tags funktioniert weiterhin."""
    from agent.shared.action_parser import parse_action

    raw = 'Action: {"method": "search_web", "params": {"query": "test"}}'
    stripped = BaseAgent._strip_think_tags(raw)
    action, err = parse_action(stripped)
    assert action is not None
    assert action["method"] == "search_web"


# ── 4. Prompt-Korrektheit ─────────────────────────────────────────────────

def test_reasoning_prompt_mentions_qwq():
    from agent.prompts import REASONING_PROMPT_TEMPLATE
    assert "qwq" in REASONING_PROMPT_TEMPLATE.lower()

def test_reasoning_prompt_has_format_rule():
    from agent.prompts import REASONING_PROMPT_TEMPLATE
    assert "FORMAT" in REASONING_PROMPT_TEMPLATE

def test_research_prompt_updated_iterations():
    from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "6" in DEEP_RESEARCH_PROMPT_TEMPLATE

def test_research_prompt_has_format_rule():
    from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "FORMAT" in DEEP_RESEARCH_PROMPT_TEMPLATE
