"""Pure helpers for Markdown-Store query normalization."""

import re


def build_safe_fts_query(query: str) -> str:
    """Normalisiert freie Nutzereingaben in eine sichere FTS5-MATCH-Query."""
    tokens = re.findall(r"\w+", str(query or "").strip(), flags=re.UNICODE)
    if not tokens:
        return ""
    deduped_tokens = list(dict.fromkeys(token for token in tokens if token))
    return " OR ".join(f'"{token}"*' for token in deduped_tokens)
