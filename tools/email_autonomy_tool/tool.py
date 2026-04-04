# tools/email_autonomy_tool/tool.py
"""
M14: E-Mail-Autonomie MCP-Tools.

Zwei MCP-Tools:
  - evaluate_email_action       — Bewertet ob E-Mail autonom gesendet werden soll
  - get_pending_email_approvals — Liste wartender Approval-Anfragen

Feature-Flag: AUTONOMY_M14_ENABLED=false
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from tools.tool_registry_v2 import ToolCategory as C, ToolParameter as P, tool

load_dotenv(override=True)
log = logging.getLogger("email_autonomy_tool")


def _m14_enabled() -> bool:
    return os.getenv("AUTONOMY_M14_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


@tool(
    name="evaluate_email_action",
    description=(
        "M14: Bewertet ob eine E-Mail autonom gesendet werden darf. "
        "Prüft Whitelist, Topic-Guard und Confidence-Threshold. "
        "Bei hoher Confidence: direkte Sendung. Bei niedrigerer: Telegram-Approval."
    ),
    parameters=[
        P("context", "str", "Kontext / Begründung für die E-Mail", required=True),
        P("recipient", "str", "Empfänger-E-Mail-Adresse", required=True),
        P("subject", "str", "E-Mail-Betreff", required=True),
        P("body", "str", "E-Mail-Body (Plaintext)", required=True),
        P("confidence", "float", "Confidence-Wert 0.0–1.0 (default: 0.9)", required=False, default=0.9),
    ],
    capabilities=["email", "autonomy"],
    category=C.COMMUNICATION,
)
async def evaluate_email_action(
    context: str,
    recipient: str,
    subject: str,
    body: str,
    confidence: float = 0.9,
) -> Dict[str, Any]:
    if not _m14_enabled():
        return {"error": "M14 ist deaktiviert (AUTONOMY_M14_ENABLED=false)"}

    from orchestration.email_autonomy_engine import get_email_autonomy_engine
    engine = get_email_autonomy_engine()
    decision = engine.evaluate(context, recipient, subject, body, confidence)

    result = {
        "action_id": decision.action_id,
        "should_send": decision.should_send,
        "confidence": decision.confidence,
        "confidence_pct": f"{decision.confidence:.0%}",
        "reason": decision.reason,
        "recipient": decision.recipient,
        "subject": decision.subject,
    }

    if decision.should_send:
        import asyncio
        success = await engine._send(decision)
        result["sent"] = success
        result["status"] = "sent" if success else "send_failed"
    elif not decision.should_send and decision.confidence > 0 and not (
        decision.recipient.strip().lower() not in engine.recipient_whitelist
    ):
        # Approval nötig
        await engine.request_approval(decision)
        result["status"] = "pending_approval"
    else:
        result["status"] = "blocked_by_policy"

    return result


@tool(
    name="get_pending_email_approvals",
    description="M14: Gibt alle wartenden E-Mail-Approval-Anfragen zurück.",
    parameters=[],
    capabilities=["email", "autonomy"],
    category=C.COMMUNICATION,
)
async def get_pending_email_approvals() -> Dict[str, Any]:
    if not _m14_enabled():
        return {"error": "M14 ist deaktiviert (AUTONOMY_M14_ENABLED=false)"}

    from orchestration.email_autonomy_engine import get_email_autonomy_engine
    engine = get_email_autonomy_engine()
    pending = engine.get_pending_decisions()
    return {
        "count": len(pending),
        "pending": pending,
    }
