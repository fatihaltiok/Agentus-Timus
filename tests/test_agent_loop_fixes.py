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
from agent.agents.meta import MetaAgent
from agent.shared.delegation_handoff import parse_delegation_handoff


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


def test_detect_meta_answer_domain_prefers_docs_status_over_restarbeit_wording():
    answer = (
        "Phase F ist im Kern abgeschlossen. Offene Restarbeit ist nur Nachschaerfung. "
        "Als naechstes steht das Zwischenprojekt zur allgemeinen Mehrschritt-Planung an."
    )

    assert BaseAgent._detect_meta_answer_domain(answer) == "docs_status"


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


def test_refine_tool_call_wraps_meta_executor_setup_task_in_generic_handoff():
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
                    "Pruefe im Repo, ob es schon Vorbereitungen fuer Twilio und Inworld "
                    "fuer eine Anruffunktion gibt."
                ),
            },
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert method == "delegate_to_agent"
    assert params["agent_type"] == "executor"
    handoff = parse_delegation_handoff(params["task"])
    assert handoff is not None
    assert handoff.target_agent == "executor"
    assert handoff.handoff_data["task_type"] == "setup_build_probe"
    assert handoff.handoff_data["project_root"].endswith("/home/fatih-ubuntu/dev/timus")


def test_refine_tool_call_wraps_meta_executor_setup_execution_in_structured_handoff():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    agent._current_task_text = (
        "# META ORCHESTRATION HANDOFF\n"
        'meta_clarity_contract_json: {"primary_objective":"Richte fuer mich eine Anruffunktion ueber Twilio und Inworld ein",'
        '"request_kind":"execute_task","answer_obligation":"probe_then_return_concrete_setup_execution_path",'
        '"completion_condition":"first_build_step_or_real_blocker_named"}\n'
    )
    try:
        method, params = agent._refine_tool_call(
            "delegate_to_agent",
            {
                "agent_type": "executor",
                "task": (
                    "Richte fuer mich eine Anruffunktion ueber Twilio und Inworld ein."
                ),
            },
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert method == "delegate_to_agent"
    assert params["agent_type"] == "executor"
    handoff = parse_delegation_handoff(params["task"])
    assert handoff is not None
    assert handoff.target_agent == "executor"
    assert handoff.handoff_data["task_type"] == "setup_build_execution"
    assert "erster konkreter Umsetzungsschritt" in params["task"]


def test_refine_tool_call_wraps_meta_executor_research_advisory_in_bounded_handoff():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    agent._current_task_text = (
        "# META ORCHESTRATION HANDOFF\n"
        'meta_clarity_contract_json: {"primary_objective":"Mach dich schlau ueber Kreislaufwirtschaft im Bau und steh mir dann hilfreich zur Seite","request_kind":"execute_task"}\n'
    )
    try:
        method, params = agent._refine_tool_call(
            "delegate_to_agent",
            {
                "agent_type": "executor",
                "task": "Mach dich schlau ueber Kreislaufwirtschaft im Bau und steh mir dann hilfreich zur Seite",
            },
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert method == "delegate_to_agent"
    assert params["agent_type"] == "executor"
    handoff = parse_delegation_handoff(params["task"])
    assert handoff is not None
    assert handoff.target_agent == "executor"
    assert handoff.handoff_data["task_type"] == "simple_live_lookup"
    assert handoff.handoff_data["query"].startswith("Mach dich schlau ueber Kreislaufwirtschaft")
    assert "avoid_deep_research: yes" in params["task"]


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
        captured["raw_task"] = task
        captured["query"] = BaseAgent._extract_working_memory_query(task)
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
    assert "meta_execution_plan_json" in captured["raw_task"]


@pytest.mark.asyncio
async def test_meta_clarity_blocks_wrong_route_action_for_direct_recommendation(monkeypatch):
    replies = iter(
        [
            (
                'Action: {"method":"delegate_to_agent","params":{"agent_type":"executor",'
                '"task":"Berechne die Route von Offenbach am Main nach Münster mit dem Auto."}}'
            ),
            "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung.",
        ]
    )

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        return next(replies)

    async def _fake_reflection(self, task: str, result: str, success: bool = True) -> None:
        return None

    async def _unexpected_remote_registry(self) -> None:
        raise AssertionError("Meta-Clarity guard should block before remote tool resolution")

    monkeypatch.setattr(BaseAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect)
    monkeypatch.setattr(BaseAgent, "_build_working_memory_context", _fake_working_memory)
    monkeypatch.setattr(BaseAgent, "_inject_working_memory_into_task", _fake_inject)
    monkeypatch.setattr(BaseAgent, "_call_llm", _fake_llm)
    monkeypatch.setattr(BaseAgent, "_run_reflection", _fake_reflection)
    monkeypatch.setattr(BaseAgent, "_ensure_remote_tool_names", _unexpected_remote_registry)

    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=3,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "task_type: single_lane\n"
        "intent_family: plan_only\n"
        "planning_needed: yes\n"
        "meta_clarity_contract_json: "
        '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Zwischenprojekt zur allgemeinen Mehrschritt-Planung" in result


@pytest.mark.asyncio
async def test_meta_clarity_limits_direct_recommendation_to_single_evidence_fetch(monkeypatch):
    import agent.base_agent as base_agent_module

    replies = iter(
        [
            (
                'Action: {"method":"delegate_to_agent","params":{"agent_type":"shell",'
                '"task":"Lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und extrahiere den naechsten Block."}}'
            ),
            (
                'Action: {"method":"delegate_to_agent","params":{"agent_type":"document",'
                '"task":"Lies docs/ZWISCHENPROJEKT_ALLGEMEINE_MEHRSCHRITT_PLANUNG_2026-04-12.md."}}'
            ),
            "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung.",
        ]
    )
    llm_last_messages = []
    http_calls = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        last = messages[-1]["content"] if isinstance(messages[-1], dict) else ""
        llm_last_messages.append(last)
        return next(replies)

    async def _fake_reflection(self, task: str, result: str, success: bool = True) -> None:
        return None

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    async def _fake_post(url, *, json=None, timeout=None):
        http_calls.append(json)
        return _FakeResponse(
            {
                "result": {
                    "status": "success",
                    "agent_type": "shell",
                    "output": "Phase F ist im Kern abgeschlossen. Als Naechstes kommt das Zwischenprojekt.",
                }
            }
        )

    monkeypatch.setattr(BaseAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect)
    monkeypatch.setattr(BaseAgent, "_build_working_memory_context", _fake_working_memory)
    monkeypatch.setattr(BaseAgent, "_inject_working_memory_into_task", _fake_inject)
    monkeypatch.setattr(BaseAgent, "_call_llm", _fake_llm)
    monkeypatch.setattr(BaseAgent, "_run_reflection", _fake_reflection)
    monkeypatch.setattr(BaseAgent, "_ensure_remote_tool_names", AsyncMock())
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "normalize_tool_result", lambda method, result: result)

    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=4,
        agent_type="meta",
        skip_model_validation=True,
    )
    agent.http_client.post = AsyncMock(side_effect=_fake_post)
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "task_type: single_lane\n"
        "intent_family: plan_only\n"
        "planning_needed: yes\n"
        "meta_clarity_contract_json: "
        '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true,'
        '"delegation_mode":"single_evidence_fetch","max_delegate_calls":1,'
        '"allowed_delegate_agents":["document"],"force_answer_after_delegate_budget":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Zwischenprojekt zur allgemeinen Mehrschritt-Planung" in result
    assert len(http_calls) == 1
    assert http_calls[0]["method"] == "delegate_to_agent"
    assert "Meta-Clarity Abschlusszwang" in llm_last_messages[1]
    assert "Kein weiterer Toolcall. Kein delegate_to_agent." in llm_last_messages[1]
    assert "Antworte jetzt direkt im Format:" in llm_last_messages[1]


