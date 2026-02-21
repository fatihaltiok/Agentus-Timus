"""
gateway/webhook_gateway.py

FastAPI Webhook-Endpunkt für eingehende Events.
Authentifizierung via HMAC-SHA256.

Konfiguration (.env):
    WEBHOOK_SECRET     = dein HMAC-Secret (beliebiger String)
    WEBHOOK_PORT       = Port (default: 8765)

Endpunkte:
    POST /webhook          Eingehender Event → Task-Queue
    GET  /webhook/health   Health-Check
    GET  /webhook/events   Unterstützte Event-Typen anzeigen

Event-Format (JSON):
    {
        "event_type": "WEBHOOK_PUSH" | "RSS_NEW_ITEM" | "PRICE_ALERT" | "EMAIL_RECEIVED",
        "source":     "github" | "zapier" | "custom" | ...,
        "payload":    { ... event-spezifische Daten ... },
        "timestamp":  "2026-02-21T20:00:00"  (optional)
    }

HMAC-Auth:
    Header: X-Timus-Signature: sha256=<hmac_hex>
    Body:   roher JSON-String
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

log = logging.getLogger("WebhookGateway")

# ──────────────────────────────────────────────────────────────────
# Event-Typen
# ──────────────────────────────────────────────────────────────────

class EventType:
    WEBHOOK_PUSH   = "WEBHOOK_PUSH"    # Generischer Webhook (GitHub, Zapier, etc.)
    RSS_NEW_ITEM   = "RSS_NEW_ITEM"    # Neuer RSS-Artikel
    PRICE_ALERT    = "PRICE_ALERT"     # Preisalarm
    EMAIL_RECEIVED = "EMAIL_RECEIVED"  # Neue E-Mail (Gmail Pub/Sub etc.)
    CUSTOM         = "CUSTOM"          # Benutzerdefiniert

KNOWN_EVENTS = [
    EventType.WEBHOOK_PUSH,
    EventType.RSS_NEW_ITEM,
    EventType.PRICE_ALERT,
    EventType.EMAIL_RECEIVED,
    EventType.CUSTOM,
]

# ──────────────────────────────────────────────────────────────────
# HMAC-Authentifizierung
# ──────────────────────────────────────────────────────────────────

def _verify_hmac(body: bytes, signature_header: Optional[str], secret: str) -> bool:
    """
    Prüft HMAC-SHA256-Signatur.
    Header-Format: 'sha256=<hex>'
    """
    if not secret:
        return True  # Kein Secret konfiguriert → offen (nur für Entwicklung)

    if not signature_header:
        return False

    try:
        prefix, sig_hex = signature_header.split("=", 1)
        if prefix != "sha256":
            return False
    except ValueError:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, sig_hex)


# ──────────────────────────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────────────────────────

def create_webhook_app() -> FastAPI:
    """Erstellt die FastAPI-App für den Webhook-Server."""

    app = FastAPI(title="Timus Webhook Gateway", version="1.0.0")

    @app.get("/webhook/health")
    async def health():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    @app.get("/webhook/events")
    async def list_events():
        return {
            "supported_events": KNOWN_EVENTS,
            "auth": "X-Timus-Signature: sha256=<hmac_hex>",
            "secret_configured": bool(os.getenv("WEBHOOK_SECRET")),
        }

    @app.post("/webhook")
    async def receive_webhook(request: Request):
        secret = os.getenv("WEBHOOK_SECRET", "")
        body = await request.body()

        # HMAC prüfen
        sig = request.headers.get("X-Timus-Signature")
        if not _verify_hmac(body, sig, secret):
            log.warning(f"Webhook abgelehnt: ungültige Signatur von {request.client.host}")
            raise HTTPException(status_code=401, detail="Ungültige Signatur")

        # JSON parsen
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Ungültiges JSON")

        event_type = data.get("event_type", EventType.CUSTOM)
        source = data.get("source", "unknown")
        payload = data.get("payload", {})

        log.info(f"Webhook empfangen: type={event_type} source={source}")

        # Event an Router weiterleiten
        try:
            from gateway.event_router import route_event
            task_id = await route_event(
                event_type=event_type,
                source=source,
                payload=payload,
            )
            return JSONResponse({
                "status": "accepted",
                "task_id": task_id,
                "event_type": event_type,
            })
        except Exception as e:
            log.error(f"Event-Routing fehlgeschlagen: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return app


# ──────────────────────────────────────────────────────────────────
# Server-Verwaltung
# ──────────────────────────────────────────────────────────────────

class WebhookServer:
    """Startet den Webhook-Server im Hintergrund."""

    def __init__(self):
        self._server_task = None
        self._port = int(os.getenv("WEBHOOK_PORT", "8765"))

    async def start(self) -> None:
        import asyncio
        import uvicorn

        app = create_webhook_app()
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self._port,
            log_level="warning",  # Nicht mit Timus-Logs vermischen
            access_log=False,
        )
        server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(
            server.serve(), name="webhook-server"
        )
        log.info(f"✅ Webhook-Server aktiv auf Port {self._port}")

    async def stop(self) -> None:
        if self._server_task:
            self._server_task.cancel()
            log.info("Webhook-Server gestoppt")
