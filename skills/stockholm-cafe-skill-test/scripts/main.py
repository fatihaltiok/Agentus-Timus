#!/usr/bin/env python3
"""Generate a curated Stockholm cafe list from a simple query payload."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Cafe:
    name: str
    area: str
    atmosphere: str
    why_stay: str
    tags: tuple[str, ...]
    score_base: int


CAFES: tuple[Cafe, ...] = (
    Cafe(
        name="Vete-Katten",
        area="Norrmalm",
        atmosphere="historic patisserie, classic interior, calm corners",
        why_stay="great for long fika, reading, and conversation",
        tags=("vintage", "classic", "cozy", "fika", "stay"),
        score_base=9,
    ),
    Cafe(
        name="Sturekatten",
        area="Ostermalm",
        atmosphere="old townhouse rooms with antique-style decor",
        why_stay="very strong vintage feeling and relaxed seating",
        tags=("vintage", "historic", "cozy", "quiet", "stay"),
        score_base=10,
    ),
    Cafe(
        name="Cafe Saturnus",
        area="Vasastan",
        atmosphere="warm neighborhood cafe with classic Stockholm vibe",
        why_stay="comfortable for longer stays and people-watching",
        tags=("cozy", "classic", "fika", "stay"),
        score_base=8,
    ),
    Cafe(
        name="Chokladkoppen",
        area="Gamla Stan",
        atmosphere="old-town character, intimate and lively",
        why_stay="good stop for relaxed breaks in a historic setting",
        tags=("historic", "cozy", "fika", "stay"),
        score_base=8,
    ),
    Cafe(
        name="Mellqvist Kaffebar",
        area="Vasastan",
        atmosphere="small, laid-back coffee bar",
        why_stay="nice for slow coffee and short work sessions",
        tags=("cozy", "coffee", "stay"),
        score_base=7,
    ),
    Cafe(
        name="Kaffeverket",
        area="Vasastan",
        atmosphere="minimal but warm specialty coffee space",
        why_stay="strong coffee quality with comfortable vibe",
        tags=("coffee", "cozy", "stay", "work"),
        score_base=7,
    ),
    Cafe(
        name="Pascal",
        area="Vasastan",
        atmosphere="bright local cafe with quality pastries",
        why_stay="solid option for longer daytime stays",
        tags=("cozy", "coffee", "stay", "pastry"),
        score_base=7,
    ),
    Cafe(
        name="Johan & Nystrom",
        area="Sodermalm",
        atmosphere="specialty coffee roastery cafe, relaxed",
        why_stay="good for focused coffee sessions and laptop work",
        tags=("coffee", "work", "stay"),
        score_base=7,
    ),
    Cafe(
        name="Drop Coffee",
        area="Sodermalm",
        atmosphere="popular specialty coffee spot with local crowd",
        why_stay="great beans and easy-going atmosphere",
        tags=("coffee", "cozy", "stay", "work"),
        score_base=7,
    ),
    Cafe(
        name="Il Caffe",
        area="Sodermalm",
        atmosphere="small and warm Scandinavian cafe aesthetic",
        why_stay="comfortable for a calm break or catch-up",
        tags=("cozy", "stay", "fika"),
        score_base=6,
    ),
)

TAG_SYNONYMS: dict[str, tuple[str, ...]] = {
    "vintage": ("vintage", "historic", "classic", "antik", "old"),
    "cozy": ("cozy", "cosy", "gemuetlich", "gemutlich", "warm"),
    "stay": ("stay", "verweilen", "lange", "long", "sitzen", "chill"),
    "work": ("work", "laptop", "arbeiten", "study", "lernen"),
    "fika": ("fika", "pastry", "cake", "kuchen"),
    "coffee": ("coffee", "kaffee", "espresso", "specialty"),
}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _parse_payload(argv: list[str]) -> dict[str, Any]:
    if len(argv) < 2:
        return {}
    raw = (argv[1] or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"query": raw}


def _tokenize(text: str) -> set[str]:
    lowered = (text or "").lower()
    return {tok for tok in re.split(r"[^a-zA-Z0-9]+", lowered) if tok}


def _preferred_tags(query_tokens: Iterable[str]) -> set[str]:
    wanted: set[str] = set()
    tokens = set(query_tokens)
    for tag, aliases in TAG_SYNONYMS.items():
        if any(alias in tokens for alias in aliases):
            wanted.add(tag)
    return wanted


def _score(cafe: Cafe, wanted: set[str]) -> int:
    score = cafe.score_base
    cafe_tags = set(cafe.tags)
    score += 3 * len(cafe_tags.intersection(wanted))
    if "vintage" in wanted and "vintage" in cafe_tags:
        score += 2
    if "cozy" in wanted and "cozy" in cafe_tags:
        score += 2
    return score


def _build_lines(cafes: list[Cafe], query: str) -> list[str]:
    lines: list[str] = ["Hier ist deine Liste (Stockholm):"]
    for idx, cafe in enumerate(cafes, start=1):
        lines.append(
            f"{idx}. {cafe.name} ({cafe.area}) - Atmosphaere: {cafe.atmosphere}. "
            f"Warum gut zum Verweilen: {cafe.why_stay}."
        )
    if query:
        lines.append("")
        lines.append(f"Suchfokus: {query}")
    lines.append("Hinweis: Oeffnungszeiten vorab pruefen.")
    return lines


def _save_markdown(lines: list[str]) -> str:
    project_root = Path(__file__).resolve().parents[3]
    results_dir = project_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"{ts}_stockholm_cafes.md"
    out_path.write_text("# Stockholm Cafe List\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)


def main() -> int:
    payload = _parse_payload(sys.argv)
    query = str(payload.get("query", "") or "").strip()
    limit = _safe_int(payload.get("limit", 8), 8)
    limit = max(1, min(limit, 15))

    tokens = _tokenize(query)
    wanted = _preferred_tags(tokens)
    ranked = sorted(CAFES, key=lambda cafe: _score(cafe, wanted), reverse=True)[:limit]

    lines = _build_lines(ranked, query=query)
    saved_path = _save_markdown(lines)

    print("\n".join(lines))
    print(f"\nGespeichert unter: {saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