@pytest.mark.asyncio
async def test_meta_clarity_redirects_wrong_direct_answer_delegate_to_allowed_evidence_agent(monkeypatch):
    import agent.base_agent as base_agent_module

    replies = iter(
        [
            (
                'Action: {"method":"delegate_to_agent","params":{"agent_type":"research",'
                '"task":"Lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und extrahiere den naechsten Block."}}'
            ),
            (
                'Action: {"method":"delegate_to_agent","params":{"agent_type":"shell",'
                '"task":"Lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und extrahiere den naechsten Block."}}'
            ),
            "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung.",
        ]
    )
    llm_last_messages = []
    http_calls = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        last = messages[-1]["content"] if isinstance(messages[-1], dict) else ""
        llm_last_messages.append(last)
        return next(replies)

    async def _fake_reflection(self, task: str, result: str, success: bool = True) -> None:
        return None

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    async def _fake_post(url, *, json=None, timeout=None):
        http_calls.append(json)
        return _FakeResponse(
            {
                "result": {
                    "status": "success",
                    "agent_type": "shell",
                    "output": "Phase F ist im Kern abgeschlossen. Als Naechstes kommt das Zwischenprojekt.",
                }
            }
        )

    monkeypatch.setattr(BaseAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect)
    monkeypatch.setattr(BaseAgent, "_build_working_memory_context", _fake_working_memory)
    monkeypatch.setattr(BaseAgent, "_inject_working_memory_into_task", _fake_inject)
    monkeypatch.setattr(BaseAgent, "_call_llm", _fake_llm)
    monkeypatch.setattr(BaseAgent, "_run_reflection", _fake_reflection)
    monkeypatch.setattr(BaseAgent, "_ensure_remote_tool_names", AsyncMock())
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "normalize_tool_result", lambda method, result: result)

    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=4,
        agent_type="meta",
        skip_model_validation=True,
    )
    agent.http_client.post = AsyncMock(side_effect=_fake_post)
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "task_type: single_lane\n"
        "intent_family: plan_only\n"
        "planning_needed: yes\n"
        "meta_clarity_contract_json: "
        '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true,'
        '"delegation_mode":"single_evidence_fetch","max_delegate_calls":1,'
        '"allowed_delegate_agents":["shell","document"],"force_answer_after_delegate_budget":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Zwischenprojekt zur allgemeinen Mehrschritt-Planung" in result
    assert len(http_calls) == 1
    assert http_calls[0]["params"]["agent_type"] == "document"
    assert "Meta-Clarity Korrektur" in llm_last_messages[1]
    assert "erlaubte_delegate_agents: document" in llm_last_messages[1]


