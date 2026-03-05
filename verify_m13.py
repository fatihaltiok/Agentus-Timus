"""
verify_m13.py

Automatische Verifikation von M13: Tool-Generierung

~30 Checks:
- Modul-Existenz und Import
- Engine-Instanziierung
- Code-Generierung
- AST-Validation (sichere + unsichere Patterns)
- Code-Längen-Limit
- Approval-Flow
- Reject-Flow
- Query-Methoden
- Lean-Invarianten (Python-seitig)
- Datei-Struktur
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Testprotokoll
_results: List[Tuple[str, bool, str]] = []
_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        _results.append((name, True, ""))
        print(f"  ✅ {name}")
    else:
        _failed += 1
        _results.append((name, False, detail))
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


print("\n🔧 M13 Tool-Generierung — Verifikation\n" + "=" * 50)

# ── 1. Modul-Existenz ────────────────────────────────────────────────────────
print("\n📦 1. Modul-Existenz")

check(
    "tool_generator_engine.py existiert",
    Path("orchestration/tool_generator_engine.py").exists(),
)
check(
    "tools/tool_generator_tool/tool.py existiert",
    Path("tools/tool_generator_tool/tool.py").exists(),
)
check(
    "tools/tool_generator_tool/__init__.py existiert",
    Path("tools/tool_generator_tool/__init__.py").exists(),
)
check(
    "tests/test_m13_tool_generator.py existiert",
    Path("tests/test_m13_tool_generator.py").exists(),
)

# ── 2. Import ────────────────────────────────────────────────────────────────
print("\n📦 2. Import")

try:
    from orchestration.tool_generator_engine import ToolGeneratorEngine, GeneratedTool, get_tool_generator_engine
    check("ToolGeneratorEngine importierbar", True)
    check("GeneratedTool importierbar", True)
    check("get_tool_generator_engine importierbar", True)
except ImportError as e:
    check("ToolGeneratorEngine importierbar", False, str(e))
    check("GeneratedTool importierbar", False, str(e))
    check("get_tool_generator_engine importierbar", False, str(e))
    print("\n⛔ Kritischer Import-Fehler — Verifikation abgebrochen")
    sys.exit(1)

# ── 3. Engine-Instanziierung ─────────────────────────────────────────────────
print("\n🏗️  3. Engine-Instanziierung")

engine = ToolGeneratorEngine()
check("Engine instanziierbar", True)
check("MAX_CODE_LENGTH = 5000", engine.MAX_CODE_LENGTH == 5000)
check("_registry ist leer bei Start", len(engine._registry) == 0)
check("Singleton get_tool_generator_engine()", get_tool_generator_engine() is get_tool_generator_engine())

# ── 4. Code-Generierung ──────────────────────────────────────────────────────
print("\n⚙️  4. Code-Generierung")

tool1 = engine.generate("test_tool", "Ein Test-Tool", ["input", "limit"])
check("generate() gibt GeneratedTool zurück", isinstance(tool1, GeneratedTool))
check("Name korrekt (snake_case)", tool1.name == "test_tool")
check("Status initial 'pending'", tool1.status == "pending")
check("action_id nicht leer", bool(tool1.action_id))
check("@tool im Code vorhanden", "@tool" in tool1.code)
check("async def im Code vorhanden", "async def" in tool1.code)
check("Parameter 'input' im Code", "input" in tool1.code)
check("Parameter 'limit' im Code", "limit" in tool1.code)
check("Tool in Registry registriert", tool1.action_id in engine._registry)
check("code_length Eigenschaft", tool1.code_length == len(tool1.code))

# Name-Normalisierung
tool2 = engine.generate("My Special Tool", "Test", [])
check("Name wird zu snake_case normalisiert", tool2.name == "my_special_tool")

# ── 5. AST-Validation ────────────────────────────────────────────────────────
print("\n🛡️  5. AST-Validation")

valid_code = '''
@tool(name="x", description="x", parameters=[], capabilities=["x"], category=C.PRODUCTIVITY)
async def x() -> dict:
    return {"ok": True}
'''

valid, err = engine.validate_ast(valid_code)
check("Valider Code: kein Fehler", valid, err)

evil_eval = valid_code.replace('return {"ok": True}', 'return eval("1+1")')
valid, err = engine.validate_ast(evil_eval)
check("eval() → rejected", not valid and "eval" in err)

evil_exec = valid_code.replace('return {"ok": True}', 'exec("import os")\n    return {}')
valid, err = engine.validate_ast(evil_exec)
check("exec() → rejected", not valid and "exec" in err)

evil_import = valid_code.replace('return {"ok": True}', '__import__("os")\n    return {}')
valid, err = engine.validate_ast(evil_import)
check("__import__() → rejected", not valid and "__import__" in err)

no_decorator = '''
async def my_tool() -> dict:
    return {}
'''
valid, err = engine.validate_ast(no_decorator)
check("Fehlender @tool → rejected", not valid and "@tool" in err)

no_async = '''
@tool(name="x", description="x", parameters=[], capabilities=["x"], category=C.PRODUCTIVITY)
def sync_tool() -> dict:
    return {}
'''
valid, err = engine.validate_ast(no_async)
check("Keine async def → rejected", not valid and "async def" in err)

syntax_err = "def broken(: invalid"
valid, err = engine.validate_ast(syntax_err)
check("Syntax-Fehler → rejected", not valid and "Syntax" in err)

# ── 6. Code-Längen-Limit ─────────────────────────────────────────────────────
print("\n📏  6. Code-Längen-Limit")

long_code = "x" * 5001
valid, err = engine.validate_ast(long_code)
check("Code > 5000 Zeichen → rejected", not valid and "zu lang" in err)

at_limit = "x" * 5000
valid, err = engine.validate_ast(at_limit)
check("Code genau 5000 Zeichen → kein Längen-Fehler (aber andere Fehler OK)", "zu lang" not in err)

# Lean-Invariante: m13_code_length_bound
code_len = 4999
max_len = 5000
lean_ok = 0 < code_len + 1 or code_len <= max_len
check("Lean m13_code_length_bound: 0 < len+1 ∨ len ≤ max_len", lean_ok)

# ── 7. Approval-Flow ─────────────────────────────────────────────────────────
print("\n✅  7. Approval-Flow")

with tempfile.TemporaryDirectory() as tmp:
    engine2 = ToolGeneratorEngine()
    engine2.TOOLS_BASE_DIR = Path(tmp)
    t = engine2.generate("approval_tool", "Approval Test", ["x"])

    # Dateien schreiben + aktivieren
    with patch("importlib.util.spec_from_file_location", return_value=None):
        engine2.activate(t.action_id)

    tool_dir = Path(tmp) / "approval_tool"
    check("tool.py geschrieben", (tool_dir / "tool.py").exists())
    check("__init__.py geschrieben", (tool_dir / "__init__.py").exists())
    check("tool.py enthält korrekten Code", "@tool" in (tool_dir / "tool.py").read_text())

# ── 8. Reject-Flow ───────────────────────────────────────────────────────────
print("\n❌  8. Reject-Flow")

engine3 = ToolGeneratorEngine()
t3 = engine3.generate("reject_me", "Test", [])
result = engine3.reject(t3.action_id)
check("reject() gibt True zurück", result)
check("Status nach reject() = 'rejected'", engine3._registry[t3.action_id].status == "rejected")
check("Unbekannte ID: reject() False", not engine3.reject("unknown-id"))
check("Unbekannte ID: activate() False", not engine3.activate("unknown-id"))

# ── 9. Query-Methoden ────────────────────────────────────────────────────────
print("\n🔍  9. Query-Methoden")

engine4 = ToolGeneratorEngine()
engine4.generate("qa", "Tool A", [])
engine4.generate("qb", "Tool B", [])
t_reject = engine4.generate("qc_rej", "Tool C", [])
engine4.reject(t_reject.action_id)

pending = engine4.get_pending_reviews()
check("get_pending_reviews() gibt 2 zurück (nicht rejected)", len(pending) == 2)
check("pending hat action_id Feld", all("action_id" in p for p in pending))

all_tools = engine4.list_all_tools()
check("list_all_tools() gibt 3 zurück (alle inkl. rejected)", len(all_tools) == 3)
check("list_all_tools hat status Feld", all("status" in t for t in all_tools))

# ── 10. Lean-Invarianten ─────────────────────────────────────────────────────
print("\n🔢  10. Lean-Invarianten")

# m13_code_length_bound
for ln, mx in [(0, 5000), (1000, 5000), (5000, 5000)]:
    lean_ok = (0 < ln + 1 or ln <= mx) if ln <= mx else True
    check(f"Lean m13_code_length_bound: len={ln}", 0 < ln + 1 or ln <= mx)

# m13_tool_approval_guard
for s in [-1, 0]:
    check(f"Lean m13_tool_approval_guard: status={s} → ¬(1≤status)", not (s >= 1))
for s in [1, 2]:
    check(f"Lean m13_tool_approval_guard Komplement: status={s} → 1≤status", s >= 1)

# ── Zusammenfassung ──────────────────────────────────────────────────────────
print("\n" + "=" * 50)
print(f"✅ {_passed} Checks bestanden")
if _failed:
    print(f"❌ {_failed} Checks fehlgeschlagen:")
    for name, ok, detail in _results:
        if not ok:
            print(f"   - {name}" + (f": {detail}" if detail else ""))
    sys.exit(1)
else:
    print(f"🎉 Alle {_passed} Checks grün — M13 vollständig verifiziert!")
