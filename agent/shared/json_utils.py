"""Robuste JSON-Extraction aus LLM-Responses."""

import re
import json
from typing import Optional


def extract_json_robust(text: str) -> Optional[dict]:
    """Extrahiert JSON aus LLM-Response via Brace-Counting.

    Funktioniert auch mit Nemotron-Responses die <think>-Blocks enthalten
    und verschachteltes JSON zurueckgeben.
    """
    # 1. <think>...</think> Blocks entfernen (Nemotron)
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # 2. Markdown Code-Blocks entfernen
    cleaned = re.sub(r'```json\s*', '', cleaned)
    cleaned = re.sub(r'```\s*', '', cleaned)

    # 3. Aeusserste { ... } finden via Brace-Counting
    start = cleaned.find('{')
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(cleaned)):
        if cleaned[i] == '{':
            depth += 1
        elif cleaned[i] == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None