@pytest.mark.asyncio
async def test_meta_interaction_mode_think_partner_blocks_research_and_forces_direct_answer(monkeypatch):
    import agent.base_agent as base_agent_module

    replies = iter(
        [
            (
                'Action: {"method":"delegate_to_agent","params":{"agent_type":"research",'
                '"task":"Recherchiere pros und cons von Denk-, Pruef- und Assistenzmodus."}}'
            ),
            "Final Answer: Intern ist die Trennung sinnvoll, solange sie fuer den Nutzer unsichtbar bleibt und nur als Laufzeitvertrag dient.",
        ]
    )
    llm_last_messages = []
    http_calls = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        last = messages[-1]["content"] if isinstance(messages[-1], dict) else ""
        llm_last_messages.append(last)
        return next(replies)

    async def _fake_reflection(self, task: str, result: str, success: bool = True) -> None:
        return None

    async def _fake_post(url, *, json=None, timeout=None):
        http_calls.append(json)
        raise AssertionError("think_partner darf keinen Remote-Toolcall ausloesen")

    monkeypatch.setattr(BaseAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect)
    monkeypatch.setattr(BaseAgent, "_build_working_memory_context", _fake_working_memory)
    monkeypatch.setattr(BaseAgent, "_inject_working_memory_into_task", _fake_inject)
    monkeypatch.setattr(BaseAgent, "_call_llm", _fake_llm)
    monkeypatch.setattr(BaseAgent, "_run_reflection", _fake_reflection)
    monkeypatch.setattr(BaseAgent, "_ensure_remote_tool_names", AsyncMock())
    monkeypatch.setattr(base_agent_module.registry_v2, "validate_tool_call", lambda *args, **kwargs: None)
    monkeypatch.setattr(base_agent_module.registry_v2, "normalize_tool_result", lambda method, result: result)

    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=3,
        agent_type="meta",
        skip_model_validation=True,
    )
    agent.http_client.post = AsyncMock(side_effect=_fake_post)
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "task_type: single_lane\n"
        "intent_family: single_step\n"
        "planning_needed: no\n"
        "meta_interaction_mode_json: "
        '{"mode":"think_partner","mode_reason":"explicit_think_partner_language","explicit_override":true,'
        '"answer_style":"reason_with_user","execution_policy":"no_research_no_execution",'
        '"completion_expectation":"insight_or_options_given"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"Ohne Recherche: Was ist deine Meinung dazu, ob Timus intern Denk-, Pruef- und Assistenzmodus haben sollte?",'
        '"request_kind":"thinking_partner","answer_obligation":"reason_with_user_without_research_or_execution",'
        '"completion_condition":"insight_or_options_given","direct_answer_required":true,'
        '"delegation_mode":"direct_only","max_delegate_calls":0,'
        '"allowed_delegate_agents":[],"force_answer_after_delegate_budget":false}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "Ohne Recherche: Was ist deine Meinung dazu, ob Timus intern Denk-, Pruef- und Assistenzmodus haben sollte?\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Trennung sinnvoll" in result
    assert http_calls == []
    assert "Meta-Interaktionsmodus Abschlusszwang" in llm_last_messages[1]
    assert "keine Recherche, keine Toolnutzung und keine Delegation" in llm_last_messages[1]


