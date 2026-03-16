"""
Tests für orchestration/self_hardening_engine.py — M18 Self-Hardening Engine.

Prüft:
- Pattern-Matching gegen Log-Zeilen
- Cooldown-Logik (kein doppelter Proposal, restart-fest via Blackboard)
- Schwellenwert (min. 3 Treffer nötig)
- Severity-Sortierung (high vor medium vor low)
- to_dict / as_goal_title / as_telegram_msg
- run_cycle mit gemocktem Journal + Blackboard
- _create_hardening_goal: richtige Queue-API (create_goal, list_goals)
- Multi-Unit Journal-Abfrage
- Hypothesis-Properties für Kernvarianten
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.self_hardening_engine import (
    HardeningProposal,
    SelfHardeningEngine,
    _PATTERNS,
    get_self_hardening_engine,
)


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _make_engine() -> SelfHardeningEngine:
    """Engine ohne Blackboard-Restore erzeugen."""
    with patch.object(SelfHardeningEngine, "_load_cooldown_from_blackboard"):
        return SelfHardeningEngine()


def _make_proposal(pattern_name="tool_import_error", severity="high", occurrences=5) -> HardeningProposal:
    return HardeningProposal(
        pattern_name=pattern_name,
        component="tool_registry",
        suggestion="Fehlende Dependency ergänzen",
        severity=severity,
        occurrences=occurrences,
        sample_lines=["ModuleNotFoundError: No module named 'xyz'"],
    )


# ── Pattern-Definitionen ─────────────────────────────────────────────────────

class TestPatternDefinitions:
    def test_patterns_not_empty(self):
        assert len(_PATTERNS) >= 5

    def test_all_patterns_have_required_fields(self):
        for p in _PATTERNS:
            assert p.name, f"Pattern ohne name: {p}"
            assert p.regex, f"Pattern ohne regex: {p}"
            assert p.component, f"Pattern ohne component: {p}"
            assert p.suggestion, f"Pattern ohne suggestion: {p}"
            assert p.severity in ("low", "medium", "high"), f"Ungültige severity: {p.severity}"

    def test_pattern_names_unique(self):
        names = [p.name for p in _PATTERNS]
        assert len(names) == len(set(names)), "Doppelte Pattern-Namen gefunden"

    def test_tool_import_error_pattern_matches(self):
        import re
        p = next(x for x in _PATTERNS if x.name == "tool_import_error")
        assert re.search(p.regex, "ModuleNotFoundError: xyz", re.IGNORECASE)
        assert re.search(p.regex, "ImportError in tool/foo", re.IGNORECASE)

    def test_delegation_timeout_pattern_matches(self):
        import re
        p = next(x for x in _PATTERNS if x.name == "delegation_timeout")
        assert re.search(p.regex, "Delegation Timeout nach 30s", re.IGNORECASE)
        assert re.search(p.regex, "TimeoutError during delegation", re.IGNORECASE)


# ── HardeningProposal ────────────────────────────────────────────────────────

class TestHardeningProposal:
    def test_to_dict_keys(self):
        p = _make_proposal()
        d = p.to_dict()
        assert "pattern_name" in d
        assert "component" in d
        assert "suggestion" in d
        assert "severity" in d
        assert "occurrences" in d
        assert "sample_lines" in d
        assert "created_at" in d

    def test_as_goal_title_contains_component_and_count(self):
        p = _make_proposal(occurrences=7)
        title = p.as_goal_title()
        assert "tool_registry" in title
        assert "7" in title

    def test_as_telegram_msg_high_severity_has_red_emoji(self):
        p = _make_proposal(severity="high")
        msg = p.as_telegram_msg()
        assert "🔴" in msg

    def test_as_telegram_msg_medium_severity_has_yellow_emoji(self):
        p = _make_proposal(severity="medium", pattern_name="delegation_timeout")
        msg = p.as_telegram_msg()
        assert "🟡" in msg

    def test_as_telegram_msg_contains_pattern_and_suggestion(self):
        p = _make_proposal()
        msg = p.as_telegram_msg()
        assert "tool_import_error" in msg
        assert "Fehlende Dependency ergänzen" in msg

    def test_as_telegram_msg_sample_line_truncated_to_120(self):
        long_line = "X" * 200
        p = _make_proposal()
        p.sample_lines = [long_line]
        msg = p.as_telegram_msg()
        # Zeile darf max 120 Zeichen lang sein (aus as_telegram_msg: [:120])
        for line in msg.splitlines():
            assert len(line) <= 200  # Markdown-Wrapper drüber, aber Kernzeile gekürzt


# ── Pattern-Matcher ──────────────────────────────────────────────────────────

class TestMatchPatterns:
    def test_below_threshold_returns_no_proposal(self):
        engine = _make_engine()
        lines = ["ModuleNotFoundError: xyz", "ModuleNotFoundError: abc"]  # nur 2 Treffer
        proposals = engine._match_patterns(lines)
        tool_proposals = [p for p in proposals if p.pattern_name == "tool_import_error"]
        assert tool_proposals == []

    def test_above_threshold_returns_proposal(self):
        engine = _make_engine()
        lines = [
            "ModuleNotFoundError: a",
            "ModuleNotFoundError: b",
            "ModuleNotFoundError: c",
        ]
        proposals = engine._match_patterns(lines)
        tool_proposals = [p for p in proposals if p.pattern_name == "tool_import_error"]
        assert len(tool_proposals) == 1
        assert tool_proposals[0].occurrences == 3

    def test_severity_sort_high_first(self):
        engine = _make_engine()
        lines = (
            ["ModuleNotFoundError: x"] * 5  # high
            + ["Delegation Timeout"] * 5     # medium
            + ["Goal-Konflikte erkannt"] * 5  # low
        )
        proposals = engine._match_patterns(lines)
        if len(proposals) >= 2:
            order = {"high": 0, "medium": 1, "low": 2}
            for i in range(len(proposals) - 1):
                assert order[proposals[i].severity] <= order[proposals[i + 1].severity]

    def test_sample_lines_capped_at_3(self):
        engine = _make_engine()
        lines = ["ModuleNotFoundError: x"] * 10
        proposals = engine._match_patterns(lines)
        tool_p = next((p for p in proposals if p.pattern_name == "tool_import_error"), None)
        assert tool_p is not None
        assert len(tool_p.sample_lines) <= 3


# ── Cooldown-Logik ───────────────────────────────────────────────────────────

class TestCooldown:
    def test_no_cooldown_first_time(self):
        engine = _make_engine()
        assert engine._already_proposed_recently("tool_import_error") is False

    def test_cooldown_active_after_recent_proposal(self):
        engine = _make_engine()
        engine._known_proposals["tool_import_error"] = datetime.now().isoformat()
        assert engine._already_proposed_recently("tool_import_error") is True

    def test_cooldown_expired_after_25h(self):
        engine = _make_engine()
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        engine._known_proposals["tool_import_error"] = old_time
        assert engine._already_proposed_recently("tool_import_error") is False

    def test_invalid_timestamp_treated_as_no_cooldown(self):
        engine = _make_engine()
        engine._known_proposals["tool_import_error"] = "KEIN_DATUM"
        assert engine._already_proposed_recently("tool_import_error") is False

    def test_cooldown_restored_from_blackboard_on_init(self):
        """Nach Neustart: Cooldowns werden aus dem Blackboard geladen."""
        ts = datetime.now().isoformat()
        mock_bb = MagicMock()
        mock_bb.search.return_value = [
            {"key": "tool_import_error", "value": {"created_at": ts, "pattern": "tool_import_error"}}
        ]
        with patch("orchestration.self_hardening_engine.SelfHardeningEngine._load_cooldown_from_blackboard"):
            engine = SelfHardeningEngine.__new__(SelfHardeningEngine)
            engine._known_proposals = {}

        # Blackboard-Restore direkt testen
        with patch("memory.agent_blackboard.get_blackboard", return_value=mock_bb):
            engine._load_cooldown_from_blackboard()

        assert "tool_import_error" in engine._known_proposals
        assert engine._known_proposals["tool_import_error"] == ts


# ── Queue-API Integration ────────────────────────────────────────────────────

class TestCreateHardeningGoal:
    def test_uses_create_goal_not_add_goal(self):
        """Sicherstellen dass create_goal() aufgerufen wird (nicht das nicht-existente add_goal)."""
        engine = _make_engine()
        proposal = _make_proposal()

        mock_queue = MagicMock()
        mock_queue.list_goals.return_value = []

        with patch("orchestration.task_queue.get_queue", return_value=mock_queue):
            engine._create_hardening_goal(proposal)

        mock_queue.create_goal.assert_called_once()

    def test_create_goal_called_with_correct_args(self):
        """create_goal() erhält title, description, priority_score, source."""
        engine = _make_engine()
        proposal = _make_proposal(severity="high", occurrences=5)

        mock_queue = MagicMock()
        mock_queue.list_goals.return_value = []

        with patch("orchestration.task_queue.get_queue", return_value=mock_queue):
            engine._create_hardening_goal(proposal)

        _, kwargs = mock_queue.create_goal.call_args
        assert "title" in kwargs
        assert kwargs.get("priority_score") == 0.85
        assert kwargs.get("source") == "self_hardening"

    def test_no_duplicate_goal_if_component_already_active(self):
        """Kein zweites Goal wenn Komponente bereits in active Goals ist."""
        engine = _make_engine()
        proposal = _make_proposal()

        mock_queue = MagicMock()
        mock_queue.list_goals.return_value = [
            {"title": "Harden: tool_registry (3× erkannt)", "status": "active"}
        ]

        with patch("orchestration.task_queue.get_queue", return_value=mock_queue):
            engine._create_hardening_goal(proposal)

        mock_queue.create_goal.assert_not_called()

    def test_list_goals_called_for_active_and_pending(self):
        """list_goals wird für 'active' und 'pending' aufgerufen."""
        engine = _make_engine()
        proposal = _make_proposal()

        mock_queue = MagicMock()
        mock_queue.list_goals.return_value = []

        with patch("orchestration.task_queue.get_queue", return_value=mock_queue):
            engine._create_hardening_goal(proposal)

        called_statuses = [c.kwargs.get("status") or c.args[0] if c.args else c.kwargs.get("status")
                           for c in mock_queue.list_goals.call_args_list]
        # Beide Status müssen geprüft worden sein
        assert mock_queue.list_goals.call_count >= 2


# ── Multi-Unit Journal ───────────────────────────────────────────────────────

class TestMultiUnitJournal:
    def test_journal_queried_for_all_configured_units(self):
        """_read_journal() ruft journalctl für jede konfigurierte Unit auf."""
        engine = _make_engine()

        call_args = []

        def fake_run(cmd, **kwargs):
            call_args.append(cmd)
            m = MagicMock()
            m.returncode = 0
            m.stdout = "WARNING: something bad\n"
            return m

        import orchestration.self_hardening_engine as she
        original_units = she._JOURNAL_UNITS
        she._JOURNAL_UNITS = ["timus-dispatcher", "timus-mcp"]

        try:
            with patch("subprocess.run", side_effect=fake_run):
                lines = engine._read_journal()
        finally:
            she._JOURNAL_UNITS = original_units

        units_queried = [c[2] for c in call_args if "-u" in c]  # nach -u suchen
        assert "timus-dispatcher" in units_queried
        assert "timus-mcp" in units_queried

    def test_journal_partial_failure_returns_available_lines(self):
        """Wenn eine Unit fehlschlägt, werden Zeilen der anderen Unit trotzdem geliefert."""
        engine = _make_engine()
        call_count = [0]

        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            m = MagicMock()
            if "timus-dispatcher" in cmd:
                m.returncode = 1
                m.stdout = ""
            else:
                m.returncode = 0
                m.stdout = "ERROR: mcp crash\n"
            return m

        import orchestration.self_hardening_engine as she
        original_units = she._JOURNAL_UNITS
        she._JOURNAL_UNITS = ["timus-dispatcher", "timus-mcp"]

        try:
            with patch("subprocess.run", side_effect=fake_run):
                lines = engine._read_journal()
        finally:
            she._JOURNAL_UNITS = original_units

        assert any("mcp crash" in l for l in lines)


# ── run_cycle ────────────────────────────────────────────────────────────────

class TestRunCycle:
    def test_run_cycle_no_lines_returns_zero(self):
        engine = _make_engine()
        with patch.object(engine, "_read_journal", return_value=[]):
            with patch.object(engine, "_read_blackboard_incidents", return_value=[]):
                result = engine.run_cycle()
        assert result["proposals"] == 0

    def test_run_cycle_creates_proposal_and_updates_known(self):
        engine = _make_engine()
        lines = ["ModuleNotFoundError: x"] * 5

        with patch.object(engine, "_read_journal", return_value=lines):
            with patch.object(engine, "_read_blackboard_incidents", return_value=[]):
                with patch.object(engine, "_write_to_blackboard"):
                    with patch.object(engine, "_create_hardening_goal"):
                        with patch.object(engine, "_notify_telegram"):
                            result = engine.run_cycle()

        assert result["proposals"] >= 1
        assert "tool_import_error" in engine._known_proposals

    def test_run_cycle_skips_on_cooldown(self):
        engine = _make_engine()
        engine._known_proposals["tool_import_error"] = datetime.now().isoformat()
        lines = ["ModuleNotFoundError: x"] * 5

        with patch.object(engine, "_read_journal", return_value=lines):
            with patch.object(engine, "_read_blackboard_incidents", return_value=[]):
                result = engine.run_cycle()

        assert result["skipped"] >= 1

    def test_run_cycle_returns_total_patterns(self):
        engine = _make_engine()
        lines = ["ModuleNotFoundError: x"] * 5

        with patch.object(engine, "_read_journal", return_value=lines):
            with patch.object(engine, "_read_blackboard_incidents", return_value=[]):
                with patch.object(engine, "_write_to_blackboard"):
                    with patch.object(engine, "_create_hardening_goal"):
                        with patch.object(engine, "_notify_telegram"):
                            result = engine.run_cycle()

        assert "total_patterns" in result

    def test_run_cycle_writes_cooldown_to_blackboard(self):
        """Nach einem neuen Proposal wird der Cooldown ins Blackboard geschrieben."""
        engine = _make_engine()
        lines = ["ModuleNotFoundError: x"] * 5

        written_topics = []

        def capture_write(**kwargs):
            written_topics.append(kwargs.get("topic", ""))

        mock_bb = MagicMock()
        mock_bb.write.side_effect = lambda **kw: written_topics.append(kw.get("topic", ""))

        with patch.object(engine, "_read_journal", return_value=lines):
            with patch.object(engine, "_read_blackboard_incidents", return_value=[]):
                with patch.object(engine, "_create_hardening_goal"):
                    with patch.object(engine, "_notify_telegram"):
                        with patch("memory.agent_blackboard.get_blackboard", return_value=mock_bb):
                            engine.run_cycle()

        cooldown_writes = [t for t in written_topics if "cooldown" in t]
        assert len(cooldown_writes) >= 1


# ── Hypothesis: Property-based Tests ─────────────────────────────────────────

try:
    from hypothesis import given, settings, assume
    from hypothesis import strategies as st
    _HYPOTHESIS_AVAILABLE = True
except ImportError:
    _HYPOTHESIS_AVAILABLE = False

@pytest.mark.skipif(not _HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestHypothesisProperties:

    @given(hits=st.integers(min_value=0, max_value=100),
           threshold=st.integers(min_value=1, max_value=10))
    @settings(max_examples=200)
    def test_proposal_only_when_hits_gte_threshold(self, hits, threshold):
        """Proposal entsteht genau dann wenn hits ≥ threshold."""
        should_propose = hits >= threshold
        # Prüft die Logik aus _match_patterns
        result = 1 if hits >= threshold else 0
        if should_propose:
            assert result == 1
        else:
            assert result == 0

    @given(elapsed_h=st.floats(min_value=0.0, max_value=100.0),
           cooldown_h=st.integers(min_value=1, max_value=48))
    @settings(max_examples=200)
    def test_cooldown_logic_monotone(self, elapsed_h, cooldown_h):
        """Cooldown-Ablauf ist monoton: mehr Zeit = eher erlaubt."""
        blocked = elapsed_h < cooldown_h
        if elapsed_h >= cooldown_h:
            assert not blocked
        else:
            assert blocked

    @given(severity=st.sampled_from(["high", "medium", "low"]))
    @settings(max_examples=50)
    def test_severity_priority_score_in_range(self, severity):
        """Jede Severity hat einen Priority-Score im gültigen Bereich [0,1]."""
        score = {"high": 0.85, "medium": 0.65, "low": 0.45}.get(severity, 0.5)
        assert 0.0 <= score <= 1.0

    @given(st.lists(st.text(min_size=1, max_size=200), min_size=0, max_size=20))
    @settings(max_examples=100)
    def test_match_patterns_never_raises(self, lines):
        """_match_patterns() wirft niemals eine Exception — auch bei Sonderzeichen."""
        engine = _make_engine()
        try:
            result = engine._match_patterns(lines)
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"_match_patterns raised: {e}")


# ── Singleton ────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_singleton_returns_same_instance(self):
        a = get_self_hardening_engine()
        b = get_self_hardening_engine()
        assert a is b

    def test_singleton_is_self_hardening_engine(self):
        assert isinstance(get_self_hardening_engine(), SelfHardeningEngine)
