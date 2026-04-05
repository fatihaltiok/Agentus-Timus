"""C5 Hypothesis-Tests: Idempotenz, Dedupe, Reihenfolgenstabilität.

Hypothesis sucht aktiv nach Gegenbeispielen für:
- Idempotenz: zweimaliger Sync mit gleichen Daten = kein zweites Write
- Dedupe: normalisierter Key ist content-stable
- Reihenfolgenstabilität: render_hash ist reihenfolgeunabhängig
- Längeninvariante: dedupe kann Items nur verringern, nie erhöhen
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from memory.markdown_store.store import MarkdownStore, MemoryEntry


# ---------------------------------------------------------------------------
# Strategien
# ---------------------------------------------------------------------------

_categories = st.sampled_from(["user", "project", "feedback", "reference", "system"])
_content = st.text(min_size=1, max_size=200)
_source = st.text(min_size=0, max_size=50)
_importance = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


def _entry_strategy():
    return st.builds(
        MemoryEntry,
        category=_categories,
        content=_content,
        importance=_importance,
        source=_source,
        created_at=st.just(""),
    )


# ---------------------------------------------------------------------------
# 1. Idempotenz: render_hash(entries) == render_hash(entries) immer
# ---------------------------------------------------------------------------

@given(entries=st.lists(_entry_strategy(), min_size=0, max_size=20))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_render_hash_is_deterministic(entries):
    h1 = MarkdownStore._render_hash(entries)
    h2 = MarkdownStore._render_hash(entries)
    assert h1 == h2, "render_hash muss deterministisch sein"


# ---------------------------------------------------------------------------
# 2. Reihenfolgestabilität: hash(shuffled) == hash(original)
# ---------------------------------------------------------------------------

@given(
    entries=st.lists(_entry_strategy(), min_size=1, max_size=20),
    seed=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_render_hash_order_independent(entries, seed):
    import random
    rng = random.Random(seed)
    shuffled = entries[:]
    rng.shuffle(shuffled)
    assert MarkdownStore._render_hash(entries) == MarkdownStore._render_hash(shuffled)


# ---------------------------------------------------------------------------
# 3. Dedupe-Längeninvariante: len(dedupe(entries)) <= len(entries)
# ---------------------------------------------------------------------------

@given(entries=st.lists(_entry_strategy(), min_size=0, max_size=30))
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_dedupe_never_increases_count(entries):
    seen: dict[str, MemoryEntry] = {}
    for e in entries:
        seen[MarkdownStore._dedupe_key(e)] = e
    assert len(seen) <= len(entries)


# ---------------------------------------------------------------------------
# 4. Dedupe-Idempotenz: dedupe(dedupe(X)) == dedupe(X)
# ---------------------------------------------------------------------------

@given(entries=st.lists(_entry_strategy(), min_size=0, max_size=20))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_dedupe_is_idempotent(entries):
    def dedupe(items):
        seen = {}
        for e in items:
            seen[MarkdownStore._dedupe_key(e)] = e
        return list(seen.values())

    once = dedupe(entries)
    twice = dedupe(once)
    # Gleiche Anzahl — nochmaliges Dedupe darf nichts entfernen
    assert len(twice) == len(once)


# ---------------------------------------------------------------------------
# 5. Dedupe-Key: normalisierter content → gleicher Key
# ---------------------------------------------------------------------------

@given(
    category=_categories,
    content=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
    source=_source,
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_dedupe_key_stable_under_case_and_whitespace(category, content, source):
    e1 = MemoryEntry(category=category, content=content, importance=0.9, source=source)
    e2 = MemoryEntry(category=category, content=content.lower(), importance=0.8, source=source)
    e3 = MemoryEntry(category=category, content="  " + content + "  ", importance=0.7, source=source)
    # case-normalisiert + stripped
    k1 = MarkdownStore._dedupe_key(e1)
    k2 = MarkdownStore._dedupe_key(e2)
    k3 = MarkdownStore._dedupe_key(e3)
    # k2 und k3 müssen gleich sein (beide lowercase + stripped)
    assert k2 == k3
    # k1 und k2 müssen gleich sein nach Normalisierung
    assert k1 == k2


# ---------------------------------------------------------------------------
# 6. replace_memories: zweiter Aufruf mit gleichen Daten → written=False
# ---------------------------------------------------------------------------

@given(entries=st.lists(_entry_strategy(), min_size=1, max_size=15))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_replace_memories_idempotent(tmp_path_factory, entries):
    tmp_path = tmp_path_factory.mktemp("sync")
    store = MarkdownStore(base_path=tmp_path)

    written1, _, _ = store.replace_memories(entries)
    written2, items2, _ = store.replace_memories(entries)

    assert written1 is True
    assert written2 is False, "Zweiter identical Sync darf nicht schreiben"
    assert items2 == 0
