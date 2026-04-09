"""
Agent Registry - Ermoeglicht dynamische Agent-zu-Agent Delegation.

FEATURES:
- Zentrale Registry mit Factory-Pattern (Lazy-Instantiierung)
- Agent-zu-Agent Delegation als MCP-Tool-Call
- Capability-basierte Agent-Auswahl
- Loop-Prevention via Delegation-Stack
"""

import asyncio
import logging
import os
import re
import time
import uuid
import httpx
from contextlib import suppress
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from contextvars import ContextVar

from agent.shared.delegation_handoff import parse_delegation_handoff
from orchestration.approval_auth_contract import normalize_phase_d_workflow_payload
from orchestration.llm_budget_guard import cap_parallelism_for_budget
from orchestration.orchestration_policy import evaluate_parallel_tasks
from orchestration.specialist_context import (
    assess_specialist_context_alignment,
    extract_specialist_context_from_handoff_data,
    parse_specialist_signal_response,
)
from orchestration.autonomy_observation import record_autonomy_observation
from orchestration.request_correlation import get_current_request_correlation

log = logging.getLogger("AgentRegistry")

# Externer SSE-Hook — wird von mcp_server.py beim Start gesetzt.
# Signatur: (from_agent: str, to_agent: str, status: str) -> None
_delegation_sse_hook: Optional[Callable] = None
# Externer C4-Hook — wird von mcp_server.py gesetzt.
# Signatur: (payload: Dict[str, Any]) -> None
_delegation_transport_hook: Optional[Callable[[Dict[str, Any]], None]] = None


