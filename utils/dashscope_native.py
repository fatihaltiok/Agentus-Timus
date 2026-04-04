"""Helpers for Alibaba DashScope native generation endpoints."""

from __future__ import annotations

import os
from typing import Any, Dict, List


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _optional_env_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return None


def _optional_env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def is_dashscope_native_multimodal_model(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    return any(
        token in normalized
        for token in (
            "qwen3.6",
            "qwen3-vl",
            "qwen2.5-vl",
            "qwen-vl",
            "qvq",
            "omni",
        )
    )


def dashscope_native_generation_url(base_url: str, model: str) -> str:
    suffix = "multimodal-generation/generation" if is_dashscope_native_multimodal_model(model) else "text-generation/generation"
    return f"{str(base_url or '').rstrip('/')}/services/aigc/{suffix}"


def _append_multimodal_part(parts: List[Dict[str, Any]], item: Any) -> None:
    if item is None:
        return
    if isinstance(item, str):
        if item.strip():
            parts.append({"text": item})
        return
    if not isinstance(item, dict):
        rendered = str(item).strip()
        if rendered:
            parts.append({"text": rendered})
        return

    item_type = str(item.get("type") or "").strip().lower()
    if item_type in {"text", "input_text"}:
        text = str(item.get("text") or "").strip()
        if text:
            parts.append({"text": text})
        return

    if item_type in {"image_url", "input_image"}:
        image_value = item.get("image_url")
        if isinstance(image_value, dict):
            image_value = image_value.get("url")
        if image_value:
            parts.append({"image": image_value})
        return

    if item_type == "video":
        video_value = item.get("video")
        if video_value is not None:
            payload: Dict[str, Any] = {"video": video_value}
            for extra in ("fps", "min_pixels", "max_pixels", "total_pixels", "max_frames"):
                if item.get(extra) is not None:
                    payload[extra] = item[extra]
            parts.append(payload)
        return

    if item_type == "video_url":
        video_value = item.get("video_url")
        if isinstance(video_value, dict):
            video_value = video_value.get("url")
        if video_value is not None:
            payload = {"video": video_value}
            for extra in ("fps", "min_pixels", "max_pixels", "total_pixels", "max_frames"):
                if item.get(extra) is not None:
                    payload[extra] = item[extra]
            parts.append(payload)
        return

    if item.get("text") is not None:
        text = str(item.get("text") or "").strip()
        if text:
            parts.append({"text": text})
        return

    if item.get("image") is not None:
        parts.append({"image": item["image"]})
        return

    if item.get("video") is not None:
        payload = {"video": item["video"]}
        for extra in ("fps", "min_pixels", "max_pixels", "total_pixels", "max_frames"):
            if item.get(extra) is not None:
                payload[extra] = item[extra]
        parts.append(payload)
        return

    if item.get("content") is not None:
        text = str(item.get("content") or "").strip()
        if text:
            parts.append({"text": text})
        return

    rendered = str(item).strip()
    if rendered:
        parts.append({"text": rendered})


def _flatten_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")

    parts: List[str] = []
    for item in content:
        if item is None:
            continue
        if isinstance(item, str):
            if item.strip():
                parts.append(item)
            continue
        if not isinstance(item, dict):
            rendered = str(item).strip()
            if rendered:
                parts.append(rendered)
            continue

        item_type = str(item.get("type") or "").strip().lower()
        if item_type in {"text", "input_text"}:
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
            continue

        if item_type in {"image_url", "input_image"}:
            image_value = item.get("image_url")
            if isinstance(image_value, dict):
                image_value = image_value.get("url")
            if image_value:
                parts.append(f"[image:{image_value}]")
            continue

        if item_type in {"video", "video_url"}:
            video_value = item.get("video")
            if video_value is None:
                video_value = item.get("video_url")
            if isinstance(video_value, dict):
                video_value = video_value.get("url")
            if video_value:
                parts.append(f"[video:{video_value}]")
            continue

        text = item.get("text")
        if text is not None and str(text).strip():
            parts.append(str(text))
            continue

        content_value = item.get("content")
        if content_value is not None and str(content_value).strip():
            parts.append(str(content_value))

    return "\n".join(parts).strip()


def dashscope_native_messages(messages: List[Dict[str, Any]], model: str) -> List[Dict[str, Any]]:
    multimodal = is_dashscope_native_multimodal_model(model)
    normalized_messages: List[Dict[str, Any]] = []

    for message in messages:
        role = str((message or {}).get("role") or "user").strip() or "user"
        content = (message or {}).get("content")
        if multimodal:
            parts: List[Dict[str, Any]] = []
            if isinstance(content, list):
                for item in content:
                    _append_multimodal_part(parts, item)
            else:
                _append_multimodal_part(parts, content)
            normalized_messages.append({"role": role, "content": parts or [{"text": ""}]})
            continue

        normalized_messages.append({"role": role, "content": _flatten_text_content(content)})

    return normalized_messages


def build_dashscope_native_payload(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float | None,
    max_tokens: int | None,
    extra_parameters: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    parameters: Dict[str, Any] = {"result_format": "message"}
    if temperature is not None:
        parameters["temperature"] = temperature
    if max_tokens is not None:
        parameters["max_tokens"] = int(max_tokens)

    enable_thinking = _optional_env_bool("DASHSCOPE_NATIVE_ENABLE_THINKING")
    if enable_thinking is not None:
        parameters["enable_thinking"] = enable_thinking

    preserve_thinking = _optional_env_bool("DASHSCOPE_NATIVE_PRESERVE_THINKING")
    if preserve_thinking is not None:
        parameters["preserve_thinking"] = preserve_thinking

    thinking_budget = _optional_env_int("DASHSCOPE_NATIVE_THINKING_BUDGET")
    if thinking_budget is not None:
        parameters["thinking_budget"] = thinking_budget

    if extra_parameters:
        parameters.update(extra_parameters)

    return {
        "model": model,
        "input": {"messages": dashscope_native_messages(messages, model)},
        "parameters": parameters,
    }


def _dashscope_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content or "").strip()

    parts: List[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
        elif isinstance(item, str) and item:
            parts.append(item)
    return "".join(parts).strip()


def extract_dashscope_native_text(payload: Dict[str, Any]) -> str:
    output = payload.get("output") if isinstance(payload, dict) else None
    if not isinstance(output, dict):
        return ""

    if isinstance(output.get("text"), str) and output.get("text", "").strip():
        return output["text"].strip()

    choices = output.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""

    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        return ""
    return _dashscope_message_text(message.get("content"))


def extract_dashscope_native_reasoning(payload: Dict[str, Any]) -> str:
    output = payload.get("output") if isinstance(payload, dict) else None
    if not isinstance(output, dict):
        return ""
    choices = output.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        return ""
    return str(message.get("reasoning_content") or "").strip()
