"""
ShellAgent — Bash-Befehle, Skripte, Cron-Jobs, Service-Management.

Erweiterungen gegenüber BaseAgent:
  - Timus-Ökosystem-Kontext automatisch injiziert (Git, Services, Disk, Pfade, Skripte)
  - max_iterations=20 für mehrstufige Shell-Tasks
  - Letzter Audit-Log-Eintrag als Session-Kontext
  - Strukturierte Ausgabe-Hinweise für systemd, git, pytest, python
  - Sicherheits-Tier-Awareness im Kontext
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from agent.base_agent import BaseAgent
from agent.prompts import SHELL_PROMPT_TEMPLATE

log = logging.getLogger("ShellAgent")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR  = _PROJECT_ROOT / "scripts"
_LOGS_DIR     = _PROJECT_ROOT / "logs"
_AUDIT_LOG    = _LOGS_DIR / "shell_audit.log"
_TEMP_DIR     = Path(tempfile.gettempdir())

_TIMUS_SERVICES = ["timus-mcp.service", "timus-dispatcher.service"]


class ShellAgent(BaseAgent):
    """
    Shell-Operator von Timus.

    Führt Bash-Befehle, Skripte und Cron-Jobs sicher aus.
    Lädt vor jedem Task automatisch den aktuellen System-Kontext:
    Git-Status, Service-Status, Disk-Nutzung, letzten Audit-Eintrag, verfügbare Skripte.
    """

    def __init__(self, tools_description_string: str) -> None:
        super().__init__(
            SHELL_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=20,
            agent_type="shell",
        )

    # ------------------------------------------------------------------
    # Erweiterter run()-Einstieg: System-Kontext injizieren
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        """Reichert den Task vor der Ausführung mit System-Kontext an."""
        context = await self._build_shell_context()
        enriched_task = task + "\n\n" + context
        return await super().run(enriched_task)

    # ------------------------------------------------------------------
    # System-Kontext aufbauen
    # ------------------------------------------------------------------

    async def _build_shell_context(self) -> str:
        """
        Erstellt einen kompakten System-Snapshot:
        - Git-Branch + geänderte Dateien
        - Service-Status (timus-mcp, timus-dispatcher)
        - Disk-Auslastung (/home, /tmp)
        - Letzter Audit-Eintrag aus Shell-Audit-Log
        - Verfügbare Skripte in scripts/
        - Bekannte Pfade + aktuelle Zeit
        """
        lines: list[str] = ["# SHELL-KONTEXT (automatisch geladen)"]

        # 1. Git-Status
        git_status = await self._get_git_status()
        if git_status:
            lines.append(git_status)

        # 2. Service-Status
        lines.append(await self._get_service_status())

        # 3. Disk-Nutzung
        disk_home = await self._get_disk_usage(_PROJECT_ROOT.parent, "/home")
        if disk_home:
            lines.append(disk_home)
        disk_tmp = await self._get_disk_usage(_TEMP_DIR, str(_TEMP_DIR))
        if disk_tmp:
            lines.append(disk_tmp)

        # 4. Letzter Audit-Eintrag
        audit_entry = self._get_last_audit_entry()
        if audit_entry:
            lines.append(f"Letzter Audit-Eintrag: {audit_entry}")

        # 5. Verfügbare Skripte
        scripts = self._list_scripts()
        if scripts:
            lines.append(f"Skripte in scripts/: {scripts}")

        # 6. Bekannte Pfade & Zeit
        lines.append(f"Projektpfad: {_PROJECT_ROOT}")
        lines.append(f"Logs: {_LOGS_DIR}")
        lines.append(f"Audit-Log: {_AUDIT_LOG}")
        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    async def _get_git_status(self) -> str:
        """Gibt Branch und geänderte Dateien im Repo zurück."""
        try:
            branch_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(_PROJECT_ROOT), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            branch = branch_result.stdout.strip() or "detached"

            status_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(_PROJECT_ROOT), "status", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            changed = [
                line[3:].strip()
                for line in status_result.stdout.strip().splitlines()
                if len(line) >= 4 and line[3:].strip()
            ]
            if changed:
                preview = ", ".join(changed[:5])
                extra = f" (+{len(changed) - 5} weitere)" if len(changed) > 5 else ""
                return f"Git: branch={branch} | Änderungen: {preview}{extra}"
            return f"Git: branch={branch} | Änderungen: sauber"
        except Exception as exc:
            log.debug("Git-Status nicht abrufbar: %s", exc)
            return "Git: (nicht abrufbar)"

    async def _get_service_status(self) -> str:
        """Fragt systemctl is-active für Timus-Services ab."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["systemctl", "is-active"] + _TIMUS_SERVICES,
                capture_output=True,
                text=True,
                timeout=5,
            )
            statuses = result.stdout.strip().split("\n")
            parts = []
            for svc, status in zip(_TIMUS_SERVICES, statuses):
                short = svc.replace(".service", "")
                parts.append(f"{short}={status.strip()}")
            return "Services: " + ", ".join(parts)
        except Exception as exc:
            log.debug("Service-Status nicht abrufbar: %s", exc)
            return "Services: (nicht abrufbar)"

    async def _get_disk_usage(self, path: Path, label: str) -> str:
        """Gibt Disk-Nutzung für einen Pfad zurück."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["df", "-h", "--output=used,avail,pcent", str(path)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 3:
                    return f"Disk {label}: {parts[0]} verwendet, {parts[1]} frei ({parts[2]})"
        except Exception as exc:
            log.debug("Disk-Usage nicht abrufbar fuer %s: %s", label, exc)
        return ""

    def _get_last_audit_entry(self) -> str:
        """Liest den letzten Audit-Log-Eintrag kompakt aus."""
        try:
            if not _AUDIT_LOG.exists():
                return ""
            lines = [line.strip() for line in _AUDIT_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
            if not lines:
                return ""
            last = lines[-1]
            return last[:180] + ("..." if len(last) > 180 else "")
        except Exception:
            return ""

    def _list_scripts(self) -> str:
        """Listet verfügbare Shell- und Python-Skripte auf."""
        try:
            if not _SCRIPTS_DIR.exists():
                return ""
            scripts = [
                f.name
                for f in sorted(_SCRIPTS_DIR.iterdir())
                if f.suffix in (".sh", ".py") and f.is_file()
            ]
            return ", ".join(scripts[:15]) if scripts else ""
        except Exception:
            return ""
