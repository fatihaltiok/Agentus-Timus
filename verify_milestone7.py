#!/usr/bin/env python3
"""
verify_milestone7.py — M15: Ambient Context Engine Verifikation

Prüft:
  1. Datei-Existenz: ambient_context_engine.py, test_m15_ambient_context.py
  2. Syntax: py_compile für alle neuen Dateien
  3. Struktur: AmbientSignal, AmbientContextEngine, get_ambient_engine vorhanden
  4. Feature-Flag: AUTONOMY_AMBIENT_CONTEXT_ENABLED in autonomous_runner.py
  5. Lean-Specs: 3 neue Specs in tools/lean_tool/tool.py
  6. CI-Specs: 3 neue Theoreme in lean/CiSpecs.lean
  7. .env: 5 neue Flags vorhanden
"""

from __future__ import annotations

import ast
import importlib
import os
import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PASS = "✅"
FAIL = "❌"
results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    icon = PASS if passed else FAIL
    print(f"{icon} {name}" + (f" — {detail}" if detail else ""))


# ──────────────────────────────────────────────────────────────────────────────
# 1. Datei-Existenz
# ──────────────────────────────────────────────────────────────────────────────

required_files = [
    "orchestration/ambient_context_engine.py",
    "tests/test_m15_ambient_context.py",
]
for f in required_files:
    fp = ROOT / f
    check(f"Datei vorhanden: {f}", fp.exists())

# ──────────────────────────────────────────────────────────────────────────────
# 2. Syntax-Check
# ──────────────────────────────────────────────────────────────────────────────

syntax_files = required_files + ["orchestration/autonomous_runner.py"]
for f in syntax_files:
    fp = ROOT / f
    if fp.exists():
        try:
            py_compile.compile(str(fp), doraise=True)
            check(f"Syntax OK: {f}", True)
        except py_compile.PyCompileError as e:
            check(f"Syntax OK: {f}", False, str(e))
    else:
        check(f"Syntax OK: {f}", False, "Datei fehlt")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Struktur: AmbientSignal, AmbientContextEngine, get_ambient_engine
# ──────────────────────────────────────────────────────────────────────────────

engine_path = ROOT / "orchestration/ambient_context_engine.py"
if engine_path.exists():
    tree = ast.parse(engine_path.read_text(encoding="utf-8"))

    def _find_class(name: str) -> bool:
        return any(
            isinstance(n, ast.ClassDef) and n.name == name
            for n in ast.walk(tree)
        )

    def _find_function(name: str) -> bool:
        return any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
            for n in ast.walk(tree)
        )

    check("AmbientSignal dataclass vorhanden", _find_class("AmbientSignal"))
    check("AmbientContextEngine class vorhanden", _find_class("AmbientContextEngine"))
    check("get_ambient_engine() vorhanden", _find_function("get_ambient_engine"))
    check("run_cycle() vorhanden", _find_function("run_cycle"))
    check("_check_emails() vorhanden", _find_function("_check_emails"))
    check("_check_files() vorhanden", _find_function("_check_files"))
    check("_check_goal_staleness() vorhanden", _find_function("_check_goal_staleness"))
    check("_check_system() vorhanden", _find_function("_check_system"))
    check("_is_duplicate() vorhanden", _find_function("_is_duplicate"))
    check("_mark_seen() vorhanden", _find_function("_mark_seen"))
    check("_process_signal() vorhanden", _find_function("_process_signal"))

    src = engine_path.read_text(encoding="utf-8")
    check("SIGNAL_THRESHOLD definiert", "SIGNAL_THRESHOLD" in src)
    check("CONFIRM_THRESHOLD definiert", "CONFIRM_THRESHOLD" in src)
    check("SYSTEM_ALERT_THRESHOLD definiert", "SYSTEM_ALERT_THRESHOLD" in src)
    check("asyncio.gather in run_cycle", "asyncio.gather" in src)

# ──────────────────────────────────────────────────────────────────────────────
# 4. Feature-Flag in autonomous_runner.py
# ──────────────────────────────────────────────────────────────────────────────

runner_path = ROOT / "orchestration/autonomous_runner.py"
if runner_path.exists():
    runner_src = runner_path.read_text(encoding="utf-8")
    check(
        "_ambient_context_feature_enabled() in autonomous_runner.py",
        "_ambient_context_feature_enabled" in runner_src,
    )
    check(
        "AUTONOMY_AMBIENT_CONTEXT_ENABLED Flag referenziert",
        "AUTONOMY_AMBIENT_CONTEXT_ENABLED" in runner_src,
    )
    check(
        "M15 Heartbeat-Hook vorhanden",
        "ambient_engine.run_cycle" in runner_src,
    )

# ──────────────────────────────────────────────────────────────────────────────
# 5. Lean-Specs in tools/lean_tool/tool.py
# ──────────────────────────────────────────────────────────────────────────────

lean_tool_path = ROOT / "tools/lean_tool/tool.py"
if lean_tool_path.exists():
    lean_src = lean_tool_path.read_text(encoding="utf-8")
    new_specs = [
        "ambient_score_in_bounds",
        "ambient_threshold_gate",
        "ambient_confirm_guard",
    ]
    for spec in new_specs:
        check(f"Lean-Spec '{spec}' vorhanden", spec in lean_src)

# ──────────────────────────────────────────────────────────────────────────────
# 6. CI-Specs in lean/CiSpecs.lean
# ──────────────────────────────────────────────────────────────────────────────

ci_specs_path = ROOT / "lean/CiSpecs.lean"
if ci_specs_path.exists():
    ci_src = ci_specs_path.read_text(encoding="utf-8")
    ci_theorems = [
        "ambient_score_lower",
        "ambient_score_upper",
        "ambient_threshold_ci",
    ]
    for thm in ci_theorems:
        check(f"CI-Theorem '{thm}' vorhanden", thm in ci_src)
else:
    check("lean/CiSpecs.lean vorhanden", False, "Datei fehlt")

# ──────────────────────────────────────────────────────────────────────────────
# 7. .env-Flags
# ──────────────────────────────────────────────────────────────────────────────

env_path = ROOT / ".env"
if env_path.exists():
    env_src = env_path.read_text(encoding="utf-8")
    env_flags = [
        "AUTONOMY_AMBIENT_CONTEXT_ENABLED",
        "AMBIENT_SIGNAL_THRESHOLD",
        "AMBIENT_CONFIRM_THRESHOLD",
        "AMBIENT_GOAL_STALE_HOURS",
        "AMBIENT_SYSTEM_ALERT_THRESHOLD",
    ]
    for flag in env_flags:
        check(f".env Flag '{flag}' vorhanden", flag in env_src)
else:
    check(".env vorhanden", False, "Datei fehlt")

# ──────────────────────────────────────────────────────────────────────────────
# Ergebnis
# ──────────────────────────────────────────────────────────────────────────────

total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

print()
print("=" * 60)
print(f"M15 Verifikation: {passed}/{total} Checks bestanden")
if failed:
    print(f"\nFehlgeschlagene Checks ({failed}):")
    for name, ok, detail in results:
        if not ok:
            print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))
    sys.exit(1)
else:
    print(f"{PASS} Alle Checks bestanden — M15 Ambient Context Engine verifiziert!")
    sys.exit(0)
