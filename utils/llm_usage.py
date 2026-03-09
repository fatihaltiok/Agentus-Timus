"""Helpers for normalized LLM usage accounting across providers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict

from agent.providers import ModelProvider


def _read_field(obj: Any, *path: str) -> Any:
    current = obj
    for part in path:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
            continue
        current = getattr(current, part, None)
    return current


def _as_non_negative_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _as_non_negative_float(value: Any) -> float:
    try:
        parsed = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(parsed, 0.0)


def _model_env_slug(model: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(model or "").strip().upper())
    return re.sub(r"_+", "_", slug).strip("_") or "DEFAULT"


@dataclass(frozen=True)
class NormalizedLLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def extract_normalized_usage(provider: ModelProvider, response_or_payload: Any) -> NormalizedLLMUsage:
    """Best-effort extraction of token counters from provider responses."""
    usage = _read_field(response_or_payload, "usage")
    if usage is None and isinstance(response_or_payload, dict):
        usage = response_or_payload.get("usageMetadata")

    if provider in {
        ModelProvider.OPENAI,
        ModelProvider.ZAI,
        ModelProvider.DEEPSEEK,
        ModelProvider.INCEPTION,
        ModelProvider.NVIDIA,
        ModelProvider.OPENROUTER,
    }:
        input_tokens = _as_non_negative_int(_read_field(usage, "prompt_tokens"))
        output_tokens = _as_non_negative_int(_read_field(usage, "completion_tokens"))
        cached_tokens = _as_non_negative_int(
            _read_field(usage, "prompt_tokens_details", "cached_tokens")
        )
        return NormalizedLLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )

    if provider == ModelProvider.ANTHROPIC:
        input_tokens = _as_non_negative_int(_read_field(usage, "input_tokens"))
        output_tokens = _as_non_negative_int(_read_field(usage, "output_tokens"))
        cached_tokens = _as_non_negative_int(_read_field(usage, "cache_read_input_tokens"))
        cached_tokens += _as_non_negative_int(_read_field(usage, "cache_creation_input_tokens"))
        return NormalizedLLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )

    if provider == ModelProvider.GOOGLE:
        usage_meta = usage or _read_field(response_or_payload, "usageMetadata")
        return NormalizedLLMUsage(
            input_tokens=_as_non_negative_int(_read_field(usage_meta, "promptTokenCount")),
            output_tokens=_as_non_negative_int(_read_field(usage_meta, "candidatesTokenCount")),
            cached_tokens=_as_non_negative_int(_read_field(usage_meta, "cachedContentTokenCount")),
        )

    return NormalizedLLMUsage()


def compute_cost_usd_from_rates(
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    input_rate_usd_per_1m: float,
    output_rate_usd_per_1m: float,
    cached_rate_usd_per_1m: float,
) -> float:
    """Computes cost in USD from token counters and per-1M-token rates."""
    safe_input_tokens = max(int(input_tokens or 0), 0)
    safe_output_tokens = max(int(output_tokens or 0), 0)
    safe_cached_tokens = max(int(cached_tokens or 0), 0)
    safe_input_rate = max(float(input_rate_usd_per_1m or 0.0), 0.0)
    safe_output_rate = max(float(output_rate_usd_per_1m or 0.0), 0.0)
    safe_cached_rate = max(float(cached_rate_usd_per_1m or 0.0), 0.0)
    total = (
        (safe_input_tokens / 1_000_000.0) * safe_input_rate
        + (safe_output_tokens / 1_000_000.0) * safe_output_rate
        + (safe_cached_tokens / 1_000_000.0) * safe_cached_rate
    )
    return round(total, 8)


def _read_price_rate(provider: ModelProvider, model: str, kind: str) -> float:
    provider_key = provider.value.upper()
    model_key = _model_env_slug(model)
    candidates = [
        f"TIMUS_LLM_PRICE_{provider_key}_{model_key}_{kind}_USD_PER_1M",
        f"TIMUS_LLM_PRICE_{provider_key}_{kind}_USD_PER_1M",
        f"TIMUS_LLM_PRICE_DEFAULT_{kind}_USD_PER_1M",
    ]
    for env_name in candidates:
        raw = os.getenv(env_name)
        if raw is None:
            continue
        try:
            return max(float(raw), 0.0)
        except ValueError:
            continue
    return 0.0


def estimate_cost_usd(provider: ModelProvider, model: str, usage: NormalizedLLMUsage) -> float:
    return compute_cost_usd_from_rates(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=usage.cached_tokens,
        input_rate_usd_per_1m=_read_price_rate(provider, model, "INPUT"),
        output_rate_usd_per_1m=_read_price_rate(provider, model, "OUTPUT"),
        cached_rate_usd_per_1m=_read_price_rate(provider, model, "CACHED_INPUT"),
    )


def build_usage_payload(provider: ModelProvider, model: str, response_or_payload: Any) -> Dict[str, Any]:
    usage = extract_normalized_usage(provider, response_or_payload)
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cached_tokens": usage.cached_tokens,
        "total_tokens": usage.total_tokens,
        "cost_usd": estimate_cost_usd(provider, model, usage),
    }
