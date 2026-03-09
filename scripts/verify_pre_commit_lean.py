#!/usr/bin/env python3
"""
Gebündelte Lean-Verifikation für den lokalen Pre-Commit-Hook.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEAN_PROJECT_DIR = Path(os.path.expanduser("~/dev/lean_verify"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.lean_tool.specs import BUILTIN_SPECS, build_combined_mathlib_specs


def _run_checked(cmd: list[str], *, cwd: Path, timeout: int, label: str) -> int:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode == 0:
        print(f"  ✓ {label}")
        return 0
    print(f"  ✗ {label}")
    output = (proc.stderr or proc.stdout).strip()
    if output:
        print(output[:1200])
    return 1


def main() -> int:
    lean_path = shutil.which("lean")
    lake_path = shutil.which("lake")

    if lean_path is None:
        print("⚠️  Lean nicht installiert — Hook übersprungen")
        return 0

    print("\n🔬 Lean 4 Verifikation (CiSpecs + 12 Mathlib-Specs) ...")

    failures = 0
    try:
        failures += _run_checked(
            [lean_path, "lean/CiSpecs.lean"],
            cwd=REPO_ROOT,
            timeout=30,
            label="lean/CiSpecs.lean",
        )
    except subprocess.TimeoutExpired:
        print("  ✗ lean/CiSpecs.lean")
        print("Lean-Prüfung hat das Timeout (30s) überschritten.")
        failures += 1

    if lake_path is None or not LEAN_PROJECT_DIR.is_dir():
        print("  ⚠️  Mathlib-Projekt fehlt — Mathlib-Specs übersprungen")
    else:
        combined = build_combined_mathlib_specs()
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".lean",
            encoding="utf-8",
            delete=False,
        ) as handle:
            handle.write(combined)
            temp_path = Path(handle.name)
        try:
            failures += _run_checked(
                [lake_path, "env", "lean", str(temp_path)],
                cwd=LEAN_PROJECT_DIR,
                timeout=60,
                label=f"Mathlib bundle ({len(BUILTIN_SPECS)} Specs)",
            )
        except subprocess.TimeoutExpired:
            print(f"  ✗ Mathlib bundle ({len(BUILTIN_SPECS)} Specs)")
            print("Mathlib-Prüfung hat das Timeout (60s) überschritten.")
            failures += 1
        finally:
            temp_path.unlink(missing_ok=True)

    if failures:
        print(f"\n❌ Commit blockiert — {failures} Lean-Prüfung(en) fehlgeschlagen.\n")
        return 1

    print("  ✅ Alle Lean-Prüfungen bestanden — Commit erlaubt\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
