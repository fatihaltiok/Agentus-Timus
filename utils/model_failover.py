"""
utils/model_failover.py

Failover-Logik für autonome Task-Ausführung.
Versucht bei Fehlern alternative Agenten in definierter Reihenfolge.

Failover-Ketten (nach Capability):
  research    → reasoning → meta → executor
  reasoning   → meta → executor
  development → meta → executor
  creative    → executor
  meta        → executor
  executor    → (kein Failover)
  visual/*    → executor (Fallback ohne Vision)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from utils.error_classifier import classify, ErrorType

log = logging.getLogger("ModelFailover")

# ──────────────────────────────────────────────────────────────────
# Failover-Ketten
# ──────────────────────────────────────────────────────────────────

FAILOVER_CHAINS: dict[str, list[str]] = {
    "research":         ["reasoning", "meta", "executor"],
    "deep_research":    ["reasoning", "meta", "executor"],
    "researcher":       ["reasoning", "meta", "executor"],
    "reasoning":        ["meta", "executor"],
    "analyst":          ["meta", "executor"],
    "debugger":         ["meta", "executor"],
    "development":      ["meta", "executor"],
    "development_agent":["meta", "executor"],
    "coder":            ["meta", "executor"],
    "creative":         ["executor"],
    "creative_agent":   ["executor"],
    "meta":             ["executor"],
    "meta_agent":       ["executor"],
    "executor":         [],             # Letztes Glied — kein Failover
    "task_agent":       [],
    "visual":           ["executor"],
    "visual_agent":     ["executor"],
    "visual_nemotron":  ["executor"],
    "vision_qwen":      ["executor"],
    "web_automation":   ["executor"],
}

MAX_ATTEMPTS = 3      # Primär + max. 2 Failover-Schritte
BASE_BACKOFF  = 2.0   # Sekunden Basis für exponential backoff


# ──────────────────────────────────────────────────────────────────
# Haupt-Funktion
# ──────────────────────────────────────────────────────────────────

async def failover_run_agent(
    agent_name: str,
    query: str,
    tools_description: str,
    session_id: str,
    on_alert: Optional[callable] = None,
) -> Optional[str]:
    """
    Führt run_agent() mit automatischem Failover aus.

    1. Primärer Agent versuchen
    2. Bei retriable Fehler: Backoff + Retry (selber Agent)
    3. Bei Failover-Fehler: nächsten Agent in der Kette versuchen
    4. Bei erschöpften Retries: on_alert() aufrufen

    Args:
        agent_name:        Primärer Agent
        query:             User-Anfrage
        tools_description: Tool-Beschreibungen
        session_id:        Session-ID
        on_alert:          Callback wenn alle Versuche erschöpft (async callable)

    Returns:
        Ergebnis-String oder None bei totalem Ausfall
    """
    from main_dispatcher import run_agent

    # Agenten-Sequenz aufbauen: primär + Failover-Kette
    chain = [agent_name] + FAILOVER_CHAINS.get(agent_name, ["executor"])
    chain = _deduplicate(chain)[:MAX_ATTEMPTS]

    last_error: Optional[Exception] = None
    attempts_log: list[str] = []

    for attempt_idx, current_agent in enumerate(chain):
        try:
            log.info(
                f"[Failover {attempt_idx + 1}/{len(chain)}] "
                f"Agent: {current_agent.upper()} | Session: {session_id}"
            )
            result = await run_agent(
                agent_name=current_agent,
                query=query,
                tools_description=tools_description,
                session_id=session_id,
            )

            if result is not None:
                if attempt_idx > 0:
                    log.info(
                        f"✅ Failover erfolgreich: {current_agent.upper()} "
                        f"nach {attempt_idx} Versuch(en)"
                    )
                return result

            # None-Ergebnis → nächsten Agent versuchen
            log.warning(f"Agent {current_agent} lieferte None — nächsten versuchen")
            attempts_log.append(f"{current_agent}=none")

        except Exception as exc:
            last_error = exc
            classified = classify(exc)
            attempts_log.append(f"{current_agent}={classified.error_type.value}")

            log.warning(
                f"❌ Agent {current_agent.upper()} Fehler: {classified.message} "
                f"[{classified.error_type.value}]"
            )

            # Retry mit Backoff (selber Agent, selber Fehler)
            if classified.retriable and attempt_idx == 0:
                backoff = _backoff(classified.backoff_seconds, attempt_idx)
                log.info(f"  → Retry in {backoff:.1f}s ...")
                await asyncio.sleep(backoff)
                try:
                    result = await run_agent(
                        agent_name=current_agent,
                        query=query,
                        tools_description=tools_description,
                        session_id=f"{session_id}_r",
                    )
                    if result is not None:
                        log.info(f"✅ Retry erfolgreich: {current_agent.upper()}")
                        return result
                except Exception as retry_exc:
                    log.warning(f"  Retry fehlgeschlagen: {retry_exc}")
                    attempts_log.append(f"{current_agent}_retry=fail")

            # Kein Failover möglich oder sinnvoll?
            if not classified.should_failover or attempt_idx == len(chain) - 1:
                break

            # Kurze Pause vor nächstem Agent
            if classified.backoff_seconds > 0:
                await asyncio.sleep(min(classified.backoff_seconds, 5.0))

    # ── Alle Versuche erschöpft ──────────────────────────────────
    error_summary = (
        f"Alle {len(attempts_log)} Versuche fehlgeschlagen: {' → '.join(attempts_log)}\n"
        f"Letzter Fehler: {last_error}"
    )
    log.error(f"💀 Totaler Ausfall | {error_summary}")

    if on_alert and callable(on_alert):
        try:
            await on_alert(
                agent=agent_name,
                query=query,
                attempts=attempts_log,
                last_error=str(last_error),
            )
        except Exception as alert_exc:
            log.error(f"Alert-Fehler: {alert_exc}")

    return None


# ──────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────────────────────────

def _backoff(base: float, attempt: int) -> float:
    """Exponential backoff: base * 2^attempt, max 60s."""
    return min(base * (2 ** attempt), 60.0)


def _deduplicate(lst: list[str]) -> list[str]:
    """Reihenfolge erhalten, Duplikate entfernen."""
    seen: set[str] = set()
    result = []
    for x in lst:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result