@pytest.mark.asyncio
async def test_meta_direct_answer_mode_skips_blackboard_enrichment(monkeypatch):
    import memory.agent_blackboard as blackboard_module

    captured = {}

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        captured["initial_user_content"] = messages[1]["content"]
        return "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung."

    async def _fake_reflection(self, task: str, result: str, success: bool = True) -> None:
        return None

    class _FakeBlackboard:
        def search(self, query, limit=3):
            return [
                {
                    "agent": "meta",
                    "topic": "skills",
                    "key": "skill_creator",
                    "value": "skill-creator ist ein Skill zum Erstellen und Aktualisieren von Skills.",
                }
            ]

    monkeypatch.setattr(BaseAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect)
    monkeypatch.setattr(BaseAgent, "_build_working_memory_context", _fake_working_memory)
    monkeypatch.setattr(BaseAgent, "_inject_working_memory_into_task", _fake_inject)
    monkeypatch.setattr(BaseAgent, "_call_llm", _fake_llm)
    monkeypatch.setattr(BaseAgent, "_run_reflection", _fake_reflection)
    monkeypatch.setattr(blackboard_module, "get_blackboard", lambda: _FakeBlackboard())

    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_clarity_contract_json: "
        '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Zwischenprojekt" in result
    assert "# Bekannte Informationen (Agent-Blackboard):" not in captured["initial_user_content"]
    assert "skill-creator" not in captured["initial_user_content"]


@pytest.mark.asyncio
async def test_meta_frame_guard_rejects_off_frame_explicit_final_answer(monkeypatch):
    replies = iter(
        [
            (
                "Final Answer: Der **skill-creator** ist ein Meta-Skill zum Erstellen "
                "und Bearbeiten von Skills fuer Timus."
            ),
            "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung.",
        ]
    )
    last_user_messages = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        last_user_messages.append(messages[-1]["content"])
        return next(replies)

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
        max_iterations=3,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"direct_answer","task_domain":"docs_status","execution_mode":"answer_directly",'
        '"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Zwischenprojekt" in result
    assert len(last_user_messages) == 2
    assert "Meta-Frame-Korrektur" in last_user_messages[1]
    assert "erkannter_antwort_drift: skill_creation" in last_user_messages[1]


@pytest.mark.asyncio
async def test_meta_frame_guard_rejects_off_frame_parse_salvage_answer(monkeypatch):
    replies = iter(
        [
            (
                "Der **skill-creator** ist ein Meta-Skill zum Erstellen und Bearbeiten "
                "von Skills fuer Timus.\n\nWas er macht:\n- Neue Skills erstellen"
            ),
            "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung.",
        ]
    )
    last_user_messages = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        last_user_messages.append(messages[-1]["content"])
        return next(replies)

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
        max_iterations=3,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"direct_answer","task_domain":"docs_status","execution_mode":"answer_directly",'
        '"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Zwischenprojekt" in result
    assert len(last_user_messages) == 2
    assert "Meta-Frame-Korrektur" in last_user_messages[1]
    assert "erkannter_antwort_drift: skill_creation" in last_user_messages[1]


@pytest.mark.asyncio
async def test_meta_frame_guard_rejects_generic_help_fallback(monkeypatch):
    replies = iter(
        [
            (
                "Final Answer: Ich sehe, dass der System-Kontext geladen wurde. "
                "Du hast mir aber noch keine konkrete Frage oder Aufgabe gestellt. "
                "Was kann ich fuer dich tun?"
            ),
            "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung.",
        ]
    )
    last_user_messages = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        last_user_messages.append(messages[-1]["content"])
        return next(replies)

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
        max_iterations=3,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"direct_answer","task_domain":"docs_status","execution_mode":"answer_directly",'
        '"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Zwischenprojekt" in result
    assert len(last_user_messages) == 2
    assert "Meta-Frame-Korrektur" in last_user_messages[1]
    assert "erkannter_antwort_drift: generic_meta_help" in last_user_messages[1]


@pytest.mark.asyncio
async def test_meta_direct_answer_mode_skips_skill_catalog_injection(monkeypatch):
    captured = {}

    async def _fake_build_meta_context(self):
        return "# TIMUS SYSTEM-KONTEXT\nAktuelle Zeit: 2026-04-21 20:00:00"

    def _fake_select_skills(self, task: str, top_k: int = 3):
        class _FakeSkill:
            name = "skill-creator"

            def get_full_context(self, include_references=False):
                return "# Skill: skill-creator\nDescription: Create or update Skills for Timus."

        return [_FakeSkill()]

    async def _fake_base_run(self, task: str):
        captured["enhanced_task"] = task
        return "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung."

    monkeypatch.setattr(MetaAgent, "_build_meta_context", _fake_build_meta_context)
    monkeypatch.setattr(MetaAgent, "_select_skills_for_task", _fake_select_skills)

    with patch.object(BaseAgent, "run", new=_fake_base_run):
        agent = MetaAgent(tools_description_string="", skip_model_validation=True)
        task = (
            "# META ORCHESTRATION HANDOFF\n"
            "meta_request_frame_json: "
            '{"frame_kind":"direct_answer","task_domain":"docs_status","execution_mode":"answer_directly",'
            '"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht"}\n'
            "meta_clarity_contract_json: "
            '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
            '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
            '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true}\n'
            "\n"
            "# ORIGINAL USER TASK\n"
            "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
        )
        result = await agent.run(task)

    assert "Zwischenprojekt" in result
    assert "# AVAILABLE SKILLS" not in captured["enhanced_task"]
    assert "skill-creator" not in captured["enhanced_task"]


