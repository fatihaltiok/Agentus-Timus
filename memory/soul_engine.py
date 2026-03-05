"""
memory/soul_engine.py — Soul Engine v2.8

Timus entwickelt eine eigene "Persönlichkeit" über 5 Achsen:
  confidence, formality, humor, verbosity, risk_appetite

Jede Achse driftet nach Interaktions-Signalen.
Der System-Prompt wird dynamisch an die aktuellen Achsen angepasst.

AUTOR: Timus Development
DATUM: 2026-02-25
"""

import os
import re
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional

import yaml

log = logging.getLogger("SoulEngine")

SOUL_MD_PATH = Path.home() / "dev" / "timus" / "memory" / "markdown_store" / "SOUL.md"

# Env-Konfiguration
DRIFT_ENABLED = os.getenv("SOUL_DRIFT_ENABLED", "true").lower() == "true"
DRIFT_DAMPING = float(os.getenv("SOUL_DRIFT_DAMPING", "0.1"))
CLAMP_MIN = float(os.getenv("SOUL_AXES_CLAMP_MIN", "5"))
CLAMP_MAX = float(os.getenv("SOUL_AXES_CLAMP_MAX", "95"))

# M16: Weighted Hooks
FEEDBACK_DELTA = float(os.getenv("M16_FEEDBACK_DELTA", "0.15"))
HOOK_MIN_WEIGHT = float(os.getenv("M16_HOOK_MIN_WEIGHT", "0.05"))
HOOK_MAX_WEIGHT = 2.0
HOOK_DECAY_RATE = float(os.getenv("M16_HOOK_DECAY_RATE", "0.97"))


@dataclass
class WeightedHook:
    """Behavior Hook mit Feedback-Gewichtung (M16)."""
    text: str
    weight: float = 1.0
    feedback_count: int = 0

    def apply_feedback(self, signal: str, delta: float = FEEDBACK_DELTA) -> None:
        """
        Ändert weight basierend auf Feedback-Signal.

        positive → weight + delta
        negative → weight - delta
        neutral  → kein Effekt (Noop)
        """
        if signal == "positive":
            self.weight = max(HOOK_MIN_WEIGHT, min(HOOK_MAX_WEIGHT, self.weight + delta))
            self.feedback_count += 1
        elif signal == "negative":
            self.weight = max(HOOK_MIN_WEIGHT, min(HOOK_MAX_WEIGHT, self.weight - delta))
            self.feedback_count += 1
        # neutral: keine Änderung

    def decay(self, rate: float = HOOK_DECAY_RATE) -> None:
        """Täglicher Decay: weight × rate (Richtung 1.0 normalisieren)."""
        if self.weight > 1.0:
            self.weight = max(1.0, self.weight * rate)
        elif self.weight < 1.0:
            self.weight = min(1.0, self.weight / rate)

    def is_active(self, threshold: float = 0.3) -> bool:
        return self.weight >= threshold

DEFAULT_AXES: Dict[str, float] = {
    "confidence": 50.0,
    "formality": 65.0,
    "humor": 15.0,
    "verbosity": 50.0,
    "risk_appetite": 40.0,
}

MAX_DRIFT_HISTORY = 30


