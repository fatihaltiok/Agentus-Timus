"""
DeveloperAgent — Code schreiben, Dateien lesen/ändern, Skripte erstellen.

Erweiterungen gegenüber BaseAgent:
  - Kontext: Git-Status, letzte Commits, geänderte Dateien, offene Dev-Tasks
  - max_iterations=15→20 für mehrstufige Code-Workflows
  - _build_dev_context(): scannt git-Status, letzte Commits, Projektstruktur
  - Timus-Ökosystem-Wissen: Tool-Struktur, BaseAgent-Pattern, Pfade
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
        enriched_task = task + "\n\n" + context
        return await super().run(enriched_task)

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
