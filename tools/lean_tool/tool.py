"""
lean_tool — Formale Verifikation für kritische Algorithmen in Timus.

Tools:
  lean_get_builtin_specs   — gibt 3 eingebettete Lean 4 Spezifikationen zurück
  lean_check_proof         — prüft eine Lean 4 Spezifikation (Mathlib-fähig)
  lean_generate_spec       — generiert Lean 4 Spec via LLM (Fallback-Template)

Mathlib-Unterstützung:
  Lake-Projekt: /home/fatih-ubuntu/dev/lean_verify
  Specs mit "import Mathlib" werden automatisch via "lake env lean" geprüft.
  Specs ohne Import laufen mit bare "lean" (schneller).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from tools.tool_registry_v2 import ToolCategory as C
from tools.tool_registry_v2 import ToolParameter as P
from tools.tool_registry_v2 import tool

load_dotenv()
logger = logging.getLogger(__name__)

# elan PATH erweitern damit shutil.which("lean"/"lake") funktioniert
_ELAN_BIN = os.path.expanduser("~/.elan/bin")
if _ELAN_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _ELAN_BIN + ":" + os.environ.get("PATH", "")

# Lake-Projekt mit Mathlib
_LEAN_PROJECT_DIR = os.path.expanduser("~/dev/lean_verify")

# ---------------------------------------------------------------------------
# Eingebettete Lean 4 Specs — Mathlib-Version (Float/ℝ korrekt)
# ---------------------------------------------------------------------------

_BUILTIN_SPECS: dict[str, str] = {
    "progress_in_bounds": """\
import Mathlib

-- Invariante: 0 ≤ progress ≤ 1 wenn completed ≤ total und total > 0
-- Quelle: orchestration/goal_queue_manager.py:161
theorem progress_in_bounds (completed total : ℕ) (h : completed ≤ total) (ht : 0 < total) :
    (completed : ℝ) / (total : ℝ) ≤ 1 := by
  rw [div_le_one (by exact_mod_cast ht)]
  exact_mod_cast h
""",
    "keyword_bonus_cap": """\
import Mathlib

-- Invariante: min (x * 0.05) 0.3 ≤ 0.3  →  keyword_bonus niemals > 0.3
-- Quelle: tools/deep_research/tool.py:880
theorem keyword_bonus_cap (x : ℝ) :
    min (x * 0.05) 0.3 ≤ 0.3 :=
  min_le_right _ _
""",
    "arxiv_boundary": """\
import Mathlib

-- Invariante: relevance == threshold → akzeptiert (¬ relevance < threshold)
-- Quelle: tools/deep_research/trend_researcher.py:82
theorem arxiv_boundary (n : ℤ) : ¬ n < n :=
  lt_irrefl n
""",
}


# ---------------------------------------------------------------------------
# Tool 1: lean_get_builtin_specs
# ---------------------------------------------------------------------------

@tool(
    name="lean_get_builtin_specs",
    description=(
        "Gibt 3 eingebettete Lean 4 Spezifikationen für kritische Timus-Algorithmen zurück: "
        "progress_in_bounds, keyword_bonus_cap, arxiv_boundary. "
        "Alle mit 'import Mathlib' — laufen via lake env lean."
    ),
    parameters=[],
    capabilities=["formal_verification", "lean4"],
    category=C.CODE,
)
async def lean_get_builtin_specs() -> dict[str, Any]:
    return {
        "success": True,
        "count": len(_BUILTIN_SPECS),
        "mathlib": os.path.isdir(_LEAN_PROJECT_DIR),
        "specs": _BUILTIN_SPECS,
    }


# ---------------------------------------------------------------------------
# Tool 2: lean_check_proof
# ---------------------------------------------------------------------------

def _build_lean_cmd(lean_path: str, tmpfile: str, use_mathlib: bool) -> tuple[list[str], str | None]:
    """Gibt (cmd, cwd) zurück — lake env lean wenn Mathlib verfügbar."""
    lake_path = shutil.which("lake")
    if use_mathlib and lake_path and os.path.isdir(_LEAN_PROJECT_DIR):
        return [lake_path, "env", "lean", tmpfile], _LEAN_PROJECT_DIR
    return [lean_path, tmpfile], None


@tool(
    name="lean_check_proof",
    description=(
        "Prüft eine Lean 4 Spezifikation lokal. "
        "Specs mit 'import Mathlib' werden via 'lake env lean' im Mathlib-Projekt geprüft "
        "(Float/ℝ verfügbar). Specs ohne Import laufen mit bare 'lean' (schneller). "
        "Rückgabe enthält immer 'success' (bool) und 'installed' (bool)."
    ),
    parameters=[
        P("spec", "string", "Lean 4 Quellcode (theorem + proof)", required=True),
        P("algorithm_name", "string", "Bezeichnung des Algorithmus (für Logs)", required=False, default="unknown"),
    ],
    capabilities=["formal_verification", "lean4"],
    category=C.CODE,
)
async def lean_check_proof(spec: str, algorithm_name: str = "unknown") -> dict[str, Any]:
    lean_path = shutil.which("lean")

    if lean_path is None:
        logger.info("Lean 4 nicht installiert — Fallback-Antwort")
        return {
            "success": False,
            "installed": False,
            "algorithm": algorithm_name,
            "message": "Lean 4 ist nicht installiert.",
            "install_cmd": (
                "curl https://raw.githubusercontent.com/leanprover/elan/master/"
                "elan-init.sh -sSf | sh"
            ),
            "spec_preview": spec[:200],
        }

    use_mathlib = "import Mathlib" in spec
    # Mathlib-Proofs dürfen länger dauern (Typechecking der Imports)
    timeout = 120 if use_mathlib else 30

    tmpfile_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", delete=False, encoding="utf-8"
        ) as f:
            f.write(spec)
            tmpfile_path = f.name

        cmd, cwd = _build_lean_cmd(lean_path, tmpfile_path, use_mathlib)
        logger.info(f"lean_check_proof: {' '.join(cmd[:3])} {'(Mathlib)' if use_mathlib else '(Core)'}")

        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "success": proc.returncode == 0,
            "installed": True,
            "mathlib": use_mathlib,
            "algorithm": algorithm_name,
            "stdout": proc.stdout[:500],
            "stderr": proc.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "installed": True,
            "mathlib": use_mathlib,
            "algorithm": algorithm_name,
            "stdout": "",
            "stderr": f"Lean-Prüfung hat Timeout ({timeout}s) überschritten.",
        }
    finally:
        if tmpfile_path and os.path.exists(tmpfile_path):
            os.unlink(tmpfile_path)


# ---------------------------------------------------------------------------
# Tool 3: lean_generate_spec
# ---------------------------------------------------------------------------

_SPEC_FALLBACK_TEMPLATE = """\
import Mathlib

