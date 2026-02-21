"""
gateway/event_router.py

Verbindet eingehende Events (Webhook, RSS, etc.) mit der Task-Queue.
Event-Typ → Agent/Beschreibung-Mapping konfigurierbar via data/events.json.

Standard-Mappings (überschreibbar):
    RSS_NEW_ITEM   → research (fasst Artikel zusammen)
    PRICE_ALERT    → executor (meldet Preisänderung)
    EMAIL_RECEIVED → reasoning (analysiert E-Mail)
    WEBHOOK_PUSH   → executor (verarbeitet Payload)
    CUSTOM         → executor (generische Verarbeitung)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from orchestration.task_queue import Priority, TaskType, get_queue

log = logging.getLogger("EventRouter")

EVENTS_CONFIG = Path(__file__).parent.parent / "data" / "events.json"

# ──────────────────────────────────────────────────────────────────
# Standard-Mappings
# ──────────────────────────────────────────────────────────────────

DEFAULT_MAPPINGS: dict[str, dict] = {
    "RSS_NEW_ITEM": {
        "agent": "research",
        "priority": Priority.LOW,
        "template": (
            "Lies und fasse den folgenden Artikel kurz zusammen (3-5 Sätze, Deutsch).\n"
            "Titel: {title}\n"
            "Quelle: {feed_title} ({link})\n"
            "Vorschau: {summary}"
        ),
    },
    "PRICE_ALERT": {
        "agent": "executor",
        "priority": Priority.HIGH,
        "template": (
            "Preisalarm: {product} hat den Zielpreis erreicht.\n"
            "Aktueller Preis: {price} {currency}\n"
            "Link: {link}"
        ),
    },
    "EMAIL_RECEIVED": {
        "agent": "reasoning",
        "priority": Priority.NORMAL,
        "template": (
            "Analysiere diese E-Mail und schlage eine Antwort vor:\n"
            "Von: {sender}\n"
            "Betreff: {subject}\n"
            "Inhalt: {body}"
        ),
    },
    "WEBHOOK_PUSH": {
        "agent": "executor",
        "priority": Priority.NORMAL,
        "template": (
            "Eingehender Webhook von {source}.\n"
            "Verarbeite folgende Daten und erstelle eine kurze Zusammenfassung:\n"
            "{payload}"
        ),
    },
    "CUSTOM": {
        "agent": "executor",
        "priority": Priority.NORMAL,
        "template": "Verarbeite diesen Event von {source}: {payload}",
    },
}


# ──────────────────────────────────────────────────────────────────
# Konfigurations-Laden
# ──────────────────────────────────────────────────────────────────

def _load_mappings() -> dict:
    """Lädt events.json falls vorhanden, fällt sonst auf Defaults zurück."""
    if not EVENTS_CONFIG.exists():
        return DEFAULT_MAPPINGS
    try:
        custom = json.loads(EVENTS_CONFIG.read_text(encoding="utf-8"))
        merged = {**DEFAULT_MAPPINGS, **custom}
        log.debug(f"events.json geladen: {len(custom)} custom Mappings")
        return merged
    except Exception as e:
        log.warning(f"events.json nicht lesbar ({e}) — Defaults verwendet")
        return DEFAULT_MAPPINGS


def _build_description(template: str, payload: dict, source: str) -> str:
    """Befüllt ein Template mit Payload-Werten."""
    context = {"source": source, "payload": json.dumps(payload, ensure_ascii=False)[:500]}
    context.update(payload)
    try:
        return template.format_map(context)
    except KeyError:
        # Fehlende Keys durch '?' ersetzen
        import string
        formatter = string.Formatter()
        result = ""
        for literal, field_name, _, _ in formatter.parse(template):
            result += literal
            if field_name is not None:
                result += str(context.get(field_name, f"<{field_name}?>"))
        return result


# ──────────────────────────────────────────────────────────────────
# Haupt-Router
# ──────────────────────────────────────────────────────────────────

async def route_event(
    event_type: str,
    source: str,
    payload: dict,
) -> Optional[str]:
    """
    Routet einen Event zur Task-Queue.

    Args:
        event_type: Typ des Events (RSS_NEW_ITEM, WEBHOOK_PUSH, ...)
        source:     Quelle des Events (Feed-URL, Service-Name, ...)
        payload:    Event-Daten als Dict

    Returns:
        Task-ID oder None bei Fehler
    """
    mappings = _load_mappings()
    mapping = mappings.get(event_type) or mappings.get("CUSTOM")

    if not mapping:
        log.warning(f"Kein Mapping für Event-Typ '{event_type}'")
        return None

    agent = mapping.get("agent", "executor")
    priority = mapping.get("priority", Priority.NORMAL)
    template = mapping.get("template", "{payload}")

    description = _build_description(template, payload, source)
    log.info(
        f"Event geroutet: {event_type} → agent={agent}, "
        f"prio={priority}, desc={description[:60]}"
    )

    queue = get_queue()
    task_id = queue.add(
        description=description,
        priority=priority,
        task_type=TaskType.TRIGGERED,
        target_agent=agent,
    )
    return task_id


# ──────────────────────────────────────────────────────────────────
# events.json initialisieren (wenn nicht vorhanden)
# ──────────────────────────────────────────────────────────────────

def init_events_config() -> None:
    """Erstellt eine kommentierte events.json als Vorlage."""
    if EVENTS_CONFIG.exists():
        return
    EVENTS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    example = {
        "_comment": (
            "Überschreibe hier die Standard-Mappings. "
            "Felder: agent, priority (0=CRITICAL,1=HIGH,2=NORMAL,3=LOW), template"
        ),
        "RSS_NEW_ITEM": {
            "agent": "research",
            "priority": 3,
            "template": (
                "Fasse diesen Artikel in 3 Sätzen zusammen:\n"
                "Titel: {title}\nQuelle: {feed_title}\nVorschau: {summary}"
            ),
        },
    }
    EVENTS_CONFIG.write_text(
        json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"events.json Vorlage erstellt: {EVENTS_CONFIG}")