@dataclass
class AgentSpec:
    """Beschreibt einen Agenten ohne ihn zu instanziieren."""
    name: str
    agent_type: str
    capabilities: List[str]
    factory: Callable
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Strukturiertes Delegationsergebnis (M17)."""
    status: str          # "success" | "partial" | "error"
    agent: str           # agent_type z.B. "shell"
    result: str          # Ergebnis-Text
    quality: int         # 0–100
    blackboard_key: str  # Key unter dem Ergebnis im Blackboard liegt
    error: str = ""      # Fehlermeldung bei status=="error"
    metadata: Dict[str, Any] = field(default_factory=dict)  # Strukturierte Key-Values
    artifacts: List[Dict[str, Any]] = field(default_factory=list)  # Typed file refs etc.


class DelegationProgressTimeout(TimeoutError):
    """Agent zeigte innerhalb des Startfensters keinen verwertbaren Fortschritt."""


class AgentRegistry:
    """
    Zentrale Registry fuer Agent-zu-Agent Delegation.

    - Registriert Agent-Blueprints (AgentSpec) ohne sofortige Instanziierung
    - Lazy-Instantiierung: Agent wird erst bei erster Delegation erstellt
    - Loop-Prevention via Delegation-Stack
    """

    MAX_DELEGATION_DEPTH = 3
    _DELEGATION_TASK_TYPE_RE = re.compile(r"^\s*-?\s*task_type:\s*([^\n]+)", re.IGNORECASE | re.MULTILINE)
    _ERROR_TEXT_PATTERNS = (
        re.compile(r"^\s*(?:error|fehler)\s*:", re.IGNORECASE),
        re.compile(r"invalid_request_error", re.IGNORECASE),
        re.compile(r"credit balance is too low", re.IGNORECASE),
        re.compile(r"ist ein system-tool und darf nicht direkt aufgerufen werden", re.IGNORECASE),
        re.compile(r"kein erfolgreicher send_email-tool-call", re.IGNORECASE),
    )
    AGENT_TYPE_ALIASES = {
        "development": "developer",
        "dev": "developer",
        "researcher": "research",
        "analyst": "reasoning",
        "vision": "visual",
        "daten": "data",
        "bash": "shell",
        "terminal": "shell",
        "monitoring": "system",
        "koordinator": "meta",
        "orchestrator": "meta",
    }

    def __init__(self):
        self._specs: Dict[str, AgentSpec] = {}
        self._instances: Dict[str, Any] = {}
        self._tools_description: Optional[str] = None
        # Task-lokaler Delegation-Stack: verhindert False-Positives bei Parallel-Requests.
        self._delegation_stack_var: ContextVar[tuple[str, ...]] = ContextVar(
            "timus_delegation_stack", default=()
        )

    def _resolve_effective_session_id(
        self, from_agent: str, session_id: Optional[str]
    ) -> Optional[str]:
        """Leitet effektive Session-ID aus Parameter oder Source-Agent ab."""
        if session_id:
            return session_id

        source_instance = self._instances.get(from_agent)
        if source_instance is not None:
            return getattr(source_instance, "conversation_session_id", None)
        return None

    def _log_canvas_delegation(
        self,
        *,
        from_agent: str,
        to_agent: str,
        session_id: Optional[str],
        status: str,
        task: str = "",
        message: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Best-effort Logging fuer Delegation im Canvas."""
        if not session_id:
            return

        try:
            from orchestration.canvas_store import canvas_store

            canvas_id = canvas_store.get_canvas_id_for_session(session_id)
            if not canvas_id:
                return

            from_node = f"agent:{from_agent}"
            to_node = f"agent:{to_agent}"

            canvas_store.upsert_node(
                canvas_id=canvas_id,
                node_id=from_node,
                node_type="agent",
                title=from_agent,
                status="running" if status == "running" else "completed",
                metadata={"last_session_id": session_id},
            )
            canvas_store.upsert_node(
                canvas_id=canvas_id,
                node_id=to_node,
                node_type="agent",
                title=to_agent,
                status=status,
                metadata={"last_session_id": session_id},
            )
            edge = canvas_store.add_edge(
                canvas_id=canvas_id,
                source_node_id=from_node,
                target_node_id=to_node,
                label="delegate_to_agent",
                kind="delegation",
                metadata={"session_id": session_id},
            )
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="delegation",
                status=status,
                agent=from_agent,
                node_id=to_node,
                session_id=session_id,
                message=message or f"{from_agent} -> {to_agent}",
                payload={
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                    "task_preview": (task or "")[:200],
                    "edge_id": edge.get("id", ""),
                    **(payload or {}),
                },
            )
        except Exception as e:
            log.debug(f"Canvas-Delegation-Logging uebersprungen: {e}")

    def normalize_agent_name(self, name: str) -> str:
        """Normalisiert Agent-Namen (Lowercase + Alias-Aufloesung)."""
        normalized = (name or "").strip().lower()
        return self.AGENT_TYPE_ALIASES.get(normalized, normalized)

    def get_current_agent_name(self) -> Optional[str]:
        """Liefert den aktuell laufenden delegierten Agenten (falls vorhanden)."""
        stack = self._delegation_stack_var.get()
        return stack[-1] if stack else None

    def register_spec(
        self,
        name: str,
        agent_type: str,
        capabilities: List[str],
        factory: Callable,
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registriert ein Agent-Blueprint (ohne zu instanziieren)."""
        self._specs[name] = AgentSpec(
            name=name,
            agent_type=agent_type,
            capabilities=capabilities,
            factory=factory,
            extra_kwargs=extra_kwargs or {},
        )
        log.info(f"AgentSpec registriert: {name} (capabilities={capabilities})")

    async def _get_tools_description(self) -> str:
        """Holt Tools-Description vom MCP-Server (lazy, gecacht)."""
        if not self._tools_description:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get("http://127.0.0.1:5000/get_tool_descriptions")
                data = resp.json()
                self._tools_description = data["descriptions"]
            log.info("Tools-Description vom MCP-Server geladen")
        return self._tools_description

    async def _get_or_create(self, name: str) -> Any:
        """Lazy-Instantiierung: Agent wird erst bei erster Delegation erstellt."""
        if name not in self._instances:
            spec = self._specs[name]
            tools_desc = await self._get_tools_description()
            self._instances[name] = spec.factory(
                tools_description_string=tools_desc,
                **spec.extra_kwargs,
            )
            log.info(f"Agent instanziiert: {name} ({spec.factory.__name__})")
        return self._instances[name]

    # Strings die auf ein nur teilweise abgeschlossenes Ergebnis hinweisen
    _PARTIAL_MARKERS = frozenset({"Limit erreicht.", "Max Iterationen."})
    _PARTIAL_TEXT_PATTERNS = (
        re.compile(r"maximale anzahl an schritten erreicht", re.IGNORECASE),
        re.compile(r"ohne finale antwort", re.IGNORECASE),
        re.compile(r"max(?:imale)?\s+iterationen?", re.IGNORECASE),
    )

    @classmethod
    def _extract_handoff_task_type(cls, task: str) -> str:
        text = str(task or "")
        match = cls._DELEGATION_TASK_TYPE_RE.search(text)
        if not match:
            return ""
        return match.group(1).strip().lower()

    @staticmethod
    def _infer_observation_source(session_id: str) -> str:
        normalized = str(session_id or "").strip().lower()
        if normalized.startswith("tg_"):
            return "telegram_chat"
        if normalized.startswith("canvas_"):
            return "canvas_chat"
        if normalized.startswith("auto_"):
            return "autonomous_runner"
        return "delegation"

    @staticmethod
    def _extract_first_email_address(text: str) -> str:
        match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", str(text or ""), re.IGNORECASE)
        return str(match.group(0) if match else "").strip()

    @classmethod
    def _extract_communication_delivery_payload(
        cls,
        *,
        task: str,
        raw: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        from_agent: str,
        to_agent: str,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        if to_agent != "communication":
            return None

        handoff = parse_delegation_handoff(task)
        handoff_data = dict(handoff.handoff_data or {}) if handoff else {}
        raw_dict = dict(raw) if isinstance(raw, dict) else {}
        nested = dict(raw_dict.get("data") or {}) if isinstance(raw_dict.get("data"), dict) else {}
        effective_metadata = dict(metadata or {})
        artifact_items = list(artifacts or [])

        recipient = (
            str(handoff_data.get("recipient") or "").strip()
            or str(raw_dict.get("to") or "").strip()
            or str(nested.get("to") or "").strip()
        )
        subject = (
            str(handoff_data.get("subject") or "").strip()
            or str(handoff_data.get("subject_hint") or "").strip()
            or str(raw_dict.get("subject") or "").strip()
            or str(nested.get("subject") or "").strip()
        )
        backend = (
            str(raw_dict.get("backend") or "").strip()
            or str(nested.get("backend") or "").strip()
            or str(effective_metadata.get("backend") or "").strip()
        )
        attachment_path = (
            str(handoff_data.get("attachment_path") or "").strip()
            or str(raw_dict.get("attachment_path") or "").strip()
            or str(nested.get("attachment_path") or "").strip()
        )
        attachment_name = (
            str(raw_dict.get("attachment") or "").strip()
            or str(nested.get("attachment") or "").strip()
        )
        if not attachment_path:
            for item in artifact_items:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                if path:
                    attachment_path = path
                    break
        if not attachment_name and attachment_path:
            attachment_name = attachment_path.rsplit("/", 1)[-1]

        lower_task = str(task or "").lower()
        email_like = bool(
            recipient
            or "send_email" in lower_task
            or "e-mail" in lower_task
            or "email" in lower_task
            or "anhang" in lower_task
            or cls._extract_first_email_address(task)
        )
        if not email_like:
            return None

        if not recipient:
            recipient = cls._extract_first_email_address(task)

        correlation = get_current_request_correlation()
        return {
            "request_id": str(correlation.get("request_id") or "").strip(),
            "session_id": str(session_id or correlation.get("session_id") or "").strip(),
            "source": cls._infer_observation_source(session_id or str(correlation.get("session_id") or "")),
            "from_agent": from_agent,
            "agent": to_agent,
            "channel": "email",
            "recipient": recipient,
            "subject": subject[:180],
            "backend": backend,
            "attachment": attachment_name[:180],
            "attachment_path": attachment_path[:240],
        }

    @classmethod
    def _record_communication_delivery_observation(
        cls,
        *,
        event_type: str,
        task: str,
        raw: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        from_agent: str,
        to_agent: str,
        session_id: str,
        error: str = "",
    ) -> None:
        payload = cls._extract_communication_delivery_payload(
            task=task,
            raw=raw,
            metadata=metadata,
            artifacts=artifacts,
            from_agent=from_agent,
            to_agent=to_agent,
            session_id=session_id,
        )
        if not payload:
            return
        if error:
            payload["error"] = str(error)[:240]
        record_autonomy_observation(event_type, payload)

    @classmethod
    def _is_simple_live_lookup_delegation(cls, agent_name: str, task: str) -> bool:
        return agent_name == "executor" and cls._extract_handoff_task_type(task) == "simple_live_lookup"

    @classmethod
    def _select_delegation_timeout(cls, agent_name: str, task: str = "") -> float:
        """Waehlt den Default-Timeout pro Agentenrolle."""
        if cls._is_simple_live_lookup_delegation(agent_name, task):
            return float(os.getenv("EXECUTOR_LOOKUP_TIMEOUT", "60"))
        if agent_name == "research":
            return float(os.getenv("RESEARCH_TIMEOUT", "600"))
        return float(os.getenv("DELEGATION_TIMEOUT", "120"))

    @classmethod
    def _select_progress_timeout(cls, agent_name: str, task: str = "") -> float:
        """Kurzes Startfenster, in dem ein delegierter Executor Fortschritt zeigen muss."""
        if agent_name != "executor":
            return 0.0
        configured = float(os.getenv("EXECUTOR_PROGRESS_TIMEOUT", "15"))
        return min(max(1.0, configured), cls._select_delegation_timeout(agent_name, task))

    @staticmethod
    def _timeout_status_for_agent(agent_name: str) -> str:
        """Research-Timeouts sind partiell, andere Timeouts bleiben Fehler."""
        return "partial" if agent_name == "research" else "error"

    @classmethod
    def _build_timeout_metadata(
        cls,
        *,
        agent_name: str,
        timeout_seconds: float,
        session_id: Optional[str],
        attempts: int,
        timeout_phase: str = "run",
    ) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
            "attempts": attempts,
            "timeout_phase": timeout_phase,
        }
        if session_id:
            meta["session_id"] = session_id
        if agent_name == "research":
            meta["recovery_hint"] = (
                "Recherche enger formulieren und genau einmal erneut delegieren."
            )
        return meta

    @staticmethod
    def _emit_transport_progress(
        *,
        from_agent: str,
        to_agent: str,
        session_id: str,
        stage: str,
        payload: Dict[str, Any],
    ) -> None:
        if _delegation_transport_hook is None:
            return
        try:
            _delegation_transport_hook(
                {
                    "kind": str(payload.get("kind") or "progress").strip().lower() or "progress",
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                    "session_id": session_id,
                    "stage": stage,
                    "payload": dict(payload),
                }
            )
        except Exception:
            pass

    @staticmethod
    def _derive_specialist_context_signal(task: str) -> Dict[str, Any]:
        handoff = parse_delegation_handoff(task)
        if not handoff:
            return {}

        specialist_context = extract_specialist_context_from_handoff_data(handoff.handoff_data)
        if not specialist_context:
            return {}

        current_task = " | ".join(
            str(item or "").strip()
            for item in (
                handoff.handoff_data.get("original_user_task"),
                handoff.handoff_data.get("query"),
                handoff.handoff_data.get("target_hint"),
                handoff.goal,
            )
            if str(item or "").strip()
        )
        alignment = assess_specialist_context_alignment(
            current_task=current_task,
            payload=specialist_context,
        )
        state = str(alignment.get("alignment_state") or "").strip().lower()
        if state not in {"context_mismatch", "needs_meta_reframe"}:
            return {}

        return {
            "signal": state,
            "alignment": alignment,
            "specialist_context": specialist_context,
        }

    @classmethod
    def _make_progress_callback(
        cls,
        progress_event: asyncio.Event,
        progress_state: Dict[str, Any],
        *,
        from_agent: str,
        to_agent: str,
        session_id: str,
    ) -> Callable[..., None]:
        def _callback(*args: Any, **kwargs: Any) -> None:
            stage = str(kwargs.get("stage") or (args[0] if args else "") or "").strip()
            payload = kwargs.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            if stage:
                progress_state["stage"] = stage
            progress_state["updated_at"] = time.monotonic()
            progress_event.set()
            cls._emit_transport_progress(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=session_id,
                stage=stage,
                payload=payload,
            )

        return _callback

    @classmethod
    async def _run_agent_with_watchdog(
        cls,
        agent: Any,
        task: str,
        *,
        timeout: float,
        progress_timeout: float,
        progress_event: asyncio.Event | None,
    ) -> Any:
        if progress_timeout <= 0 or progress_event is None:
            return await asyncio.wait_for(agent.run(task), timeout=timeout)

        deadline = asyncio.get_running_loop().time() + timeout
        run_task = asyncio.create_task(agent.run(task))
        progress_task = asyncio.create_task(progress_event.wait())
        try:
            wait_budget = min(timeout, progress_timeout)
            done, _ = await asyncio.wait(
                {run_task, progress_task},
                timeout=wait_budget,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if run_task in done:
                return run_task.result()
            if progress_task in done and progress_event.is_set():
                remaining = max(0.001, deadline - asyncio.get_running_loop().time())
                return await asyncio.wait_for(run_task, timeout=remaining)
            run_task.cancel()
            with suppress(asyncio.CancelledError):
                await run_task
            raise DelegationProgressTimeout(
                f"Timeout: Agent '{getattr(agent, 'role', 'executor')}' zeigte innerhalb von {wait_budget}s keinen Fortschritt"
            )
        finally:
            progress_task.cancel()
            with suppress(asyncio.CancelledError):
                await progress_task

    async def delegate(
        self,
        from_agent: str,
        to_agent: str,
        task: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delegiert Task mit Loop-Prevention via Stack.

        Gibt immer ein strukturiertes Dict zurueck:
            {"status": "success",  "agent": "...", "result": "..."}
            {"status": "partial",  "agent": "...", "result": "...", "note": "..."}
            {"status": "error",    "agent": "...", "error":  "..."}
        """
        from_agent = self.normalize_agent_name(from_agent)
        to_agent = self.normalize_agent_name(to_agent)
        effective_session_id = self._resolve_effective_session_id(from_agent, session_id)

        if to_agent not in self._specs:
            error_msg = (
                f"FEHLER: Agent '{to_agent}' nicht registriert. "
                f"Verfuegbar: {list(self._specs.keys())}"
            )
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error",
                task=task,
                message=f"Delegation fehlgeschlagen: Agent '{to_agent}' nicht registriert",
                payload={"reason": "agent_not_registered"},
            )
            return {"status": "error", "agent": to_agent, "error": error_msg}

        # Formales Delegation-Policy-Gate (M4.1)
        from utils.policy_gate import audit_policy_decision, evaluate_policy_gate

        policy_decision = evaluate_policy_gate(
            gate="delegation",
            subject=f"{from_agent}->{to_agent}",
            payload={"from_agent": from_agent, "to_agent": to_agent, "task": task},
            source="agent_registry.delegate",
        )
        audit_policy_decision(policy_decision)
        if bool(policy_decision.get("blocked")):
            reason = str(policy_decision.get("reason") or "Policy blockiert Delegation.")
            error_msg = f"FEHLER: Delegation blockiert — {reason}"
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="cancelled",
                task=task,
                message=f"Delegation policy-blockiert: {from_agent} -> {to_agent}",
                payload={
                    "reason": "policy_blocked",
                    "policy_gate": {
                        "action": policy_decision.get("action"),
                        "violations": policy_decision.get("violations", []),
                        "strict_mode": bool(policy_decision.get("strict_mode")),
                    },
                },
            )
            return {"status": "error", "agent": to_agent, "error": error_msg, "blocked_by_policy": True}

        stack = list(self._delegation_stack_var.get())

        if to_agent in stack:
            chain = " -> ".join(stack)
            error_msg = f"FEHLER: Zirkulaere Delegation ({chain} -> {to_agent})"
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error",
                task=task,
                message=f"Zirkulaere Delegation: {chain} -> {to_agent}",
                payload={"reason": "cycle_detected", "chain": chain},
            )
            return {"status": "error", "agent": to_agent, "error": error_msg}

        if len(stack) >= self.MAX_DELEGATION_DEPTH:
            error_msg = (
                f"FEHLER: Max Delegation-Tiefe ({self.MAX_DELEGATION_DEPTH}) erreicht"
            )
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error",
                task=task,
                message=f"Max Delegation-Tiefe ({self.MAX_DELEGATION_DEPTH}) erreicht",
                payload={"reason": "max_depth"},
            )
            return {"status": "error", "agent": to_agent, "error": error_msg}

        next_stack = tuple(stack + [to_agent])
        stack_token = self._delegation_stack_var.set(next_stack)
        log.info(f"Delegation: {from_agent} -> {to_agent} (Stack: {list(next_stack)})")

        # Live-SSE-Animation im Canvas
        try:
            if _delegation_sse_hook is not None:
                _delegation_sse_hook(from_agent, to_agent, "running")
        except Exception:
            pass

        self._log_canvas_delegation(
            from_agent=from_agent,
            to_agent=to_agent,
            session_id=effective_session_id,
            status="running",
            task=task,
            message=f"Delegation gestartet: {from_agent} -> {to_agent}",
            payload={"stack_depth": len(next_stack)},
        )
        self._record_communication_delivery_observation(
            event_type="communication_task_started",
            task=task,
            from_agent=from_agent,
            to_agent=to_agent,
            session_id=effective_session_id or "",
        )

        timeout = self._select_delegation_timeout(to_agent, task)
        progress_timeout = self._select_progress_timeout(to_agent, task)
        max_retries = int(os.getenv("DELEGATION_MAX_RETRIES", "1"))

        agent = None
        previous_session_id: Optional[str] = None
        target_has_session_attr = False
        previous_progress_callback: Any = None
        had_progress_callback = False
        previous_delegation_context: Any = None
        had_delegation_context = False
        progress_event: asyncio.Event | None = None
        progress_state: Dict[str, Any] = {}
        last_error: Optional[Exception] = None
        last_timeout_phase = "run"
        try:
            agent = await self._get_or_create(to_agent)
            if hasattr(agent, "conversation_session_id"):
                target_has_session_attr = True
                previous_session_id = getattr(agent, "conversation_session_id", None)
                if effective_session_id:
                    setattr(agent, "conversation_session_id", effective_session_id)
            if to_agent == "executor":
                progress_event = asyncio.Event()
                had_progress_callback = hasattr(agent, "_delegation_progress_callback")
                previous_progress_callback = getattr(agent, "_delegation_progress_callback", None)
                setattr(
                    agent,
                    "_delegation_progress_callback",
                    self._make_progress_callback(
                        progress_event,
                        progress_state,
                        from_agent=from_agent,
                        to_agent=to_agent,
                        session_id=effective_session_id or "",
                    ),
                )
                had_delegation_context = hasattr(agent, "_delegation_context")
                previous_delegation_context = getattr(agent, "_delegation_context", None)
                setattr(
                    agent,
                    "_delegation_context",
                    {
                        "from_agent": from_agent,
                        "session_id": effective_session_id,
                        "task_type": self._extract_handoff_task_type(task),
                    },
                )

            for attempt in range(max_retries):
                try:
                    if progress_event is not None:
                        progress_event.clear()
                    raw = await self._run_agent_with_watchdog(
                        agent,
                        task,
                        timeout=timeout,
                        progress_timeout=progress_timeout,
                        progress_event=progress_event,
                    )
                    last_error = None
                    break
                except DelegationProgressTimeout as e:
                    last_error = e
                    last_timeout_phase = "progress"
                    log.warning(
                        f"Delegation {from_agent} -> {to_agent} Startfenster-Timeout "
                        f"(Versuch {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except asyncio.TimeoutError as e:
                    last_error = TimeoutError(
                        f"Timeout: Agent '{to_agent}' hat nicht innerhalb von {timeout}s geantwortet"
                    )
                    last_timeout_phase = "run"
                    log.warning(
                        f"Delegation {from_agent} -> {to_agent} Timeout "
                        f"(Versuch {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except Exception as e:
                    last_error = e
                    log.warning(
                        f"Delegation {from_agent} -> {to_agent} Fehler "
                        f"(Versuch {attempt + 1}/{max_retries}): {e}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
            else:
                raise last_error  # type: ignore[misc]

            if last_error is not None:
                raise last_error

            raw_result_str = AgentRegistry._stringify_delegation_result(raw)
            explicit_specialist_signal = parse_specialist_signal_response(raw_result_str)
            result_str = raw_result_str
            if explicit_specialist_signal:
                cleaned_text = str(explicit_specialist_signal.get("cleaned_text") or "").strip()
                if cleaned_text:
                    result_str = cleaned_text
            _meta, _artifacts = AgentRegistry._build_result_metadata_and_artifacts(
                raw,
                to_agent,
            )
            specialist_signal = AgentRegistry._derive_specialist_context_signal(task)
            if explicit_specialist_signal:
                specialist_signal = {
                    "signal": str(explicit_specialist_signal.get("signal") or ""),
                    "alignment": {
                        "alignment_state": str(explicit_specialist_signal.get("signal") or ""),
                        "reason": str(explicit_specialist_signal.get("reason") or ""),
                    },
                    "specialist_context": (
                        dict(specialist_signal.get("specialist_context") or {})
                        if specialist_signal
                        else {}
                    ),
                    "signal_source": "agent",
                }
            if specialist_signal:
                _meta = dict(_meta or {})
                _meta["specialist_return_signal"] = str(specialist_signal.get("signal") or "")
                _meta["specialist_context_alignment"] = dict(specialist_signal.get("alignment") or {})
                _meta["specialist_signal_source"] = str(specialist_signal.get("signal_source") or "heuristic")
                if specialist_signal.get("specialist_context"):
                    _meta["specialist_context"] = dict(specialist_signal.get("specialist_context") or {})
            if explicit_specialist_signal:
                outcome_status, outcome_error = "partial", str(
                    explicit_specialist_signal.get("message")
                    or "Spezialist fordert eine Meta-Neurahmung."
                )
            else:
                outcome_status, outcome_error = AgentRegistry._classify_delegation_outcome(
                    raw,
                    result_str,
                )

            if specialist_signal:
                signal_name = str(specialist_signal.get("signal") or "")
                record_autonomy_observation(
                    "specialist_signal_emitted",
                    {
                        "from_agent": from_agent,
                        "agent": to_agent,
                        "signal": signal_name,
                        "signal_source": str(specialist_signal.get("signal_source") or "heuristic"),
                        "alignment_state": str(
                            dict(specialist_signal.get("alignment") or {}).get("alignment_state") or ""
                        ),
                        "reason": str(
                            dict(specialist_signal.get("alignment") or {}).get("reason") or ""
                        ),
                        "session_id": effective_session_id or "",
                    },
                )
                signal_payload = {
                    "kind": signal_name,
                    "message": (
                        "Spezialist meldet einen moeglichen Kontext-Mismatch."
                        if signal_name == "context_mismatch"
                        else "Spezialist braucht vermutlich einen Meta-Reframe."
                    ),
                    "signal": signal_name,
                    "reason": str(
                        dict(specialist_signal.get("alignment") or {}).get("reason") or ""
                    ),
                }
                self._emit_transport_progress(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id or "",
                    stage=f"delegation_{signal_name}",
                    payload=signal_payload,
                )

            # Partial-Result-Erkennung
            if outcome_status == "partial":
                self._emit_transport_progress(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id or "",
                    stage="delegation_partial",
                    payload={
                        "kind": "partial_result",
                        "message": f"{to_agent} liefert ein partielles Ergebnis.",
                        "content_preview": result_str[:400],
                        "note": "Aufgabe nicht vollstaendig abgeschlossen",
                    },
                )
                status = "partial"
                self._log_canvas_delegation(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id,
                    status="completed",
                    task=task,
                    message=f"Delegation partiell: {from_agent} -> {to_agent}",
                    payload={"result_preview": result_str[:240]},
                )
                # M12: Routing-Analytics (partial)
                self._record_routing_outcome(task, to_agent, "partial")
                bb_key = AgentRegistry._auto_write_to_blackboard(
                    to_agent,
                    task,
                    result_str,
                    "partial",
                    session_id=effective_session_id,
                    metadata=_meta,
                    artifacts=_artifacts,
                )
                _res = AgentResult(
                    status="partial",
                    agent=to_agent,
                    result=result_str,
                    quality=40,
                    blackboard_key=bb_key,
                    metadata=_meta,
                    artifacts=_artifacts,
                )
                self._record_communication_delivery_observation(
                    event_type="communication_task_partial",
                    task=task,
                    raw=raw,
                    metadata=_meta,
                    artifacts=_artifacts,
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id or "",
                    error=result_str,
                )
                return {
                    "status": _res.status,
                    "agent": _res.agent,
                    "result": _res.result,
                    "quality": _res.quality,
                    "blackboard_key": _res.blackboard_key,
                    "metadata": _res.metadata,
                    "artifacts": _res.artifacts,
                    "note": "Aufgabe nicht vollstaendig abgeschlossen",
                }

            if outcome_status == "error":
                self._log_canvas_delegation(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id,
                    status="error",
                    task=task,
                    message=f"Delegation inhaltlich fehlgeschlagen: {from_agent} -> {to_agent}",
                    payload={"error_preview": outcome_error[:240]},
                )
                self._record_routing_outcome(task, to_agent, "error")
                try:
                    if _delegation_sse_hook is not None:
                        _delegation_sse_hook(from_agent, to_agent, "error")
                except Exception:
                    pass
                bb_key = AgentRegistry._auto_write_to_blackboard(
                    to_agent,
                    task,
                    outcome_error[:1000],
                    "error",
                    session_id=effective_session_id,
                    metadata=_meta,
                    artifacts=_artifacts,
                )
                _res = AgentResult(
                    status="error",
                    agent=to_agent,
                    result="",
                    quality=0,
                    blackboard_key=bb_key,
                    error=outcome_error,
                    metadata=_meta,
                    artifacts=_artifacts,
                )
                self._record_communication_delivery_observation(
                    event_type="communication_task_failed",
                    task=task,
                    raw=raw,
                    metadata=_meta,
                    artifacts=_artifacts,
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id or "",
                    error=outcome_error,
                )
                self._record_communication_delivery_observation(
                    event_type="send_email_failed",
                    task=task,
                    raw=raw,
                    metadata=_meta,
                    artifacts=_artifacts,
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id or "",
                    error=outcome_error,
                )
                return {
                    "status": _res.status,
                    "agent": _res.agent,
                    "error": f"FEHLER: Delegation an '{to_agent}' fehlgeschlagen: {_res.error}",
                    "quality": _res.quality,
                    "blackboard_key": _res.blackboard_key,
                    "metadata": _res.metadata,
                    "artifacts": _res.artifacts,
                }

            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="completed",
                task=task,
                message=f"Delegation abgeschlossen: {from_agent} -> {to_agent}",
                payload={"result_preview": result_str[:240]},
            )
            # M12: Routing-Analytics aufzeichnen
            self._record_routing_outcome(task, to_agent, "success")
            try:
                if _delegation_sse_hook is not None:
                    _delegation_sse_hook(from_agent, to_agent, "completed")
            except Exception:
                pass
            bb_key = AgentRegistry._auto_write_to_blackboard(
                to_agent,
                task,
                result_str,
                "success",
                session_id=effective_session_id,
                metadata=_meta,
                artifacts=_artifacts,
            )
            _res = AgentResult(
                status="success",
                agent=to_agent,
                result=result_str,
                quality=80,
                blackboard_key=bb_key,
                metadata=_meta,
                artifacts=_artifacts,
            )
            self._record_communication_delivery_observation(
                event_type="communication_task_completed",
                task=task,
                raw=raw,
                metadata=_meta,
                artifacts=_artifacts,
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id or "",
            )
            self._record_communication_delivery_observation(
                event_type="send_email_succeeded",
                task=task,
                raw=raw,
                metadata=_meta,
                artifacts=_artifacts,
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id or "",
            )
            return {
                "status": _res.status,
                "agent": _res.agent,
                "result": _res.result,
                "quality": _res.quality,
                "blackboard_key": _res.blackboard_key,
                "metadata": _res.metadata,
                "artifacts": _res.artifacts,
            }

        except TimeoutError as e:
            timeout_status = self._timeout_status_for_agent(to_agent)
            timeout_meta = self._build_timeout_metadata(
                agent_name=to_agent,
                timeout_seconds=timeout,
                session_id=effective_session_id,
                attempts=max_retries,
                timeout_phase=last_timeout_phase,
            )
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error" if timeout_status == "error" else "completed",
                task=task,
                message=f"Delegation Timeout: {e}",
                payload={
                    "timeout_seconds": timeout,
                    "attempts": max_retries,
                    "timeout_phase": last_timeout_phase,
                    "last_progress_stage": str(progress_state.get("stage") or ""),
                },
            )
            self._record_routing_outcome(task, to_agent, timeout_status)
            try:
                if _delegation_sse_hook is not None:
                    _delegation_sse_hook(
                        from_agent,
                        to_agent,
                        "error" if timeout_status == "error" else "completed",
                    )
            except Exception:
                pass
            bb_key = AgentRegistry._auto_write_to_blackboard(
                to_agent,
                task,
                str(e),
                timeout_status,
                session_id=effective_session_id,
                metadata=timeout_meta,
                artifacts=[],
            )
            if timeout_status == "partial":
                self._emit_transport_progress(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    session_id=effective_session_id or "",
                    stage="delegation_partial_timeout",
                    payload={
                        "kind": "partial_result",
                        "message": f"{to_agent} hat nur ein partielles Ergebnis geliefert.",
                        "content_preview": str(e)[:400],
                        "timeout_seconds": timeout,
                        "last_progress_stage": str(progress_state.get("stage") or ""),
                    },
                )
                return {
                    "status": "partial",
                    "agent": to_agent,
                    "result": "",
                    "error": str(e),
                    "quality": 40,
                    "blackboard_key": bb_key,
                    "metadata": timeout_meta,
                    "artifacts": [],
                    "note": "Recherche-Timeout: Aufgabe enger formulieren und einmal neu delegieren.",
                }
            return {
                "status": "error",
                "agent": to_agent,
                "error": f"FEHLER: Delegation an '{to_agent}' fehlgeschlagen: {e}",
                "quality": 0,
                "blackboard_key": bb_key,
                "metadata": timeout_meta,
                "artifacts": [],
            }
        except Exception as e:
            log.error(f"Delegation {from_agent} -> {to_agent} fehlgeschlagen: {e}")
            self._log_canvas_delegation(
                from_agent=from_agent,
                to_agent=to_agent,
                session_id=effective_session_id,
                status="error",
                task=task,
                message=f"Delegation fehlgeschlagen: {e}",
                payload={"exception": str(e)[:300]},
            )
            # M12: Routing-Analytics aufzeichnen
            self._record_routing_outcome(task, to_agent, "error")
            try:
                if _delegation_sse_hook is not None:
                    _delegation_sse_hook(from_agent, to_agent, "error")
            except Exception:
                pass
            bb_key = AgentRegistry._auto_write_to_blackboard(
                to_agent,
                task,
                str(e),
                "error",
                session_id=effective_session_id,
            )
            _res = AgentResult(
                status="error",
                agent=to_agent,
                result="",
                quality=0,
                blackboard_key=bb_key,
                error=str(e),
            )
            return {
                "status": _res.status,
                "agent": _res.agent,
                "error": f"FEHLER: Delegation an '{to_agent}' fehlgeschlagen: {_res.error}",
                "quality": _res.quality,
                "blackboard_key": _res.blackboard_key,
                "metadata": {},
                "artifacts": [],
            }
        finally:
            if target_has_session_attr and agent is not None:
                setattr(agent, "conversation_session_id", previous_session_id)
            if agent is not None and to_agent == "executor":
                if had_progress_callback:
                    setattr(agent, "_delegation_progress_callback", previous_progress_callback)
                elif hasattr(agent, "_delegation_progress_callback"):
                    delattr(agent, "_delegation_progress_callback")
                if had_delegation_context:
                    setattr(agent, "_delegation_context", previous_delegation_context)
                elif hasattr(agent, "_delegation_context"):
                    delattr(agent, "_delegation_context")
            self._delegation_stack_var.reset(stack_token)

    @staticmethod
    def _record_routing_outcome(task: str, chosen_agent: str, outcome: str) -> None:
        """M12: Routing-Entscheidung für Self-Improvement aufzeichnen."""
        try:
            if not os.getenv("AUTONOMY_SELF_IMPROVEMENT_ENABLED", "false").lower() in {"true", "1", "yes"}:
                return
            import hashlib
            from orchestration.self_improvement_engine import get_improvement_engine, RoutingRecord
            task_hash = hashlib.sha256(task.encode()).hexdigest()[:8]
            OUTCOME_SCORE_MAP = {"success": 0.8, "partial": 0.4, "error": 0.0}
            outcome_score = OUTCOME_SCORE_MAP.get(outcome, 0.4)
            get_improvement_engine().record_routing(RoutingRecord(
                task_hash=task_hash,
                chosen_agent=chosen_agent,
                outcome=outcome,
                outcome_score=outcome_score,
                source="delegation_runtime",
            ))
        except Exception:
            pass

    @staticmethod
    def _delegation_blackboard_ttl(status: str) -> int:
        """Liefert positive TTL fuer Delegations-Ergebnisse."""
        return {"success": 120, "partial": 60, "error": 30}.get(status, 60)

    @staticmethod
    def _auto_write_to_blackboard(
        agent_type: str,
        task: str,
        result: str,
        status: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Schreibt Delegationsergebnis automatisch ins Blackboard (M17). Gibt Key zurück."""
        try:
            from memory.agent_blackboard import get_blackboard
            bb = get_blackboard()
            key = f"delegation:{agent_type}:{int(time.time())}"
            ttl = AgentRegistry._delegation_blackboard_ttl(status)
            bb.write(
                agent="agent_registry",
                topic="delegation_results",
                key=key,
                value={
                    "task": task[:200],
                    "result": result[:1000],
                    "status": status,
                    "metadata": metadata or {},
                    "artifacts": artifacts or [],
                },
                ttl_minutes=ttl,
                session_id=session_id or "",
            )
            return key
        except Exception as e:
            log.warning("Auto-Blackboard-Write fehlgeschlagen: %s", e)
            return ""

    @staticmethod
    def _stringify_delegation_result(raw: Any) -> str:
        """String-Darstellung fuer Delegationsergebnisse mit Dict-Spezialfall."""
        if isinstance(raw, dict):
            preferred = raw.get("result")
            if isinstance(preferred, str) and preferred.strip():
                return preferred
        return str(raw)

    @classmethod
    def _classify_delegation_outcome(cls, raw: Any, result_text: str) -> tuple[str, str]:
        """Klassifiziert delegierte Ergebnisse, damit Fehlertext nicht als Erfolg durchgeht."""
        stripped = (result_text or "").strip()
        explicit_signal = parse_specialist_signal_response(stripped)
        if explicit_signal:
            signal_message = str(explicit_signal.get("message") or "").strip()
            fallback = (
                "Spezialist fordert eine Meta-Neurahmung."
                if explicit_signal.get("signal") == "needs_meta_reframe"
                else "Spezialist meldet einen moeglichen Kontext-Mismatch."
            )
            return "partial", signal_message or fallback
        if isinstance(raw, dict):
            workflow_payload = normalize_phase_d_workflow_payload(raw)
            workflow_status = str(workflow_payload.get("status") or "").strip().lower()
            if workflow_status in {"approval_required", "auth_required", "awaiting_user", "challenge_required"}:
                return "partial", str(
                    raw.get("error")
                    or raw.get("message")
                    or raw.get("result")
                    or workflow_payload.get("message")
                    or result_text
                )
            raw_status = str(raw.get("status") or "").strip().lower()
            if raw.get("skipped") is True:
                return "error", str(raw.get("reason") or "Delegierter Tool-Call wurde blockiert")
            if raw_status in {"error", "partial"}:
                return raw_status, str(raw.get("error") or raw.get("result") or result_text)
            if raw.get("success") is False:
                return "error", str(raw.get("error") or result_text)
            if raw.get("error"):
                return "error", str(raw.get("error"))
            if raw_status == "success" and any(pattern.search(stripped) for pattern in cls._PARTIAL_TEXT_PATTERNS):
                return "partial", stripped

        if result_text in cls._PARTIAL_MARKERS:
            return "partial", result_text

        for pattern in cls._PARTIAL_TEXT_PATTERNS:
            if pattern.search(stripped):
                return "partial", stripped

        for pattern in cls._ERROR_TEXT_PATTERNS:
            if pattern.search(stripped):
                return "error", stripped

        return "success", ""

    @staticmethod
    def _extract_declared_metadata(raw: Any) -> Dict[str, Any]:
        """Extrahiert explizit deklarierte Metadaten ohne Regex-Fallback."""
        meta: Dict[str, Any] = {}
        if not isinstance(raw, dict):
            return meta

        workflow_payload = normalize_phase_d_workflow_payload(raw)
        if workflow_payload:
            meta["phase_d_workflow"] = workflow_payload
            meta["workflow_id"] = str(workflow_payload.get("workflow_id") or "")
            meta["workflow_status"] = str(workflow_payload.get("status") or "")
            meta["workflow_service"] = str(
                workflow_payload.get("service") or workflow_payload.get("platform") or ""
            )

        raw_meta = raw.get("metadata")
        if isinstance(raw_meta, dict):
            meta.update(raw_meta)

        for key in (
            "pdf_filepath",
            "image_path",
            "narrative_filepath",
            "session_id",
            "word_count",
            "saved_as",
            "file_path",
            "filepath",
        ):
            value = raw.get(key)
            if value not in (None, "") and key not in meta:
                meta[key] = value

        return meta

    @staticmethod
    def _extract_metadata(result: Any, agent_type: str) -> Dict[str, Any]:
        """
        Extrahiert strukturierte Key-Value-Paare.
        Gibt dem Meta-LLM ein sauberes JSON-Dict statt Textsuche.

        Extrahierte Keys:
          pdf_filepath   — PDF-Pfad aus Deep Research
          image_path     — Bildpfad aus Creative Agent
          session_id     — Research-Session-ID
          narrative_filepath — Markdown-Bericht-Pfad
          word_count     — Wörterzahl aus Berichts-Header
        """
        meta: Dict[str, Any] = AgentRegistry._extract_declared_metadata(result)
        result_text = AgentRegistry._stringify_delegation_result(result)
        regex_used = False

        # --- Datei-Pfade ---
        path_patterns = {
            "pdf_filepath":        r'pdf_filepath["\s:]+([^\s\'"}\]]+\.pdf)',
            "image_path":          r'(?:image_path|saved_as|image_url)["\s:]+([^\s\'"}\]]+\.(?:png|jpg|jpeg|webp))',
            "narrative_filepath":  r'narrative_filepath["\s:]+([^\s\'"}\]]+\.(?:md|txt))',
        }
        for key, pattern in path_patterns.items():
            if key in meta:
                continue
            m = re.search(pattern, result_text, re.IGNORECASE)
            if m:
                meta[key] = m.group(1).strip().strip('"\'')
                regex_used = True

        # --- session_id ---
        if "session_id" not in meta:
            m = re.search(r'"?session_id"?\s*[=:]\s*"?([a-zA-Z0-9_-]{8,})"?', result_text)
            if m:
                meta["session_id"] = m.group(1)
                regex_used = True

        # --- Wörterzahl aus Header ---
        if "word_count" not in meta:
            m = re.search(r'([\d,\.]+)\s+W[oö]rter', result_text)
            if m:
                try:
                    meta["word_count"] = int(m.group(1).replace(",", "").replace(".", ""))
                    regex_used = True
                except ValueError:
                    pass

        # --- Fallback: alle absoluten Pfade mit bekannten Endungen ---
        if not meta.get("pdf_filepath"):
            m = re.search(r'(/[^\s\'"}\]]+\.pdf)', result_text)
            if m:
                meta["pdf_filepath"] = m.group(1)
                regex_used = True
        if not meta.get("image_path"):
            m = re.search(r'(/[^\s\'"}\]]+\.(?:png|jpg|jpeg|webp))', result_text)
            if m:
                meta["image_path"] = m.group(1)
                regex_used = True
        if not meta.get("narrative_filepath"):
            m = re.search(r'(/[^\s\'"}\]]+\.(?:md|txt))', result_text)
            if m:
                meta["narrative_filepath"] = m.group(1)
                regex_used = True

        if meta:
            log.debug("Metadata extrahiert für %s: %s", agent_type, list(meta.keys()))
        if regex_used:
            log.warning(
                "Regex-Fallback fuer Delegationsergebnis genutzt: agent=%s keys=%s",
                agent_type,
                sorted(meta.keys()),
            )
        return meta

    @staticmethod
    def _normalize_artifact(path: str, *, artifact_type: str, label: str, source: str, origin: str) -> Dict[str, Any]:
        return {
            "type": artifact_type,
            "path": path,
            "label": label,
            "source": source,
            "origin": origin,
        }

    @staticmethod
    def _infer_artifact_type(path: str, *, fallback: str = "file") -> str:
        lower = (path or "").lower()
        if lower.endswith(".pdf"):
            return "pdf"
        if lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            return "image"
        if lower.endswith((".md", ".txt")):
            return "report"
        if lower.endswith(".docx"):
            return "docx"
        if lower.endswith((".csv", ".xlsx", ".json")):
            return "data"
        return fallback

    @staticmethod
    def _extract_declared_artifacts(raw: Any, agent_type: str) -> List[Dict[str, Any]]:
        artifacts: List[Dict[str, Any]] = []
        if not isinstance(raw, dict):
            return artifacts

        raw_artifacts = raw.get("artifacts")
        if not isinstance(raw_artifacts, list):
            return artifacts

        for item in raw_artifacts:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            artifacts.append(
                {
                    "type": item.get("type") or AgentRegistry._infer_artifact_type(path),
                    "path": path,
                    "label": item.get("label") or path.rsplit("/", 1)[-1],
                    "source": item.get("source") or agent_type,
                    "origin": item.get("origin") or "artifacts",
                }
            )

        return artifacts

    @staticmethod
    def _artifacts_from_metadata(
        metadata: Dict[str, Any],
        agent_type: str,
        *,
        origin: str,
    ) -> List[Dict[str, Any]]:
        artifacts: List[Dict[str, Any]] = []

        typed_keys = (
            ("pdf_filepath", "pdf", "Research PDF"),
            ("image_path", "image", "Generated image"),
            ("narrative_filepath", "report", "Narrative report"),
            ("saved_as", "file", "Saved file"),
            ("file_path", "file", "Output file"),
            ("filepath", "file", "Output file"),
        )

        seen_paths: set[str] = set()
        for key, fallback_type, label in typed_keys:
            value = metadata.get(key)
            path = str(value or "").strip()
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            artifacts.append(
                AgentRegistry._normalize_artifact(
                    path,
                    artifact_type=AgentRegistry._infer_artifact_type(path, fallback=fallback_type),
                    label=label,
                    source=agent_type,
                    origin=origin,
                )
            )

        return artifacts

    @staticmethod
    def _build_result_metadata_and_artifacts(raw: Any, agent_type: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Erzwingt die Fallback-Politik:
        artifacts -> metadata -> regex-fallback + warning
        """
        declared_artifacts = AgentRegistry._extract_declared_artifacts(raw, agent_type)
        declared_metadata = AgentRegistry._extract_declared_metadata(raw)
        metadata_artifacts = AgentRegistry._artifacts_from_metadata(
            declared_metadata,
            agent_type,
            origin="metadata",
        )

        if declared_artifacts:
            return declared_metadata, declared_artifacts
        if metadata_artifacts:
            log.warning(
                "Metadata-Fallback fuer Delegationsergebnis genutzt: agent=%s keys=%s",
                agent_type,
                sorted(declared_metadata.keys()),
            )
            return declared_metadata, metadata_artifacts

        regex_metadata = AgentRegistry._extract_metadata(raw, agent_type)
        regex_artifacts = AgentRegistry._artifacts_from_metadata(
            regex_metadata,
            agent_type,
            origin="regex",
        )
        return regex_metadata, regex_artifacts

    def find_by_capability(self, capability: str) -> List[AgentSpec]:
        """Findet alle AgentSpecs mit einer bestimmten Capability."""
        capability = (capability or "").strip().lower()
        return [
            spec for spec in self._specs.values()
            if capability in spec.capabilities
        ]

    def list_agents(self) -> List[str]:
        """Listet alle registrierten Agent-Namen."""
        return list(self._specs.keys())

    def list_agent_specs(self) -> List[AgentSpec]:
        """Listet alle registrierten AgentSpecs (mit Capabilities)."""
        return list(self._specs.values())

    def get_agent_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Gibt Info ueber einen registrierten Agenten."""
        spec = self._specs.get(name)
        if not spec:
            return None
        return {
            "name": spec.name,
            "type": spec.agent_type,
            "capabilities": spec.capabilities,
            "instantiated": name in self._instances,
        }

    async def delegate_parallel(
        self,
        tasks: List[Dict[str, Any]],
        from_agent: str = "meta",
        max_parallel: int = 5,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fan-Out: Startet mehrere unabhaengige Tasks parallel.
        Fan-In:  Bündelt alle Ergebnisse strukturiert zurueck.

        Jeder Task bekommt eine FRISCHE Agenten-Instanz (kein Singleton-Conflict
        wenn z.B. 2x research gleichzeitig laeuft).

        MemoryAccessGuard setzt read-only pro asyncio-Task via ContextVar —
        Worker A und B beeinflussen sich gegenseitig nicht.

        Gibt zurueck:
            {
                "trace_id": "abc123def",
                "total_tasks": 3,
                "success": 2, "partial": 0, "errors": 1,
                "results": [...],
                "summary": "2/3 erfolgreich | 0 partiell | 1 Fehler"
            }
        """
        from memory.memory_guard import MemoryAccessGuard

        trace_id = uuid.uuid4().hex[:12]
        effective_session_id = self._resolve_effective_session_id(from_agent, session_id)
        policy_decision = evaluate_parallel_tasks(tasks)
        if not policy_decision.get("allowed", False):
            log.warning(
                "[delegate_parallel] Policy-Block | trace=%s reason=%s dependent=%s",
                trace_id,
                policy_decision.get("reason", "unknown"),
                policy_decision.get("dependent_task_ids", []),
            )
            return {
                "trace_id": trace_id,
                "total_tasks": len(tasks),
                "success": 0,
                "partial": 0,
                "errors": len(tasks),
                "results": [],
                "budget_state": "n/a",
                "effective_max_parallel": 0,
                "policy_state": policy_decision.get("policy_state", "blocked"),
                "policy_reason": policy_decision.get("reason", "unknown"),
                "dependent_task_ids": policy_decision.get("dependent_task_ids", []),
                "independent_task_ids": policy_decision.get("independent_task_ids", []),
                "summary": "Parallel-Delegation durch Policy blockiert",
            }
        requested_parallel = max(1, min(10, int(max_parallel)))
        effective_parallel, budget_decision = cap_parallelism_for_budget(
            requested_parallel=requested_parallel,
            agent=from_agent,
            session_id=effective_session_id or "",
        )
        semaphore = asyncio.Semaphore(effective_parallel)

        log.info(
            f"[delegate_parallel] Start | {len(tasks)} Tasks | "
            f"TraceID: {trace_id} | MaxParallel: {requested_parallel}"
        )
        if effective_parallel != requested_parallel:
            log.warning(
                "[delegate_parallel] Budget-Cap aktiv | requested=%s effective=%s state=%s msg=%s",
                requested_parallel,
                effective_parallel,
                budget_decision.state,
                budget_decision.message,
            )

        def _parallel_payload(
            *,
            task_id: str,
            agent_name: str,
            status: str,
            trace: str,
            task_desc: str,
            raw: Any = None,
            error: str = "",
        ) -> Dict[str, Any]:
            result_str = AgentRegistry._stringify_delegation_result(raw) if raw is not None else ""
            metadata: Dict[str, Any] = {}
            artifacts: List[Dict[str, Any]] = []
            if raw is not None:
                metadata, artifacts = AgentRegistry._build_result_metadata_and_artifacts(
                    raw,
                    agent_name,
                )

            quality = {"success": 80, "partial": 40, "error": 0}.get(status, 0)
            blackboard_value = error or result_str
            blackboard_key = AgentRegistry._auto_write_to_blackboard(
                agent_name,
                task_desc,
                blackboard_value,
                status,
                session_id=effective_session_id,
                metadata=metadata,
                artifacts=artifacts,
            )

            result = AgentResult(
                status=status,
                agent=agent_name,
                result=result_str,
                quality=quality,
                blackboard_key=blackboard_key,
                error=error,
                metadata=metadata,
                artifacts=artifacts,
            )
            payload = {
                "task_id": task_id,
                "agent": result.agent,
                "status": result.status,
                "result": result.result,
                "quality": result.quality,
                "blackboard_key": result.blackboard_key,
                "metadata": result.metadata,
                "artifacts": result.artifacts,
                "trace": trace,
            }
            if result.error:
                payload["error"] = result.error
            return payload

        async def run_single(task: Dict[str, Any]) -> Dict[str, Any]:
            task_id    = task.get("task_id") or f"t{uuid.uuid4().hex[:6]}"
            agent_name = self.normalize_agent_name(task.get("agent", ""))
            task_desc  = task.get("task", "")
            _default_timeout = AgentRegistry._select_delegation_timeout(agent_name, task_desc)
            timeout = float(task.get("timeout", _default_timeout))
            progress_timeout = AgentRegistry._select_progress_timeout(agent_name, task_desc)
            subtrace   = f"{trace_id}-{task_id}"

            if not agent_name or not task_desc:
                return _parallel_payload(
                    task_id=task_id,
                    agent_name=agent_name,
                    status="error",
                    trace=subtrace,
                    task_desc=task_desc,
                    error="Fehlende 'agent' oder 'task' Felder",
                )

            async with semaphore:
                try:
                    # Schritt 1: Spec prüfen
                    spec = self._specs.get(agent_name)
                    if not spec:
                        return _parallel_payload(
                            task_id=task_id,
                            agent_name=agent_name,
                            status="error",
                            trace=subtrace,
                            task_desc=task_desc,
                            error=(
                                f"Agent '{agent_name}' nicht registriert. "
                                f"Verfuegbar: {list(self._specs.keys())}"
                            ),
                        )

                    # Schritt 2: FRISCHE Instanz erstellen (kein Singleton-Conflict)
                    tools_desc = self._tools_description or ""
                    fresh_agent = spec.factory(tools_desc, **spec.extra_kwargs)
                    previous_session_id: Optional[str] = None
                    target_has_session_attr = False
                    had_progress_callback = False
                    previous_progress_callback = None
                    progress_event: asyncio.Event | None = None
                    if hasattr(fresh_agent, "conversation_session_id"):
                        target_has_session_attr = True
                        previous_session_id = getattr(fresh_agent, "conversation_session_id", None)
                        if effective_session_id:
                            setattr(fresh_agent, "conversation_session_id", effective_session_id)
                    if agent_name == "executor":
                        progress_event = asyncio.Event()
                        had_progress_callback = hasattr(fresh_agent, "_delegation_progress_callback")
                        previous_progress_callback = getattr(fresh_agent, "_delegation_progress_callback", None)
                        setattr(
                            fresh_agent,
                            "_delegation_progress_callback",
                            AgentRegistry._make_progress_callback(
                                progress_event,
                                {},
                                from_agent=from_agent,
                                to_agent=agent_name,
                                session_id=effective_session_id or "",
                            ),
                        )

                    # Schritt 3: read-only fuer diesen Task setzen (ContextVar — nur dieser Task)
                    MemoryAccessGuard.set_read_only(True)

                    # Schritt 4: Canvas-Logging (Fan-Out Start)
                    self._log_canvas_delegation(
                        from_agent=from_agent,
                        to_agent=agent_name,
                        session_id=effective_session_id,
                        status="running",
                        task=task_desc,
                        message=f"[Parallel] {from_agent} -> {agent_name} | trace={subtrace}",
                        payload={"trace_id": subtrace, "parallel": True},
                    )

                    # Schritt 5: Task ausfuehren
                    raw = await AgentRegistry._run_agent_with_watchdog(
                        fresh_agent,
                        task_desc,
                        timeout=timeout,
                        progress_timeout=progress_timeout,
                        progress_event=progress_event,
                    )

                    # Schritt 6: read-only zuruecksetzen
                    MemoryAccessGuard.set_read_only(False)

                    # Schritt 7: Ergebnis klassifizieren statt Fehlertext blind als Erfolg zu werten
                    result_str = AgentRegistry._stringify_delegation_result(raw)
                    status, error_text = AgentRegistry._classify_delegation_outcome(
                        raw,
                        result_str,
                    )

                    self._log_canvas_delegation(
                        from_agent=from_agent,
                        to_agent=agent_name,
                        session_id=effective_session_id,
                        status="completed" if status != "error" else "error",
                        task=task_desc,
                        message=f"[Parallel] Abgeschlossen: {agent_name} | status={status}",
                        payload={"trace_id": subtrace, "parallel": True},
                    )

                    log.info(f"[delegate_parallel] {agent_name} fertig | status={status} | trace={subtrace}")
                    return _parallel_payload(
                        task_id=task_id,
                        agent_name=agent_name,
                        status=status,
                        trace=subtrace,
                        task_desc=task_desc,
                        raw=raw if status != "error" else None,
                        error=error_text,
                    )

                except asyncio.TimeoutError:
                    MemoryAccessGuard.set_read_only(False)
                    log.warning(
                        f"[delegate_parallel] Timeout: {agent_name} nach {timeout}s | trace={subtrace}"
                    )
                    return _parallel_payload(
                        task_id=task_id,
                        agent_name=agent_name,
                        status="partial",
                        trace=subtrace,
                        task_desc=task_desc,
                        error=f"Timeout nach {timeout}s",
                    )

                except Exception as e:
                    MemoryAccessGuard.set_read_only(False)
                    log.error(
                        f"[delegate_parallel] Fehler: {agent_name}: {e} | trace={subtrace}"
                    )
                    return _parallel_payload(
                        task_id=task_id,
                        agent_name=agent_name,
                        status="error",
                        trace=subtrace,
                        task_desc=task_desc,
                        error=str(e),
                    )
                finally:
                    try:
                        if target_has_session_attr:
                            setattr(fresh_agent, "conversation_session_id", previous_session_id)
                        if agent_name == "executor":
                            if had_progress_callback:
                                setattr(fresh_agent, "_delegation_progress_callback", previous_progress_callback)
                            elif hasattr(fresh_agent, "_delegation_progress_callback"):
                                delattr(fresh_agent, "_delegation_progress_callback")
                    except Exception:
                        pass

        # ── Fan-Out ────────────────────────────────────────────────────────────
        raw_results = await asyncio.gather(
            *[run_single(t) for t in tasks],
            return_exceptions=True,
        )

        # ── Fan-In ─────────────────────────────────────────────────────────────
        results: List[Dict[str, Any]] = []
        success_count = partial_count = error_count = 0

        for r in raw_results:
            if isinstance(r, Exception):
                results.append(_parallel_payload(
                    task_id=f"t{uuid.uuid4().hex[:6]}",
                    agent_name="unknown",
                    status="error",
                    trace=f"{trace_id}-exception",
                    task_desc="",
                    error=str(r),
                ))
                error_count += 1
            else:
                results.append(r)
                s = r.get("status", "error")
                if s == "success":
                    success_count += 1
                elif s == "partial":
                    partial_count += 1
                else:
                    error_count += 1

        summary = (
            f"{success_count}/{len(tasks)} erfolgreich | "
            f"{partial_count} partiell | {error_count} Fehler"
        )

        log.info(f"[delegate_parallel] Abgeschlossen | TraceID: {trace_id} | {summary}")

        return {
            "trace_id":    trace_id,
            "total_tasks": len(tasks),
            "success":     success_count,
            "partial":     partial_count,
            "errors":      error_count,
            "results":     results,
            "policy_state": policy_decision.get("policy_state", "allowed"),
            "policy_reason": policy_decision.get("reason", "independent_tasks"),
            "dependent_task_ids": policy_decision.get("dependent_task_ids", []),
            "independent_task_ids": policy_decision.get("independent_task_ids", []),
            "budget_state": budget_decision.state,
            "effective_max_parallel": effective_parallel,
            "summary":     summary,
        }


# Singleton-Instanz
agent_registry = AgentRegistry()


def register_all_agents():
    """Registriert alle Standard-Timus-Agenten als Specs (ohne Instanziierung)."""
    from agent.agents import (
        ExecutorAgent, DeepResearchAgent, ReasoningAgent,
        CreativeAgent, MetaAgent, VisualAgent,
        DataAgent, DocumentAgent, CommunicationAgent, SystemAgent, ShellAgent,
    )
    from agent.agents.image import ImageAgent
    from agent.developer_agent_v2 import DeveloperAgentV2

    registry = agent_registry

    registry.register_spec(
        "executor", "executor",
        ["execution", "tools", "simple_tasks"],
        ExecutorAgent,
    )
    registry.register_spec(
        "research", "research",
        ["research", "search", "deep_analysis"],
        DeepResearchAgent,
    )
    registry.register_spec(
        "reasoning", "reasoning",
        ["reasoning", "analysis", "debugging"],
        ReasoningAgent,
        extra_kwargs={"enable_thinking": True},
    )
    registry.register_spec(
        "creative", "creative",
        ["creative", "images", "content_generation"],
        CreativeAgent,
    )
    registry.register_spec(
        "developer", "developer",
        ["code", "development", "files", "refactoring"],
        DeveloperAgentV2,
    )
    registry.register_spec(
        "visual", "visual",
        ["vision", "ui", "browser", "screenshots", "navigation"],
        VisualAgent,
    )
    registry.register_spec(
        "meta", "meta",
        ["orchestration", "planning", "coordination"],
        MetaAgent,
    )
    registry.register_spec(
        "image", "image",
        ["image_analysis", "vision", "photo", "bild"],
        ImageAgent,
    )
    registry.register_spec(
        "data", "data",
        ["data", "csv", "excel", "json", "analysis", "statistics"],
        DataAgent,
    )
    registry.register_spec(
        "document", "document",
        ["document", "pdf", "docx", "report", "writing"],
        DocumentAgent,
    )
    registry.register_spec(
        "communication", "communication",
        ["communication", "email", "letter", "linkedin"],
        CommunicationAgent,
    )
    registry.register_spec(
        "system", "system",
        ["system", "monitoring", "logs", "processes", "stats"],
        SystemAgent,
    )
    registry.register_spec(
        "shell", "shell",
        ["shell", "bash", "command", "script", "cron"],
        ShellAgent,
    )

    log.info(f"Alle Agenten registriert: {registry.list_agents()}")


__all__ = [
    "AgentRegistry",
    "AgentSpec",
    "AgentResult",
    "agent_registry",
    "register_all_agents",
]