class SoulEngine:
    """
    Verwaltet die 5 Persönlichkeits-Achsen von Timus.

    Achsen werden in SOUL.md gespeichert (YAML frontmatter).
    Drift erfolgt nach jeder Reflexion basierend auf Interaktions-Signalen.
    """

    def __init__(self):
        self._axes_cache: Optional[Dict[str, float]] = None

    # ---------------------------------------------------------------
    # Öffentliche API
    # ---------------------------------------------------------------

    def get_axes(self) -> Dict[str, float]:
        """Liest aktuelle Achsen aus SOUL.md."""
        data = self._read_frontmatter()
        axes_raw = data.get("axes", {})
        if isinstance(axes_raw, dict) and axes_raw:
            axes = {}
            for k, v in axes_raw.items():
                try:
                    axes[k] = self._clamp(float(v))
                except (ValueError, TypeError):
                    axes[k] = DEFAULT_AXES.get(k, 50.0)
            # Fehlende Achsen mit Defaults auffüllen
            for k, default in DEFAULT_AXES.items():
                if k not in axes:
                    axes[k] = default
            return axes
        return dict(DEFAULT_AXES)

    def set_axes(self, axes: Dict[str, float]) -> None:
        """Schreibt Achsen direkt in SOUL.md (für Tests und manuelle Overrides)."""
        data = self._read_frontmatter()
        data["axes"] = {k: self._clamp(float(v)) for k, v in axes.items()}
        data["axes_updated_at"] = date.today().isoformat()
        self._write_frontmatter(data)
        self._axes_cache = None

    def apply_drift(
        self,
        reflection: Any,  # ReflectionResult
        user_input: str = "",
        session_stats: Optional[Dict] = None,
    ) -> Dict[str, float]:
        """
        Hauptmethode: Drift nach Task-Reflexion anwenden.

        Erkennt 7 Signale, berechnet Δ-Werte, dämpft und clamped.
        Schreibt Änderungen in SOUL.md.
        Gibt neue Achsen zurück.
        """
        if not DRIFT_ENABLED:
            log.debug("Soul-Drift deaktiviert (SOUL_DRIFT_ENABLED=false)")
            return self.get_axes()

        axes = self.get_axes()
        deltas: List[Dict[str, Any]] = []

        # --- Signal-Erkennung ---
        user_lower = (user_input or "").lower()
        what_worked: List[str] = getattr(reflection, "what_worked", []) or []
        what_failed: List[str] = getattr(reflection, "what_failed", []) or []
        success: bool = getattr(reflection, "success", True)
        task_type: str = (session_stats or {}).get("task_type", "")

        # Signal 1: User lehnte Vorschlag ab / korrigierte Timus
        rejection_keywords = ["nein", "falsch", "nicht so", "das stimmt nicht", "stimmt nicht", "falsch ist"]
        if any(kw in user_lower for kw in rejection_keywords):
            deltas.append({"axis": "confidence", "delta": -2, "reason": "user_rejection"})

        # Signal 2: Task erfolgreich + Reflexion positiv
        if success and len(what_worked) >= 2:
            deltas.append({"axis": "confidence", "delta": +3, "reason": "task_success"})

        # Signal 3: User nutzt Emoji oder Umgangssprache
        if re.search(r'[\U0001F600-\U0001F9FF]', user_input or ""):
            deltas.append({"axis": "formality", "delta": -2, "reason": "user_emoji"})
            deltas.append({"axis": "humor", "delta": +1, "reason": "user_emoji"})
        elif re.search(r'\b(hey|ok|jo|yep|nah|lol|haha|geil|krass)\b', user_lower):
            deltas.append({"axis": "formality", "delta": -1, "reason": "user_slang"})

        # Signal 4: User antwortet sehr knapp (< 8 Wörter)
        word_count = len((user_input or "").split())
        if 0 < word_count < 8:
            deltas.append({"axis": "verbosity", "delta": -2, "reason": "user_short_input"})

        # Signal 5: User schreibt ausführlich (> 60 Wörter)
        if word_count > 60:
            deltas.append({"axis": "verbosity", "delta": +2, "reason": "user_long_input"})

        # Signal 6: Mehrere Fehler in Folge
        if len(what_failed) >= 3:
            deltas.append({"axis": "confidence", "delta": -3, "reason": "multiple_failures"})
            deltas.append({"axis": "risk_appetite", "delta": -2, "reason": "multiple_failures"})

        # Signal 7: Viel funktioniert + kreative/Entwicklungs-Aufgabe
        if len(what_worked) >= 3 and any(t in task_type.lower() for t in ["creative", "development", "code"]):
            deltas.append({"axis": "risk_appetite", "delta": +2, "reason": "creative_success"})

        if not deltas:
            log.debug("Soul-Drift: Keine Signale erkannt")
            return axes

        # --- Dämpfung + Clamp anwenden ---
        data = self._read_frontmatter()
        current_axes = self.get_axes()
        drift_history = list(data.get("drift_history", []) or [])

        for entry in deltas:
            axis = entry["axis"]
            raw_delta = entry["delta"]
            dampened_delta = raw_delta * DRIFT_DAMPING
            old_val = current_axes.get(axis, DEFAULT_AXES.get(axis, 50.0))
            new_val = self._clamp(old_val + dampened_delta)
            current_axes[axis] = new_val

            history_entry = {
                "date": datetime.now().isoformat()[:10],
                "axis": axis,
                "delta": round(dampened_delta, 3),
                "reason": entry["reason"],
            }
            drift_history.append(history_entry)
            log.info(
                "Soul-Drift: %s %s→%.1f (Δ%.2f, %s)",
                axis, f"{old_val:.1f}", new_val, dampened_delta, entry["reason"]
            )

        # Auf Max 30 Einträge begrenzen
        drift_history = drift_history[-MAX_DRIFT_HISTORY:]

        # Schreiben
        data["axes"] = {k: round(v, 2) for k, v in current_axes.items()}
        data["axes_updated_at"] = date.today().isoformat()
        data["drift_history"] = drift_history
        self._write_frontmatter(data)
        self._axes_cache = None

        return current_axes

    def _apply_single_signal(self, signal: str, delta: float) -> None:
        """Wendet ein einzelnes Signal direkt an (für Tests und manuelle Overrides)."""
        # Map signal name zu axis
        signal_map = {
            "task_success": "confidence",
            "user_rejection": "confidence",
            "multiple_failures": "confidence",
            "creative_success": "risk_appetite",
            "user_emoji": "formality",
            "user_short_input": "verbosity",
            "user_long_input": "verbosity",
        }
        axis = signal_map.get(signal, "confidence")
        data = self._read_frontmatter()
        axes = self.get_axes()
        old_val = axes.get(axis, 50.0)
        dampened = delta * DRIFT_DAMPING
        new_val = self._clamp(old_val + dampened)
        axes[axis] = new_val
        data["axes"] = {k: round(v, 2) for k, v in axes.items()}

        drift_history = list(data.get("drift_history", []) or [])
        drift_history.append({
            "date": datetime.now().isoformat()[:10],
            "axis": axis,
            "delta": round(dampened, 3),
            "reason": signal,
        })
        data["drift_history"] = drift_history[-MAX_DRIFT_HISTORY:]
        data["axes_updated_at"] = date.today().isoformat()
        self._write_frontmatter(data)
        self._axes_cache = None

    # ---------------------------------------------------------------
    # M16: Weighted Hooks API
    # ---------------------------------------------------------------

    def get_weighted_hooks(self) -> List[WeightedHook]:
        """
        Liest weighted_hooks aus SOUL.md Frontmatter.
        Fallback: behavior_hooks als ungewichtete Hooks (weight=1.0).
        """
        data = self._read_frontmatter()
        weighted_raw = data.get("weighted_hooks", [])
        if weighted_raw and isinstance(weighted_raw, list):
            hooks = []
            for item in weighted_raw:
                if isinstance(item, dict):
                    hooks.append(WeightedHook(
                        text=item.get("text", ""),
                        weight=float(item.get("weight", 1.0)),
                        feedback_count=int(item.get("feedback_count", 0)),
                    ))
                elif isinstance(item, str):
                    hooks.append(WeightedHook(text=item))
            return hooks

        # Fallback: behavior_hooks (plain list) → WeightedHook(weight=1.0)
        behavior = data.get("behavior_hooks", [])
        if isinstance(behavior, list):
            return [WeightedHook(text=h) for h in behavior if h]
        return []

    def set_weighted_hooks(self, hooks: List[WeightedHook]) -> None:
        """Schreibt weighted_hooks in SOUL.md Frontmatter."""
        data = self._read_frontmatter()
        data["weighted_hooks"] = [
            {
                "text": h.text,
                "weight": round(h.weight, 4),
                "feedback_count": h.feedback_count,
            }
            for h in hooks
        ]
        data["weighted_hooks_updated_at"] = date.today().isoformat()
        self._write_frontmatter(data)

    def apply_hook_feedback(self, hook_name: str, signal: str) -> bool:
        """
        Wendet Feedback-Signal auf einen Hook an (Suche nach Teilstring).

        Args:
            hook_name: Suchbegriff (Teilstring des Hook-Textes)
            signal: "positive", "negative" oder "neutral"

        Returns:
            True wenn Hook gefunden und aktualisiert wurde
        """
        hooks = self.get_weighted_hooks()
        updated = False
        for hook in hooks:
            if hook_name.lower() in hook.text.lower() or hook.text.lower() in hook_name.lower():
                hook.apply_feedback(signal)
                updated = True
        if updated:
            self.set_weighted_hooks(hooks)
            log.info("Hook-Feedback angewendet: %r signal=%s", hook_name, signal)
        return updated

    def decay_hooks(self) -> int:
        """
        Täglicher Decay aller Hook-Weights (×HOOK_DECAY_RATE).
        Gibt Anzahl der geänderten Hooks zurück.
        """
        hooks = self.get_weighted_hooks()
        changed = 0
        for hook in hooks:
            old = hook.weight
            hook.decay()
            if abs(hook.weight - old) > 0.001:
                changed += 1
        if changed > 0:
            self.set_weighted_hooks(hooks)
            log.info("Hook-Decay: %d Hooks angepasst", changed)
        return changed

    def get_active_hooks(self, threshold: float = 0.3) -> List[WeightedHook]:
        """
        Gibt nur aktive Hooks zurück (weight >= threshold).
        Hooks unter dem Threshold werden als inaktiv betrachtet.
        """
        return [h for h in self.get_weighted_hooks() if h.is_active(threshold)]

    def get_tone_descriptor(self) -> str:
        """
        Gibt einen kurzen Ton-Deskriptor zurück: 'vorsichtig', 'neutral', 'direkt'.
        Für Curiosity Engine und Prompt-Anpassungen.
        """
        axes = self.get_axes()
        confidence = axes.get("confidence", 50.0)
        if confidence < 40:
            return "vorsichtig"
        elif confidence > 65:
            return "direkt"
        return "neutral"

    def get_tone_config(self) -> Dict[str, Any]:
        """Gibt vollständige Ton-Konfiguration für Curiosity-Nachrichten zurück."""
        axes = self.get_axes()
        tone = self.get_tone_descriptor()

        intro_map = {
            "vorsichtig": "Ich bin mir nicht sicher, aber könnte das relevant sein?",
            "neutral": "Hey, ich bin gerade im Hintergrund über dieses Thema gestolpert...",
            "direkt": "Schau dir das an — das löst genau unser Problem.",
        }

        return {
            "tone": tone,
            "axes": axes,
            "intro_hint": intro_map[tone],
            "humor_enabled": axes.get("humor", 15.0) > 60,
            "formal": axes.get("formality", 65.0) > 75,
            "verbose": axes.get("verbosity", 50.0) > 70,
        }

    # ---------------------------------------------------------------
    # Interne Helfer
    # ---------------------------------------------------------------

    def _clamp(self, value: float) -> float:
        """Begrenzt Achsen-Werte auf [CLAMP_MIN, CLAMP_MAX]."""
        return max(CLAMP_MIN, min(CLAMP_MAX, value))

    def _read_frontmatter(self) -> Dict[str, Any]:
        """Liest SOUL.md YAML-Frontmatter via PyYAML."""
        if not SOUL_MD_PATH.exists():
            return {}
        try:
            content = SOUL_MD_PATH.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return yaml.safe_load(parts[1]) or {}
        except Exception as e:
            log.error("SoulEngine: SOUL.md lesen fehlgeschlagen: %s", e)
        return {}

    def _write_frontmatter(self, data: Dict[str, Any]) -> None:
        """Schreibt SOUL.md Frontmatter via PyYAML, Markdown-Body bleibt erhalten."""
        try:
            existing = ""
            if SOUL_MD_PATH.exists():
                existing = SOUL_MD_PATH.read_text(encoding="utf-8")

            # Body extrahieren (alles nach dem zweiten ---)
            parts = existing.split("---", 2)
            body = parts[2] if len(parts) >= 3 else "\n\n# Timus Persona\n\nDiese Datei definiert das Verhalten und die Persönlichkeit von Timus.\n"

            new_frontmatter = yaml.dump(
                data,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                indent=2,
            )
            SOUL_MD_PATH.write_text(
                f"---\n{new_frontmatter.rstrip()}\n---{body}",
                encoding="utf-8",
            )
        except Exception as e:
            log.error("SoulEngine: SOUL.md schreiben fehlgeschlagen: %s", e)


# ---------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------

_soul_engine: Optional[SoulEngine] = None


def get_soul_engine() -> SoulEngine:
    """Gibt die globale SoulEngine-Instanz zurück."""
    global _soul_engine
    if _soul_engine is None:
        _soul_engine = SoulEngine()
    return _soul_engine
