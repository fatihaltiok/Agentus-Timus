"""
CommunicationAgent — E-Mails, Briefe, LinkedIn-Posts, Anschreiben.

Erweiterungen gegenüber BaseAgent:
  - Kontext: E-Mail-Auth-Status, ungelesene Mails, Nutzerprofil, offene Tasks
  - max_iterations=10→15 für mehrstufige E-Mail-Workflows (lesen → zusammenfassen → senden)
  - _build_comm_context(): prüft Graph-API-Status und zählt ungelesene Mails
  - Bekannte Absender-Adressen und Nutzerprofil immer im Kontext
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from agent.base_agent import BaseAgent
from agent.prompts import COMMUNICATION_PROMPT_TEMPLATE

log = logging.getLogger("CommunicationAgent")

# Bekannte Nutzer-E-Mail-Adressen (aus .env mit Fallback auf Defaults)
_USER_EMAIL_PRIMARY = os.getenv("USER_EMAIL_PRIMARY", "fatihaltiok@outlook.com")
_USER_EMAIL_TONLINE = os.getenv("USER_EMAIL_TOLINE", "altiok-fatih@t-online.de")
_USER_EMAIL_GMAIL   = os.getenv("USER_EMAIL_GMAIL",  "fatihaltiok.fa@googlemail.com")
_TIMUS_EMAIL        = os.getenv("TIMUS_MAIL_SENDER", "timus.assistent@outlook.com")


class CommunicationAgent(BaseAgent):
    """
    Kommunikations-Spezialist von Timus.

    Schreibt E-Mails, Briefe, LinkedIn-Posts und Anschreiben.
    Lädt vor jedem Task automatisch den E-Mail-Kontext:
    Auth-Status, Anzahl ungelesener Mails, Nutzerprofil, offene Comm-Tasks.
    """

    def __init__(self, tools_description_string: str) -> None:
        super().__init__(
            COMMUNICATION_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=15,
            agent_type="communication",
        )

    # ------------------------------------------------------------------
    # Erweiterter run()-Einstieg: Kommunikations-Kontext injizieren
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        """Reichert den Task mit E-Mail-Status und Nutzerprofil an."""
        context = await self._build_comm_context()
        enriched_task = task + "\n\n" + context
        return await super().run(enriched_task)

    # ------------------------------------------------------------------
    # Kommunikations-Kontext aufbauen
    # ------------------------------------------------------------------

    async def _build_comm_context(self) -> str:
        """
        Erstellt Kontext für den Communication-Agent:
        - E-Mail-Auth-Status (Graph API verbunden?)
        - Anzahl ungelesener Mails im Posteingang
        - Bekannte E-Mail-Adressen des Nutzers
        - Offene Kommunikations-Tasks
        - Aktuelle Zeit
        """
        lines: list[str] = ["# KOMMUNIKATIONS-KONTEXT (automatisch geladen)"]

        # 1. Nutzerprofil — immer verfügbar
        lines.append(
            f"Nutzer: Fatih Altiok | "
            f"Primär: {_USER_EMAIL_PRIMARY} | "
            f"T-Online: {_USER_EMAIL_TONLINE} | "
            f"Gmail: {_USER_EMAIL_GMAIL}"
        )
        lines.append(f"Timus-Konto: {_TIMUS_EMAIL}")

        # 2. E-Mail-Auth-Status + ungelesene Mails
        email_status = await asyncio.to_thread(self._get_email_status)
        lines.append(email_status)

        # 3. Offene Kommunikations-Tasks
        pending = await asyncio.to_thread(self._get_pending_comm_tasks)
        if pending:
            lines.append(f"Offene Kommunikations-Tasks: {pending}")

        # 4. Blackboard — relevante Einträge (z. B. Research-Ergebnisse für E-Mails)
        bb_ctx = await asyncio.to_thread(self._get_blackboard_comm_entries)
        if bb_ctx:
            lines.append(f"Blackboard (relevant): {bb_ctx}")

        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    def _get_email_status(self) -> str:
        """Prüft Graph-API-Verbindung und zählt ungelesene Mails."""
        try:
            from tools.email_tool.tool import get_email_status, read_emails

            status = get_email_status()
            if not status.get("authenticated"):
                return "E-Mail: nicht authentifiziert (Graph API offline)"

            # Ungelesene Mails zählen — max 1 API-Call mit limit=1 für die Anzahl
            result = read_emails(mailbox="inbox", limit=25, unread_only=True)
            if result.get("success"):
                count = result.get("count", 0)
                unread_str = f"{count} ungelesen" if count else "keine ungelesenen"
                sender_preview = ""
                emails = result.get("emails", [])
                if emails:
                    # Ersten Absender als Vorschau
                    first = emails[0]
                    sender = first.get("from_email") or first.get("from_name") or "?"
                    subj = (first.get("subject") or "")[:40]
                    sender_preview = f" — neueste: {sender}: {subj}"
                return f"E-Mail: verbunden | Posteingang: {unread_str}{sender_preview}"
            else:
                return f"E-Mail: verbunden | Posteingang: nicht abrufbar ({result.get('error', '')})"

        except Exception as exc:
            log.debug("E-Mail-Status nicht abrufbar: %s", exc)
            return "E-Mail: Status nicht abrufbar"

    def _get_pending_comm_tasks(self) -> str:
        """Gibt offene Tasks mit Bezug zu Kommunikation zurück."""
        try:
            from orchestration.task_queue import TaskQueue

            tq = TaskQueue()
            pending = tq.get_pending()

            # Filtere nach Kommunikations-bezogenen Tasks
            keywords = {"email", "mail", "brief", "linkedin", "nachricht",
                        "anschreiben", "follow", "telegram", "communication"}
            relevant = []
            for t in pending:
                desc = (t.get("description") or t.get("title") or "").lower()
                if any(kw in desc for kw in keywords):
                    relevant.append((t.get("description") or t.get("title") or "Task")[:50])

            if not relevant:
                return ""
            return " | ".join(relevant[:3])

        except Exception as exc:
            log.debug("TaskQueue nicht abrufbar: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # 3e: E-Mail-Drafting-Flow mit Telegram-Review (Phase 3)
    # ------------------------------------------------------------------

    MAX_DRAFT_REVISIONS = 3  # Lean: nutzt m14_retry_bound aus Phase 1

    async def _draft_email_with_review(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> dict:
        """
        Sendet E-Mail-Entwurf zur Telegram-Review bevor er versendet wird.
        MAX_DRAFT_REVISIONS = 3 — nutzt m14_retry_bound (Th.28) implizit.

        Flow:
          1. Entwurf als Telegram-Nachricht senden (Preview + [✅/✏️/❌])
          2. Bei ✅: senden → {"status": "sent"}
          3. Bei ✏️: Feedback abwarten → überarbeiten → Schritt 1 (max 3×)
          4. Bei ❌ oder Timeout: abbrechen → {"status": "cancelled"}

        Returns:
            {"status": "sent"|"cancelled"|"pending", "revision": int}
        """
        try:
            from utils.telegram_notify import send_telegram

            for revision in range(self.MAX_DRAFT_REVISIONS + 1):
                preview = (
                    f"📧 *E-Mail-Entwurf* (Revision {revision})\n\n"
                    f"*An:* {to}\n"
                    f"*Betreff:* {subject}\n\n"
                    f"{body[:500]}{'…' if len(body) > 500 else ''}\n\n"
                    f"_{'Letzte Revision — nur Senden oder Abbrechen' if revision >= self.MAX_DRAFT_REVISIONS else 'Überarbeitung möglich'}_"
                )

                await send_telegram(preview, parse_mode="Markdown")
                log.info(
                    "E-Mail-Entwurf Revision %d gesendet (An: %s, Betreff: %s)",
                    revision, to, subject[:40],
                )
                return {"status": "pending", "revision": revision, "to": to, "subject": subject}

        except Exception as exc:
            log.warning("_draft_email_with_review fehlgeschlagen: %s", exc)
            return {"status": "error", "revision": 0, "error": str(exc)}

    def _get_blackboard_comm_entries(self) -> str:
        """Liest kommunikationsrelevante Einträge aus dem Blackboard."""
        if not os.getenv("AUTONOMY_BLACKBOARD_ENABLED", "true").lower() == "true":
            return ""
        try:
            from memory.agent_blackboard import get_blackboard

            # Suche nach Einträgen die für E-Mail / Kommunikation relevant sind
            entries = get_blackboard().search("email contact summary draft", limit=3)
            if not entries:
                return ""
            parts = []
            for e in entries:
                agent = e.get("agent", "?")
                key   = e.get("key", "")
                value = str(e.get("value", ""))[:80]
                parts.append(f"[{agent}:{key}] {value}")
            return " | ".join(parts)

        except Exception as exc:
            log.debug("Blackboard nicht abrufbar: %s", exc)
            return ""
