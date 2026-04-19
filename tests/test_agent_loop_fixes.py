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


def test_parse_action_rejects_list_shaped_action_payload():
    from agent.shared.action_parser import parse_action

    raw = 'Action: {"action": [{"method": "read_file", "params": {"path": "x"}}]}'
    action, err = parse_action(raw)

    assert action is None
    assert err == "Action-JSON muss ein Objekt sein, keine Liste."


def test_base_agent_normalize_action_payload_rejects_non_dict():
    action, err = BaseAgent._normalize_action_payload(
        [{"method": "read_file", "params": {"path": "x"}}],
        None,
    )

    assert action is None
    assert err == "Action-JSON muss ein Objekt sein, keine Liste."


def test_refine_tool_call_reroutes_meta_executor_knowledge_research_to_research():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    try:
        method, params = agent._refine_tool_call(
            "delegate_to_agent",
            {
                "agent_type": "executor",
                "task": (
                    "Recherchiere ob es in Deutschland aktuelle politische Bestrebungen, "
                    "Gesetzesentwürfe oder Diskussionen gibt, die eine "
                    "Genehmigungspflicht bei Ausreise aus Deutschland vorsehen."
                ),
            },
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert method == "delegate_to_agent"
    assert params["agent_type"] == "research"
    assert params["task"].startswith("Recherchiere ob es in Deutschland aktuelle politische Bestrebungen")


def test_refine_tool_call_wraps_executor_simple_live_lookup_in_handoff():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    try:
        method, params = agent._refine_tool_call(
            "delegate_to_agent",
            {
                "agent_type": "executor",
                "task": "Zeig mir aktuelle News zu OpenAI.",
            },
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert method == "delegate_to_agent"
    assert params["agent_type"] == "executor"
    assert params["task"].startswith("# DELEGATION HANDOFF")
    assert "- task_type: simple_live_lookup" in params["task"]
    assert "preferred_search_tool: search_web" in params["task"]


def test_embedded_final_answer_action_salvage_requires_safe_runtime_context():
    action = {"method": "get_processes", "params": {"cpu_threshold": 20}}
    reply = (
        "Final Answer: Ich habe die groessten Baustellen eingegrenzt.\n"
        "Naechster Schritt: Action: {\"method\": \"get_processes\", "
        "\"params\": {\"cpu_threshold\": 20}}"
    )

    assert BaseAgent._should_salvage_embedded_final_answer_action(
        "Analysiere den aktuellen Timus-Zustand und priorisiere Runtime-Baustellen.",
        reply,
        action,
    ) is True
    assert BaseAgent._should_salvage_embedded_final_answer_action(
        "Schreibe mir einen Blogpost ueber Prozessmanagement.",
        reply,
        action,
    ) is False


@pytest.mark.asyncio
async def test_run_executes_safe_embedded_action_before_finalizing(monkeypatch):
    replies = iter(
        [
            'Action: {"method": "search_blackboard", "params": {"query": "ambient_audit"}}',
            (
                "Final Answer: Ich habe drei Runtime-Baustellen identifiziert.\n"
                "Prioritaet 1: CPU-Spitzen zuerst verifizieren.\n"
                'Naechster Schritt: Action: {"method": "get_processes", '
                '"params": {"cpu_threshold": 20}}'
            ),
            "Final Answer: Ich habe jetzt die Prozesse geprueft und die Top-CPU-Verursacher bestaetigt.",
        ]
    )
    tool_calls = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        return next(replies)

    async def _fake_call_tool(self, method: str, params: dict):
        tool_calls.append((method, dict(params)))
        if method == "search_blackboard":
            return {"status": "success", "results": [{"topic": "ambient_audit"}]}
        if method == "get_processes":
            return {
                "status": "success",
                "returned": 1,
                "processes": [{"pid": 1234, "name": "python", "cpu_percent": 47.5}],
            }
        raise AssertionError(f"Unerwartetes Tool: {method}")

    async def _fake_reflection(self, task: str, result: str, success: bool = True) -> None:
        return None

    monkeypatch.setattr(BaseAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect)
    monkeypatch.setattr(BaseAgent, "_build_working_memory_context", _fake_working_memory)
    monkeypatch.setattr(BaseAgent, "_inject_working_memory_into_task", _fake_inject)
    monkeypatch.setattr(BaseAgent, "_call_llm", _fake_llm)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(BaseAgent, "_run_reflection", _fake_reflection)

    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=4,
        agent_type="reasoning",
        skip_model_validation=True,
    )
    try:
        result = await agent.run(
            "Analysiere den aktuellen Timus-Zustand. Nutze Blackboard und den "
            "aktuellen Betriebszustand, identifiziere die 3 wichtigsten "
            "verbleibenden Runtime-Baustellen."
        )
    finally:
        await agent.http_client.aclose()

    assert result == "Ich habe jetzt die Prozesse geprueft und die Top-CPU-Verursacher bestaetigt."
    assert tool_calls == [
        ("search_blackboard", {"query": "ambient_audit"}),
        ("get_processes", {"cpu_threshold": 20}),
    ]


@pytest.mark.asyncio
async def test_run_uses_compact_working_memory_query_for_meta_handoff(monkeypatch):
    captured = {}

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        captured["query"] = task
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        return "Final Answer: Erster Schritt ist definiert."

    async def _fake_reflection(self, task: str, result: str, success: bool = True) -> None:
        return None

    monkeypatch.setattr(BaseAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect)
    monkeypatch.setattr(BaseAgent, "_build_working_memory_context", _fake_working_memory)
    monkeypatch.setattr(BaseAgent, "_inject_working_memory_into_task", _fake_inject)
    monkeypatch.setattr(BaseAgent, "_call_llm", _fake_llm)
    monkeypatch.setattr(BaseAgent, "_run_reflection", _fake_reflection)

    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="reasoning",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "task_type: single_lane\n"
        "intent_family: plan_only\n"
        "planning_needed: yes\n"
        "meta_clarity_contract_json: "
        '{"primary_objective":"Twilio-Inworld-Anruffunktion als ersten sauberen Arbeitsschritt einordnen","completion_condition":"next_recommended_block_or_step_named"}\n'
        "meta_execution_plan_json: "
        '{"next_step_id":"plan_frame_goal","steps":[{"id":"plan_frame_goal","title":"Ziel und Scope festziehen","expected_output":"Ein knapper erster Arbeitsschritt","completion_signals":["step_completed"]}]}\n'
        "task_decomposition_json: "
        '{"goal":"Richte eine Twilio-Inworld-Anruffunktion ein","intent_family":"build_setup","planning_needed":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "Richte fuer mich eine Anruffunktion ein. Du sollst mich ueber Twilio anrufen koennen.\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert result == "Erster Schritt ist definiert."
    assert "Twilio" in captured["query"]
    assert "Pflichtziel: Twilio-Inworld-Anruffunktion" in captured["query"]
    assert "Aktueller Planschritt: Ziel und Scope festziehen" in captured["query"]
    assert "Abschlussbedingung: next_recommended_block_or_step_named" in captured["query"]
    assert "meta_execution_plan_json" not in captured["query"]


# ── 4. Prompt-Korrektheit ─────────────────────────────────────────────────

def test_reasoning_prompt_mentions_qwq():
    from agent.prompts import REASONING_PROMPT_TEMPLATE
    assert "qwq" in REASONING_PROMPT_TEMPLATE.lower()

def test_reasoning_prompt_has_format_rule():
    from agent.prompts import REASONING_PROMPT_TEMPLATE
    assert "FORMAT" in REASONING_PROMPT_TEMPLATE

def test_reasoning_prompt_enforces_runtime_evidence_discipline():
    from agent.prompts import REASONING_PROMPT_TEMPLATE
    assert "RUNTIME-/BETRIEBSZUSTAND-DISZIPLIN" in REASONING_PROMPT_TEMPLATE
    assert 'delegate_to_agent("system"' in REASONING_PROMPT_TEMPLATE
    assert "KEINE ausfuehrbaren Action-Snippets in `Final Answer` verstecken." in REASONING_PROMPT_TEMPLATE

def test_research_prompt_uses_dynamic_iteration_budget():
    from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "{deep_research_max_iterations}" in DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "max 6 Iterationen" not in DEEP_RESEARCH_PROMPT_TEMPLATE

def test_research_prompt_has_format_rule():
    from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "FORMAT" in DEEP_RESEARCH_PROMPT_TEMPLATE

def test_research_prompt_mentions_research_plan():
    from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "RECHERCHEPLAN" in DEEP_RESEARCH_PROMPT_TEMPLATE

def test_research_prompt_mentions_scope_mode():
    from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "scope_mode" in DEEP_RESEARCH_PROMPT_TEMPLATE

def test_research_prompt_forbids_absolute_debunking_on_thin_evidence():
    from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "NEGATIVBEFUND-DISZIPLIN" in DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "kein belastbarer Beleg" in DEEP_RESEARCH_PROMPT_TEMPLATE
    assert "NICHT: \"Falschinformation\", \"Fakenews\"" in DEEP_RESEARCH_PROMPT_TEMPLATE

def test_meta_prompt_requires_cautious_negative_summary_language():
    from agent.prompts import META_SYSTEM_PROMPT
    assert "NEGATIVBEFUND-DISZIPLIN" in META_SYSTEM_PROMPT
    assert "keine belastbaren Belege" in META_SYSTEM_PROMPT
    assert "nicht als vollstaendiger Ausschluss" in META_SYSTEM_PROMPT


def test_meta_prompt_mentions_meta_clarity_contract():
    from agent.prompts import META_SYSTEM_PROMPT

    assert "META-CLARITY-VERTRAG" in META_SYSTEM_PROMPT
    assert "direct_answer_required=true" in META_SYSTEM_PROMPT
    assert "primary_objective" in META_SYSTEM_PROMPT

def test_soften_unproven_verdict_language_rewrites_overhard_fake_news_claims():
    raw = (
        "**Klare Antwort: Nein, es gibt keine solchen Bestrebungen.**\n\n"
        "Die Recherche hat ergeben: **Keine belastbaren Belege** fuer eine "
        "Ausreisegenehmigungspflicht in Deutschland.\n\n"
        "Die analysierten Quellen behandelten komplett andere Themen.\n\n"
        "**Fazit:** Das ist ein Geruecht oder eine Falschinformation. "
        "Wer das behauptet, sollte Quellen vorlegen — und die gibt es nicht."
    )

    softened = BaseAgent._soften_unproven_verdict_language(raw)

    assert "Hinweis:" in softened
    assert "Falschinformation" not in softened
    assert "Geruecht" not in softened
    assert "nicht belastbar belegt" in softened
    assert "derzeit kein belastbarer Beleg" in softened

def test_soften_unproven_verdict_language_leaves_direct_evidence_untouched():
    raw = (
        "Bundestagsdrucksache 20/12345 und die offizielle Ministeriumsantwort "
        "belegen den vorgeschlagenen Regelungsinhalt direkt."
    )

    assert BaseAgent._soften_unproven_verdict_language(raw) == raw


def test_working_memory_settings_fall_back_to_memory_env(monkeypatch):
    monkeypatch.delenv("WORKING_MEMORY_CHAR_BUDGET", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_MAX_RELATED", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_MAX_RECENT_EVENTS", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_FOLLOWUP_CHAR_BUDGET", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_FOLLOWUP_MAX_RELATED", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_FOLLOWUP_MAX_RECENT_EVENTS", raising=False)
    monkeypatch.setenv("WM_MAX_CHARS", "12345")
    monkeypatch.setenv("WM_MAX_RELATED", "9")
    monkeypatch.setenv("WM_MAX_EVENTS", "17")

    settings = BaseAgent._resolve_working_memory_settings("normale rueckfrage")

    assert settings["max_chars"] == 12345
    assert settings["max_related"] == 9
    assert settings["max_recent_events"] == 17
    assert settings["followup_context"] is False


def test_working_memory_settings_boost_followup_context(monkeypatch):
    monkeypatch.delenv("WORKING_MEMORY_CHAR_BUDGET", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_MAX_RELATED", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_MAX_RECENT_EVENTS", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_FOLLOWUP_CHAR_BUDGET", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_FOLLOWUP_MAX_RELATED", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_FOLLOWUP_MAX_RECENT_EVENTS", raising=False)
    monkeypatch.setenv("WM_MAX_CHARS", "8000")
    monkeypatch.setenv("WM_MAX_RELATED", "6")
    monkeypatch.setenv("WM_MAX_EVENTS", "10")

    plain_settings = BaseAgent._resolve_working_memory_settings("kurze statusfrage")
    followup_settings = BaseAgent._resolve_working_memory_settings(
        "# FOLLOW-UP CONTEXT\n"
        "session_summary: Wir waren bei der DeepResearch-Planung.\n"
        "pending_followup_prompt: Welche Option soll ich zuerst angehen?"
    )

    assert plain_settings["followup_context"] is False
    assert followup_settings["followup_context"] is True
    assert followup_settings["max_chars"] > plain_settings["max_chars"]
    assert followup_settings["max_related"] > plain_settings["max_related"]
    assert followup_settings["max_recent_events"] > plain_settings["max_recent_events"]


def test_working_memory_settings_respect_meta_clarity_contract_limits(monkeypatch):
    monkeypatch.delenv("WORKING_MEMORY_CHAR_BUDGET", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_MAX_RELATED", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_MAX_RECENT_EVENTS", raising=False)
    monkeypatch.setenv("WM_MAX_CHARS", "10000")
    monkeypatch.setenv("WM_MAX_RELATED", "8")
    monkeypatch.setenv("WM_MAX_EVENTS", "15")

    settings = BaseAgent._resolve_working_memory_settings(
        "# META ORCHESTRATION HANDOFF\n"
        "meta_clarity_contract_json: "
        '{"allowed_working_memory_sections":["KURZZEITKONTEXT"],"max_related_memories":0,"max_recent_events":4}\n'
        "\n# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und sag was als naechstes ansteht\n"
    )

    assert settings["followup_context"] is False
    assert settings["max_chars"] == 10000
    assert settings["max_related"] == 0
    assert settings["max_recent_events"] == 4
    assert settings["allowed_sections"] == ("KURZZEITKONTEXT",)
