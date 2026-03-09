"""Runtime budget guards for LLM usage."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional

from agent.providers import ModelProvider
from orchestration.self_improvement_engine import get_improvement_engine


def _env_float(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(int(raw), 1)
    except ValueError:
        return default


def _env_text(name: str) -> str:
    return (os.getenv(name, "") or "").strip()


@dataclass(frozen=True)
class BudgetThresholds:
    warn_usd: float = 0.0
    soft_limit_usd: float = 0.0
    hard_limit_usd: float = 0.0


@dataclass(frozen=True)
class BudgetScopeState:
    scope: str
    current_cost_usd: float
    thresholds: BudgetThresholds
    state: str


@dataclass(frozen=True)
class LLMBudgetDecision:
    blocked: bool
    warning: bool
    soft_limited: bool
    max_tokens_cap: Optional[int]
    state: str
    scopes: List[BudgetScopeState]
    message: str


@dataclass(frozen=True)
class BudgetModelOverride:
    provider: ModelProvider
    model: str


def _normalize_thresholds(thresholds: BudgetThresholds) -> BudgetThresholds:
    warn_raw = float(thresholds.warn_usd or 0.0)
    soft_raw = float(thresholds.soft_limit_usd or 0.0)
    hard_raw = float(thresholds.hard_limit_usd or 0.0)
    warn = max(warn_raw if math.isfinite(warn_raw) else 0.0, 0.0)
    soft = max(soft_raw if math.isfinite(soft_raw) else 0.0, warn)
    hard = max(hard_raw if math.isfinite(hard_raw) else 0.0, soft)
    return BudgetThresholds(warn_usd=warn, soft_limit_usd=soft, hard_limit_usd=hard)


def _state_for_cost(current_cost_usd: float, thresholds: BudgetThresholds) -> str:
    normalized = _normalize_thresholds(thresholds)
    current = max(float(current_cost_usd or 0.0), 0.0)
    if normalized.hard_limit_usd > 0.0 and current >= normalized.hard_limit_usd:
        return "hard_limit"
    if normalized.soft_limit_usd > 0.0 and current >= normalized.soft_limit_usd:
        return "soft_limit"
    if normalized.warn_usd > 0.0 and current >= normalized.warn_usd:
        return "warn"
    return "ok"


def _thresholds_for_scope(scope: str) -> BudgetThresholds:
    upper = scope.upper()
    return _normalize_thresholds(
        BudgetThresholds(
            warn_usd=_env_float(f"TIMUS_LLM_BUDGET_{upper}_WARN_USD", 0.0),
            soft_limit_usd=_env_float(f"TIMUS_LLM_BUDGET_{upper}_SOFT_LIMIT_USD", 0.0),
            hard_limit_usd=_env_float(f"TIMUS_LLM_BUDGET_{upper}_HARD_LIMIT_USD", 0.0),
        )
    )


def _scope_state(scope: str, current_cost_usd: float) -> BudgetScopeState:
    thresholds = _thresholds_for_scope(scope)
    return BudgetScopeState(
        scope=scope,
        current_cost_usd=max(float(current_cost_usd or 0.0), 0.0),
        thresholds=thresholds,
        state=_state_for_cost(current_cost_usd, thresholds),
    )


def _summarize_states(scopes: List[BudgetScopeState]) -> str:
    active = [scope for scope in scopes if scope.state != "ok"]
    if not active:
        return ""
    parts = [
        f"{scope.scope}={scope.state} (${scope.current_cost_usd:.6f})"
        for scope in active
    ]
    return ", ".join(parts)


def evaluate_llm_budget(
    *,
    agent: str,
    session_id: str = "",
    requested_max_tokens: int,
) -> LLMBudgetDecision:
    """Evaluates warning/soft/hard states against configured LLM budgets."""
    window_days = _env_int("TIMUS_LLM_BUDGET_WINDOW_DAYS", 1)
    soft_cap = _env_int("TIMUS_LLM_BUDGET_SOFT_MAX_TOKENS", 600)
    engine = get_improvement_engine()

    global_summary = engine.get_llm_usage_summary(days=window_days, limit=3)
    scopes = [_scope_state("global", global_summary.get("total_cost_usd", 0.0))]

    if agent:
        agent_summary = engine.get_llm_usage_summary(days=window_days, agent=agent, limit=3)
        scopes.append(_scope_state("agent", agent_summary.get("total_cost_usd", 0.0)))

    if session_id:
        session_summary = engine.get_llm_usage_summary(days=window_days, session_id=session_id, limit=3)
        scopes.append(_scope_state("session", session_summary.get("total_cost_usd", 0.0)))

    states = [scope.state for scope in scopes]
    if "hard_limit" in states:
        return LLMBudgetDecision(
            blocked=True,
            warning=True,
            soft_limited=True,
            max_tokens_cap=None,
            state="hard_limit",
            scopes=scopes,
            message=f"LLM hard budget erreicht: {_summarize_states(scopes)}",
        )
    if "soft_limit" in states:
        return LLMBudgetDecision(
            blocked=False,
            warning=True,
            soft_limited=True,
            max_tokens_cap=min(max(int(requested_max_tokens or 1), 1), soft_cap),
            state="soft_limit",
            scopes=scopes,
            message=f"LLM soft budget aktiv: {_summarize_states(scopes)}",
        )
    if "warn" in states:
        return LLMBudgetDecision(
            blocked=False,
            warning=True,
            soft_limited=False,
            max_tokens_cap=min(max(int(requested_max_tokens or 1), 1), max(int(requested_max_tokens or 1), 1)),
            state="warn",
            scopes=scopes,
            message=f"LLM budget warn: {_summarize_states(scopes)}",
        )
    return LLMBudgetDecision(
        blocked=False,
        warning=False,
        soft_limited=False,
        max_tokens_cap=min(max(int(requested_max_tokens or 1), 1), max(int(requested_max_tokens or 1), 1)),
        state="ok",
        scopes=scopes,
        message="",
    )


def get_public_budget_status() -> dict:
    """Returns aggregate budget status for status snapshots and tooling."""
    decision = evaluate_llm_budget(agent="", session_id="", requested_max_tokens=1)
    return {
        "state": decision.state,
        "message": decision.message,
        "scopes": [
            {
                "scope": scope.scope,
                "current_cost_usd": round(scope.current_cost_usd, 6),
                "warn_usd": round(scope.thresholds.warn_usd, 6),
                "soft_limit_usd": round(scope.thresholds.soft_limit_usd, 6),
                "hard_limit_usd": round(scope.thresholds.hard_limit_usd, 6),
                "state": scope.state,
            }
            for scope in decision.scopes
        ],
        "soft_max_tokens": _env_int("TIMUS_LLM_BUDGET_SOFT_MAX_TOKENS", 600),
        "window_days": _env_int("TIMUS_LLM_BUDGET_WINDOW_DAYS", 1),
    }


def resolve_soft_budget_model_override(
    *,
    agent: str,
    provider: ModelProvider,
    model: str,
    decision: LLMBudgetDecision,
) -> Optional[BudgetModelOverride]:
    """Returns an optional cheaper model override for soft-limited calls."""
    if decision.blocked or not decision.soft_limited:
        return None

    agent_key = (agent or "default").strip().upper() or "DEFAULT"
    provider_raw = (
        _env_text(f"TIMUS_LLM_BUDGET_{agent_key}_SOFT_PROVIDER")
        or _env_text("TIMUS_LLM_BUDGET_DEFAULT_SOFT_PROVIDER")
    )
    model_raw = (
        _env_text(f"TIMUS_LLM_BUDGET_{agent_key}_SOFT_MODEL")
        or _env_text("TIMUS_LLM_BUDGET_DEFAULT_SOFT_MODEL")
    )
    if not model_raw:
        return None

    target_provider = provider
    if provider_raw:
        try:
            target_provider = ModelProvider(provider_raw.lower())
        except ValueError:
            target_provider = provider

    if target_provider == provider and model_raw == model:
        return None
    return BudgetModelOverride(provider=target_provider, model=model_raw)


def cap_parallelism_for_budget(
    *,
    requested_parallel: int,
    agent: str,
    session_id: str = "",
) -> tuple[int, LLMBudgetDecision]:
    """Caps parallelism under budget pressure."""
    requested = max(1, min(10, int(requested_parallel)))
    decision = evaluate_llm_budget(agent=agent, session_id=session_id, requested_max_tokens=1)

    warn_cap = _env_int("TIMUS_LLM_BUDGET_WARN_MAX_PARALLEL", 0)
    soft_cap = _env_int("TIMUS_LLM_BUDGET_SOFT_MAX_PARALLEL", 2)
    hard_cap = _env_int("TIMUS_LLM_BUDGET_HARD_MAX_PARALLEL", 1)

    if decision.blocked:
        return min(requested, hard_cap), decision
    if decision.soft_limited:
        return min(requested, soft_cap), decision
    if decision.warning and warn_cap > 0:
        return min(requested, warn_cap), decision
    return requested, decision
