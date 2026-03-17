from __future__ import annotations

import re


def strip_meta_canvas_wrappers(query: str) -> str:
    """Entfernt Canvas-Praefixe, bevor fuer Meta ein strukturierter Handoff gebaut wird."""
    cleaned = str(query or "").strip()
    if not cleaned:
        return ""

    previous = None
    while cleaned != previous:
        previous = cleaned
        cleaned = re.sub(
            r"^\s*Antworte\s+ausschlie(?:ß|ss)lich\s+auf\s+Deutsch\..*?\bNutzeranfrage:\s*",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
            count=1,
        ).strip()
        cleaned = re.sub(
            r"^\s*#\s*live location context\b.*?"
            r"(?:use this location only for nearby, routing, navigation,"
            r" or explicit place-context tasks\.?\s*)",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
            count=1,
        ).strip()

    return cleaned or str(query or "").strip()
