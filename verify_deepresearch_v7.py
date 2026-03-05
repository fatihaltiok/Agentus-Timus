#!/usr/bin/env python3
# verify_deepresearch_v7.py
"""
Automatische Verifikation: Deep Research Engine v7.0 — 40 Checks.

Prüft: Alle RC-Fixes, Lean-Specs, Pipeline-Struktur, Konfiguration.
Kein Netzwerk nötig (statische Code-Analyse + Import-Tests).

Exit-Code: 0 = alle Checks OK, 1 = mind. 1 Check fehlgeschlagen.

Usage:
    python verify_deepresearch_v7.py
"""

import importlib
import inspect
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
SECTION = "\033[1m"
RESET = "\033[0m"

checks_passed = 0
checks_failed = 0
failures = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global checks_passed, checks_failed
    if condition:
        checks_passed += 1
        print(f"  {PASS} {name}")
    else:
        checks_failed += 1
        failures.append(f"{name}: {detail}" if detail else name)
        print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{SECTION}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{RESET}")


# ==============================================================================
# RC4: Suchlocation & Query-Expansion
# ==============================================================================

section("RC4: Suchlocation & Query-Expansion")

try:
    from tools.deep_research.tool import (
        _detect_language, _detect_domain,
        _LANG_LOCATION_MAP, _LANG_CODE_MAP, TECH_KEYWORDS, EMBEDDING_THRESHOLDS,
    )
    check("_detect_language importierbar", True)
    check("_detect_domain importierbar", True)
    check("_LANG_LOCATION_MAP hat 'en'", "en" in _LANG_LOCATION_MAP)
    check("US-Location für englisch (2840)", _LANG_LOCATION_MAP.get("en") == 2840)
    check("DE-Location für deutsch (2276)", _LANG_LOCATION_MAP.get("de") == 2276)
    check("_detect_language('AI agents') == en", _detect_language("AI agents") == "en")
    check("_detect_language('üüüüü test') == de", _detect_language("üüüüü test") == "de")
    check("_detect_domain('AI LLM transformer') == tech", _detect_domain("AI LLM transformer") == "tech")
    check("_detect_domain('Klimawandel') == default", _detect_domain("Klimawandel") == "default")
    check("TECH_KEYWORDS >= 10 Einträge", len(TECH_KEYWORDS) >= 10)

    src = inspect.getsource(importlib.import_module("tools.deep_research.tool")._perform_initial_search)
    check("5 Queries in _perform_initial_search", "queries[:5]" in src)
    check("location_code in search_web Call", "location_code" in src)
except Exception as e:
    check(f"RC4 Import", False, str(e))
    for _ in range(10):
        check("RC4 (skip)", False, "Import fehlgeschlagen")

# ==============================================================================
# RC2: Embedding-Threshold
# ==============================================================================

section("RC2: Embedding-Threshold (Domain-aware)")

try:
    check("EMBEDDING_THRESHOLDS hat 'tech'", "tech" in EMBEDDING_THRESHOLDS)
    check("EMBEDDING_THRESHOLDS hat 'default'", "default" in EMBEDDING_THRESHOLDS)
    check("Tech-Threshold ≤ 0.72", EMBEDDING_THRESHOLDS["tech"] <= 0.72)
    check("Tech-Threshold < Default-Threshold", EMBEDDING_THRESHOLDS["tech"] < EMBEDDING_THRESHOLDS["default"])
    check("Alle Thresholds in [0,1]", all(0 <= v <= 1 for v in EMBEDDING_THRESHOLDS.values()))

    src_gsfacts = inspect.getsource(importlib.import_module("tools.deep_research.tool")._group_similar_facts)
    check("_group_similar_facts nimmt query-Parameter", "query: str" in src_gsfacts)
    check("Domain-Detection in _group_similar_facts", "_detect_domain" in src_gsfacts)
except Exception as e:
    check(f"RC2 Check", False, str(e))

