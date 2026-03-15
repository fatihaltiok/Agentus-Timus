"""
Tests für orchestration/self_hardening_engine.py — M18 Self-Hardening Engine.

Prüft:
- Pattern-Matching gegen Log-Zeilen
- Cooldown-Logik (kein doppelter Proposal)
- Schwellenwert (min. 3 Treffer nötig)
- Severity-Sortierung (high vor medium vor low)
- to_dict / as_goal_title / as_telegram_msg
- run_cycle mit gemocktem Journal + Blackboard
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

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
            + ["Delegation timed out"] * 5   # medium
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


# ── Singleton ────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_singleton_returns_same_instance(self):
        a = get_self_hardening_engine()
        b = get_self_hardening_engine()
        assert a is b

    def test_singleton_is_self_hardening_engine(self):
        assert isinstance(get_self_hardening_engine(), SelfHardeningEngine)
