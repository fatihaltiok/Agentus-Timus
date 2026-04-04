"""Einheitlicher Action/JSON-Parser fuer LLM-Antworten.

3-Priority Parser (bester Code aus BaseAgent._parse_action):
  1. Direct JSON (ganzer Text)
  2. Zeilenweise Suche
  3. Regex Fallback
"""

import json
import re
from typing import Any, Optional, Tuple


def _normalize_parsed_action(data: Any) -> Tuple[Optional[dict], Optional[str]]:
    if isinstance(data, dict):
        if "action" in data:
            action = data["action"]
            if isinstance(action, dict):
                return action, None
            return None, "Action-JSON muss ein Objekt sein, keine Liste."
        if "method" in data:
            return data, None
    return None, None


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
            action, error = _normalize_parsed_action(data)
            if action is not None or error is not None:
                return action, error
        except json.JSONDecodeError:
            pass  # Fallback zu anderen Methoden

    # PRIORITAET 2: Zeilenweise suchen (einzeiliges JSON)
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                action, error = _normalize_parsed_action(data)
                if action is not None or error is not None:
                    return action, error
            except json.JSONDecodeError:
                continue

    # PRIORITAET 3: Regex Fallback
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",          # Markdown-Code-Block
        r"```\s*([\s\S]*?)\s*```",               # Ungetypter Code-Block
        r'Action:\s*(\{[\s\S]*?\})\s*(?:\n|$)', # Action: {...} einzeilig
        r'Action:\s*(\{[\s\S]+\})',              # Action: {...} mehrzeilig
        r'(\{[^{}]*"method"[^{}]*\})',           # {"method": ...} flach
        r"(\{[^{}]+\})",                         # Beliebiges flaches JSON
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                json_str = re.sub(r",\s*([\}\]])", r"\1", match.group(1).strip())
                data = json.loads(json_str)
                action, error = _normalize_parsed_action(data)
                if action is not None or error is not None:
                    return action, error
            except (json.JSONDecodeError, ValueError):
                continue

    # PRIORITAET 4: Verschachteltes JSON — größten {}-Block extrahieren
    brace_match = re.search(r'(\{(?:[^{}]|\{[^{}]*\})*\})', text, re.DOTALL)
    if brace_match:
        try:
            json_str = re.sub(r",\s*([\}\]])", r"\1", brace_match.group(1).strip())
            data = json.loads(json_str)
            action, error = _normalize_parsed_action(data)
            if action is not None or error is not None:
                return action, error
        except (json.JSONDecodeError, ValueError):
            pass

    return None, "Kein JSON gefunden"