@pytest.mark.asyncio
async def test_meta_docs_status_direct_answer_uses_frame_bound_evidence_context(monkeypatch):
    captured = {}

    async def _fake_build_meta_context(self):
        return (
            "# TIMUS SYSTEM-KONTEXT (automatisch geladen)\n"
            "Aktive Routinen: PDF Chunking Fertig - Neuronal Dynamics (now+check)\n"
            "Agent-Blackboard: Projektstatus ist vorhanden\n"
            "Aktuelle Zeit: 2026-04-21 20:00:00"
        )

    async def _fake_base_run(self, task: str):
        captured["enhanced_task"] = task
        return "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung."

    monkeypatch.setattr(MetaAgent, "_build_meta_context", _fake_build_meta_context)

    with patch.object(BaseAgent, "run", new=_fake_base_run):
        agent = MetaAgent(tools_description_string="", skip_model_validation=True)
        task = (
            "# META ORCHESTRATION HANDOFF\n"
            "meta_request_frame_json: "
            '{"frame_kind":"direct_answer","task_domain":"docs_status","execution_mode":"answer_directly",'
            '"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht"}\n'
            "meta_clarity_contract_json: "
            '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
            '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
            '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true}\n'
            "\n"
            "# ORIGINAL USER TASK\n"
            "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
        )
        result = await agent.run(task)

    assert "Zwischenprojekt" in result
    assert "# DOCS-STATUS EVIDENZVERTRAG" in captured["enhanced_task"]
    assert "docs/PHASE_F_PLAN.md" in captured["enhanced_task"]
    assert "docs/CHANGELOG_DEV.md" in captured["enhanced_task"]
    assert "PDF Chunking Fertig - Neuronal Dynamics" not in captured["enhanced_task"]
    assert "Agent-Blackboard: Projektstatus ist vorhanden" not in captured["enhanced_task"]


@pytest.mark.asyncio
async def test_meta_advisory_direct_recommendation_injects_answer_threshold_context(monkeypatch):
    captured = {}

    async def _fake_build_meta_context(self):
        return "# TIMUS SYSTEM-KONTEXT\nAktive Routinen: irrelevant"

    async def _fake_base_run(self, task: str):
        captured["enhanced_task"] = task
        return "Final Answer: Fahrt nach Mainz ins Gutenberg-Museum und spaeter ans Rheinufer."

    monkeypatch.setattr(MetaAgent, "_build_meta_context", _fake_build_meta_context)

    with patch.object(BaseAgent, "run", new=_fake_base_run):
        agent = MetaAgent(tools_description_string="", skip_model_validation=True)
        task = (
            "# META ORCHESTRATION HANDOFF\n"
            "meta_request_frame_json: "
            '{"frame_kind":"followup","task_domain":"travel_advisory","execution_mode":"answer_directly",'
            '"primary_objective":"ich hab Lust einen Ausflug zu machen"}\n'
            "meta_clarity_contract_json: "
            '{"primary_objective":"ich hab Lust einen Ausflug zu machen",'
            '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
            '"completion_condition":"concrete_trip_recommendations_named","direct_answer_required":true}\n'
            "meta_context_bundle_json: "
            '{"active_goal":"Ausflug am Wochenende mit Kultur","open_loop":"konkrete Vorschlaege fuer Frankfurt-Umfeld",'
            '"next_expected_step":"konkrete Vorschlaege fuer naechstes Wochenende","current_query":"was kannst du mir fuer das naechste Wochenende empfehlen"}\n'
            "\n"
            "# ORIGINAL USER TASK\n"
            "was kannst du mir fuer das naechste Wochenende empfehlen\n"
        )
        result = await agent.run(task)

    assert "Mainz" in result
    assert "# ADVISORY-ANTWORTSCHWELLE" in captured["enhanced_task"]
    assert "Der Nutzer will jetzt eine konkrete Empfehlung" in captured["enhanced_task"]
    assert "Aktive Anker:" in captured["enhanced_task"]
    assert "Ausflug am Wochenende mit Kultur" in captured["enhanced_task"]
    assert "konkrete Vorschlaege fuer Frankfurt-Umfeld" in captured["enhanced_task"]