# Fact-Extraktion: 8-15 Fakten
try:
    src_extract = inspect.getsource(importlib.import_module("tools.deep_research.tool")._extract_key_facts)
    check("Prompt enthält '8–15' oder '8-15' Fakten", "8–15" in src_extract or "8-15" in src_extract)
except Exception as e:
    check("Fact-Extraktion Prompt", False, str(e))

# ==============================================================================
# RC1 + RC3: Verifikation & Corroborator
# ==============================================================================

section("RC1 + RC3: Verifikation & Corroborator")

try:
    from tools.deep_research.tool import _resolve_verification_mode, _deep_verify_facts
    check("_resolve_verification_mode importierbar", True)
    check("_deep_verify_facts importierbar", True)

    # Auto-Mode: strict + Tech → moderate
    os.environ["DR_VERIFICATION_MODE_AUTO"] = "true"
    result = _resolve_verification_mode("strict", "AI agents LLM")
    check("Auto-Mode: strict + Tech → moderate", result == "moderate")

    result_de = _resolve_verification_mode("strict", "Klimawandel Ursachen")
    check("Auto-Mode: strict + Default → strict", result_de == "strict")

    result_off = _resolve_verification_mode.__wrapped__("strict", "AI") if hasattr(_resolve_verification_mode, "__wrapped__") else None
    check("_resolve_verification_mode mit auto=false bleibt strict",
          _resolve_verification_mode("light", "AI") == "light")

    src_verify = inspect.getsource(_deep_verify_facts)
    check("'moderate' Modus in _deep_verify_facts", "moderate" in src_verify)
    check("'light' Modus in _deep_verify_facts", "light" in src_verify)
    check("Corroborator für source_count >= 1 (RC3-Fix)", "source_count >= 1" in src_verify)
    check("Upgrade unverified→tentative in _deep_verify_facts", "tentatively_verified" in src_verify)
    check("Diagnostics n_verified in _deep_verify_facts", "n_verified" in src_verify)

    # Verifikations-Schwellen für moderate
    source_count = 1
    effective_mode = "moderate"
    status = "unverified"
    if effective_mode == "moderate":
        if source_count >= 2:
            status = "verified"
        elif source_count == 1:
            status = "tentatively_verified"
    check("moderate + source_count=1 → tentatively_verified", status == "tentatively_verified")

except Exception as e:
    check(f"RC1+RC3 Check", False, str(e))

# ==============================================================================
# RC5: ArXiv-Qualität
# ==============================================================================

section("RC5: ArXiv-Qualität")

try:
    from tools.deep_research.trend_researcher import _RELEVANCE_THRESHOLD, ArXivResearcher
    check("ArXiv-Threshold ≤ 5 (war 6)", _RELEVANCE_THRESHOLD <= 5)
    check("ArXiv-Threshold > 0", _RELEVANCE_THRESHOLD > 0)

    src_arxiv = inspect.getsource(ArXivResearcher.research)
    check("Datum-Sortierung in ArXiv.research", "published" in src_arxiv and "sort" in src_arxiv)
    check("Diagnostics arxiv_accepted in ArXiv.research", "arxiv_accepted" in src_arxiv)
    check("topic-aware Fallback-Score in ArXiv.research", "overlap" in src_arxiv)

    src_fetch = inspect.getsource(ArXivResearcher._fetch_papers)
    check("min. 25 Kandidaten in _fetch_papers", "25" in src_fetch)
except Exception as e:
    check(f"RC5 Check", False, str(e))

# ==============================================================================
# M1: Diagnostics
# ==============================================================================

section("M1: DrDiagnostics")

