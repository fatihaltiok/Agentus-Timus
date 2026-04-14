"""Lokaler Health-Server fuer den Dispatcher-Prozess."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import FastAPI

log = logging.getLogger("DispatcherHealthServer")


def _now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_host(raw_host: Optional[str], default: str = "127.0.0.1") -> str:
    host = str(raw_host or default).strip() or default
    try:
        if ipaddress.ip_address(host).is_unspecified:
            return host
    except ValueError:
        pass
    return host


class DispatcherHealthState:
    def __init__(self, *, host: str, port: int, mcp_health_url: str) -> None:
        self.host = host
        self.port = int(port)
        self.mcp_health_url = str(mcp_health_url or "").strip() or "http://127.0.0.1:5000/health"
        self.started_at = _now_iso()
        self.ready_at = ""
        self.shutdown_at = ""
        self.last_heartbeat_at = self.started_at
        self.phase = "starting"
        self.mode = "daemon"
        self.error = ""
        self.tools_loaded = False
        self.tool_description_count = 0
        self.components: dict[str, dict[str, Any]] = {}
        self.mcp: dict[str, Any] = {
            "url": self.mcp_health_url,
            "reachable": False,
            "ready": False,
            "status": "unknown",
            "detail": "",
            "last_checked_at": "",
        }

    def set_mode(self, mode: str) -> None:
        self.mode = str(mode or "daemon").strip() or "daemon"

    def set_phase(self, phase: str, *, error: str = "") -> None:
        self.phase = str(phase or "starting").strip() or "starting"
        self.error = str(error or "").strip()

    def set_tools_loaded(self, loaded: bool, *, description_count: int = 0) -> None:
        self.tools_loaded = bool(loaded)
        self.tool_description_count = max(0, int(description_count or 0))

    def set_component(
        self,
        name: str,
        *,
        active: bool,
        required: bool,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        key = str(name or "").strip() or "unknown"
        self.components[key] = {
            "active": bool(active),
            "required": bool(required),
            "detail": dict(detail or {}),
            "updated_at": _now_iso(),
        }

    def set_mcp_status(
        self,
        *,
        reachable: bool,
        ready: bool,
        status: str,
        detail: str = "",
    ) -> None:
        self.mcp.update(
            {
                "reachable": bool(reachable),
                "ready": bool(ready),
                "status": str(status or "unknown").strip() or "unknown",
                "detail": str(detail or "").strip(),
                "last_checked_at": _now_iso(),
            }
        )

    def touch_heartbeat(self) -> None:
        self.last_heartbeat_at = _now_iso()

    def mark_ready(self) -> None:
        self.phase = "ready"
        self.ready_at = _now_iso()
        self.error = ""

    def mark_shutdown(self) -> None:
        self.phase = "shutting_down"
        self.shutdown_at = _now_iso()

    def snapshot(self) -> dict[str, Any]:
        degraded_reasons: list[str] = []
        if self.phase == "ready":
            if not self.tools_loaded:
                degraded_reasons.append("tools_not_loaded")
            if not bool(self.mcp.get("reachable")):
                degraded_reasons.append("mcp_unreachable")
            elif not bool(self.mcp.get("ready")):
                degraded_reasons.append("mcp_not_ready")
            for name, component in sorted(self.components.items()):
                if bool(component.get("required")) and not bool(component.get("active")):
                    degraded_reasons.append(f"{name}_inactive")

        if self.phase in {"starting", "waiting_for_mcp", "starting_components"}:
            status = "starting"
            ready = False
        elif self.phase == "ready":
            status = "healthy" if not degraded_reasons else "degraded"
            ready = not degraded_reasons
        elif self.phase == "shutting_down":
            status = "shutting_down"
            ready = False
        elif self.phase == "error":
            status = "error"
            ready = False
            if self.error:
                degraded_reasons.append(self.error)
        else:
            status = "unknown"
            ready = False

        return {
            "status": status,
            "phase": self.phase,
            "ready": ready,
            "host": self.host,
            "port": self.port,
            "mode": self.mode,
            "started_at": self.started_at,
            "ready_at": self.ready_at,
            "shutdown_at": self.shutdown_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "degraded_reasons": degraded_reasons,
            "error": self.error,
            "tools_loaded": self.tools_loaded,
            "tool_description_count": self.tool_description_count,
            "mcp": dict(self.mcp),
            "components": {key: dict(value) for key, value in self.components.items()},
        }


def create_dispatcher_health_app(state: DispatcherHealthState) -> FastAPI:
    app = FastAPI(title="Timus Dispatcher Health", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return state.snapshot()

    return app


class DispatcherHealthServer:
    def __init__(self) -> None:
        self.enabled = _env_bool("DISPATCHER_HEALTH_ENABLED", True)
        self.host = _resolve_host(os.getenv("DISPATCHER_HEALTH_HOST", "127.0.0.1"))
        self.port = int(os.getenv("DISPATCHER_HEALTH_PORT", "5010"))
        self.mcp_health_url = os.getenv("DISPATCHER_HEALTH_MCP_URL", "http://127.0.0.1:5000/health").strip()
        self.state = DispatcherHealthState(host=self.host, port=self.port, mcp_health_url=self.mcp_health_url)
        self._server_task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        if not self.enabled:
            log.info("Dispatcher-Health-Server deaktiviert")
            return
        import uvicorn

        app = create_dispatcher_health_app(self.state)
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(server.serve(), name="dispatcher-health-server")
        log.info("✅ Dispatcher-Health-Server aktiv auf %s:%s", self.host, self.port)

    async def stop(self) -> None:
        self.state.mark_shutdown()
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            self._server_task = None
            log.info("Dispatcher-Health-Server gestoppt")

    async def refresh_mcp_health(self, *, timeout: float = 2.5) -> None:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.mcp_health_url, timeout=timeout)
            if response.status_code != 200:
                self.state.set_mcp_status(
                    reachable=False,
                    ready=False,
                    status=f"http_{response.status_code}",
                    detail=f"status_code={response.status_code}",
                )
                return
            payload = response.json() if "application/json" in response.headers.get("content-type", "") else {}
            self.state.set_mcp_status(
                reachable=True,
                ready=bool(payload.get("ready")),
                status=str(payload.get("status") or "ok"),
                detail=str(payload.get("lifecycle", {}).get("phase") or ""),
            )
        except Exception as e:
            self.state.set_mcp_status(
                reachable=False,
                ready=False,
                status="unreachable",
                detail=str(e)[:160],
            )

    def set_mode(self, mode: str) -> None:
        self.state.set_mode(mode)

    def set_phase(self, phase: str, *, error: str = "") -> None:
        self.state.set_phase(phase, error=error)

    def set_tools_loaded(self, loaded: bool, *, description_count: int = 0) -> None:
        self.state.set_tools_loaded(loaded, description_count=description_count)

    def set_component(
        self,
        name: str,
        *,
        active: bool,
        required: bool,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        self.state.set_component(name, active=active, required=required, detail=detail)

    def mark_ready(self) -> None:
        self.state.mark_ready()

    def touch_heartbeat(self) -> None:
        self.state.touch_heartbeat()

    def snapshot(self) -> dict[str, Any]:
        return self.state.snapshot()
