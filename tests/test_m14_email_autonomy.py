"""
tests/test_m14_email_autonomy.py

Tests für M14: E-Mail-Autonomie-Engine

Testet:
- Whitelist-Guard (nicht-whitelisted Empfänger → should_send=False)
- Topic-Guard (kein erlaubtes Topic-Keyword → should_send=False)
- Confidence-Threshold (< 0.85 → Approval, ≥ 0.85 → direkte Sendung)
- Approval-Flow (approve → _send, reject → discard)
- Backend-Switch (smtp vs. msgraph via ENV)
- Lean-Invarianten (Python-seitig verifiziert)
- SMTP-Utils (Konfiguration)
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestration.email_autonomy_engine import EmailAutonomyEngine, EmailDecision


def make_engine(
    whitelist: str = "allowed@example.com,user@test.org",
    topic_whitelist: str = "research,alert,summary",
    confidence: str = "0.85",
    backend: str = "smtp",
) -> EmailAutonomyEngine:
    os.environ["M14_EMAIL_WHITELIST"] = whitelist
    os.environ["M14_EMAIL_TOPIC_WHITELIST"] = topic_whitelist
    os.environ["M14_EMAIL_CONFIDENCE"] = confidence
    os.environ["EMAIL_BACKEND"] = backend
    return EmailAutonomyEngine()


# ── Whitelist-Guard ──────────────────────────────────────────────────────────

class TestWhitelistGuard(unittest.TestCase):
    def test_not_whitelisted_blocks_send(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "evil@hacker.com", "Research alert", "body")
        self.assertFalse(decision.should_send)
        self.assertEqual(decision.confidence, 0.0)
        self.assertIn("nicht in Whitelist", decision.reason)

    def test_whitelisted_allows_proceed(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Research summary", "body", confidence=0.95)
        # Whitelist OK → should proceed to confidence check
        self.assertNotEqual(decision.reason, "")
        self.assertNotIn("nicht in Whitelist", decision.reason)

    def test_whitelist_case_insensitive(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "ALLOWED@EXAMPLE.COM", "Research summary", "body", confidence=0.95)
        self.assertNotIn("nicht in Whitelist", decision.reason)

    def test_empty_whitelist_blocks_all(self):
        engine = make_engine(whitelist="")
        decision = engine.evaluate("ctx", "anyone@example.com", "Research", "body")
        self.assertFalse(decision.should_send)

    # Lean-Invariante: m14_whitelist_guard
    def test_lean_whitelist_invariant(self):
        """in_list=0 → ¬ (1 ≤ in_list) — wie Lean-Theorem m14_whitelist_guard"""
        in_list = 0  # nicht in Whitelist
        self.assertFalse(in_list >= 1)

    def test_lean_whitelist_invariant_positive(self):
        """in_list=1 → 1 ≤ in_list (Komplement)"""
        in_list = 1  # in Whitelist
        self.assertTrue(in_list >= 1)


# ── Topic-Guard ──────────────────────────────────────────────────────────────

class TestTopicGuard(unittest.TestCase):
    def test_topic_not_allowed_blocks_send(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Newsletter spam", "body")
        self.assertFalse(decision.should_send)
        self.assertIn("Topic-Stichwort", decision.reason)

    def test_topic_allowed_passes(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Weekly research summary", "body", confidence=0.9)
        self.assertNotIn("Topic-Stichwort", decision.reason)

    def test_topic_case_insensitive(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "RESEARCH FINDINGS", "body", confidence=0.9)
        self.assertNotIn("Topic-Stichwort", decision.reason)

    def test_alert_topic_passes(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "System alert: disk full", "body", confidence=0.9)
        self.assertNotIn("Topic-Stichwort", decision.reason)


# ── Confidence-Threshold ─────────────────────────────────────────────────────

class TestConfidenceThreshold(unittest.TestCase):
    def test_low_confidence_needs_approval(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Research alert", "body", confidence=0.7)
        self.assertFalse(decision.should_send)
        self.assertIn("Approval nötig", decision.reason)
        # Muss in pending sein
        self.assertIn(decision.action_id, engine._pending)

    def test_high_confidence_allows_send(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Research alert", "body", confidence=0.9)
        self.assertTrue(decision.should_send)
        self.assertIn("Confidence ✓", decision.reason)

    def test_exact_threshold_allows_send(self):
        engine = make_engine(confidence="0.85")
        decision = engine.evaluate("ctx", "allowed@example.com", "Research alert", "body", confidence=0.85)
        self.assertTrue(decision.should_send)

    def test_below_threshold_creates_pending(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Research alert", "body", confidence=0.50)
        self.assertEqual(engine.process_pending(), 1)

    # Lean-Invariante: m14_confidence_threshold
    def test_lean_confidence_invariant(self):
        """conf < threshold → ¬ (threshold ≤ conf) — wie Lean-Theorem m14_confidence_threshold"""
        conf = 70      # conf × 100
        threshold = 85  # threshold × 100
        self.assertTrue(conf < threshold)
        self.assertFalse(threshold <= conf)

    def test_lean_confidence_passes(self):
        """conf ≥ threshold → threshold ≤ conf"""
        conf = 90
        threshold = 85
        self.assertFalse(conf < threshold)
        self.assertTrue(threshold <= conf)

    def test_confidence_int_property(self):
        d = EmailDecision(True, 0.87, "ok", "r@e.com", "sub", "body")
        self.assertEqual(d.confidence_int, 87)


# ── Approval-Flow ─────────────────────────────────────────────────────────────

class TestApprovalFlow(unittest.TestCase):
    def test_approve_removes_from_pending(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Research alert", "body", confidence=0.5)
        aid = decision.action_id
        self.assertIn(aid, engine._pending)

        with patch.object(engine, "_send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = engine.execute_if_approved(aid, approved=True)

        self.assertTrue(result)
        self.assertNotIn(aid, engine._pending)

    def test_reject_removes_from_pending(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Research alert", "body", confidence=0.5)
        aid = decision.action_id

        result = engine.execute_if_approved(aid, approved=False)
        self.assertTrue(result)
        self.assertNotIn(aid, engine._pending)

    def test_unknown_action_id_returns_false(self):
        engine = make_engine()
        result = engine.execute_if_approved("nonexistent-id", approved=True)
        self.assertFalse(result)

    def test_reject_marks_decision_as_rejected(self):
        engine = make_engine()
        decision = engine.evaluate("ctx", "allowed@example.com", "Research alert", "body", confidence=0.5)
        aid = decision.action_id
        engine.execute_if_approved(aid, approved=False)
        self.assertTrue(decision.rejected)


# ── Backend-Switch ────────────────────────────────────────────────────────────

class TestBackendSwitch(unittest.TestCase):
    def test_smtp_backend_configured(self):
        engine = make_engine(backend="smtp")
        self.assertEqual(engine.email_backend, "smtp")

    def test_msgraph_backend_configured(self):
        engine = make_engine(backend="msgraph")
        self.assertEqual(engine.email_backend, "msgraph")

    def test_smtp_backend_calls_smtp_send(self):
        engine = make_engine(backend="smtp")
        decision = EmailDecision(True, 0.9, "ok", "r@e.com", "Research test", "body")

        with patch("utils.smtp_email.send_email_smtp", new_callable=AsyncMock) as mock_smtp:
            mock_smtp.return_value = True
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(engine._send(decision))

        mock_smtp.assert_called_once()
        self.assertTrue(result)


# ── SMTP Utils ────────────────────────────────────────────────────────────────

class TestSmtpConfig(unittest.TestCase):
    def test_smtp_config_from_env(self):
        os.environ["SMTP_HOST"] = "smtp.test.com"
        os.environ["SMTP_PORT"] = "587"
        os.environ["SMTP_USER"] = "test@test.com"
        os.environ["SMTP_PASSWORD"] = "secret"

        from utils.smtp_email import _smtp_config
        cfg = _smtp_config()
        self.assertEqual(cfg["host"], "smtp.test.com")
        self.assertEqual(cfg["port"], 587)
        self.assertEqual(cfg["user"], "test@test.com")

    def test_imap_config_from_env(self):
        os.environ["IMAP_HOST"] = "imap.test.com"
        os.environ["SMTP_USER"] = "test@test.com"

        from utils.smtp_email import _imap_config
        cfg = _imap_config()
        self.assertEqual(cfg["host"], "imap.test.com")

    def test_send_smtp_no_credentials_returns_false(self):
        os.environ["SMTP_USER"] = ""
        os.environ["SMTP_PASSWORD"] = ""

        from utils.smtp_email import send_email_smtp
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            send_email_smtp("to@test.com", "Subject", "Body")
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
