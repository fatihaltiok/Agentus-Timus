"""
tests/test_m16_hooks.py — M16: Phase 2 Tests

Testet WeightedHook Dataclass und Soul Engine Weighted-Hooks-API.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from memory.soul_engine import WeightedHook, SoulEngine, HOOK_MIN_WEIGHT, FEEDBACK_DELTA


# ──────────────────────────────────────────────────────────────────
# WeightedHook Dataclass
# ──────────────────────────────────────────────────────────────────

def test_weighted_hook_default_weight():
    h = WeightedHook(text="Sei direkt")
    assert h.weight == 1.0
    assert h.feedback_count == 0


def test_positive_feedback_raises_weight():
    h = WeightedHook(text="Teste gründlich", weight=1.0)
    h.apply_feedback("positive")
    assert h.weight == pytest.approx(1.0 + FEEDBACK_DELTA, abs=1e-6)
    assert h.feedback_count == 1


def test_negative_feedback_lowers_weight():
    h = WeightedHook(text="Sei schnell", weight=1.0)
    h.apply_feedback("negative")
    assert h.weight == pytest.approx(1.0 - FEEDBACK_DELTA, abs=1e-6)
    assert h.feedback_count == 1


def test_neutral_feedback_no_change():
    h = WeightedHook(text="Neutral hook", weight=0.8)
    h.apply_feedback("neutral")
    assert h.weight == 0.8
    assert h.feedback_count == 0


def test_weight_lower_bound():
    h = WeightedHook(text="Hook", weight=HOOK_MIN_WEIGHT + 0.001)
    # Viele negative Signale
    for _ in range(100):
        h.apply_feedback("negative")
    assert h.weight >= HOOK_MIN_WEIGHT


def test_weight_upper_bound():
    h = WeightedHook(text="Hook", weight=1.9)
    for _ in range(100):
        h.apply_feedback("positive")
    assert h.weight <= 2.0


def test_three_positive_increases_weight():
    h = WeightedHook(text="Hook", weight=1.0)
    h.apply_feedback("positive")
    h.apply_feedback("positive")
    h.apply_feedback("positive")
    expected = min(2.0, 1.0 + 3 * FEEDBACK_DELTA)
    assert h.weight == pytest.approx(expected, abs=1e-6)
    assert h.feedback_count == 3


def test_three_negative_decreases_weight():
    h = WeightedHook(text="Hook", weight=1.0)
    h.apply_feedback("negative")
    h.apply_feedback("negative")
    h.apply_feedback("negative")
    expected = max(HOOK_MIN_WEIGHT, 1.0 - 3 * FEEDBACK_DELTA)
    assert h.weight == pytest.approx(expected, abs=1e-6)


def test_decay_above_one():
    h = WeightedHook(text="Hook", weight=1.5)
    h.decay(rate=0.97)
    assert h.weight == pytest.approx(max(1.0, 1.5 * 0.97), abs=1e-6)


def test_decay_below_one():
    h = WeightedHook(text="Hook", weight=0.7)
    h.decay(rate=0.97)
    # weight < 1.0 → wird durch decay / rate erhöht (Richtung 1.0)
    assert h.weight >= 0.7  # darf nicht sinken
    assert h.weight <= 1.0  # bleibt unter 1.0


def test_decay_at_one_no_change():
    h = WeightedHook(text="Hook", weight=1.0)
    h.decay(rate=0.97)
    assert h.weight == pytest.approx(1.0, abs=1e-6)


def test_is_active_above_threshold():
    h = WeightedHook(text="Hook", weight=0.5)
    assert h.is_active(threshold=0.3) is True


def test_is_inactive_below_threshold():
    h = WeightedHook(text="Hook", weight=0.2)
    assert h.is_active(threshold=0.3) is False


# ──────────────────────────────────────────────────────────────────
# SoulEngine Weighted-Hooks-API (mit temporärer SOUL.md)
# ──────────────────────────────────────────────────────────────────

def _make_soul_engine(tmp_path: Path) -> SoulEngine:
    """Erstellt SoulEngine mit temporärer SOUL.md."""
    soul_md = tmp_path / "SOUL.md"
    frontmatter = yaml.dump(
        {
            "axes": {"confidence": 50.0, "formality": 65.0, "humor": 15.0, "verbosity": 50.0, "risk_appetite": 40.0},
            "weighted_hooks": [
                {"text": "Sei direkt", "weight": 1.0, "feedback_count": 0},
                {"text": "Prüfe zuerst", "weight": 0.8, "feedback_count": 2},
                {"text": "Nicht raten", "weight": 0.25, "feedback_count": 1},
            ],
        },
        allow_unicode=True,
        default_flow_style=False,
    )
    soul_md.write_text(f"---\n{frontmatter.rstrip()}\n---\n\n# Timus Persona\n", encoding="utf-8")

    import memory.soul_engine as se
    original_path = se.SOUL_MD_PATH
    se.SOUL_MD_PATH = soul_md

    engine = SoulEngine()
    # Patch: Engine nutzt tmp soul_md
    engine._SOUL_MD_PATH = soul_md

    # Monkey-patch die Klassen-Methoden für tmp path
    import types
    original_read = engine._read_frontmatter
    original_write = engine._write_frontmatter

    def patched_read(self=engine):
        try:
            content = soul_md.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return yaml.safe_load(parts[1]) or {}
        except Exception:
            pass
        return {}

    def patched_write(data, self=engine):
        try:
            existing = soul_md.read_text(encoding="utf-8") if soul_md.exists() else ""
            parts = existing.split("---", 2)
            body = parts[2] if len(parts) >= 3 else "\n\n# Timus Persona\n"
            new_fm = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
            soul_md.write_text(f"---\n{new_fm.rstrip()}\n---{body}", encoding="utf-8")
        except Exception as e:
            pass

    engine._read_frontmatter = patched_read
    engine._write_frontmatter = patched_write

    return engine


@pytest.fixture
def soul_engine(tmp_path):
    return _make_soul_engine(tmp_path)


def test_get_weighted_hooks_loads(soul_engine):
    hooks = soul_engine.get_weighted_hooks()
    assert len(hooks) == 3
    texts = [h.text for h in hooks]
    assert "Sei direkt" in texts
    assert "Prüfe zuerst" in texts


def test_set_and_reload_weighted_hooks(soul_engine):
    hooks = soul_engine.get_weighted_hooks()
    hooks[0].weight = 1.45
    soul_engine.set_weighted_hooks(hooks)
    reloaded = soul_engine.get_weighted_hooks()
    assert reloaded[0].weight == pytest.approx(1.45, abs=1e-3)


def test_apply_hook_feedback_positive(soul_engine):
    ok = soul_engine.apply_hook_feedback("Sei direkt", "positive")
    assert ok is True
    hooks = soul_engine.get_weighted_hooks()
    sei_direkt = next(h for h in hooks if "Sei direkt" in h.text)
    assert sei_direkt.weight > 1.0


def test_apply_hook_feedback_negative(soul_engine):
    ok = soul_engine.apply_hook_feedback("Prüfe zuerst", "negative")
    assert ok is True
    hooks = soul_engine.get_weighted_hooks()
    pruefe = next(h for h in hooks if "Prüfe zuerst" in h.text)
    assert pruefe.weight < 0.8


def test_apply_hook_feedback_not_found(soul_engine):
    ok = soul_engine.apply_hook_feedback("NonExistentHook12345", "positive")
    assert ok is False


def test_decay_hooks_returns_count(soul_engine):
    # Weight auf 1.5 setzen → decay sollte es ändern
    hooks = soul_engine.get_weighted_hooks()
    hooks[0].weight = 1.5
    soul_engine.set_weighted_hooks(hooks)
    count = soul_engine.decay_hooks()
    assert count >= 1


def test_get_active_hooks_filters_low_weight(soul_engine):
    # Hook mit weight=0.25 ist unter threshold=0.3
    active = soul_engine.get_active_hooks(threshold=0.3)
    texts = [h.text for h in active]
    assert "Nicht raten" not in texts
    assert "Sei direkt" in texts