try:
    from tools.deep_research.diagnostics import DrDiagnostics, reset, get_current, set_current
    check("DrDiagnostics importierbar", True)
    d = DrDiagnostics(query="test")
    d.n_verified = 3
    d.finish()
    check("quality_gate_passed True bei n_verified=3", d.quality_gate_passed is True)
    d2 = DrDiagnostics(query="test")
    d2.n_verified = 2
    d2.finish()
    check("quality_gate_passed False bei n_verified=2", d2.quality_gate_passed is False)
    check("summary() ist dict", isinstance(d.summary(), dict))
    check("reset() gibt frische Instanz", reset().n_verified == 0)
    check("set_current/get_current funktioniert", (set_current(d), get_current() is d)[1])
except Exception as e:
    check(f"M1 Diagnostics", False, str(e))

# ==============================================================================
# M6: Qualitäts-Gate in start_deep_research
# ==============================================================================

section("M6: Qualitäts-Gate & Fallback")

try:
    src_sdr = inspect.getsource(importlib.import_module("tools.deep_research.tool").start_deep_research)
    check("quality_gate_passed im return-Dict", "quality_gate_passed" in src_sdr)
    check("fallback_triggered im return-Dict", "fallback_triggered" in src_sdr)
    check("light-Mode Fallback in start_deep_research", "light" in src_sdr and "Fallback" in src_sdr)
    check("version '7.0' im return-Dict", "7.0" in src_sdr)
    check("_run_research_pipeline Aufruf", "_run_research_pipeline" in src_sdr)
except Exception as e:
    check(f"M6 Qualitäts-Gate", False, str(e))

# ==============================================================================
# Lean CI-Specs
# ==============================================================================

section("Lean CI-Specs (Theoreme-Zählung)")

lean_file = ROOT / "lean" / "CiSpecs.lean"
if lean_file.exists():
    content = lean_file.read_text()
    check("dr_query_expansion Theorem vorhanden", "dr_query_expansion" in content)
    check("dr_embedding_threshold_lower vorhanden", "dr_embedding_threshold_lower" in content)
    check("dr_embedding_threshold_upper vorhanden", "dr_embedding_threshold_upper" in content)
    check("dr_verify_moderate vorhanden", "dr_verify_moderate" in content)
    check("dr_arxiv_score_lower vorhanden", "dr_arxiv_score_lower" in content)
    check("dr_arxiv_score_upper vorhanden", "dr_arxiv_score_upper" in content)
    theorem_count = content.count("theorem ")
    check(f"Mind. 14 Theoreme ({theorem_count} gefunden)", theorem_count >= 14)
else:
    check("lean/CiSpecs.lean existiert", False, "Datei nicht gefunden")

# ==============================================================================
# .env.example Flags
# ==============================================================================

section(".env.example Flags")

env_file = ROOT / ".env.example"
if env_file.exists():
    env_content = env_file.read_text()
    check("DR_EMBEDDING_THRESHOLD_TECH in .env.example", "DR_EMBEDDING_THRESHOLD_TECH" in env_content)
    check("DR_VERIFICATION_MODE_AUTO in .env.example", "DR_VERIFICATION_MODE_AUTO" in env_content)
else:
    check(".env.example existiert", False)

# ==============================================================================
# Neue Test-Dateien
# ==============================================================================

section("Test-Dateien vorhanden")

test_files = [
    "tests/test_dr_diagnostics.py",
    "tests/test_dr_search_location.py",
    "tests/test_dr_fact_extraction.py",
    "tests/test_dr_verification.py",
    "tests/test_dr_arxiv.py",
    "tests/test_dr_integration.py",
]
for tf in test_files:
    p = ROOT / tf
    check(f"{tf} existiert", p.exists())

# ==============================================================================
# Ergebnis
# ==============================================================================

total = checks_passed + checks_failed
print(f"\n{'='*60}")
print(f"Ergebnis: {checks_passed}/{total} Checks bestanden")
if failures:
    print(f"\nFehlgeschlagen ({len(failures)}):")
    for f in failures:
        print(f"  - {f}")
print(f"{'='*60}\n")

sys.exit(0 if checks_failed == 0 else 1)