@pytest.mark.asyncio
async def test_meta_setup_build_runtime_context_binds_to_original_user_task(monkeypatch):
    captured = {}

    async def _fake_build_meta_context(self):
        return "# TIMUS SYSTEM-KONTEXT\nAktive Routinen: irrelevant"

    async def _fake_base_run(self, task: str):
        captured["enhanced_task"] = task
        return "Final Answer: Ich pruefe zuerst die vorhandenen Twilio- und Inworld-Vorbereitungen."

    monkeypatch.setattr(MetaAgent, "_build_meta_context", _fake_build_meta_context)

    with patch.object(BaseAgent, "run", new=_fake_base_run):
        agent = MetaAgent(tools_description_string="", skip_model_validation=True)
        task = (
            "# META ORCHESTRATION HANDOFF\n"
            "meta_request_frame_json: "
            '{"frame_kind":"new_task","task_domain":"setup_build","execution_mode":"plan_and_delegate",'
            '"primary_objective":"richte fuer mich eine anruffunktion ueber twilio und inworld ein"}\n'
            "meta_clarity_contract_json: "
            '{"primary_objective":"richte fuer mich eine anruffunktion ueber twilio und inworld ein",'
            '"request_kind":"execute_task","answer_obligation":"probe_then_return_concrete_setup_execution_path",'
            '"completion_condition":"first_build_step_or_real_blocker_named","direct_answer_required":false}\n'
            "\n"
            "# ORIGINAL USER TASK\n"
            "richte fuer mich eine anruffunktion ueber twilio und inworld ein\n"
        )
        result = await agent.run(task)

    assert "Twilio" in result
    assert "# PRIMAERES NUTZERZIEL" in captured["enhanced_task"]
    assert "Benutzeranfrage: richte fuer mich eine anruffunktion ueber twilio und inworld ein" in captured["enhanced_task"]
    assert "# SETUP-BUILD AUFTRAGSKLARHEIT" in captured["enhanced_task"]
    assert "Bearbeite die konkrete Benutzeranfrage, nicht den internen Handoff." in captured["enhanced_task"]
    assert "Was moechtest du bauen oder einrichten?" not in captured["enhanced_task"]


@pytest.mark.asyncio
async def test_meta_frame_guard_rejects_setup_build_generic_help(monkeypatch):
    replies = iter(
        [
            (
                "Final Answer: Ich sehe hier einen META ORCHESTRATION HANDOFF mit einer Build/Setup-Aufgabe, "
                "aber mir fehlt die konkrete Benutzeranfrage. Was moechtest du bauen oder einrichten?"
            ),
            "Final Answer: Es gibt bereits Twilio- und Inworld-Vorbereitungen im Repo; als Naechstes solltest du die konkrete Voice-Bridge implementieren.",
        ]
    )
    last_user_messages = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        last_user_messages.append(messages[-1]["content"])
        return next(replies)

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
        max_iterations=3,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"new_task","task_domain":"setup_build","execution_mode":"plan_and_delegate",'
        '"primary_objective":"richte fuer mich eine anruffunktion ueber twilio und inworld ein"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"richte fuer mich eine anruffunktion ueber twilio und inworld ein",'
        '"request_kind":"execute_task","answer_obligation":"probe_then_return_concrete_setup_execution_path",'
        '"completion_condition":"first_build_step_or_real_blocker_named","direct_answer_required":false}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "richte fuer mich eine anruffunktion ueber twilio und inworld ein\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Twilio" in result
    assert len(last_user_messages) == 2
    assert "Meta-Frame-Korrektur" in last_user_messages[1]
    assert "task_domain: setup_build" in last_user_messages[1]
    assert "erkannter_antwort_drift: generic_meta_help" in last_user_messages[1]


