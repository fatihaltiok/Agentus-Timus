"""Vision Message Formatting Utilities.

Einheitliches Erstellen von Vision-Messages fuer OpenAI und Anthropic.
"""

from typing import Dict, List, Tuple


def build_openai_vision_message(text: str, image_b64: str, detail: str = "low") -> dict:
    """Baut eine multimodale User-Message im OpenAI-Format.

    Args:
        text: Textinhalt der Nachricht.
        image_b64: Base64-kodiertes Bild.
        detail: "low" (schnell/guenstig) oder "high" (detailliert).

    Returns:
        OpenAI-kompatibles Message-Dict.
    """
    if not image_b64:
        return {"role": "user", "content": text}

    media_type = "image/jpeg" if image_b64[:4] != "iVBO" else "image/png"
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{image_b64}",
                    "detail": detail,
                },
            },
        ],
    }


def convert_openai_to_anthropic(messages: List[dict]) -> Tuple[str, List[dict]]:
    """Konvertiert OpenAI Vision Messages in Anthropic Format.

    Extrahiert system-Content separat und wandelt image_url -> image/source um.

    Args:
        messages: Liste von OpenAI-formatierten Messages.

    Returns:
        (system_content, anthropic_messages) Tuple.
    """
    system_content = ""
    chat_messages = []

    for msg in messages:
        if msg["role"] == "system":
            system_content = msg["content"]
            continue

        content = msg.get("content")
        if msg["role"] == "user" and isinstance(content, list):
            converted = []
            for item in content:
                if item.get("type") == "text":
                    converted.append({"type": "text", "text": item["text"]})
                elif item.get("type") == "image_url":
                    url = item["image_url"]["url"]
                    if url.startswith("data:image"):
                        parts = url.split(",", 1)
                        media_type = parts[0].split(";")[0].replace("data:", "")
                        converted.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": parts[1],
                                },
                            }
                        )
            chat_messages.append({"role": "user", "content": converted})
        else:
            chat_messages.append(msg)

    return system_content, chat_messages
