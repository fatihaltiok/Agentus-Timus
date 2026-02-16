# orchestration/lane_manager.py
"""
Lane Manager - Orchestrierung von Tool-Calls mit "Default serial, explicit parallel".

KONZEPT:
- Jede Session/Task bekommt eine Lane (Isolation)
- Tools laufen standardmaeßig seriell (safe default)
- Parallele Ausführung nur wenn im Tool-Metadata erlaubt
- Queue-Status für Ueberwachung
- Race-Condition-Schutz durch pro-Lane Locks

USAGE:
    from orchestration.lane_manager import LaneManager

    manager = LaneManager()

    # Lane erstellen
    lane = manager.create_lane("session_123")

    # Tool-Call einreihen (seriell default)
    result = await lane.execute_tool("search_web", {"query": "test"})

    # Mehrere Tools parallel (wenn erlaubt)
    results = await lane.execute_parallel([
        ("search_web", {"query": "a"}),
        ("search_web", {"query": "b"}),  # nur wenn parallel_allowed=True
    ])

AUTOR: Timus Development
DATUM: Februar 2026
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, Callable, Tuple
from datetime import datetime
from collections import deque

log = logging.getLogger("LaneManager")


class LaneStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    QUEUED = "queued"
    ERROR = "error"
    CLOSED = "closed"


class ToolCallPriority(int, Enum):
    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


@dataclass
class QueuedToolCall:
    tool_name: str
    params: Dict[str, Any]
    priority: int = ToolCallPriority.NORMAL
    queued_at: float = field(default_factory=time.time)
    future: asyncio.Future = field(default=None)
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class ToolCallResult:
    tool_name: str
    params: Dict[str, Any]
    result: Any
    success: bool
    duration_ms: float
    error: Optional[str] = None
    call_id: str = ""


@dataclass
class LaneStats:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    queue_wait_time_ms: float = 0.0
    parallel_calls: int = 0


class Lane:
    """
    Einzelne Lane fuer eine Session/Task.

    Verwaltet eine Queue von Tool-Calls und fuehrt sie seriell aus,
    es sei denn parallele Ausführung ist explizit erlaubt.
    """

    def __init__(
        self,
        lane_id: str,
        registry,
        max_queue_size: int = 100,
        default_timeout: float = 300.0,
    ):
        self.lane_id = lane_id
        self.registry = registry
        self.max_queue_size = max_queue_size
        self.default_timeout = default_timeout

        self._queue: deque[QueuedToolCall] = deque()
        self._lock = asyncio.Lock()
        self._status = LaneStatus.IDLE
        self._current_call: Optional[QueuedToolCall] = None
        self._stats = LaneStats()
        self._created_at = time.time()
        self._last_activity = time.time()

    @property
    def status(self) -> LaneStatus:
        return self._status

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def is_idle(self) -> bool:
        return self._status == LaneStatus.IDLE and self.queue_size == 0

    @property
    def stats(self) -> LaneStats:
        return self._stats

    def _update_activity(self):
        self._last_activity = time.time()

    async def enqueue(
        self,
        tool_name: str,
        params: Dict[str, Any],
        priority: int = ToolCallPriority.NORMAL,
    ) -> QueuedToolCall:
        """Reiht einen Tool-Call in die Queue ein."""
        if len(self._queue) >= self.max_queue_size:
            raise RuntimeError(
                f"Lane {self.lane_id} queue full ({self.max_queue_size})"
            )

        call = QueuedToolCall(
            tool_name=tool_name,
            params=params,
            priority=priority,
        )

        self._queue.append(call)
        self._update_activity()

        log.debug(
            f"Lane {self.lane_id}: Enqueued {tool_name} (queue={len(self._queue)})"
        )
        return call

    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout: Optional[float] = None,
        bypass_queue: bool = False,
    ) -> ToolCallResult:
        """
        Fuehrt ein Tool aus (seriell, mit Queue).

        Args:
            tool_name: Name des Tools
            params: Parameter fuer das Tool
            timeout: Optionaler Timeout in Sekunden
            bypass_queue: Wenn True, wird die Queue umgangen (direkte Ausfuehrung)

        Returns:
            ToolCallResult mit Ergebnis
        """
        start_time = time.time()
        call_id = str(uuid.uuid4())[:8]

        if bypass_queue:
            return await self._execute_direct(tool_name, params, call_id, timeout)

        async with self._lock:
            self._status = LaneStatus.BUSY
            self._update_activity()

            try:
                result = await self._execute_direct(tool_name, params, call_id, timeout)
                return result
            finally:
                if self._queue:
                    self._status = LaneStatus.QUEUED
                else:
                    self._status = LaneStatus.IDLE

    async def _execute_direct(
        self,
        tool_name: str,
        params: Dict[str, Any],
        call_id: str,
        timeout: Optional[float] = None,
    ) -> ToolCallResult:
        """Direkte Tool-Ausfuehrung mit Statistiken."""
        start_time = time.time()
        self._stats.total_calls += 1

        try:
            effective_timeout = timeout or self.default_timeout

            metadata = self.registry.get_tool(tool_name)
            is_parallel_allowed = getattr(metadata, "parallel_allowed", False)
            tool_timeout = getattr(metadata, "timeout", None)

            if tool_timeout:
                effective_timeout = min(effective_timeout, tool_timeout)

            log.debug(
                f"Lane {self.lane_id}: Executing {tool_name} (timeout={effective_timeout}s)"
            )

            try:
                result = await asyncio.wait_for(
                    self.registry.execute(tool_name, **params),
                    timeout=effective_timeout,
                )

                duration_ms = (time.time() - start_time) * 1000
                self._stats.successful_calls += 1
                self._stats.total_duration_ms += duration_ms

                return ToolCallResult(
                    tool_name=tool_name,
                    params=params,
                    result=result,
                    success=True,
                    duration_ms=duration_ms,
                    call_id=call_id,
                )

            except asyncio.TimeoutError:
                duration_ms = (time.time() - start_time) * 1000
                self._stats.failed_calls += 1
                self._stats.total_duration_ms += duration_ms

                return ToolCallResult(
                    tool_name=tool_name,
                    params=params,
                    result=None,
                    success=False,
                    duration_ms=duration_ms,
                    error=f"Timeout after {effective_timeout}s",
                    call_id=call_id,
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._stats.failed_calls += 1
            self._stats.total_duration_ms += duration_ms

            log.error(f"Lane {self.lane_id}: Tool {tool_name} failed: {e}")

            return ToolCallResult(
                tool_name=tool_name,
                params=params,
                result=None,
                success=False,
                duration_ms=duration_ms,
                error=str(e),
                call_id=call_id,
            )

    async def execute_parallel(
        self,
        calls: List[Tuple[str, Dict[str, Any]]],
        max_concurrent: int = 3,
    ) -> List[ToolCallResult]:
        """
        Fuehrt mehrere Tool-Calls parallel aus (wenn erlaubt).

        Args:
            calls: Liste von (tool_name, params) Tupeln
            max_concurrent: Maximale parallele Calls

        Returns:
            Liste von ToolCallResults
        """
        results = []
        allowed_calls = []
        rejected_calls = []

        for tool_name, params in calls:
            try:
                metadata = self.registry.get_tool(tool_name)
                if getattr(metadata, "parallel_allowed", False):
                    allowed_calls.append((tool_name, params))
                else:
                    rejected_calls.append((tool_name, params))
                    log.warning(
                        f"Lane {self.lane_id}: Tool {tool_name} does not allow parallel execution"
                    )
            except ValueError:
                rejected_calls.append((tool_name, params))

        for tool_name, params in rejected_calls:
            results.append(
                ToolCallResult(
                    tool_name=tool_name,
                    params=params,
                    result=None,
                    success=False,
                    duration_ms=0,
                    error="Tool not allowed for parallel execution",
                )
            )

        if not allowed_calls:
            return results

        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_semaphore(
            tool_name: str, params: Dict
        ) -> ToolCallResult:
            async with semaphore:
                return await self.execute_tool(tool_name, params, bypass_queue=True)

        self._status = LaneStatus.BUSY
        self._update_activity()
        self._stats.parallel_calls += len(allowed_calls)

        try:
            tasks = [
                execute_with_semaphore(name, params) for name, params in allowed_calls
            ]
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in parallel_results:
                if isinstance(r, Exception):
                    results.append(
                        ToolCallResult(
                            tool_name="unknown",
                            params={},
                            result=None,
                            success=False,
                            duration_ms=0,
                            error=str(r),
                        )
                    )
                else:
                    results.append(r)

        finally:
            self._status = LaneStatus.IDLE

        return results

    def get_status_report(self) -> Dict[str, Any]:
        """Gibt einen Status-Bericht zurueck."""
        return {
            "lane_id": self.lane_id,
            "status": self._status.value,
            "queue_size": self.queue_size,
            "total_calls": self._stats.total_calls,
            "successful_calls": self._stats.successful_calls,
            "failed_calls": self._stats.failed_calls,
            "total_duration_ms": round(self._stats.total_duration_ms, 2),
            "parallel_calls": self._stats.parallel_calls,
            "created_at": datetime.fromtimestamp(self._created_at).isoformat(),
            "last_activity": datetime.fromtimestamp(self._last_activity).isoformat(),
            "idle_seconds": round(time.time() - self._last_activity, 2),
        }


class LaneManager:
    """
    Zentraler Manager fuer alle Lanes.

    Verwaltet:
    - Lane-Erstellung und -Lifecycle
    - Default-Einstellungen
    - Globale Statistiken
    """

    def __init__(
        self,
        registry=None,
        max_lanes: int = 100,
        default_timeout: float = 300.0,
        lane_idle_timeout: float = 3600.0,
    ):
        self.registry = registry
        self.max_lanes = max_lanes
        self.default_timeout = default_timeout
        self.lane_idle_timeout = lane_idle_timeout

        self._lanes: Dict[str, Lane] = {}
        self._lock = asyncio.Lock()
        self._created_at = time.time()

    def set_registry(self, registry):
        """Setzt die Tool-Registry (optional, kann auch spaeter gesetzt werden)."""
        self.registry = registry

    async def create_lane(
        self,
        lane_id: Optional[str] = None,
        **kwargs,
    ) -> Lane:
        """
        Erstellt eine neue Lane.

        Args:
            lane_id: Optionaler Lane-ID (sonst wird einer generiert)
            **kwargs: Zusatzliche Parameter fuer die Lane

        Returns:
            Die erstellte Lane
        """
        if not self.registry:
            raise RuntimeError("Registry not set. Call set_registry() first.")

        async with self._lock:
            if len(self._lanes) >= self.max_lanes:
                await self._cleanup_idle_lanes()

                if len(self._lanes) >= self.max_lanes:
                    raise RuntimeError(f"Maximum lanes reached ({self.max_lanes})")

            effective_id = lane_id or str(uuid.uuid4())[:8]

            if effective_id in self._lanes:
                log.debug(f"Lane {effective_id} already exists, returning existing")
                return self._lanes[effective_id]

            lane = Lane(
                lane_id=effective_id,
                registry=self.registry,
                default_timeout=kwargs.get("timeout", self.default_timeout),
            )

            self._lanes[effective_id] = lane
            log.info(f"Created lane {effective_id} (total={len(self._lanes)})")

            return lane

    async def get_lane(self, lane_id: str) -> Optional[Lane]:
        """Holt eine bestehende Lane."""
        return self._lanes.get(lane_id)

    async def get_or_create_lane(self, lane_id: str) -> Lane:
        """Holt oder erstellt eine Lane."""
        lane = await self.get_lane(lane_id)
        if lane:
            return lane
        return await self.create_lane(lane_id)

    async def close_lane(self, lane_id: str) -> bool:
        """Schliesst eine Lane."""
        async with self._lock:
            if lane_id in self._lanes:
                lane = self._lanes[lane_id]
                lane._status = LaneStatus.CLOSED
                del self._lanes[lane_id]
                log.info(f"Closed lane {lane_id} (remaining={len(self._lanes)})")
                return True
            return False

    async def _cleanup_idle_lanes(self) -> int:
        """Raeumt inaktive Lanes auf."""
        now = time.time()
        closed = 0

        for lane_id, lane in list(self._lanes.items()):
            if lane.is_idle and (now - lane._last_activity) > self.lane_idle_timeout:
                await self.close_lane(lane_id)
                closed += 1

        if closed:
            log.info(f"Cleaned up {closed} idle lanes")

        return closed

    def get_all_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken aller Lanes zurueck."""
        return {
            "total_lanes": len(self._lanes),
            "max_lanes": self.max_lanes,
            "lanes": {
                lane_id: lane.get_status_report()
                for lane_id, lane in self._lanes.items()
            },
            "created_at": datetime.fromtimestamp(self._created_at).isoformat(),
        }

    def list_lanes(self) -> List[str]:
        """Listet alle Lane-IDs auf."""
        return list(self._lanes.keys())


lane_manager = LaneManager()
