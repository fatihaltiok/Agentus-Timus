"""
OpenAI API Compatibility Helper
================================

Handles API differences between older models (gpt-4, gpt-4o-mini)
and newer models (gpt-4.1+, gpt-5+, gpt-6+).

Key differences:
- max_tokens → max_completion_tokens (new models)
- temperature restrictions (some models only support default=1)

Usage:
    from utils.openai_compat import prepare_openai_params

    params = {
        "model": "gpt-5-mini-2025-08-07",
        "messages": [...],
        "temperature": 0.7,
        "max_tokens": 2000
    }

    fixed_params = prepare_openai_params(params)
    response = client.chat.completions.create(**fixed_params)
"""

import re
from typing import Dict, Any, Optional


def is_new_openai_model(model_name: str) -> bool:
    """
    Detect if a model uses the new OpenAI API.

    New models include:
    - gpt-4.1-*
    - gpt-5-*
    - gpt-6-*
    - gpt-realtime-*

    Args:
        model_name: The OpenAI model identifier

    Returns:
        True if model uses new API, False otherwise
    """
    if not model_name:
        return False

    model_lower = model_name.lower()

    # Match patterns like: gpt-4.1, gpt-5, gpt-5.1, gpt-6, gpt-realtime
    new_model_patterns = [
        r'gpt-4\.1',       # gpt-4.1-2025-04-14
        r'gpt-5',          # gpt-5-2025-08-07, gpt-5-mini-2025-08-07, gpt-5.1-*
        r'gpt-6',          # Future-proof
        r'gpt-realtime',   # gpt-realtime-mini-2025-12-15
    ]

    for pattern in new_model_patterns:
        if re.search(pattern, model_lower):
            return True

    return False


def supports_custom_temperature(model_name: str) -> bool:
    """
    Check if model supports custom temperature values.

    Known restrictions (only support default temperature=1):
    - gpt-5 (base model)
    - gpt-5-mini
    - gpt-5-nano
    - gpt-realtime variants

    Args:
        model_name: The OpenAI model identifier

    Returns:
        True if custom temperature is supported, False otherwise
    """
    if not model_name:
        return True  # Assume old model supports it

    model_lower = model_name.lower()

    # Models that DON'T support custom temperature (only default)
    # Based on testing: gpt-5, gpt-5-mini, gpt-5-nano reject any temperature value
    restricted_patterns = [
        r'^gpt-5$',         # gpt-5 (exact match)
        r'^gpt-5-mini$',    # gpt-5-mini (exact match)
        r'^gpt-5-nano$',    # gpt-5-nano (exact match)
        r'gpt-realtime',    # gpt-realtime, gpt-realtime-mini
    ]

    for pattern in restricted_patterns:
        if re.search(pattern, model_lower):
            return False

    return True


def prepare_openai_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert OpenAI API parameters to be compatible with the model.

    Handles:
    1. max_tokens → max_completion_tokens for new models
    2. temperature restrictions (removes if not supported)

    Args:
        params: Original API parameters dict (will not be modified)

    Returns:
        New dict with compatible parameters

    Example:
        >>> params = {
        ...     "model": "gpt-5-mini-2025-08-07",
        ...     "messages": [...],
        ...     "temperature": 0,
        ...     "max_tokens": 2000
        ... }
        >>> fixed = prepare_openai_params(params)
        >>> fixed
        {
            "model": "gpt-5-mini-2025-08-07",
            "messages": [...],
            "max_completion_tokens": 2000
        }
        # Note: temperature=0 was removed, max_tokens → max_completion_tokens
    """
    # Create a copy to avoid modifying the original
    result = params.copy()

    model = params.get("model", "")
    is_new = is_new_openai_model(model)

    # Handle max_tokens vs max_completion_tokens
    if "max_tokens" in result:
        if is_new:
            # New models use max_completion_tokens
            result["max_completion_tokens"] = result.pop("max_tokens")
        # else: keep max_tokens for old models

    # Handle temperature restrictions
    if "temperature" in result:
        # If custom temperature is not supported, remove it
        if not supports_custom_temperature(model):
            result.pop("temperature")
            # Model will use its default (usually 1)

    return result


def get_safe_temperature(model_name: str, desired_temp: float = 0.7) -> Optional[float]:
    """
    Get a safe temperature value for the given model.

    Args:
        model_name: The OpenAI model identifier
        desired_temp: The desired temperature (default: 0.7)

    Returns:
        Safe temperature value, or None to use model default

    Example:
        >>> get_safe_temperature("gpt-5-mini", 0.7)
        None  # Model doesn't support custom temp, will use default=1

        >>> get_safe_temperature("gpt-5.1", 0.7)
        0.7  # Model supports custom temperature
    """
    if not supports_custom_temperature(model_name):
        return None  # Use model default

    return desired_temp


# Convenience function for common case
def create_chat_params(
    model: str,
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    **kwargs
) -> Dict[str, Any]:
    """
    Create OpenAI chat completion parameters with automatic compatibility.

    Args:
        model: OpenAI model name
        messages: Chat messages list
        temperature: Desired temperature (will be adjusted if needed)
        max_tokens: Maximum tokens (will be converted if needed)
        **kwargs: Additional API parameters

    Returns:
        Compatible parameters dict ready for client.chat.completions.create()

    Example:
        >>> params = create_chat_params(
        ...     model="gpt-5-2025-08-07",
        ...     messages=[{"role": "user", "content": "Hello"}],
        ...     temperature=0.0,
        ...     max_tokens=1000
        ... )
        >>> response = client.chat.completions.create(**params)
    """
    base_params = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **kwargs
    }

    return prepare_openai_params(base_params)


if __name__ == "__main__":
    # Quick test
    print("Testing OpenAI Compatibility Helper\n")

    test_cases = [
        ("gpt-4o-mini", 0, 1000),
        ("gpt-4.1", 0, 1000),
        ("gpt-5", 0.7, 2000),
        ("gpt-5-mini", 0.7, 2000),
        ("gpt-5-nano", 0, 1000),
        ("gpt-5.1", 0, 1500),
        ("gpt-5.2", 0.7, 2000),
        ("gpt-realtime-mini", 0, 500),
    ]

    for model, temp, tokens in test_cases:
        print(f"Model: {model}")
        print(f"  Is new API: {is_new_openai_model(model)}")
        print(f"  Supports custom temp: {supports_custom_temperature(model)}")

        params = {
            "model": model,
            "messages": [{"role": "user", "content": "test"}],
            "temperature": temp,
            "max_tokens": tokens
        }

        fixed = prepare_openai_params(params)
        print(f"  Original: temperature={temp}, max_tokens={tokens}")
        print(f"  Fixed: temperature={fixed.get('temperature', 'removed')}, "
              f"max_tokens={fixed.get('max_tokens', 'N/A')}, "
              f"max_completion_tokens={fixed.get('max_completion_tokens', 'N/A')}")
        print()
