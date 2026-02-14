"""Einheitlicher Action/JSON-Parser fuer LLM-Antworten.

3-Priority Parser (bester Code aus BaseAgent._parse_action):
  1. Direct JSON (ganzer Text)
  2. Zeilenweise Suche
  3. Regex Fallback
"""

import json
import re
from typing import Optional, Tuple


def parse_action(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """Extrahiert Action-Dict aus LLM-Antwort.

    Returns:
        (action_dict, None) bei Erfolg oder (None, error_message) bei Fehler.
    """
    text = text.strip()

    # PRIORITAET 1: Versuche direktes JSON-Parsing (mehrzeilig/verschachtelt, Nemotron)
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            if "action" in data:
                return data["action"], None
            if "method" in data:
                return data, None
        except json.JSONDecodeError:
            pass  # Fallback zu anderen Methoden

    # PRIORITAET 2: Zeilenweise suchen (einzeiliges JSON)
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if "action" in data:
                    return data["action"], None
                if "method" in data:
                    return data, None
            except json.JSONDecodeError:
                continue

    # PRIORITAET 3: Regex Fallback
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r'Action:\s*(\{[\s\S]*?\})\s*(?:\n|$)',
        r'(\{[^{}]*"method"[^{}]*\})',
        r"(\{[^{}]+\})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                json_str = re.sub(r",\s*([\}\]])", r"\1", match.group(1).strip())
                data = json.loads(json_str)
                if "action" in data:
                    return data["action"], None
                if "method" in data:
                    return data, None
            except (json.JSONDecodeError, ValueError):
                continue

    return None, "Kein JSON gefunden"
