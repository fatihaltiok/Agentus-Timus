"""Phase E E2: compile prioritized improvement candidates into concrete tasks."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Mapping


_CATEGORY_TARGET_FILES: dict[str, tuple[str, ...]] = {
    "routing": (
        "main_dispatcher.py",
        "orchestration/meta_orchestration.py",
        "orchestration/meta_response_policy.py",
    ),
    "context": (
        "orchestration/conversation_state.py",
        "orchestration/topic_state_history.py",
        "orchestration/turn_understanding.py",
        "orchestration/specialist_context.py",
    ),
    "policy": (
        "orchestration/approval_auth_contract.py",
        "orchestration/pending_workflow_state.py",
        "orchestration/auth_session_state.py",
        "orchestration/meta_response_policy.py",
    ),
    "runtime": (
        "server/mcp_server.py",
        "orchestration/autonomy_observation.py",
        "orchestration/health_orchestrator.py",
        "orchestration/autonomous_runner.py",
    ),
    "tool": (
        "tools/visual_browser_tool/tool.py",
        "tools/mouse_tool/tool.py",
        "tools/email_tool/tool.py",
    ),
    "specialist": (
        "agent/agent_registry.py",
        "orchestration/specialist_context.py",
    ),
    "memory": (
        "memory/memory_system.py",
        "orchestration/preference_instruction_memory.py",
        "orchestration/topic_state_history.py",
    ),
    "ux_handoff": (
        "server/mcp_server.py",
        "orchestration/longrunner_transport.py",
        "gateway/telegram_gateway.py",
        "server/canvas_ui.py",
    ),
}

_CATEGORY_TEST_TARGETS: dict[str, tuple[str, ...]] = {
    "routing": (
        "tests/test_meta_orchestration.py",
        "tests/test_specialist_handoffs.py",
    ),
    "context": (
        "tests/test_android_chat_language.py",
        "tests/test_topic_state_history.py",
    ),
    "policy": (
        "tests/test_specialist_handoffs.py",
        "tests/test_pending_workflow_state.py",
    ),
    "runtime": (
        "tests/test_autonomy_observation.py",
        "tests/test_c2_entrypoints.py",
    ),
    "tool": (
        "tests/test_visual_browser_tool.py",
        "tests/test_mouse_tool_text_entry.py",
    ),
    "specialist": (
        "tests/test_specialist_context_runtime.py",
        "tests/test_specialist_handoffs.py",
    ),
    "memory": (
        "tests/test_improvement_candidates.py",
        "tests/test_session_reflection_suggestions.py",
    ),
    "ux_handoff": (
        "tests/test_c4_longrunner_runtime.py",
        "tests/test_telegram_feedback_gateway.py",
    ),
}

_SENSITIVE_POLICY_TOKENS = {
    "2fa",
    "captcha",
    "credential",
    "credentials",
    "oauth",
    "passkey",
    "passwort",
    "password",
    "secret",
}

_CONFIG_HINT_TOKENS = {
    "config",
    "cooldown",
    "env",
    "flag",
    "limit",
    "retry",
    "threshold",
    "timeout",
}

_TEST_HINT_TOKENS = {
    "contract",
    "crosshair",
    "hypothesis",
    "regression",
    "test",
}

_SHELL_HINT_TOKENS = {
    "cpu",
    "disk",
    "health",
    "journal",
    "port",
    "ram",
    "restart",
    "service",
    "status",
}


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _normalize_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        text = text.replace("follow-up", "followup")
        text = re.sub(r"[^a-z0-9_]+", " ", text)
        for token in text.split():
            if token:
                tokens.add(token)
    return tokens


def _stable_task_id(candidate_id: str) -> str:
    digest = hashlib.sha1(str(candidate_id or "").encode("utf-8")).hexdigest()[:10]
    return f"task:{digest}"


def _target_files_for_candidate(category: str, tokens: set[str], target: str) -> list[str]:
    files = list(_CATEGORY_TARGET_FILES.get(category, ()))
    if category == "specialist":
        normalized_target = str(target or "").strip().lower()
        if normalized_target in {"executor", "research", "visual", "system", "meta"}:
            files.insert(0, f"agent/agents/{normalized_target}.py")
    if category == "tool":
        if {"email", "smtp"} & tokens:
            files = ["tools/email_tool/tool.py", *files]
        elif {"mouse", "keyboard", "clipboard"} & tokens:
            files = ["tools/mouse_tool/tool.py", *files]
        elif {"browser", "visual", "chrome", "login"} & tokens:
            files = ["tools/visual_browser_tool/tool.py", *files]
    deduped: list[str] = []
    for item in files:
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:4]


def _test_targets_for_candidate(category: str, tokens: set[str]) -> list[str]:
    files = list(_CATEGORY_TEST_TARGETS.get(category, ()))
    if category == "tool" and {"email", "smtp"} & tokens:
        files = ["tests/test_specialist_context_runtime.py", *files]
    deduped: list[str] = []
    for item in files:
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:3]


def _likely_root_cause(candidate: Mapping[str, Any], tokens: set[str]) -> str:
    category = str(candidate.get("category") or "").strip().lower()
    source_count = int(candidate.get("source_count") or 1)
    freshness = str(candidate.get("freshness_state") or "").strip().lower()
    if category == "routing":
        return "dispatcher_or_meta_policy_drift"
    if category == "context":
        return "state_anchor_or_followup_binding_gap"
    if category == "policy":
        if _SENSITIVE_POLICY_TOKENS & tokens:
            return "sensitive_auth_or_secret_boundary"
        return "approval_auth_policy_gap"
    if category == "runtime":
        if {"health", "restart", "service"} & tokens:
            return "service_health_or_runtime_coordination_gap"
        return "runtime_guard_or_observability_gap"
    if category == "tool":
        return "tool_contract_or_ui_integration_gap"
    if category == "specialist":
        return "specialist_context_alignment_gap"
    if category == "memory":
        return "memory_retrieval_or_decay_gap"
    if category == "ux_handoff":
        return "workflow_rendering_or_resume_gap"
    if source_count == 1 and freshness == "stale":
        return "stale_single_source_signal"
    return "structural_runtime_gap"


def _choose_task_kind(candidate: Mapping[str, Any], tokens: set[str]) -> str:
    category = str(candidate.get("category") or "").strip().lower()
    evidence_level = str(candidate.get("evidence_level") or "").strip().lower()
    freshness = str(candidate.get("freshness_state") or "").strip().lower()
    signal_class = str(candidate.get("signal_class") or "").strip().lower()
    source_count = int(candidate.get("source_count") or 1)

    if category == "policy" and (_SENSITIVE_POLICY_TOKENS & tokens):
        return "do_not_autofix"
    if freshness == "stale" and source_count <= 1 and evidence_level in {"observation", "incident"}:
        return "verification_needed"
    if signal_class == "transient_signal" and source_count <= 1:
        return "verification_needed"
    if _TEST_HINT_TOKENS & tokens:
        return "test_gap"
    if _CONFIG_HINT_TOKENS & tokens:
        return "config_change_candidate"
    if category == "runtime" and (_SHELL_HINT_TOKENS & tokens):
        return "shell_task"
    return "developer_task"


def _safe_fix_class(task_kind: str, category: str) -> str:
    if task_kind == "do_not_autofix":
        return "human_mediated_only"
    if task_kind == "verification_needed":
        return "needs_stronger_evidence"
    if task_kind == "test_gap":
        return "regression_test_expansion"
    if task_kind == "config_change_candidate":
        return "conservative_threshold_tuning"
    if task_kind == "shell_task":
        return "runtime_probe_or_service_recovery"
    if category == "routing":
        return "routing_policy_hardening"
    if category == "context":
        return "state_binding_hardening"
    if category == "policy":
        return "workflow_guard_hardening"
    if category == "runtime":
        return "runtime_guard_hardening"
    if category == "tool":
        return "tool_contract_hardening"
    if category == "specialist":
        return "specialist_alignment_hardening"
    if category == "memory":
        return "memory_retrieval_hardening"
    if category == "ux_handoff":
        return "workflow_rendering_hardening"
    return "minimal_logic_hardening"


def _rollback_risk(task_kind: str, category: str) -> str:
    if task_kind == "do_not_autofix":
        return "high"
    if task_kind == "verification_needed":
        return "low"
    if task_kind == "shell_task":
        return "medium"
    if category in {"routing", "context", "tool", "ux_handoff"}:
        return "medium"
    return "low"


def _execution_mode_hint(task_kind: str) -> str:
    if task_kind == "do_not_autofix":
        return "human_only"
    if task_kind == "verification_needed":
        return "observe_only"
    return "developer_task"


def compile_improvement_task(candidate: Mapping[str, Any]) -> dict[str, Any]:
    candidate_id = _clean_text(candidate.get("candidate_id"), limit=80)
    category = _clean_text(candidate.get("category"), limit=64).lower() or "runtime"
    target = _clean_text(candidate.get("target"), limit=80)
    problem = _clean_text(candidate.get("problem"))
    proposed_action = _clean_text(candidate.get("proposed_action"))
    tokens = _normalize_tokens(category, target, problem, proposed_action, candidate.get("summary"))
    task_kind = _choose_task_kind(candidate, tokens)
    required_checks = ["py_compile"]
    if task_kind in {"developer_task", "config_change_candidate", "test_gap", "shell_task"}:
        required_checks.append("pytest_targeted")

    return {
        "task_id": _stable_task_id(candidate_id),
        "candidate_id": candidate_id,
        "state": "compiled",
        "task_kind": task_kind,
        "execution_mode_hint": _execution_mode_hint(task_kind),
        "title": _clean_text(f"{category}:{target}" if target else category, limit=96),
        "category": category,
        "target": target,
        "problem": problem,
        "proposed_action": proposed_action,
        "priority_score": round(float(candidate.get("priority_score") or 0.0), 3),
        "priority_reasons": list(candidate.get("priority_reasons") or []),
        "evidence": {
            "evidence_level": _clean_text(candidate.get("evidence_level"), limit=32),
            "evidence_basis": _clean_text(candidate.get("evidence_basis"), limit=64),
            "signal_class": _clean_text(candidate.get("signal_class"), limit=32),
            "source_count": max(1, int(candidate.get("source_count") or 1)),
            "occurrence_count": max(1, int(candidate.get("occurrence_count") or 1)),
            "freshness_state": _clean_text(candidate.get("freshness_state"), limit=32),
            "merged_sources": [
                _clean_text(item, limit=48)
                for item in (candidate.get("merged_sources") or [candidate.get("source")])
                if _clean_text(item, limit=48)
            ],
        },
        "likely_root_cause": _likely_root_cause(candidate, tokens),
        "safe_fix_class": _safe_fix_class(task_kind, category),
        "target_files": _target_files_for_candidate(category, tokens, target),
        "verification_plan": {
            "required_checks": required_checks,
            "suggested_test_targets": _test_targets_for_candidate(category, tokens),
            "success_criteria": (
                "Der Kandidat bleibt reproduzierbar adressiert, die Ziel-Regressionen sind gruen "
                "und es entstehen keine neuen Routing-, Policy- oder Runtime-Brueche."
            ),
        },
        "rollback_risk": _rollback_risk(task_kind, category),
    }


def compile_improvement_tasks(
    candidates: Iterable[Mapping[str, Any]],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    compiled = [compile_improvement_task(candidate) for candidate in candidates]
    compiled.sort(
        key=lambda item: (
            -float(item.get("priority_score") or 0.0),
            str(item.get("task_kind") or ""),
            str(item.get("candidate_id") or ""),
        )
    )
    if limit is None:
        return compiled
    return compiled[: max(0, int(limit))]
