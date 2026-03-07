"""
Leichtgewichtige Hilfsfunktionen für Agent-Token-Management und Think-Tag-Stripping.
Isoliert von base_agent.py damit CrossHair symbolisch ausführen kann.

CrossHair-Contracts sind als Docstring-Annotationen direkt in den Funktionen.
"""
import os
import re


def get_max_tokens_for_model(model: str) -> int:
    """Gibt modell-abhängiges max_tokens zurück.

    pre: isinstance(model, str)
    post: __return__ >= 2000
    post: __return__ > 0
    """
    model_lower = model.lower()
    if any(m in model_lower for m in ["deepseek-reasoner", "deepseek-r1", "qwq", "qvq"]):
        return int(os.getenv("REASONING_MAX_TOKENS", "8000"))
    if "nemotron" in model_lower:
        return int(os.getenv("NEMOTRON_MAX_TOKENS", "4000"))
    return int(os.getenv("DEFAULT_MAX_TOKENS", "2000"))


def strip_think_tags(text: str) -> str:
    """Entfernt <think>...</think> Blöcke aus LLM-Antworten.

    Behandelt auch unclosed Tags (z.B. wenn max_tokens mitten im
    Thinking-Block abschneidet): <think>... ohne </think> → alles
    ab <think> bis zum Ende wird entfernt.

    pre: isinstance(text, str)
    post: len(__return__) <= len(text)
    post: '<think>' not in __return__
    """
    if not text or "<think>" not in text:
        return text
    # 1. Vollständige <think>...</think> Blöcke entfernen
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # 2. Unclosed <think> (kein schließendes Tag) — ab <think> bis Ende strippen
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()
