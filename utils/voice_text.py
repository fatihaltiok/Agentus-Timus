def normalize_tts_text(text: str) -> str:
    """Normalisiert TTS-Text für Inworld und begrenzt die Nutzlast."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) > 500:
        return cleaned[:500] + "..."
    return cleaned
