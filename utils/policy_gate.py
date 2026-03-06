# utils/policy_gate.py
"""
Leichtgewichtiger Policy-Gate fuer destruktive Aktionen.
Kein vollstaendiges RBAC — nur Blocklist/Allowlist + Muster-Erkennung.
"""

import json
import logging
import os
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("policy_gate")
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

# Destruktive Tool-Aufrufe (Methoden-Namen)
BLOCKED_ACTIONS = [
    "delete_file",
    "remove_file",
    "rm_file",
    "submit_payment",
    "buy",
    "purchase",
    "checkout",
    "submit_form",
    "shutdown",
    "reboot",
    "format_disk",
    "drop_table",
    "delete_database",
]

# Muster in User-Anfragen die Bestaetigung erfordern
DANGEROUS_QUERY_PATTERNS = [
    r"\bl[oö]sche?\b.*\bdatei",
    r"\bdelete\b.*\bfile",
    r"\bkaufe?\b",
    r"\bbestell",
    r"\bbezahl",
    r"\bformat\b.*\bdisk",
    r"\bsudo\s+rm\b",
    r"\brm\s+-rf\b",
    r"\bdrop\s+table\b",
]

# Immer erlaubt (Whitelist ueberschreibt Blocklist)
ALWAYS_ALLOWED = [
    "search_web",
    "get_text",
    "read_file",
    "list_files",
    "scan_ui_elements",
    "screenshot",
    "describe_screen",
    "describe_screen_elements",
    "get_element_coordinates",
    "save_annotated_screenshot",
    "get_supported_element_types",
    "verify_fact",
    "verify_multiple_facts",
    "get_all_screen_text",
    "should_analyze_screen",
    "run_plan",
    "run_skill",
    "list_available_skills",
]

SENSITIVE_PARAM_PATTERNS = [
    (r"password", "Passwort-Parameter erkannt"),
    (r"api[_-]?key", "API-Key Parameter erkannt"),
    (r"secret", "Secret-Parameter erkannt"),
    (r"token", "Token-Parameter erkannt"),
    (r"credential", "Credential-Parameter erkannt"),
]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _policy_strict_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_POLICY_GATES_STRICT", False)


def _policy_audit_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_DECISIONS_ENABLED", False)


def _policy_canary_percent() -> int:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return 0
    try:
        raw = int(os.getenv("AUTONOMY_CANARY_PERCENT", "0").strip())
    except Exception:
        raw = 0
    return max(0, min(100, raw))


def _canary_bucket_for_key(key: str) -> int:
    '''
    post: 0 <= __return__ <= 99
    '''
    digest = hashlib.sha256((key or "").encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:8], 16) % 100


def _policy_rollout_guard_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_POLICY_ROLLBACK_ENABLED", False)