@pytest.mark.asyncio
async def test_meta_clarity_blocks_parallel_delegation_for_docs_direct_answer(monkeypatch):
    replies = iter(
        [
            (
                'Action: {"method":"delegate_multiple_agents","params":{"tasks":['
                '{"task_id":"phase","agent":"shell","task":"Lies docs/PHASE_F_PLAN.md"},'
                '{"task_id":"changelog","agent":"shell","task":"Lies docs/CHANGELOG_DEV.md"}'
                ']}}'
            ),
            "Final Answer: Als Naechstes kommt das Zwischenprojekt zur allgemeinen Mehrschritt-Planung.",
        ]
    )
    last_user_messages = []

    async def _fake_detect(self, task: str) -> bool:
        return False

    async def _fake_working_memory(self, task: str) -> str:
        return ""

    def _fake_inject(self, task: str, working_memory_context: str) -> str:
        return task

    async def _fake_llm(self, messages):
        last_user_messages.append(messages[-1]["content"])
        return next(replies)

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
        max_iterations=3,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"direct_answer","task_domain":"docs_status","execution_mode":"answer_directly",'
        '"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"next_recommended_block_or_step_named","direct_answer_required":true,'
        '"delegation_mode":"single_evidence_fetch","max_delegate_calls":1,'
        '"allowed_delegate_agents":["document"],"force_answer_after_delegate_budget":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert "Zwischenprojekt" in result
    assert len(last_user_messages) == 2
    assert "Meta-Clarity Korrektur" in last_user_messages[1]
    assert "erlaubte_delegate_agents: document" in last_user_messages[1]
    assert "Kein anderer delegate_to_agent. Kein delegate_multiple_agents." in last_user_messages[1]


