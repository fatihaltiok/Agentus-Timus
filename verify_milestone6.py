#!/usr/bin/env python3
"""
Milestone 6 Rollout Verification

Führt einen schnellen Go/No-Go Check aus:
1) Standard-Run-Agent Pfad persistiert Event mit Runtime-Metadaten
2) Fehlerpfad (unbekannter Agent) persistiert Error-Event
3) Working-Memory Kontext + Stats werden erzeugt
4) Dynamischer Recall priorisiert offene Anliegen innerhalb der Session
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

    print("[1/4] Prüfe Standardpfad...")
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
    _assert(
        isinstance(ok_event.get("metadata", {}).get("memory_snapshot"), dict),
        "memory_snapshot fehlt im Standardpfad.",
    )
    print("  ✅ Standardpfad OK")

    print("[2/4] Prüfe Fehlerpfad (unbekannter Agent)...")
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
    _assert(
        isinstance(err_event.get("metadata", {}).get("memory_snapshot"), dict),
        "memory_snapshot fehlt im Fehlerpfad.",
    )
    print("  ✅ Fehlerpfad OK")

    print("[3/4] Prüfe Working-Memory Stats...")
    wm_context = memory_manager.build_working_memory_context(
        "was habe ich eben zu grafikkarten gesucht?",
        max_chars=800,
        max_related=3,
        max_recent_events=4,
    )
    wm_stats = memory_manager.get_last_working_memory_stats()
    _assert(isinstance(wm_stats, dict), "Working-Memory Stats fehlen.")
    _assert("status" in wm_stats, "Working-Memory Stats enthalten keinen Status.")
    _assert("focus_terms_count" in wm_stats, "focus_terms_count fehlt in Working-Memory Stats.")
    _assert("prefer_unresolved" in wm_stats, "prefer_unresolved fehlt in Working-Memory Stats.")
    if wm_stats.get("status") == "ok":
        _assert(len(wm_context) <= 800, "Working-Memory Budget überschritten.")
        _assert(wm_stats.get("final_chars") == len(wm_context), "final_chars inkonsistent.")
    print("  ✅ Working-Memory Stats OK")

    print("[4/4] Prüfe dynamischen Recall für offene Anliegen...")
    recall_session = f"m6v_recall_{uuid.uuid4().hex[:8]}"
    memory_manager.log_interaction_event(
        user_input="suche grafikkarten preise auf ebay",
        assistant_response="ActionPlan fehlgeschlagen: Tippen fehlgeschlagen",
        agent_name="executor",
        status="error",
        external_session_id=recall_session,
        metadata={"source": "verify_m6"},
    )
    memory_manager.log_interaction_event(
        user_input="wie ist das wetter",
        assistant_response="Heute sonnig.",
        agent_name="executor",
        status="completed",
        external_session_id=recall_session,
        metadata={"source": "verify_m6"},
    )
    recall = memory_manager.unified_recall(
        query="was ist aktuell offen",
        n_results=3,
        session_id=recall_session,
    )
    _assert(recall.get("status") == "success", "Unified recall liefert keinen Erfolg.")
    recall_items = recall.get("memories", [])
    _assert(bool(recall_items), "Unified recall lieferte keine Ergebnisse.")
    top_text = str(recall_items[0].get("text", "")).lower()
    _assert("grafikkarten" in top_text, "Offenes Anliegen wurde nicht priorisiert.")
    print("  ✅ Dynamischer Recall OK")

    print("\nMilestone 6 Verification: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except AssertionError as exc:
        print(f"\nMilestone 6 Verification: FAIL - {exc}")
        raise SystemExit(1)