def _policy_runtime_overrides() -> Dict[str, Any]:
    overrides: Dict[str, Any] = {
        "strict_force_off": False,
        "canary_percent_override": None,
        "rollout_last_action": None,
    }
    try:
        from orchestration.task_queue import get_queue

        queue = get_queue()
        strict_state = queue.get_policy_runtime_state("strict_force_off")
        if strict_state:
            overrides["strict_force_off"] = str(strict_state.get("state_value") or "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        canary_state = queue.get_policy_runtime_state("canary_percent_override")
        if canary_state:
            try:
                overrides["canary_percent_override"] = int(str(canary_state.get("state_value") or "").strip())
            except Exception:
                overrides["canary_percent_override"] = None

        last_action_state = queue.get_policy_runtime_state("rollout_last_action")
        if last_action_state:
            overrides["rollout_last_action"] = last_action_state
    except Exception:
        return overrides
    return overrides


def _detect_sensitive_param_keys(params: Dict[str, Any]) -> list[str]:
    found: list[str] = []
    for key in params.keys():
        key_lower = str(key).lower()
        if any(re.search(pattern, key_lower) for pattern, _ in SENSITIVE_PARAM_PATTERNS):
            found.append(str(key))
    return found


def _mask_payload_for_audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in payload.items():
        key_lower = str(key).lower()
        if any(re.search(pattern, key_lower) for pattern, _ in SENSITIVE_PARAM_PATTERNS):
            safe[str(key)] = "***MASKED***"
        elif isinstance(value, str):
            safe[str(key)] = value[:200] + ("..." if len(value) > 200 else "")
        elif isinstance(value, dict):
            safe[str(key)] = _mask_payload_for_audit(value)
        else:
            safe[str(key)] = value
    return safe


def check_tool_policy(
    method_name: str, params: dict = None
) -> Tuple[bool, Optional[str]]:
    """
    Prueft ob ein Tool-Aufruf erlaubt ist.

    Returns:
        (allowed, reason) — wenn nicht erlaubt, erklaert reason warum.
    """
    if method_name in ALWAYS_ALLOWED:
        return True, None

    if method_name in BLOCKED_ACTIONS:
        reason = f"Policy blockiert: '{method_name}' ist eine destruktive Aktion und erfordert Bestaetigung."
        log.warning(f"[policy] {reason}")
        return False, reason

    if params:
        for key in params.keys():
            key_lower = key.lower()
            for pattern, _warning in SENSITIVE_PARAM_PATTERNS:
                if re.search(pattern, key_lower):
                    log.warning(f"[policy] Sensitiver Parameter in Tool-Call: {key}")
                    break

    return True, None


def check_query_policy(user_query: str) -> Tuple[bool, Optional[str]]:
    """
    Prueft ob eine User-Anfrage potenziell gefaehrlich ist.

    Returns:
        (safe, warning) — wenn nicht safe, sollte der Dispatcher Bestaetigung einholen.
    """
    query_lower = user_query.lower()

    for pattern in DANGEROUS_QUERY_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            warning = f"Potenziell destruktive Anfrage erkannt ('{match.group()}'). Bestaetigung empfohlen."
            log.warning(f"[policy] {warning}")
            return False, warning

    return True, None


def evaluate_policy_gate(
    *,
    gate: str,
    subject: str,
    payload: Optional[Dict[str, Any]] = None,
    source: str = "unknown",
    strict: Optional[bool] = None,
    runtime_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Formale Policy-Entscheidung fuer kritische Pfade.

    gate:
      - "query"      (User-Query)
      - "tool"       (Tool-Call)
      - "delegation" (Agent-Delegation)
      - "autonomous_task" (Task aus autonomem Runner / Self-Healing)
    """
    gate_type = (gate or "").strip().lower()
    subject_text = (subject or "").strip()
    data = payload or {}
    overrides = runtime_overrides if isinstance(runtime_overrides, dict) else _policy_runtime_overrides()
    strict_forced_off = bool(overrides.get("strict_force_off", False))

    strict_mode_base = _policy_strict_enabled() if strict is None else bool(strict)
    strict_mode = bool(strict_mode_base and not strict_forced_off)
    canary_override_raw = overrides.get("canary_percent_override")
    try:
        canary_override = None if canary_override_raw is None else int(canary_override_raw)
    except Exception:
        canary_override = None
    canary_percent_effective = (
        max(0, min(100, canary_override))
        if canary_override is not None
        else _policy_canary_percent()
    )

    decision: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "policy_version": "m4.3",
        "gate": gate_type,
        "source": source,
        "subject": subject_text[:200],
        "strict_mode": strict_mode,
        "allowed": True,
        "blocked": False,
        "action": "allow",
        "reason": None,
        "violations": [],
        "payload": _mask_payload_for_audit(data),
        "audit_enabled": _policy_audit_enabled(),
        "canary_percent": canary_percent_effective,
        "canary_bucket": None,
        "canary_enforced": True,
        "strict_forced_off": strict_forced_off,
        "runtime_canary_override": canary_override,
    }

    if gate_type == "query":
        query_text = str(data.get("query") or subject_text)
        safe, warning = check_query_policy(query_text)
        if not safe:
            decision["violations"].append("dangerous_query")
            decision["reason"] = warning
            if strict_mode:
                decision["allowed"] = False
                decision["blocked"] = True
                decision["action"] = "block"
            else:
                decision["action"] = "observe"

    elif gate_type == "tool":
        method_name = subject_text
        raw_params = data.get("params", data)
        params = raw_params if isinstance(raw_params, dict) else {}
        allowed, reason = check_tool_policy(method_name, params)
        if not allowed:
            decision["violations"].append("blocked_tool")
            decision["reason"] = reason
            decision["allowed"] = False
            decision["blocked"] = True
            decision["action"] = "block"
            decision["hard_block"] = True
        else:
            sensitive_keys = _detect_sensitive_param_keys(params)
            if sensitive_keys:
                decision["violations"].append("sensitive_params")
                decision["reason"] = f"Sensitive Parameter erkannt: {', '.join(sensitive_keys[:4])}"
                decision["sensitive_keys"] = sensitive_keys[:8]
                if strict_mode:
                    decision["allowed"] = False
                    decision["blocked"] = True
                    decision["action"] = "block"
                else:
                    decision["action"] = "observe"

    elif gate_type == "delegation":
        task_text = str(data.get("task") or "")
        to_agent = str(data.get("to_agent") or "").strip().lower()
        safe, warning = check_query_policy(task_text)
        if not safe:
            decision["violations"].append("dangerous_task")
            decision["reason"] = warning
            if strict_mode and to_agent in {"shell", "system"}:
                decision["allowed"] = False
                decision["blocked"] = True
                decision["action"] = "block"
            else:
                decision["action"] = "observe"

    elif gate_type == "autonomous_task":
        task_text = str(data.get("task") or subject_text)
        safe, warning = check_query_policy(task_text)
        if not safe:
            decision["violations"].append("dangerous_autonomous_task")
            decision["reason"] = warning
            # Autonome Pfade haben keinen sicheren Human-Confirm-Loop.
            if strict_mode:
                decision["allowed"] = False
                decision["blocked"] = True
                decision["action"] = "block"
            else:
                decision["action"] = "observe"

    # Canary-Rollout fuer strict-Enforcement (ausser harte Blocklisten-Treffer).
    if (
        bool(decision.get("strict_mode"))
        and bool(decision.get("blocked"))
        and not bool(decision.get("hard_block"))
    ):
        percent = int(decision.get("canary_percent", 0) or 0)
        if 0 < percent < 100:
            canary_key = f"{gate_type}|{source}|{subject_text[:120]}"
            bucket = _canary_bucket_for_key(canary_key)
            enforced = bucket < percent
            decision["canary_bucket"] = bucket
            decision["canary_enforced"] = bool(enforced)
            if not enforced:
                decision["allowed"] = True
                decision["blocked"] = False
                decision["action"] = "observe"
                decision["violations"].append("canary_deferred")
        else:
            decision["canary_enforced"] = True

    return decision


def evaluate_and_apply_rollout_guard(*, window_hours: Optional[int] = None, queue=None) -> Dict[str, Any]:
    """Prueft Policy-Metriken und setzt bei Bedarf Runtime-Rollback-Overrides."""
    if not _policy_rollout_guard_enabled():
        return {"status": "disabled", "action": "none"}

    try:
        from orchestration.task_queue import get_queue

        q = queue or get_queue()
    except Exception:
        return {"status": "error", "action": "queue_unavailable"}

    try:
        window = max(1, int(window_hours if window_hours is not None else os.getenv("AUTONOMY_POLICY_ROLLBACK_WINDOW_HOURS", "1")))
    except Exception:
        window = 1
    try:
        min_decisions = max(1, int(os.getenv("AUTONOMY_POLICY_ROLLBACK_MIN_DECISIONS", "20")))
    except Exception:
        min_decisions = 20
    try:
        block_rate_threshold = float(os.getenv("AUTONOMY_POLICY_ROLLBACK_BLOCK_RATE_PCT", "40"))
    except Exception:
        block_rate_threshold = 40.0
    try:
        cooldown_min = max(1, int(os.getenv("AUTONOMY_POLICY_ROLLBACK_COOLDOWN_MIN", "60")))
    except Exception:
        cooldown_min = 60

    metrics = q.get_policy_decision_metrics(window_hours=window)
    decisions_total = int(metrics.get("decisions_total", 0) or 0)
    blocked_total = int(metrics.get("blocked_total", 0) or 0)
    block_rate = 0.0 if decisions_total == 0 else (blocked_total / decisions_total) * 100.0

    last_action_state = q.get_policy_runtime_state("rollout_last_action")
    if last_action_state:
        updated_at_raw = str(last_action_state.get("updated_at") or "")
        try:
            updated_at = datetime.fromisoformat(updated_at_raw) if updated_at_raw else None
        except Exception:
            updated_at = None
        if updated_at is not None:
            if (datetime.now() - updated_at) < timedelta(minutes=cooldown_min):
                return {
                    "status": "ok",
                    "action": "cooldown_active",
                    "window_hours": window,
                    "decisions_total": decisions_total,
                    "blocked_total": blocked_total,
                    "block_rate_pct": round(block_rate, 2),
                }

    should_rollback = decisions_total >= min_decisions and block_rate >= float(block_rate_threshold)
    if not should_rollback:
        return {
            "status": "ok",
            "action": "no_action",
            "window_hours": window,
            "decisions_total": decisions_total,
            "blocked_total": blocked_total,
            "block_rate_pct": round(block_rate, 2),
        }

    reason = (
        f"policy_block_rate_spike:{round(block_rate,2)}pct "
        f"(blocked={blocked_total}, total={decisions_total}, threshold={block_rate_threshold})"
    )
    now_iso = datetime.now().isoformat()
    q.set_policy_runtime_state(
        "strict_force_off",
        "true",
        metadata_update={
            "reason": reason,
            "action": "auto_rollback",
            "window_hours": window,
            "triggered_at": now_iso,
        },
        observed_at=now_iso,
    )
    q.set_policy_runtime_state(
        "canary_percent_override",
        "0",
        metadata_update={
            "reason": reason,
            "action": "auto_rollback",
            "triggered_at": now_iso,
        },
        observed_at=now_iso,
    )
    q.set_policy_runtime_state(
        "rollout_last_action",
        "rollback_applied",
        metadata_update={
            "reason": reason,
            "triggered_at": now_iso,
            "block_rate_pct": round(block_rate, 2),
            "blocked_total": blocked_total,
            "decisions_total": decisions_total,
        },
        observed_at=now_iso,
    )
    return {
        "status": "ok",
        "action": "rollback_applied",
        "window_hours": window,
        "decisions_total": decisions_total,
        "blocked_total": blocked_total,
        "block_rate_pct": round(block_rate, 2),
        "reason": reason,
    }


def audit_policy_decision(decision: Dict[str, Any]) -> None:
    """Persistiert Policy-Entscheidungen (optional per Feature-Flag)."""
    if not isinstance(decision, dict):
        return

    log_level = logging.WARNING if decision.get("blocked") else logging.INFO
    log.log(
        log_level,
        "[policy-decision] gate=%s action=%s blocked=%s source=%s reason=%s",
        decision.get("gate"),
        decision.get("action"),
        decision.get("blocked"),
        decision.get("source"),
        decision.get("reason"),
    )

    # Persistente Aggregation im TaskQueue-Store (best effort).
    try:
        from orchestration.task_queue import get_queue

        get_queue().record_policy_decision(
            decision,
            observed_at=str(decision.get("timestamp") or ""),
        )
    except Exception:
        pass

    if not bool(decision.get("audit_enabled")):
        return

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = LOGS_DIR / f"{date_str}_policy_decisions.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(decision, ensure_ascii=True, default=str) + "\n")
    except Exception as e:
        log.debug("Policy-Decision-Audit fehlgeschlagen: %s", e)


def get_policy_decision_metrics(window_hours: int = 24) -> Dict[str, Any]:
    """Liest Policy-Decision-JSONL und aggregiert Kennzahlen fuer Monitoring."""
    window = max(1, int(window_hours))

    # Primärquelle ab M4.3: persistente TaskQueue-Metriken.
    try:
        from orchestration.task_queue import get_queue

        db_metrics = get_queue().get_policy_decision_metrics(window_hours=window)
        if int(db_metrics.get("decisions_total", 0) or 0) > 0:
            return db_metrics
    except Exception:
        pass

    now = datetime.now()
    since = now - timedelta(hours=window)
    metrics: Dict[str, Any] = {
        "window_hours": window,
        "decisions_total": 0,
        "blocked_total": 0,
        "observed_total": 0,
        "allowed_total": 0,
        "strict_decisions": 0,
        "canary_deferred_total": 0,
        "by_gate": {},
        "by_source": {},
        "last_blocked": None,
    }

    if not LOGS_DIR.exists():
        return metrics

    paths = sorted(LOGS_DIR.glob("*_policy_decisions.jsonl"), reverse=True)
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except Exception:
                        continue

                    timestamp_str = str(entry.get("timestamp") or "")
                    try:
                        ts = datetime.fromisoformat(timestamp_str) if timestamp_str else None
                    except Exception:
                        ts = None
                    if ts is None or ts < since:
                        continue

                    metrics["decisions_total"] += 1
                    gate = str(entry.get("gate") or "unknown")
                    source = str(entry.get("source") or "unknown")
                    action = str(entry.get("action") or "allow")
                    blocked = bool(entry.get("blocked"))
                    strict_mode = bool(entry.get("strict_mode"))
                    canary_enforced = bool(entry.get("canary_enforced", True))

                    by_gate = metrics["by_gate"]
                    by_gate[gate] = int(by_gate.get(gate, 0) or 0) + 1
                    by_source = metrics["by_source"]
                    by_source[source] = int(by_source.get(source, 0) or 0) + 1

                    if strict_mode:
                        metrics["strict_decisions"] += 1
                    if strict_mode and not canary_enforced:
                        metrics["canary_deferred_total"] += 1
                    if blocked:
                        metrics["blocked_total"] += 1
                        last_blocked = metrics.get("last_blocked")
                        if not isinstance(last_blocked, dict) or timestamp_str > str(last_blocked.get("timestamp") or ""):
                            metrics["last_blocked"] = {
                                "timestamp": timestamp_str,
                                "gate": gate,
                                "source": source,
                                "reason": str(entry.get("reason") or ""),
                            }
                    elif action == "observe":
                        metrics["observed_total"] += 1
                    else:
                        metrics["allowed_total"] += 1
        except Exception:
            continue

    return metrics


def audit_tool_call(method_name: str, params: dict, result: dict = None) -> None:
    """
    Loggt Tool-Aufrufe fuer Audit-Zwecke.

    Sensible Parameter werden maskiert.
    """
    safe_params = {}
    if params:
        for key, value in params.items():
            key_lower = key.lower()
            is_sensitive = any(
                re.search(pattern, key_lower) for pattern, _ in SENSITIVE_PARAM_PATTERNS
            )
            if is_sensitive:
                safe_params[key] = "***MASKED***"
            elif isinstance(value, str) and len(value) > 100:
                safe_params[key] = f"{value[:50]}... ({len(value)} chars)"
            else:
                safe_params[key] = value

    log.info(f"[audit] Tool-Call: {method_name}({safe_params})")
    if result:
        if isinstance(result, dict):
            if result.get("error"):
                log.warning(f"[audit] Tool-Result ERROR: {result.get('error')}")
            elif result.get("blocked_by_policy"):
                log.warning(f"[audit] Tool-Result BLOCKED by policy")
            elif result.get("validation_failed"):
                log.warning(f"[audit] Tool-Result FAILED validation")
