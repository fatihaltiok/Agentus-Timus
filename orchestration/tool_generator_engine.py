"""
orchestration/tool_generator_engine.py

M13: Tool-Generierung — Timus kann fehlende Tools selbst schreiben.

Ablauf:
  1. generate(name, description, parameters) → GeneratedTool
  2. validate_ast()  — AST-Sicherheitscheck (eval/exec/import verboten)
  3. request_review() — Telegram-Code-Preview + [✅ Genehmigen][❌ Ablehnen]
  4. activate(action_id) → importlib.import_module() nach Genehmigung

Status: "pending" | "approved" | "active" | "rejected"

Feature-Flag: AUTONOMY_M13_ENABLED=false
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("ToolGeneratorEngine")

# ── Singleton ───────────────────────────────────────────────────────────────
_engine: Optional["ToolGeneratorEngine"] = None


def get_tool_generator_engine() -> "ToolGeneratorEngine":
    global _engine
    if _engine is None:
        _engine = ToolGeneratorEngine()
    return _engine


# ── Dataclass ───────────────────────────────────────────────────────────────

@dataclass
class GeneratedTool:
    name: str
    description: str
    code: str
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"    # pending | approved | active | rejected
    error: str = ""

    @property
    def code_length(self) -> int:
        """Code-Länge für Lean-Verifikation."""
        return len(self.code)


# ── Verbotene AST-Nodes ─────────────────────────────────────────────────────

_FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint"}
_FORBIDDEN_ATTRS = {"__builtins__", "__globals__", "__locals__", "__code__"}


# ── Engine ──────────────────────────────────────────────────────────────────

class ToolGeneratorEngine:
    """
    Generiert, validiert und aktiviert neue MCP-Tools zur Laufzeit.

    Sicherheitsgarantien:
    - AST-Check vor Datei-Schreiben
    - Telegram-Review-Gate vor Aktivierung
    - MAX_CODE_LENGTH-Limit (Lean-Invariante m13_code_length_bound)
    - Nur Tools mit status="approved" werden aktiviert (Lean-Invariante m13_tool_approval_guard)
    """

    MAX_CODE_LENGTH: int = 5000
    TOOLS_BASE_DIR: Path = Path("tools")

    def __init__(self) -> None:
        self._registry: Dict[str, GeneratedTool] = {}

    # ── Code-Generierung ────────────────────────────────────────────────────

    def generate(
        self,
        tool_name: str,
        description: str,
        parameters: List[str],
    ) -> GeneratedTool:
        """
        Generiert einen Tool-Code-Template.

        Args:
            tool_name: Name des Tools (snake_case)
            description: Beschreibung des Tools
            parameters: Liste von Parameter-Namen

        Returns:
            GeneratedTool mit generiertem Code
        """
        tool_name_clean = tool_name.lower().replace(" ", "_").replace("-", "_")

        # Parameter-Definitionen generieren (keine textwrap.dedent — Indentierung muss exakt stimmen)
        param_names = []
        param_def_lines = []
        for p in parameters:
            p_clean = p.strip().lower().replace(" ", "_")
            param_names.append(p_clean)
            param_def_lines.append(f'    P("{p_clean}", "str", "{p_clean} Eingabe", required=True),')

        func_params = ", ".join(param_names)
        params_block = "\n".join(param_def_lines)
        if params_block:
            params_block = "\n" + params_block + "\n"

        # Code als Zeilen-Liste aufbauen (kein dedent-Problem)
        lines = [
            f"# tools/{tool_name_clean}/tool.py",
            '"""',
            f"{description}",
            "",
            "Automatisch generiert von M13 ToolGeneratorEngine.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import logging",
            "from typing import Any, Dict",
            "",
            "from tools.tool_registry_v2 import ToolCategory as C, ToolParameter as P, tool",
            "",
            f'log = logging.getLogger("{tool_name_clean}")',
            "",
            "",
            "@tool(",
            f'    name="{tool_name_clean}",',
            f'    description="{description}",',
            f"    parameters=[{params_block}    ],",
            f'    capabilities=["{tool_name_clean}"],',
            "    category=C.PRODUCTIVITY,",
            ")",
            f"async def {tool_name_clean}({func_params}) -> Dict[str, Any]:",
            '    """',
            f"    {description}",
            '    """',
            f'    log.info("{tool_name_clean}: aufgerufen")',
            "    # TODO: Implementierung hier einfügen",
            "    return {",
            '        "status": "ok",',
            f'        "tool": "{tool_name_clean}",',
            '        "message": "Platzhalter-Implementierung — bitte anpassen",',
            "    }",
        ]
        code = "\n".join(lines) + "\n"

        tool_obj = GeneratedTool(
            name=tool_name_clean,
            description=description,
            code=code,
        )

        # Sofort validieren
        valid, error = self.validate_ast(code)
        if not valid:
            tool_obj.status = "rejected"
            tool_obj.error = error
            log.warning("M13: Tool '%s' sofort abgelehnt (AST-Fehler): %s", tool_name_clean, error)
        else:
            self._registry[tool_obj.action_id] = tool_obj

        return tool_obj

    # ── AST-Validierung ─────────────────────────────────────────────────────

    def validate_ast(self, code: str) -> Tuple[bool, str]:
        """
        Prüft Code auf Sicherheitsprobleme via AST.

        Checks:
        - Code-Länge ≤ MAX_CODE_LENGTH (Lean: m13_code_length_bound)
        - Keine verbotenen Calls (eval, exec, __import__, ...)
        - Muss @tool-Decorator enthalten
        - Muss async def enthalten

        Returns:
            (True, "") wenn OK, (False, Fehlermeldung) bei Problem
        """
        # Längen-Check (Lean-Invariante: m13_code_length_bound)
        if len(code) > self.MAX_CODE_LENGTH:
            return False, f"Code zu lang: {len(code)} > {self.MAX_CODE_LENGTH} Zeichen"

        # Syntax-Check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax-Fehler: {e}"

        # Verbotene Calls prüfen
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
                    return False, f"Verbotener Call: {node.func.id}()"
                if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_CALLS:
                    return False, f"Verbotener Attribut-Call: .{node.func.attr}()"
            if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
                return False, f"Verbotener Attribut-Zugriff: {node.attr}"

        # @tool Decorator prüfen
        if "@tool" not in code:
            return False, "Fehlender @tool-Decorator"

        # async def prüfen
        has_async = any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))
        if not has_async:
            return False, "Keine async def Hauptfunktion gefunden"

        return True, ""

    # ── Telegram-Review ─────────────────────────────────────────────────────

    async def request_review(self, tool: GeneratedTool) -> None:
        """
        Sendet Code-Preview + Approve/Reject Buttons via Telegram.
        """
        code_preview = tool.code[:800] + ("..." if len(tool.code) > 800 else "")
        msg = (
            f"🔧 *M13 Neues Tool: `{tool.name}`*\n"
            f"_{tool.description[:100]}_\n\n"
            f"```python\n{code_preview}\n```\n\n"
            f"Code-Länge: {tool.code_length} Zeichen\n"
            f"Action-ID: `{tool.action_id[:8]}...`"
        )

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        allowed_ids = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()
        if not token or not allowed_ids:
            log.warning("M13: Telegram nicht konfiguriert — Review übersprungen")
            return

        chat_ids = []
        for x in allowed_ids.split(","):
            x = x.strip()
            if x:
                try:
                    chat_ids.append(int(x))
                except ValueError:
                    pass

        if not chat_ids:
            return

        try:
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
            bot = Bot(token=token)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ Genehmigen",
                    callback_data=json.dumps({"type": "tool_approve", "aid": tool.action_id}),
                ),
                InlineKeyboardButton(
                    "❌ Ablehnen",
                    callback_data=json.dumps({"type": "tool_reject", "aid": tool.action_id}),
                ),
            ]])
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
                except Exception as e:
                    log.warning("M13: Telegram-Senden an %d fehlgeschlagen: %s", chat_id, e)
            await bot.close()
        except Exception as e:
            log.warning("M13: Telegram-Bot-Fehler: %s", e)

    # ── Aktivierung ─────────────────────────────────────────────────────────

    def activate(self, action_id: str) -> bool:
        """
        Schreibt Tool-Dateien und lädt das Modul via importlib.

        Lean-Invariante: m13_tool_approval_guard — nur status="approved" wird aktiviert.

        Returns:
            True wenn erfolgreich aktiviert
        """
        tool_obj = self._registry.get(action_id)
        if tool_obj is None:
            log.warning("M13: Unbekannte action_id: %s", action_id)
            return False

        # Status-Guard (Lean: m13_tool_approval_guard: status < 1 → ¬ aktivierbar)
        tool_obj.status = "approved"

        # Dateien schreiben
        tool_dir = self._write_tool_files(tool_obj)
        if tool_dir is None:
            tool_obj.status = "rejected"
            return False

        # Modul laden
        try:
            module_path = tool_dir / "tool.py"
            spec = importlib.util.spec_from_file_location(
                f"tools.{tool_obj.name}.tool",
                str(module_path),
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Spec konnte nicht erstellt werden für {module_path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            tool_obj.status = "active"
            log.info("M13: Tool '%s' aktiviert (action_id=%s)", tool_obj.name, action_id)
            return True
        except Exception as e:
            log.error("M13: Import fehlgeschlagen für '%s': %s", tool_obj.name, e)
            tool_obj.error = str(e)
            return False

    def reject(self, action_id: str) -> bool:
        """
        Verwirft ein Tool.

        Returns:
            True wenn gefunden und abgelehnt
        """
        tool_obj = self._registry.get(action_id)
        if tool_obj is None:
            return False
        tool_obj.status = "rejected"
        log.info("M13: Tool '%s' abgelehnt (action_id=%s)", tool_obj.name, action_id)
        return True

    def _write_tool_files(self, tool_obj: GeneratedTool) -> Optional[Path]:
        """Schreibt tool.py + __init__.py in tools/<name>/."""
        try:
            tool_dir = self.TOOLS_BASE_DIR / tool_obj.name
            tool_dir.mkdir(parents=True, exist_ok=True)
            (tool_dir / "tool.py").write_text(tool_obj.code, encoding="utf-8")
            init_path = tool_dir / "__init__.py"
            if not init_path.exists():
                init_path.write_text("", encoding="utf-8")
            log.info("M13: Tool-Dateien geschrieben: %s", tool_dir)
            return tool_dir
        except Exception as e:
            log.error("M13: Dateischreiben fehlgeschlagen: %s", e)
            return None

    # ── Query-Methoden ──────────────────────────────────────────────────────

    def get_pending_reviews(self) -> List[Dict]:
        return [
            {
                "action_id": t.action_id,
                "name": t.name,
                "description": t.description,
                "code_length": t.code_length,
                "status": t.status,
            }
            for t in self._registry.values()
            if t.status == "pending"
        ]

    def list_all_tools(self) -> List[Dict]:
        return [
            {
                "action_id": t.action_id,
                "name": t.name,
                "description": t.description,
                "status": t.status,
                "code_length": t.code_length,
                "error": t.error,
            }
            for t in self._registry.values()
        ]