def test_meta_frame_answer_redirect_rejects_question_shaped_direct_recommendation():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"followup","task_domain":"travel_advisory","execution_mode":"answer_directly",'
        '"primary_objective":"ich hab Lust einen Ausflug zu machen"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"ich hab Lust einen Ausflug zu machen",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"concrete_trip_recommendations_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "was kannst du mir fuer das naechste Wochenende empfehlen\n"
    )
    agent._current_task_text = task

    try:
        redirect = agent._build_meta_frame_answer_redirect_prompt(
            task,
            "Bevor ich dir was vorschlage, sag mir kurz ob ihr eher Museen oder Architektur wollt?",
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert redirect is not None
    assert "reask_instead_of_recommendation" in redirect
    assert "Keine weitere Rueckfrage" in redirect


def test_meta_frame_answer_redirect_allows_structured_recommendation_with_optional_next_step():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"followup","task_domain":"travel_advisory","execution_mode":"answer_directly",'
        '"primary_objective":"ich hab Lust einen Ausflug zu machen"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"ich hab Lust einen Ausflug zu machen",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"concrete_trip_recommendations_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "was kannst du mir fuer das naechste Wochenende empfehlen\n"
    )
    agent._current_task_text = task

    try:
        redirect = agent._build_meta_frame_answer_redirect_prompt(
            task,
            (
                "**Kultur-Ausflug am Wochenende:**\n\n"
                "1. Altstadt + kleines Museum\n"
                "2. Schlosspark + Galerie\n"
                "3. Kirche + Café\n\n"
                "Wenn du willst, konkretisiere ich den besten davon."
            ),
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert redirect is None


def test_meta_frame_answer_redirect_allows_markdown_numbered_recommendation():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"followup","task_domain":"travel_advisory","execution_mode":"answer_directly",'
        '"primary_objective":"ich hab Lust einen Ausflug zu machen"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"ich hab Lust einen Ausflug zu machen",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"concrete_trip_recommendations_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "was kannst du mir fuer das naechste Wochenende empfehlen\n"
    )
    agent._current_task_text = task

    try:
        redirect = agent._build_meta_frame_answer_redirect_prompt(
            task,
            (
                "Drei konkrete Kulturausfluege fuer dein Wochenende:\n\n"
                "**1. Museum + Altstadt-Kombination**\n"
                "Ruhiger Einstieg, dann Spaziergang durch die Altstadt.\n\n"
                "**2. Schloss oder historisches Anwesen**\n"
                "Architektur, Geschichte und Park in einem Block.\n\n"
                "**3. Kleinere Galerie oder Atelier-Ausstellung**\n"
                "Persoenlicher, oft weniger ueberlaufen.\n\n"
                "Wenn du willst, konkretisiere ich den passendsten davon."
            ),
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert redirect is None


def test_meta_frame_answer_redirect_rejects_numbered_question_reask():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    task = (
        "# META ORCHESTRATION HANDOFF\n"
        "meta_request_frame_json: "
        '{"frame_kind":"followup","task_domain":"travel_advisory","execution_mode":"answer_directly",'
        '"primary_objective":"ich hab Lust einen Ausflug zu machen"}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"ich hab Lust einen Ausflug zu machen",'
        '"request_kind":"direct_recommendation","answer_obligation":"answer_now_with_single_recommendation",'
        '"completion_condition":"concrete_trip_recommendations_named","direct_answer_required":true}\n'
        "\n"
        "# ORIGINAL USER TASK\n"
        "was kannst du mir fuer das naechste Wochenende empfehlen\n"
    )
    agent._current_task_text = task

    try:
        redirect = agent._build_meta_frame_answer_redirect_prompt(
            task,
            (
                "Gut, lass uns das zusammen durchdenken.\n\n"
                "Bevor ich dir konkrete Empfehlungen gebe, brauche ich noch ein paar Eckdaten:\n\n"
                "1. Welche Stadt oder Region meinst du?\n"
                "2. Was bedeutet Kultur fuer dich genau?\n"
                "3. Ruhe oder Trubel?\n"
                "4. Ganzes Wochenende oder nur ein Tag?\n"
            ),
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert redirect is not None
    assert "reask_instead_of_recommendation" in redirect


def test_detect_meta_answer_domain_does_not_treat_city_mentions_as_location_route():
    answer = (
        "Frankfurt direkt vor der Tuer waere die einfache Variante. "
        "Offenbach, Mainz oder Wiesbaden waeren auch moeglich, wenn du rausfahren willst."
    )

    assert BaseAgent._detect_meta_answer_domain(answer) != "location_route"


def test_meta_clarity_blocks_parallel_delegation_for_setup_build():
    agent = BaseAgent(
        system_prompt_template="Du bist ein Test-Agent.",
        tools_description_string="",
        max_iterations=2,
        agent_type="meta",
        skip_model_validation=True,
    )
    agent._current_task_text = (
        "# META ORCHESTRATION HANDOFF\n"
        'meta_clarity_contract_json: {"primary_objective":"Richte fuer mich eine Anruffunktion ein","request_kind":"execute_task","delegation_mode":"single_structured_probe_then_direct_close","max_delegate_calls":1,"allowed_delegate_agents":["executor"],"force_answer_after_delegate_budget":true}\n'
    )
    try:
        message, reason = agent._check_meta_clarity_tool_intent(
            "delegate_multiple_agents",
            {
                "tasks": [
                    {"task_id": "twilio", "agent": "shell", "task": "grep -R twilio ."},
                    {"task_id": "inworld", "agent": "shell", "task": "grep -R inworld ."},
                ]
            },
        )
    finally:
        asyncio.run(agent.http_client.aclose())

    assert "parallele Delegation" in message
    assert reason == "meta_clarity_parallel_delegation_not_allowed"


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


def test_working_memory_settings_respect_meta_context_authority_limits(monkeypatch):
    monkeypatch.delenv("WORKING_MEMORY_CHAR_BUDGET", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_MAX_RELATED", raising=False)
    monkeypatch.delenv("WORKING_MEMORY_MAX_RECENT_EVENTS", raising=False)
    monkeypatch.setenv("WM_MAX_CHARS", "10000")
    monkeypatch.setenv("WM_MAX_RELATED", "8")
    monkeypatch.setenv("WM_MAX_EVENTS", "15")

    settings = BaseAgent._resolve_working_memory_settings(
        "# META ORCHESTRATION HANDOFF\n"
        "meta_context_authority_json: "
        '{"working_memory_allowed_sections":["KURZZEITKONTEXT"],"working_memory_max_related":1,"working_memory_max_recent":3,"allowed_context_classes":["conversation_state"],"working_memory_query_mode":"objective_only"}\n'
        "\n# ORIGINAL USER TASK\n"
        "wo kann ich am Wochenende hin in Deutschland\n"
    )

    assert settings["followup_context"] is False
    assert settings["max_chars"] == 10000
    assert settings["max_related"] == 1
    assert settings["max_recent_events"] == 3
    assert settings["allowed_sections"] == ("KURZZEITKONTEXT",)
    assert settings["allowed_context_classes"] == ("conversation_state",)
    assert settings["query_mode"] == "objective_only"


def test_resolve_working_memory_query_respects_objective_only_mode():
    query = BaseAgent._resolve_working_memory_query(
        "# META ORCHESTRATION HANDOFF\n"
        "meta_context_authority_json: "
        '{"primary_objective":"Ohne Recherche: Was ist deine Meinung dazu?","working_memory_query_mode":"objective_only"}\n'
        "meta_execution_plan_json: "
        '{"next_step_id":"plan_respond","steps":[{"id":"plan_respond","title":"Direkt antworten","expected_output":"klare Einschaetzung"}]}\n'
        "meta_clarity_contract_json: "
        '{"primary_objective":"Ohne Recherche: Was ist deine Meinung dazu?","completion_condition":"insight_or_options_given"}\n'
        "\n# ORIGINAL USER TASK\n"
        "Ohne Recherche: Was ist deine Meinung dazu, ob Timus intern Modi haben sollte?\n"
    )

    assert query == "Ohne Recherche: Was ist deine Meinung dazu?"
