#!/usr/bin/env python3
"""
Milestone 6 Rollout Verification

Führt einen schnellen Go/No-Go Check aus:
1) Standard-Run-Agent Pfad persistiert Event mit Runtime-Metadaten
2) Fehlerpfad (unbekannter Agent) persistiert Error-Event
3) Working-Memory Kontext + Stats werden erzeugt
"""

import asyncio
import sys
import uuid
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

import main_dispatcher
from memory.memory_system import memory_manager
import utils.policy_gate as policy_gate


class _DummyAuditLogger:
    def log_start(self, *_args, **_kwargs):
        return None

    def log_end(self, *_args, **_kwargs):
        return None


class _DummyAgent:
    def __init__(self, tools_description_string: str, **_kwargs):
        self.tools_description_string = tools_description_string

    async def run(self, query: str):
        return f"verify_ok:{query}"

    def get_runtime_telemetry(self):
        return {
            "agent_type": "verify_m6",
            "run_duration_sec": 0.01,
            "working_memory": {"enabled": True, "context_chars": 64},
        }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def main() -> int:
    # Patch non-critical runtime deps for deterministic local check
    import utils.audit_logger as audit_logger

    audit_logger.AuditLogger = _DummyAuditLogger
    policy_gate.audit_tool_call = lambda *_a, **_k: None
    policy_gate.check_query_policy = lambda _q: (True, None)

    agent_key = "verify_m6_agent"
    main_dispatcher.AGENT_CLASS_MAP[agent_key] = _DummyAgent

    print("[1/3] Prüfe Standardpfad...")
    ok_session = f"m6v_ok_{uuid.uuid4().hex[:8]}"
    ok_query = f"verify_m6_ok_{uuid.uuid4().hex[:8]}"
    ok_result = await main_dispatcher.run_agent(
        agent_name=agent_key,
        query=ok_query,
        tools_description="tools",
        session_id=ok_session,
    )
    _assert(ok_result == f"verify_ok:{ok_query}", "Standardpfad lieferte unerwartetes Ergebnis.")

    ok_events = memory_manager.persistent.get_recent_interaction_events(
        limit=20,
        session_id=ok_session,
    )
    ok_event = next((ev for ev in ok_events if ev.get("user_input") == ok_query), None)
    _assert(ok_event is not None, "Kein persistiertes Event im Standardpfad gefunden.")
    _assert(ok_event.get("status") == "completed", "Standardpfad-Status ist nicht 'completed'.")
    _assert(ok_event.get("metadata", {}).get("execution_path") == "standard", "execution_path fehlt/ist falsch.")
    print("  ✅ Standardpfad OK")

    print("[2/3] Prüfe Fehlerpfad (unbekannter Agent)...")
    err_session = f"m6v_err_{uuid.uuid4().hex[:8]}"
    err_query = f"verify_m6_err_{uuid.uuid4().hex[:8]}"
    err_result = await main_dispatcher.run_agent(
        agent_name="verify_m6_missing_agent",
        query=err_query,
        tools_description="tools",
        session_id=err_session,
    )
    _assert(err_result is None, "Fehlerpfad sollte None zurückgeben.")

    err_events = memory_manager.persistent.get_recent_interaction_events(
        limit=20,
        session_id=err_session,
    )
    err_event = next((ev for ev in err_events if ev.get("user_input") == err_query), None)
    _assert(err_event is not None, "Kein persistiertes Error-Event gefunden.")
    _assert(err_event.get("status") == "error", "Fehlerpfad-Status ist nicht 'error'.")
    _assert(err_event.get("metadata", {}).get("error") == "agent_not_found", "Fehler-Metadaten fehlen.")
    print("  ✅ Fehlerpfad OK")

    print("[3/3] Prüfe Working-Memory Stats...")
    wm_context = memory_manager.build_working_memory_context(
        "was habe ich eben zu grafikkarten gesucht?",
        max_chars=800,
        max_related=3,
        max_recent_events=4,
    )
    wm_stats = memory_manager.get_last_working_memory_stats()
    _assert(isinstance(wm_stats, dict), "Working-Memory Stats fehlen.")
    _assert("status" in wm_stats, "Working-Memory Stats enthalten keinen Status.")
    if wm_stats.get("status") == "ok":
        _assert(len(wm_context) <= 800, "Working-Memory Budget überschritten.")
        _assert(wm_stats.get("final_chars") == len(wm_context), "final_chars inkonsistent.")
    print("  ✅ Working-Memory Stats OK")

    print("\nMilestone 6 Verification: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except AssertionError as exc:
        print(f"\nMilestone 6 Verification: FAIL - {exc}")
        raise SystemExit(1)
