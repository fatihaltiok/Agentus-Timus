"""Lightweight LLM workers for bounded orchestration tasks.

Phase 1 keeps workers deliberately small:
- no BaseAgent inheritance
- no registry lifecycle
- no tool-calling
- budget-aware and env-driven
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.providers import (
    ModelProvider,
    get_provider_client,
    resolve_model_provider_env,
    validate_configured_model_or_raise,
)
from agent.shared.json_utils import extract_json_robust
from orchestration.llm_budget_guard import (
    cap_parallelism_for_budget,
    evaluate_llm_budget,
    resolve_soft_budget_model_override,
)
from orchestration.self_improvement_engine import LLMUsageRecord, get_improvement_engine
from utils.llm_usage import build_usage_payload
from utils.openai_compat import prepare_openai_params

logger = logging.getLogger("TimusEphemeralWorkers")

_OPENAI_COMPAT_PROVIDERS = {
    ModelProvider.OPENAI,
    ModelProvider.ZAI,
    ModelProvider.DEEPSEEK,
    ModelProvider.INCEPTION,
    ModelProvider.NVIDIA,
    ModelProvider.OPENROUTER,
    ModelProvider.GOOGLE,
}


def _env_flag(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "true" if default else "false") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: Optional[int] = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else int(default)
    except (TypeError, ValueError):
        value = int(default)
    value = max(int(minimum), value)
    if maximum is not None:
        value = min(value, int(maximum))
    return value


def _resolve_worker_model_provider(
    *,
    profile_prefix: str,
    default_model: str,
    default_provider: ModelProvider,
) -> tuple[str, ModelProvider]:
    global_model = str(os.getenv("EPHEMERAL_WORKER_MODEL", default_model) or default_model).strip() or default_model
    global_provider_raw = str(
        os.getenv("EPHEMERAL_WORKER_PROVIDER", default_provider.value) or default_provider.value
    ).strip().lower()
    try:
        global_provider = ModelProvider(global_provider_raw)
    except ValueError:
        global_provider = default_provider
    return resolve_model_provider_env(
        model_env=f"{profile_prefix}_MODEL",
        provider_env=f"{profile_prefix}_PROVIDER",
        fallback_model=global_model,
        fallback_provider=global_provider,
    )


def _resolve_worker_limits(profile_prefix: str) -> tuple[int, int]:
    max_tokens = _env_int(
        f"{profile_prefix}_MAX_TOKENS",
        _env_int("EPHEMERAL_WORKER_MAX_TOKENS", 800, minimum=64, maximum=8000),
        minimum=64,
        maximum=8000,
    )
    timeout_sec = _env_int(
        f"{profile_prefix}_TIMEOUT_SEC",
        _env_int("EPHEMERAL_WORKER_TIMEOUT_SEC", 30, minimum=5, maximum=300),
        minimum=5,
        maximum=300,
    )
    return max_tokens, timeout_sec


def _extract_response_text(response_payload: Any) -> str:
    choices = getattr(response_payload, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                parts.append(getattr(item, "text"))
        return "".join(parts).strip()
    return str(content or "").strip()


def _record_worker_usage(
    *,
    agent: str,
    session_id: str,
    provider: ModelProvider,
    model: str,
    latency_ms: int,
    success: bool,
    response_payload: Any = None,
) -> None:
    try:
        usage = build_usage_payload(provider, model, response_payload)
        get_improvement_engine().record_llm_usage(
            LLMUsageRecord(
                trace_id=f"worker-{uuid.uuid4().hex[:12]}",
                session_id=session_id or "",
                agent=agent,
                provider=provider.value,
                model=model,
                input_tokens=int(usage["input_tokens"]),
                output_tokens=int(usage["output_tokens"]),
                cached_tokens=int(usage["cached_tokens"]),
                cost_usd=float(usage["cost_usd"]),
                latency_ms=max(int(latency_ms or 0), 0),
                success=bool(success),
            )
        )
    except Exception as exc:
        logger.debug("Ephemeral worker usage logging failed: %s", exc)


@dataclass(frozen=True)
class WorkerProfile:
    profile_prefix: str
    provider: ModelProvider
    model: str
    max_tokens: int
    timeout_sec: int


@dataclass(frozen=True)
class WorkerTask:
    worker_type: str
    system_prompt: str
    input_payload: Dict[str, Any]
    response_schema: Dict[str, Any] = field(default_factory=dict)
    max_tokens: Optional[int] = None
    timeout_sec: Optional[int] = None


@dataclass(frozen=True)
class WorkerResult:
    worker_type: str
    status: str
    payload: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0
    provider: str = ""
    model: str = ""
    max_tokens: int = 0
    fallback_used: bool = False


def ephemeral_workers_enabled() -> bool:
    return _env_flag("EPHEMERAL_WORKERS_ENABLED", False)


def resolve_worker_profile(
    *,
    profile_prefix: str,
    default_model: str = "gpt-5.4-mini",
    default_provider: ModelProvider = ModelProvider.OPENAI,
) -> WorkerProfile:
    model, provider = _resolve_worker_model_provider(
        profile_prefix=profile_prefix,
        default_model=default_model,
        default_provider=default_provider,
    )
    max_tokens, timeout_sec = _resolve_worker_limits(profile_prefix)
    return WorkerProfile(
        profile_prefix=profile_prefix,
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        timeout_sec=timeout_sec,
    )


async def run_worker(
    task: WorkerTask,
    *,
    profile_prefix: str,
    agent: str,
    session_id: str = "",
) -> WorkerResult:
    if not ephemeral_workers_enabled():
        return WorkerResult(worker_type=task.worker_type, status="disabled", fallback_used=True)

    profile = resolve_worker_profile(profile_prefix=profile_prefix)
    max_tokens = max(1, int(task.max_tokens or profile.max_tokens))
    timeout_sec = max(1, int(task.timeout_sec or profile.timeout_sec))

    budget = evaluate_llm_budget(
        agent=agent,
        session_id=session_id,
        requested_max_tokens=max_tokens,
    )
    if budget.blocked:
        return WorkerResult(
            worker_type=task.worker_type,
            status="blocked",
            error=budget.message,
            provider=profile.provider.value,
            model=profile.model,
            max_tokens=max_tokens,
            fallback_used=True,
        )

    model_override = resolve_soft_budget_model_override(
        agent=agent,
        provider=profile.provider,
        model=profile.model,
        decision=budget,
    )
    effective_provider = model_override.provider if model_override else profile.provider
    effective_model = model_override.model if model_override else profile.model
    effective_tokens = min(max_tokens, max(int(budget.max_tokens_cap or max_tokens), 1))

    if effective_provider not in _OPENAI_COMPAT_PROVIDERS:
        return WorkerResult(
            worker_type=task.worker_type,
            status="unsupported_provider",
            error=f"Worker provider '{effective_provider.value}' is not openai-compatible.",
            provider=effective_provider.value,
            model=effective_model,
            max_tokens=effective_tokens,
            fallback_used=True,
        )

    validate_configured_model_or_raise(
        effective_provider,
        effective_model,
        agent_type=f"{agent}_{task.worker_type}_worker",
    )
    client = get_provider_client().get_client(effective_provider)

    schema_block = json.dumps(task.response_schema or {}, ensure_ascii=False, indent=2)
    input_block = json.dumps(task.input_payload or {}, ensure_ascii=False, indent=2)
    messages = [
        {
            "role": "system",
            "content": task.system_prompt.strip(),
        },
        {
            "role": "user",
            "content": (
                "Arbeite nur mit dem folgenden JSON-Eingang.\n"
                "Antworte ausschliesslich mit gueltigem JSON ohne Markdown.\n"
                "Erwarte dieses Antwortschema:\n"
                f"{schema_block}\n\n"
                "Eingang:\n"
                f"{input_block}"
            ),
        },
    ]
    kwargs = prepare_openai_params(
        {
            "model": effective_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": effective_tokens,
        }
    )

    started = time.perf_counter()
    response_payload: Any = None
    try:
        response_payload = await asyncio.wait_for(
            asyncio.to_thread(client.chat.completions.create, **kwargs),
            timeout=timeout_sec,
        )
        text = _extract_response_text(response_payload)
        if not text:
            _record_worker_usage(
                agent=agent,
                session_id=session_id,
                provider=effective_provider,
                model=effective_model,
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=False,
                response_payload=response_payload,
            )
            return WorkerResult(
                worker_type=task.worker_type,
                status="empty",
                error="Worker returned empty content.",
                duration_ms=round((time.perf_counter() - started) * 1000),
                provider=effective_provider.value,
                model=effective_model,
                max_tokens=effective_tokens,
                fallback_used=True,
            )

        parsed = extract_json_robust(text)
        if not isinstance(parsed, dict):
            _record_worker_usage(
                agent=agent,
                session_id=session_id,
                provider=effective_provider,
                model=effective_model,
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=False,
                response_payload=response_payload,
            )
            return WorkerResult(
                worker_type=task.worker_type,
                status="invalid_json",
                error="Worker response was not a JSON object.",
                duration_ms=round((time.perf_counter() - started) * 1000),
                provider=effective_provider.value,
                model=effective_model,
                max_tokens=effective_tokens,
                fallback_used=True,
            )

        _record_worker_usage(
            agent=agent,
            session_id=session_id,
            provider=effective_provider,
            model=effective_model,
            latency_ms=round((time.perf_counter() - started) * 1000),
            success=True,
            response_payload=response_payload,
        )
        return WorkerResult(
            worker_type=task.worker_type,
            status="ok",
            payload=parsed,
            duration_ms=round((time.perf_counter() - started) * 1000),
            provider=effective_provider.value,
            model=effective_model,
            max_tokens=effective_tokens,
            fallback_used=False,
        )
    except asyncio.TimeoutError:
        _record_worker_usage(
            agent=agent,
            session_id=session_id,
            provider=effective_provider,
            model=effective_model,
            latency_ms=round((time.perf_counter() - started) * 1000),
            success=False,
            response_payload=response_payload,
        )
        return WorkerResult(
            worker_type=task.worker_type,
            status="timeout",
            error=f"Worker timed out after {timeout_sec}s.",
            duration_ms=round((time.perf_counter() - started) * 1000),
            provider=effective_provider.value,
            model=effective_model,
            max_tokens=effective_tokens,
            fallback_used=True,
        )
    except Exception as exc:
        _record_worker_usage(
            agent=agent,
            session_id=session_id,
            provider=effective_provider,
            model=effective_model,
            latency_ms=round((time.perf_counter() - started) * 1000),
            success=False,
            response_payload=response_payload,
        )
        return WorkerResult(
            worker_type=task.worker_type,
            status="error",
            error=str(exc),
            duration_ms=round((time.perf_counter() - started) * 1000),
            provider=effective_provider.value,
            model=effective_model,
            max_tokens=effective_tokens,
            fallback_used=True,
        )


async def run_worker_batch(
    tasks: List[WorkerTask],
    *,
    profile_prefix: str,
    agent: str,
    session_id: str = "",
    requested_parallel: Optional[int] = None,
) -> List[WorkerResult]:
    if not tasks:
        return []

    global_cap = _env_int("EPHEMERAL_WORKER_MAX_PARALLEL", 2, minimum=1, maximum=8)
    requested = max(1, min(int(requested_parallel or len(tasks)), global_cap))
    effective_parallel, _ = cap_parallelism_for_budget(
        requested_parallel=requested,
        agent=agent,
        session_id=session_id,
    )
    semaphore = asyncio.Semaphore(max(1, effective_parallel))

    async def _runner(worker_task: WorkerTask) -> WorkerResult:
        async with semaphore:
            return await run_worker(
                worker_task,
                profile_prefix=profile_prefix,
                agent=agent,
                session_id=session_id,
            )

    return list(await asyncio.gather(*[_runner(task) for task in tasks]))
