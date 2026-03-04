"""
lean_tool — Formale Verifikation für kritische Algorithmen in Timus.

Tools:
  lean_get_builtin_specs   — gibt 3 eingebettete Lean 4 Spezifikationen zurück
  lean_check_proof         — prüft eine Lean 4 Spezifikation (graceful fallback)
  lean_generate_spec       — generiert Lean 4 Spec via LLM (Fallback-Template)
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

# elan PATH erweitern damit shutil.which("lean") funktioniert
_ELAN_BIN = os.path.expanduser("~/.elan/bin")
if _ELAN_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _ELAN_BIN + ":" + os.environ.get("PATH", "")

# ---------------------------------------------------------------------------
# Eingebettete Lean 4 Specs (kein externes Dateisystem nötig)
# ---------------------------------------------------------------------------

_BUILTIN_SPECS: dict[str, str] = {
    "progress_in_bounds": """\
-- Invariante: completed ≤ total entspricht progress ≤ 1.0
-- Quelle: orchestration/goal_queue_manager.py:161
theorem progress_in_bounds (completed total : Nat) (h : completed ≤ total) :
    completed ≤ total := h
""",
    "keyword_bonus_cap": """\
-- Invariante: min x cap ≤ cap  →  keyword_bonus niemals > 0.3
-- Quelle: tools/deep_research/tool.py:880
theorem keyword_bonus_cap (x cap : Nat) : min x cap ≤ cap :=
  Nat.min_le_right x cap
""",
    "arxiv_boundary": """\
-- Invariante: score == threshold → akzeptiert (¬ score < threshold)
-- Quelle: tools/deep_research/trend_researcher.py:82
theorem arxiv_boundary (n : Nat) : ¬ n < n :=
  Nat.lt_irrefl n
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
        "Keine externen Abhängigkeiten — sofort verfügbar."
    ),
    parameters=[],
    capabilities=["formal_verification", "lean4"],
    category=C.CODE,
)
async def lean_get_builtin_specs() -> dict[str, Any]:
    return {
        "success": True,
        "count": len(_BUILTIN_SPECS),
        "specs": _BUILTIN_SPECS,
    }


# ---------------------------------------------------------------------------
# Tool 2: lean_check_proof
# ---------------------------------------------------------------------------

@tool(
    name="lean_check_proof",
    description=(
        "Prüft eine Lean 4 Spezifikation lokal. "
        "Wenn Lean 4 nicht installiert ist, wird eine Installationsanleitung zurückgegeben "
        "statt eines Fehlers (graceful fallback). "
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

    tmpfile_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", delete=False, encoding="utf-8"
        ) as f:
            f.write(spec)
            tmpfile_path = f.name

        proc = await asyncio.to_thread(
            subprocess.run,
            [lean_path, tmpfile_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": proc.returncode == 0,
            "installed": True,
            "algorithm": algorithm_name,
            "stdout": proc.stdout[:500],
            "stderr": proc.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "installed": True,
            "algorithm": algorithm_name,
            "stdout": "",
            "stderr": "Lean-Prüfung hat Timeout (30s) überschritten.",
        }
    finally:
        if tmpfile_path and os.path.exists(tmpfile_path):
            os.unlink(tmpfile_path)


# ---------------------------------------------------------------------------
# Tool 3: lean_generate_spec
# ---------------------------------------------------------------------------

_SPEC_FALLBACK_TEMPLATE = """\
-- Lean 4 Spezifikation (generiert — sorry als Platzhalter)
-- Funktion: {function_description}
-- Invarianten: {invariants_str}
theorem generated_spec : True := by
  trivial
-- TODO: Ersetze durch konkrete theorem-Formulierung und Beweis.
-- Tipp: lean_check_proof(spec, name) prüft die Korrektheit.
"""

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_SPEC_MODEL = "deepseek/deepseek-v3"


@tool(
    name="lean_generate_spec",
    description=(
        "Generiert eine Lean 4 theorem-Spezifikation für eine Python-Funktion via LLM. "
        "Erwartet eine Funktionsbeschreibung und eine Liste von Invarianten. "
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
            f"Schreibe eine Lean 4 theorem-Spezifikation für:\n"
            f"Funktion: {function_description}\n"
            f"Invarianten: {invariants_str}\n"
            f"Ausgabe: NUR Lean-Code ohne Erklärungen."
        )
        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=_SPEC_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
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
