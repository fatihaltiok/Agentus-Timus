# tools/deep_research/diagnostics.py
"""
DrDiagnostics — Diagnoseschicht für Deep Research Engine v7.0.

Wraps jede Phase mit Metriken ohne Produktions-Logik zu verändern.
Alle Felder sind direkt messbar; keine Schätzwerte.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("dr_diagnostics")


@dataclass
class DrDiagnostics:
    """
    Sammelt Metriken aus jeder Phase der Deep Research Pipeline.

    Felder:
        query                 — die ursprüngliche Anfrage
        language_detected     — "en" / "de" / ...
        location_used         — DataForSEO Location Code oder Name
        n_queries_issued      — Anzahl gesendeter Suchanfragen
        n_sources_found       — Gesamt-Treffer aus allen Queries
        n_sources_relevant    — nach Relevanz-Filter
        n_facts_extracted     — Rohfakten aus allen Quellen
        n_facts_grouped       — Gruppen nach Embedding-Merge
        embedding_threshold   — verwendeter Threshold (float)
        domain_detected       — "tech" / "science" / "default"
        n_verified            — verifizierte Fakten
        n_tentative           — tentative Fakten
        n_unverified          — nicht-verifizierte Fakten
        verification_mode_req — angeforderter Modus ("strict" / "moderate" / "light")
        verification_mode_eff — tatsächlich verwendeter Modus (kann abweichen)
        n_corroborator_calls  — wie oft fact_corroborator aufgerufen wurde
        arxiv_fetched         — abgerufene ArXiv-Paper
        arxiv_accepted        — Paper die Threshold bestanden
        arxiv_threshold       — verwendeter Relevanz-Threshold
        duration_seconds      — Gesamtdauer
        quality_gate_passed   — True wenn verified_count >= 3
        fallback_triggered    — True wenn light-Retry ausgelöst wurde
        phase_times           — Dict mit Zeitstempeln je Phase
    """

    query: str = ""
    language_detected: str = "unknown"
    location_used: str = "unknown"
    n_queries_issued: int = 0
    n_sources_found: int = 0
    n_sources_relevant: int = 0
    n_facts_extracted: int = 0
    n_facts_grouped: int = 0
    embedding_threshold: float = 0.85
    domain_detected: str = "default"
    n_verified: int = 0
    n_tentative: int = 0
    n_unverified: int = 0
    verification_mode_req: str = "strict"
    verification_mode_eff: str = "strict"
    n_corroborator_calls: int = 0
    arxiv_fetched: int = 0
    arxiv_accepted: int = 0
    arxiv_threshold: int = 6
    duration_seconds: float = 0.0
    quality_gate_passed: bool = False
    fallback_triggered: bool = False
    phase_times: Dict[str, float] = field(default_factory=dict)
    _start: float = field(default_factory=time.monotonic, repr=False, compare=False)

    def mark_phase(self, phase: str) -> None:
        """Speichert Zeitstempel zu Beginn/Ende einer Phase."""
        self.phase_times[phase] = round(time.monotonic() - self._start, 2)

    def finish(self) -> None:
        """Setzt duration_seconds und quality_gate_passed."""
        self.duration_seconds = round(time.monotonic() - self._start, 2)
        self.quality_gate_passed = self.n_verified >= 3

    def summary(self) -> Dict[str, Any]:
        """Gibt alle Metriken als flaches Dict zurück (für JSON/Logging)."""
        return {
            "query": self.query,
            "language_detected": self.language_detected,
            "location_used": self.location_used,
            "n_queries_issued": self.n_queries_issued,
            "n_sources_found": self.n_sources_found,
            "n_sources_relevant": self.n_sources_relevant,
            "n_facts_extracted": self.n_facts_extracted,
            "n_facts_grouped": self.n_facts_grouped,
            "embedding_threshold": self.embedding_threshold,
            "domain_detected": self.domain_detected,
            "n_verified": self.n_verified,
            "n_tentative": self.n_tentative,
            "n_unverified": self.n_unverified,
            "verification_mode_req": self.verification_mode_req,
            "verification_mode_eff": self.verification_mode_eff,
            "n_corroborator_calls": self.n_corroborator_calls,
            "arxiv_fetched": self.arxiv_fetched,
            "arxiv_accepted": self.arxiv_accepted,
            "arxiv_threshold": self.arxiv_threshold,
            "duration_seconds": self.duration_seconds,
            "quality_gate_passed": self.quality_gate_passed,
            "fallback_triggered": self.fallback_triggered,
            "phase_times": self.phase_times,
        }

    def print_report(self) -> None:
        """Gibt farbcodierten Diagnose-Report auf stdout aus."""
        GREEN = "\033[92m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        RESET = "\033[0m"
        BOLD = "\033[1m"

        def ok(v: bool) -> str:
            return f"{GREEN}✓{RESET}" if v else f"{RED}✗{RESET}"

        print(f"\n{BOLD}=== Deep Research v7.0 — Diagnose ==={RESET}")
        print(f"Query         : {self.query}")
        print(f"Dauer         : {self.duration_seconds:.1f}s")
        print()
        print(f"{BOLD}Phase 1 — Suche{RESET}")
        print(f"  Sprache        : {self.language_detected}  ({self.location_used})")
        print(f"  Queries        : {self.n_queries_issued}")
        print(f"  Quellen gesamt : {self.n_sources_found}")
        print(f"  Quellen relev. : {self.n_sources_relevant}")
        print()
        print(f"{BOLD}Phase 2 — Fakten{RESET}")
        print(f"  Extrahiert     : {self.n_facts_extracted}")
        print(f"  Domain         : {self.domain_detected} (Threshold={self.embedding_threshold})")
        print(f"  Gruppen        : {self.n_facts_grouped}")
        print()
        print(f"{BOLD}Phase 3 — Verifikation{RESET}")
        print(f"  Modus angefragt: {self.verification_mode_req}")
        print(f"  Modus effektiv : {self.verification_mode_eff}")
        print(f"  Corroborator   : {self.n_corroborator_calls}x aufgerufen")
        verified_ok = self.n_verified >= 3
        print(f"  Verifiziert    : {ok(verified_ok)} {self.n_verified}")
        print(f"  Tentative      : {self.n_tentative}")
        print(f"  Unverifiziert  : {self.n_unverified}")
        print()
        print(f"{BOLD}Phase 4 — ArXiv{RESET}")
        print(f"  Threshold      : {self.arxiv_threshold}")
        print(f"  Abgerufen      : {self.arxiv_fetched}")
        arxiv_ok = self.arxiv_accepted >= 3
        print(f"  Akzeptiert     : {ok(arxiv_ok)} {self.arxiv_accepted}")
        print()
        print(f"{BOLD}Qualitäts-Gate{RESET}")
        print(f"  Passed         : {ok(self.quality_gate_passed)}")
        if self.fallback_triggered:
            print(f"  Fallback       : {YELLOW}light-Mode Retry ausgelöst{RESET}")
        print()
        print(f"{BOLD}Phase-Zeiten (s){RESET}")
        for phase, t in self.phase_times.items():
            print(f"  {phase:<20}: {t:.2f}s")
        print()


# Globaler Singleton — wird von start_deep_research() gesetzt
_current: Optional[DrDiagnostics] = None


def get_current() -> Optional[DrDiagnostics]:
    return _current


def set_current(d: DrDiagnostics) -> None:
    global _current
    _current = d


def reset() -> DrDiagnostics:
    """Erstellt neue Diagnostics-Instanz und setzt sie als current."""
    global _current
    _current = DrDiagnostics()
    return _current
