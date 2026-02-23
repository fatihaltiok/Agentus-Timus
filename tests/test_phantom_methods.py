"""Tests für B.4 — Phantommethoden werden durch SYSTEM_ONLY_TOOLS blockiert."""
import pytest
from agent.base_agent import BaseAgent


def _agent_instance():
    """Erstellt Minimal-BaseAgent ohne echten MCP-Server."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.action_call_counts = {}
    agent.last_skip_times = {}
    agent.recent_actions = []
    return agent


class TestPhantomMethods:
    def test_run_tool_blocked(self):
        agent = _agent_instance()
        skip, reason = agent.should_skip_action("run_tool", {})
        assert skip is True
        assert reason is not None

    def test_communicate_blocked(self):
        agent = _agent_instance()
        skip, reason = agent.should_skip_action("communicate", {})
        assert skip is True

    def test_final_answer_blocked(self):
        agent = _agent_instance()
        skip, reason = agent.should_skip_action("final_answer", {})
        assert skip is True

    def test_task_complete_blocked(self):
        agent = _agent_instance()
        skip, reason = agent.should_skip_action("task_complete", {})
        assert skip is True

    def test_no_action_needed_blocked(self):
        agent = _agent_instance()
        skip, reason = agent.should_skip_action("no_action_needed", {})
        assert skip is True

    def test_existing_system_tools_still_blocked(self):
        """Alte Einträge (add_interaction, end_session) bleiben geblockt."""
        agent = _agent_instance()
        for tool in ("add_interaction", "end_session", "get_memory_stats"):
            skip, _ = agent.should_skip_action(tool, {})
            assert skip is True, f"{tool} sollte geblockt sein"

    def test_legitimate_tool_not_blocked(self):
        """Normale Tools wie search_web werden nicht durch SYSTEM_ONLY_TOOLS blockiert."""
        agent = _agent_instance()
        skip, _ = agent.should_skip_action("search_web", {"query": "test"})
        assert skip is False

    def test_system_only_tools_contains_phantoms(self):
        """Direkte Überprüfung der Klassen-Definition."""
        expected = {"run_tool", "communicate", "final_answer", "task_complete", "no_action_needed"}
        assert expected.issubset(BaseAgent.SYSTEM_ONLY_TOOLS)
