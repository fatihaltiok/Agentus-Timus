"""
orchestration/email_autonomy_engine.py

M14: E-Mail-Autonomie-Engine — Policy-Layer für autonome E-Mail-Aktionen.

Entscheidet selbstständig ob E-Mails sinnvoll sind:
- Whitelist-Guard: Empfänger muss in M14_EMAIL_WHITELIST sein
- Topic-Guard: Betreff muss Topic-Whitelist-Stichwort enthalten
- Confidence-Threshold: ≥ 0.85 für sofortige Sendung, sonst Telegram-Approval
- EMAIL_BACKEND: resend (empfohlen) | smtp | msgraph

Feature-Flag: AUTONOMY_M14_ENABLED=false
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("EmailAutonomyEngine")

# ── Singleton ───────────────────────────────────────────────────────────────
_engine: Optional["EmailAutonomyEngine"] = None


def get_email_autonomy_engine() -> "EmailAutonomyEngine":
    global _engine
    if _engine is None:
        _engine = EmailAutonomyEngine()
    return _engine


# ── Dataclass ───────────────────────────────────────────────────────────────

@dataclass
class EmailDecision:
    should_send: bool
    confidence: float        # 0.0–1.0
    reason: str
    recipient: str
    subject: str
    body: str
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    approved: bool = False
    rejected: bool = False

    @property
    def confidence_int(self) -> int:
        """confidence × 100 als Integer (für Lean-Verifikation)."""
        return int(self.confidence * 100)


# ── Engine ──────────────────────────────────────────────────────────────────

class EmailAutonomyEngine:
    """
    Policy-Layer für autonome E-Mail-Entscheidungen.

    ENV-Konfiguration:
        M14_EMAIL_WHITELIST         = kommagetrennte Empfänger-Adressen
        M14_EMAIL_TOPIC_WHITELIST   = kommagetrennte Themen-Stichwörter
        M14_EMAIL_CONFIDENCE        = Schwellwert 0.0–1.0 (default 0.85)
        EMAIL_BACKEND               = resend | smtp | msgraph (default smtp)
        RESEND_API_KEY              = re_xxxx  (nur bei EMAIL_BACKEND=resend)
        RESEND_FROM                 = Timus <timus@deinedomain.com>
    """

    def __init__(self) -> None:
        self._pending: Dict[str, EmailDecision] = {}

    # ── Konfiguration ───────────────────────────────────────────────────────

    @property
    def recipient_whitelist(self) -> List[str]:
        raw = os.getenv("M14_EMAIL_WHITELIST", "")
        return [x.strip().lower() for x in raw.split(",") if x.strip()]

    @property
    def topic_whitelist(self) -> List[str]:
        raw = os.getenv("M14_EMAIL_TOPIC_WHITELIST", "research,alert,summary")
        return [x.strip().lower() for x in raw.split(",") if x.strip()]

    @property
    def confidence_threshold(self) -> float:
        try:
            return float(os.getenv("M14_EMAIL_CONFIDENCE", "0.85"))
        except ValueError:
            return 0.85

    @property
    def email_backend(self) -> str:
        return os.getenv("EMAIL_BACKEND", "smtp").strip().lower()

    # ── Policy-Checks ───────────────────────────────────────────────────────

    def _in_whitelist(self, recipient: str) -> bool:
        """Prüft ob Empfänger in Whitelist ist.

        post: not __return__ or len(self.recipient_whitelist) > 0
        post: __return__ == (recipient.strip().lower() in self.recipient_whitelist)
        """
        if not self.recipient_whitelist:
            return False
        return recipient.strip().lower() in self.recipient_whitelist

    def _topic_allowed(self, subject: str) -> bool:
        """Prüft ob Betreff ein erlaubtes Topic-Stichwort enthält."""
        if not self.topic_whitelist:
            return False
        subject_lower = subject.lower()
        return any(kw in subject_lower for kw in self.topic_whitelist)

    # ── Hauptlogik ──────────────────────────────────────────────────────────

    def evaluate(
        self,
        context: str,
        recipient: str,
        subject: str,
        body: str,
        confidence: float = 0.9,
    ) -> EmailDecision:
        """
        Bewertet ob eine E-Mail autonom gesendet werden soll.

        pre: 0.0 <= confidence <= 1.0
        post: 0.0 <= __return__.confidence <= 1.0
        post: not __return__.should_send or self._in_whitelist(recipient)
        post: not (__return__.confidence < self.confidence_threshold) or not __return__.should_send

        Returns:
            EmailDecision mit should_send, confidence, reason
        """
        # Whitelist-Guard (Lean-Invariante: m14_whitelist_guard)
        if not self._in_whitelist(recipient):
            return EmailDecision(
                should_send=False,
                confidence=0.0,
                reason=f"Empfänger '{recipient}' nicht in Whitelist",
                recipient=recipient,
                subject=subject,
                body=body,
            )

        # Topic-Guard
        if not self._topic_allowed(subject):
            return EmailDecision(
                should_send=False,
                confidence=confidence * 0.5,
                reason=f"Betreff '{subject}' enthält kein erlaubtes Topic-Stichwort",
                recipient=recipient,
                subject=subject,
                body=body,
            )

        # Confidence-Threshold-Check (Lean-Invariante: m14_confidence_threshold)
        if confidence < self.confidence_threshold:
            decision = EmailDecision(
                should_send=False,
                confidence=confidence,
                reason=f"Confidence {confidence:.2f} < Threshold {self.confidence_threshold:.2f} — Approval nötig",
                recipient=recipient,
                subject=subject,
                body=body,
            )
            self._pending[decision.action_id] = decision
            return decision

        # Alles OK → direktes Senden
        return EmailDecision(
            should_send=True,
            confidence=confidence,
            reason="Whitelist ✓, Topic ✓, Confidence ✓",
            recipient=recipient,
            subject=subject,
            body=body,
        )

    async def request_approval(self, decision: EmailDecision) -> None:
        """
        Sendet Telegram-Approval-Request mit [✅ Senden][❌ Abbrechen] Buttons.
        """
        self._pending[decision.action_id] = decision

        msg = (
            f"📧 *M14 E-Mail-Anfrage*\n"
            f"An: `{decision.recipient}`\n"
            f"Betreff: {decision.subject[:80]}\n"
            f"Confidence: {decision.confidence:.0%}\n"
            f"Grund: {decision.reason[:100]}\n\n"
            f"_{decision.body[:200]}_"
        )

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        allowed_ids = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()
        if not token or not allowed_ids:
            log.warning("M14: Telegram nicht konfiguriert — Approval übersprungen")
            return

        chat_ids = []
        for x in allowed_ids.split(","):
            x = x.strip()
            if x:
                try:
                    chat_ids.append(int(x))
                except ValueError:
                    pass

        if not chat_ids:
            return

        try:
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
            bot = Bot(token=token)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ Senden",
                    callback_data=json.dumps({"type": "email_approve", "aid": decision.action_id}),
                ),
                InlineKeyboardButton(
                    "❌ Abbrechen",
                    callback_data=json.dumps({"type": "email_reject", "aid": decision.action_id}),
                ),
            ]])
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
                except Exception as e:
                    log.warning("M14: Telegram-Senden an %d fehlgeschlagen: %s", chat_id, e)
            await bot.close()
        except Exception as e:
            log.warning("M14: Telegram-Bot-Fehler: %s", e)

    def execute_if_approved(self, action_id: str, approved: bool) -> bool:
        """
        Führt die E-Mail-Sendung aus (approved=True) oder verwirft sie (approved=False).

        Returns:
            True wenn ausgeführt/verworfen, False wenn action_id unbekannt
        """
        decision = self._pending.get(action_id)
        if decision is None:
            log.warning("M14: Unbekannte action_id: %s", action_id)
            return False

        if not approved:
            decision.rejected = True
            self._pending.pop(action_id, None)
            log.info("M14: E-Mail an %s abgelehnt (action_id=%s)", decision.recipient, action_id)
            return True

        decision.approved = True
        self._pending.pop(action_id, None)

        # Asynchrone Sendung starten
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._send(decision))
            else:
                loop.run_until_complete(self._send(decision))
        except RuntimeError:
            # Falls kein Event-Loop aktiv
            asyncio.run(self._send(decision))

        return True

    async def _send(self, decision: EmailDecision) -> bool:
        """Sendet E-Mail über konfigurierten Backend (smtp | resend | msgraph)."""
        if self.email_backend == "resend":
            from utils.resend_email import send_email_resend
            success = await send_email_resend(
                to=decision.recipient,
                subject=decision.subject,
                body=decision.body,
            )
        elif self.email_backend == "smtp":
            from utils.smtp_email import send_email_smtp
            success = await send_email_smtp(
                to=decision.recipient,
                subject=decision.subject,
                body=decision.body,
            )
        else:
            # msgraph-Backend: bestehende email_tool nutzen
            try:
                from tools.email_tool.tool import _send_email_msgraph
                success = await _send_email_msgraph(
                    to=decision.recipient,
                    subject=decision.subject,
                    body=decision.body,
                )
            except ImportError:
                log.error("M14: msgraph-Backend nicht verfügbar")
                success = False

        if success:
            log.info("M14: E-Mail an %s gesendet (action_id=%s)", decision.recipient, decision.action_id)
        else:
            log.error("M14: Sendung fehlgeschlagen (action_id=%s)", decision.action_id)
        return success

    def process_pending(self) -> int:
        """Gibt Anzahl wartender Approval-Anfragen zurück."""
        return len(self._pending)

    def get_pending_decisions(self) -> List[Dict]:
        """Gibt alle wartenden Entscheidungen als Dict-Liste zurück."""
        return [
            {
                "action_id": d.action_id,
                "recipient": d.recipient,
                "subject": d.subject,
                "confidence": d.confidence,
                "reason": d.reason,
            }
            for d in self._pending.values()
        ]