-- Lean 4 Spezifikation (generiert — sorry als Platzhalter)
-- Funktion: {function_description}
-- Invarianten: {invariants_str}
theorem generated_spec : True := by
  trivial
-- TODO: Ersetze durch konkrete theorem-Formulierung und Beweis.
-- Tipp: lean_check_proof(spec, name) prüft die Korrektheit via Mathlib.
"""

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_SPEC_MODEL = "deepseek/deepseek-v3"


@tool(
    name="lean_generate_spec",
    description=(
        "Generiert eine Lean 4 theorem-Spezifikation für eine Python-Funktion via LLM. "
        "Erwartet eine Funktionsbeschreibung und eine Liste von Invarianten. "
        "Verwendet 'import Mathlib' für Float/ℝ-Typen. "
        "Fallback-Template wenn kein OPENROUTER_API_KEY vorhanden. "
        "Rückgabe enthält immer 'lean_spec' (string)."
    ),
    parameters=[
        P("function_description", "string", "Beschreibung der Python-Funktion", required=True),
        P("invariants", "array", "Liste von Invarianten als Strings, z.B. ['0 <= p <= 1']", required=True),
    ],
    capabilities=["formal_verification", "lean4", "llm"],
    category=C.CODE,
)
async def lean_generate_spec(
    function_description: str,
    invariants: list[str],
) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    invariants_str = "; ".join(invariants) if invariants else "keine"

    if not api_key:
        logger.info("Kein OPENROUTER_API_KEY — Fallback-Template")
        spec = _SPEC_FALLBACK_TEMPLATE.format(
            function_description=function_description,
            invariants_str=invariants_str,
        )
        return {
            "success": True,
            "lean_spec": spec,
            "source": "fallback_template",
        }

    try:
        client = OpenAI(api_key=api_key, base_url=_OPENROUTER_BASE)
        prompt = (
            f"Schreibe eine Lean 4 theorem-Spezifikation mit 'import Mathlib' für:\n"
            f"Funktion: {function_description}\n"
            f"Invarianten: {invariants_str}\n"
            f"Ausgabe: NUR Lean-Code ohne Erklärungen. Beginne mit 'import Mathlib'."
        )
        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=_SPEC_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1,
            )
        )
        spec = response.choices[0].message.content or ""
        return {
            "success": True,
            "lean_spec": spec.strip(),
            "source": "llm",
            "model": _SPEC_MODEL,
        }
    except Exception as exc:
        logger.warning(f"LLM-Aufruf fehlgeschlagen: {exc} — Fallback")
        spec = _SPEC_FALLBACK_TEMPLATE.format(
            function_description=function_description,
            invariants_str=invariants_str,
        )
        return {
            "success": True,
            "lean_spec": spec,
            "source": "fallback_template",
            "error": str(exc),
        }
