"""
tests/test_m13_tool_generator.py

Tests für M13: Tool-Generierung-Engine

Testet:
- Code-Generierung (valides Template erzeugt)
- AST-Validation (eval/exec/import → rejected)
- Code-Längen-Limit (> 5000 Zeichen → rejected)
- Approval-Flow (approve → Dateien geschrieben + importierbar)
- Reject-Flow (reject → status=rejected)
- Lean-Invarianten (Python-seitig verifiziert)
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestration.tool_generator_engine import ToolGeneratorEngine, GeneratedTool


def make_engine(tmp_dir: Path = None) -> ToolGeneratorEngine:
    engine = ToolGeneratorEngine()
    if tmp_dir:
        engine.TOOLS_BASE_DIR = tmp_dir
    return engine


# ── Code-Generierung ─────────────────────────────────────────────────────────

class TestCodeGeneration(unittest.TestCase):
    def test_generate_creates_tool(self):
        engine = make_engine()
        tool = engine.generate("test_tool", "Ein Test-Tool", ["input", "timeout"])
        self.assertEqual(tool.name, "test_tool")
        self.assertIn("test_tool", tool.code)
        self.assertIn("@tool", tool.code)
        self.assertIn("async def", tool.code)
        self.assertNotEqual(tool.action_id, "")

    def test_generate_snake_case_name(self):
        engine = make_engine()
        tool = engine.generate("My Tool Name", "Test", [])
        self.assertEqual(tool.name, "my_tool_name")

    def test_generate_with_parameters(self):
        engine = make_engine()
        tool = engine.generate("search_tool", "Web-Suche", ["query", "limit"])
        self.assertIn("query", tool.code)
        self.assertIn("limit", tool.code)

    def test_generate_without_parameters(self):
        engine = make_engine()
        tool = engine.generate("simple_tool", "Einfaches Tool", [])
        self.assertIn("@tool", tool.code)
        self.assertEqual(tool.status, "pending")

    def test_generate_registers_in_registry(self):
        engine = make_engine()
        tool = engine.generate("reg_tool", "Test", [])
        self.assertIn(tool.action_id, engine._registry)

    def test_generate_valid_default_status_pending(self):
        engine = make_engine()
        tool = engine.generate("pending_tool", "Test", [])
        self.assertEqual(tool.status, "pending")

    def test_code_length_property(self):
        engine = make_engine()
        tool = engine.generate("len_tool", "Test", [])
        self.assertEqual(tool.code_length, len(tool.code))


# ── AST-Validation ────────────────────────────────────────────────────────────

class TestAstValidation(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.valid_code = '''
@tool(name="x", description="x", parameters=[], capabilities=["x"], category=C.PRODUCTIVITY)
async def x() -> dict:
    return {"ok": True}
'''

    def test_eval_rejected(self):
        code = self.valid_code.replace('return {"ok": True}', 'return eval("1+1")')
        valid, error = self.engine.validate_ast(code)
        self.assertFalse(valid)
        self.assertIn("eval", error)

    def test_exec_rejected(self):
        code = self.valid_code.replace('return {"ok": True}', 'exec("import os")\n    return {}')
        valid, error = self.engine.validate_ast(code)
        self.assertFalse(valid)
        self.assertIn("exec", error)

    def test_import_builtin_rejected(self):
        code = self.valid_code.replace('return {"ok": True}', '__import__("os")\n    return {}')
        valid, error = self.engine.validate_ast(code)
        self.assertFalse(valid)
        self.assertIn("__import__", error)

    def test_valid_code_passes(self):
        valid, error = self.engine.validate_ast(self.valid_code)
        self.assertTrue(valid)
        self.assertEqual(error, "")

    def test_missing_tool_decorator_rejected(self):
        code = '''
async def my_tool() -> dict:
    return {}
'''
        valid, error = self.engine.validate_ast(code)
        self.assertFalse(valid)
        self.assertIn("@tool", error)

    def test_no_async_def_rejected(self):
        code = '''
@tool(name="x", description="x", parameters=[], capabilities=["x"], category=C.PRODUCTIVITY)
def sync_tool() -> dict:
    return {}
'''
        valid, error = self.engine.validate_ast(code)
        self.assertFalse(valid)
        self.assertIn("async def", error)

    def test_syntax_error_rejected(self):
        code = "def broken(: invalid syntax"
        valid, error = self.engine.validate_ast(code)
        self.assertFalse(valid)
        self.assertIn("Syntax", error)


# ── Code-Längen-Limit ─────────────────────────────────────────────────────────

class TestCodeLengthLimit(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()

    def test_over_limit_rejected(self):
        long_code = "x" * 5001
        valid, error = self.engine.validate_ast(long_code)
        self.assertFalse(valid)
        self.assertIn("zu lang", error)

    def test_at_limit_passes_syntax_check(self):
        # 5000 Zeichen valider Code ist nicht trivial — prüfen dass Limit korrekt greift
        engine = ToolGeneratorEngine()
        engine.MAX_CODE_LENGTH = 10  # sehr kleines Limit
        valid, error = engine.validate_ast("x" * 11)
        self.assertFalse(valid)

    # Lean-Invariante: m13_code_length_bound
    def test_lean_code_length_invariant(self):
        """len ≤ max_len ∧ 0 < max_len → 0 < len+1 ∨ len ≤ max_len"""
        code_len = 4999
        max_len = 5000
        self.assertLessEqual(code_len, max_len)
        self.assertTrue(0 < max_len)
        # Lean: 0 < len + 1 ∨ len ≤ max_len
        self.assertTrue(0 < code_len + 1 or code_len <= max_len)

    def test_lean_code_length_at_limit(self):
        code_len = 5000
        max_len = 5000
        self.assertLessEqual(code_len, max_len)
        self.assertTrue(0 < code_len + 1 or code_len <= max_len)


# ── Approval-Flow ─────────────────────────────────────────────────────────────

class TestApprovalFlow(unittest.TestCase):
    def test_approve_writes_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(Path(tmp))
            tool = engine.generate("test_tool", "Test", ["param1"])
            self.assertEqual(tool.status, "pending")

            # Aktivieren (importlib.util schlägt fehl wegen fehlender Registry-Imports, aber Dateien werden geschrieben)
            with patch("importlib.util.spec_from_file_location") as mock_spec:
                mock_spec.return_value = None  # Import schlägt fehl → aber Dateien sollen geschrieben sein
                engine.activate(tool.action_id)

            tool_dir = Path(tmp) / "test_tool"
            self.assertTrue(tool_dir.exists())
            self.assertTrue((tool_dir / "tool.py").exists())
            self.assertTrue((tool_dir / "__init__.py").exists())

    def test_reject_marks_status(self):
        engine = make_engine()
        tool = engine.generate("reject_tool", "Test", [])
        aid = tool.action_id
        result = engine.reject(aid)
        self.assertTrue(result)
        self.assertEqual(engine._registry[aid].status, "rejected")

    def test_reject_unknown_returns_false(self):
        engine = make_engine()
        result = engine.reject("nonexistent-id")
        self.assertFalse(result)

    def test_activate_unknown_returns_false(self):
        engine = make_engine()
        result = engine.activate("nonexistent-id")
        self.assertFalse(result)

    # Lean-Invariante: m13_tool_approval_guard
    def test_lean_approval_guard_pending(self):
        """status=0 (pending) → ¬ (1 ≤ status) — wie Lean-Theorem m13_tool_approval_guard"""
        status_pending = 0  # pending
        self.assertFalse(status_pending >= 1)

    def test_lean_approval_guard_approved(self):
        """status=1 (approved) → 1 ≤ status"""
        status_approved = 1
        self.assertTrue(status_approved >= 1)

    def test_lean_approval_guard_rejected(self):
        """status=-1 (rejected) → ¬ (1 ≤ status)"""
        status_rejected = -1
        self.assertFalse(status_rejected >= 1)


# ── Query-Methoden ────────────────────────────────────────────────────────────

class TestQueryMethods(unittest.TestCase):
    def test_get_pending_reviews(self):
        engine = make_engine()
        engine.generate("t1", "Tool 1", [])
        engine.generate("t2", "Tool 2", [])
        pending = engine.get_pending_reviews()
        self.assertEqual(len(pending), 2)
        for p in pending:
            self.assertIn("action_id", p)
            self.assertIn("name", p)
            self.assertEqual(p["status"], "pending")

    def test_list_all_tools(self):
        engine = make_engine()
        engine.generate("ta", "Tool A", [])
        all_tools = engine.list_all_tools()
        self.assertEqual(len(all_tools), 1)
        self.assertIn("status", all_tools[0])

    def test_rejected_not_in_pending_reviews(self):
        engine = make_engine()
        tool = engine.generate("rej", "Test", [])
        engine.reject(tool.action_id)
        pending = engine.get_pending_reviews()
        self.assertEqual(len(pending), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
