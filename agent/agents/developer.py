"""
DeveloperAgent — Code schreiben, Dateien lesen/ändern, Skripte erstellen.

Erweiterungen gegenüber BaseAgent:
  - Kontext: Git-Status, letzte Commits, geänderte Dateien, offene Dev-Tasks
  - max_iterations=15→20 für mehrstufige Code-Workflows
  - _build_dev_context(): scannt git-Status, letzte Commits, Projektstruktur
  - Timus-Ökosystem-Wissen: Tool-Struktur, BaseAgent-Pattern, Pfade
  - Mercury Edit via apply_code_edit für präzise Änderungen an bestehenden Dateien
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from agent.base_agent import BaseAgent
from agent.prompts import DEVELOPER_SYSTEM_PROMPT

log = logging.getLogger("DeveloperAgent")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Schlüsselwörter die auf numerische Invarianten hinweisen → Lean-Spec empfehlen
_LEAN_TRIGGER: frozenset[str] = frozenset({
    "score", "rate", "progress", "confidence", "clamp", "threshold",
    "percent", "ratio", "bounds", "invariant", "average", "avg",
    "min(", "max(", "/ total", "/ n", "between 0", "between 1",
    "success_rate", "duration_ms", "ttl", "gap_minutes",
})

_LEAN_HINT = (
    "\n\n## LEAN 4 HINWEIS (automatisch erkannt)\n"
    "Dieser Task enthält numerische Invarianten (Score/Rate/Bounds/Clamp).\n"
    "Nach dem Schreiben des Codes: `lean_generate_spec` aufrufen und die Invariante\n"
    "als Lean 4 Theorem dokumentieren. Beispiel:\n"
    "  lean_generate_spec('Beschreibung der Invariante', ['0 ≤ result ≤ 1'])\n"
)


def _needs_lean_hint(task: str) -> bool:
    t = task.lower()
    return any(kw in t for kw in _LEAN_TRIGGER)


class DeveloperAgent(BaseAgent):
    """
    Code-Spezialist von Timus (mercury-coder-small).

    Schreibt, liest und modifiziert Code, erstellt Skripte und Tools.
    Lädt vor jedem Task den aktuellen Entwicklungs-Kontext:
    Git-Status, letzte Commits, geänderte Dateien, offene Dev-Tasks.
    """

    def __init__(self, tools_description_string: str) -> None:
        super().__init__(
            DEVELOPER_SYSTEM_PROMPT,
            tools_description_string,
            max_iterations=20,
            agent_type="developer",
        )

    # ------------------------------------------------------------------
    # Erweiterter run()-Einstieg: Entwicklungs-Kontext injizieren
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        """Reichert den Task mit Git-Status und Projektkontext an."""
        context = await self._build_dev_context()
        lean_hint = _LEAN_HINT if _needs_lean_hint(task) else ""
        if lean_hint:
            log.info("DeveloperAgent | Lean-Hint injiziert (numerische Invariante erkannt)")
        return await super().run(task + "\n\n" + context + lean_hint)

    # ------------------------------------------------------------------
    # Entwicklungs-Kontext aufbauen
    # ------------------------------------------------------------------

    async def _build_dev_context(self) -> str:
        """
        Erstellt Kontext für den Developer-Agent:
        - Git-Branch und geänderte Dateien
        - Letzte 3 Commits (Hash + Message)
        - Projektstruktur (Kernpfade)
        - Offene Developer-Tasks
        - Aktuelle Zeit
        """
        lines: list[str] = ["# ENTWICKLUNGS-KONTEXT (automatisch geladen)"]

        # 1. Git-Status
        git_status = await asyncio.to_thread(self._get_git_status)
        if git_status:
            lines.append(git_status)

        # 2. Letzte Commits
        recent_commits = await asyncio.to_thread(self._get_recent_commits)
        if recent_commits:
            lines.append(f"Letzte Commits: {recent_commits}")

        # 3. Kernpfade des Projekts
        lines.append(
            f"Projektpfad: {_PROJECT_ROOT} | "
            "Agenten: agent/agents/ | Tools: tools/ | "
            "Orchestration: orchestration/ | Memory: memory/ | "
            "Server: server/ | Tests: tests/"
        )
        lines.append(
            "Bestehende Dateien bevorzugt mit apply_code_edit anpassen; "
            "write_file primär für neue Dateien oder vollständige Replacement-Fälle."
        )

        # 4. Offene Developer-Tasks
        pending = await asyncio.to_thread(self._get_pending_dev_tasks)
        if pending:
            lines.append(f"Offene Dev-Tasks: {pending}")

        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    def _get_git_status(self) -> str:
        """Gibt den aktuellen Git-Branch und die Anzahl geänderter Dateien zurück."""
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=5, cwd=_PROJECT_ROOT,
            ).stdout.strip()

            # Geänderte Dateien (nur .py, keine __pycache__)
            diff_out = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=_PROJECT_ROOT,
            ).stdout.strip()

            changed_files = [
                f for f in diff_out.splitlines()
                if f.endswith(".py") and "__pycache__" not in f
            ] if diff_out else []

            if changed_files:
                preview = ", ".join(changed_files[:4])
                suffix = f" (+{len(changed_files) - 4} weitere)" if len(changed_files) > 4 else ""
                return f"Git-Branch: {branch} | Geändert: {preview}{suffix}"
            return f"Git-Branch: {branch} | Keine ungestagten Änderungen"

        except Exception as exc:
            log.debug("Git-Status nicht abrufbar: %s", exc)
            return ""

    def _get_recent_commits(self, n: int = 3) -> str:
        """Gibt die letzten n Commit-Hashes und -Messages zurück."""
        try:
            result = subprocess.run(
                ["git", "log", f"--{n}", "--oneline", "--no-decorate"],
                capture_output=True, text=True, timeout=5, cwd=_PROJECT_ROOT,
            )
            lines = result.stdout.strip().splitlines()
            return " | ".join(lines[:n]) if lines else ""
        except Exception as exc:
            log.debug("Git-Log nicht abrufbar: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # 3b: Auto-Test nach Code-Generierung (Phase 3)
    # ------------------------------------------------------------------

    MAX_TEST_ITERATIONS = 3  # Lean: developer_test_attempts_bound

    def _find_test_file(self, changed_file: str) -> str:
        """
        Leitet Test-Datei aus Quell-Pfad ab.
        Pattern: tools/X/tool.py → tests/test_X*.py, tests/test_X.py
        """
        path = Path(changed_file)
        stem = path.stem  # z.B. "tool" oder "engine"
        parent_name = path.parent.name  # z.B. "email_tool" oder "autonomy_scorecard"

        candidates = [
            _PROJECT_ROOT / "tests" / f"test_{parent_name}.py",
            _PROJECT_ROOT / "tests" / f"test_{parent_name}s.py",
            _PROJECT_ROOT / "tests" / f"test_{stem}.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return ""

    def _auto_run_tests(self, changed_files: list) -> dict:
        """
        Führt Tests für geänderte Dateien aus.
        Lean Th.47: attempts ≤ MAX_TEST_ITERATIONS → attempts < MAX_TEST_ITERATIONS + 1

        Args:
            changed_files: Liste geänderter Dateipfade
        Returns:
            {"status": "passed"|"failed"|"skipped", "test_file": str, "output": str}
        """
        for attempt in range(self.MAX_TEST_ITERATIONS):
            for file in changed_files:
                test_file = self._find_test_file(file)
                if not test_file:
                    continue

                try:
                    result = subprocess.run(
                        ["python", "-m", "pytest", test_file, "-x", "--timeout=30", "-q"],
                        capture_output=True, text=True, timeout=60, cwd=_PROJECT_ROOT,
                    )
                    status = "passed" if result.returncode == 0 else "failed"
                    output = (result.stdout + result.stderr)[-500:]
                    log.info(
                        "Auto-Test [%s/%s]: %s → %s",
                        attempt + 1, self.MAX_TEST_ITERATIONS, Path(test_file).name, status,
                    )

                    # Ergebnis im Blackboard speichern
                    try:
                        from memory.agent_blackboard import get_blackboard
                        get_blackboard().write(
                            agent="developer",
                            topic="test_result",
                            key=file,
                            value=f"{status}: {output[:200]}",
                        )
                    except Exception:
                        pass

                    return {"status": status, "test_file": test_file, "output": output, "attempt": attempt + 1}
                except subprocess.TimeoutExpired:
                    log.warning("Auto-Test Timeout (Versuch %d)", attempt + 1)
                except Exception as exc:
                    log.debug("Auto-Test fehlgeschlagen: %s", exc)

        return {"status": "skipped", "test_file": "", "output": "Keine Test-Datei gefunden", "attempt": 0}

    def _get_pending_dev_tasks(self) -> str:
        """Gibt offene Tasks mit Bezug zu Code/Entwicklung zurück."""
        try:
            from orchestration.task_queue import TaskQueue

            tq = TaskQueue()
            pending = tq.get_pending()

            keywords = {"code", "skript", "tool", "agent", "implement", "fix",
                        "bug", "feature", "python", "datei", "funktion", "klasse",
                        "developer", "entwickl", "refactor"}
            relevant = []
            for t in pending:
                desc = (t.get("description") or t.get("title") or "").lower()
                if any(kw in desc for kw in keywords):
                    relevant.append((t.get("description") or t.get("title") or "Task")[:50])

            return " | ".join(relevant[:3]) if relevant else ""

        except Exception as exc:
            log.debug("TaskQueue nicht abrufbar: %s", exc)
            return ""
