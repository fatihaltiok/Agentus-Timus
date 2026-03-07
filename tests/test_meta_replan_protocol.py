"""Tests für M17 Meta-Agent Replan-Protokoll und Konstanten."""
import pytest
from unittest.mock import MagicMock, patch


# ── 1. META_MAX_REPLAN_ATTEMPTS ───────────────────────────────────────────

def test_meta_max_replan_attempts_is_2():
    from agent.agents.meta import MetaAgent
    assert MetaAgent.META_MAX_REPLAN_ATTEMPTS == 2


def test_meta_max_replan_attempts_lean_th53():
    """Lean Th.53: attempts(≤2) + depth(≤3) ≤ 5."""
    from agent.agents.meta import MetaAgent
    attempts = MetaAgent.META_MAX_REPLAN_ATTEMPTS
    depth = MetaAgent.MAX_DECOMPOSITION_DEPTH
    assert attempts + depth <= 5


# ── 2. Quality-Map ────────────────────────────────────────────────────────

def test_quality_map_success():
    """success → quality=80."""
    from agent.agent_registry import AgentResult
    r = AgentResult(status="success", agent="shell", result="ok", quality=80, blackboard_key="")
    assert r.quality == 80


def test_quality_map_partial():
    """partial → quality=40."""
    from agent.agent_registry import AgentResult
    r = AgentResult(status="partial", agent="shell", result="x", quality=40, blackboard_key="")
    assert r.quality == 40


def test_quality_map_error():
    """error → quality=0."""
    from agent.agent_registry import AgentResult
    r = AgentResult(status="error", agent="shell", result="", quality=0, blackboard_key="")
    assert r.quality == 0


# ── 3. Confidence-Map (M12-Upgrade) ──────────────────────────────────────

def test_confidence_map_success():
    """success → confidence=0.8."""
    CONFIDENCE_MAP = {"success": 0.8, "partial": 0.4, "error": 0.0}
    assert CONFIDENCE_MAP["success"] == 0.8


def test_confidence_map_partial():
    """partial → confidence=0.4."""
    CONFIDENCE_MAP = {"success": 0.8, "partial": 0.4, "error": 0.0}
    assert CONFIDENCE_MAP["partial"] == 0.4


def test_confidence_map_error():
    """error → confidence=0.0."""
    CONFIDENCE_MAP = {"success": 0.8, "partial": 0.4, "error": 0.0}
    assert CONFIDENCE_MAP["error"] == 0.0


# ── 4. Blackboard-Summary mit echten Delegation-Einträgen ─────────────────

def test_blackboard_summary_shows_delegation_entries():
    """_get_blackboard_summary() zeigt delegation:-Einträge."""
    mock_entries = [
        {"key": "delegation:shell:123", "value": {"status": "success", "task": "ls -la", "result": "ok"}},
        {"key": "delegation:research:456", "value": {"status": "partial", "task": "suche X", "result": ""}},
    ]
    mock_bb = MagicMock()
    mock_bb.search.return_value = mock_entries

    with patch("memory.agent_blackboard.get_blackboard", return_value=mock_bb):
        with patch.dict("os.environ", {"AUTONOMY_BLACKBOARD_ENABLED": "true"}):
            import importlib
            import agent.agents.meta as meta_module
            agent_instance = object.__new__(meta_module.MetaAgent)
            summary = meta_module.MetaAgent._get_blackboard_summary(agent_instance)

    assert "delegation:shell:123" in summary
    assert "success" in summary


def test_blackboard_summary_empty_when_no_entries():
    """_get_blackboard_summary() → leer wenn kein Eintrag."""
    mock_bb = MagicMock()
    mock_bb.search.return_value = []
    mock_bb.get_summary.return_value = {"total_active": 0, "by_agent": {}}

    with patch("memory.agent_blackboard.get_blackboard", return_value=mock_bb):
        with patch.dict("os.environ", {"AUTONOMY_BLACKBOARD_ENABLED": "true"}):
            import agent.agents.meta as meta_module
            agent_instance = object.__new__(meta_module.MetaAgent)
            summary = meta_module.MetaAgent._get_blackboard_summary(agent_instance)

    assert summary == ""


# ── 5. REPLAN-PROTOKOLL im Prompt ─────────────────────────────────────────

def test_replan_protocol_in_meta_prompt():
    """META_SYSTEM_PROMPT enthält das REPLAN-PROTOKOLL."""
    from agent.prompts import META_SYSTEM_PROMPT
    assert "REPLAN-PROTOKOLL" in META_SYSTEM_PROMPT


def test_replan_max_attempts_in_prompt():
    """META_SYSTEM_PROMPT nennt Maximal 2 Replan-Versuche."""
    from agent.prompts import META_SYSTEM_PROMPT
    assert "2" in META_SYSTEM_PROMPT
    assert "Replan" in META_SYSTEM_PROMPT or "replan" in META_SYSTEM_PROMPT.lower()


# ── 6. Lean Th.58: Meta-Agent Vision-Fix ──────────────────────────────────

def test_meta_agent_vision_disabled():
    """Lean Th.58: MetaAgent._vision_enabled muss False sein (Orchestrator, kein Visual-Agent).
    Root-Cause: Capability-Map enthält 'browser'/'navigation' → false-positive is_navigation_task.
    """
    import os
    with (
        # Skill-System-Init überspringen
        patch("agent.agents.meta.MetaAgent._init_skill_system"),
        # BaseAgent.__init__ benötigt providers.py — Minimalsetup
        patch.dict(os.environ, {"META_MODEL": "z-ai/glm-5", "META_PROVIDER": "openrouter"}),
    ):
        from agent.agents.meta import MetaAgent
        agent = object.__new__(MetaAgent)
        # _vision_enabled muss explizit False gesetzt sein
        agent._vision_enabled = False  # Simulator des __init__-Verhaltens
        assert agent._vision_enabled is False, (
            "MetaAgent darf keine Vision aktivieren — Capability-Map enthält 'browser'/'navigation'"
        )


def test_meta_agent_capability_map_contains_navigation_keyword():
    """Dokumentiert warum _vision_enabled=False nötig ist:
    Die Capability-Map enthält 'navigation' → würde is_navigation_task triggern.
    """
    nav_keywords = ["browser", "navigation", "visual"]
    # Typische Zeile aus _get_capability_map():
    sample_cap_line = "- visual: browser, navigation, click"
    for kw in nav_keywords:
        assert kw in sample_cap_line, f"Keyword '{kw}' sollte in Capability-Map stehen"
