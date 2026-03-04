"""
ShellAgent — Bash-Befehle, Skripte, Cron-Jobs, Service-Management.

Erweiterungen gegenüber BaseAgent:
  - Timus-Ökosystem-Kontext automatisch injiziert (Services, Disk, Pfade, Skripte)
  - max_iterations=20 für mehrstufige Shell-Tasks
  - Letzte Befehle aus Audit-Log als Session-Kontext
  - Strukturierte Ausgabe-Hinweise für systemd, git, pytest, python
  - Sicherheits-Tier-Awareness im Kontext
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from agent.base_agent import BaseAgent
from agent.prompts import SHELL_PROMPT_TEMPLATE

log = logging.getLogger("ShellAgent")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR  = _PROJECT_ROOT / "scripts"
_LOGS_DIR     = _PROJECT_ROOT / "logs"
_AUDIT_LOG    = _LOGS_DIR / "shell_audit.log"

_TIMUS_SERVICES = ["timus-mcp.service", "timus-dispatcher.service"]


class ShellAgent(BaseAgent):
    """
    Shell-Operator von Timus.

    Führt Bash-Befehle, Skripte und Cron-Jobs sicher aus.
    Lädt vor jedem Task automatisch den aktuellen System-Kontext:
    Service-Status, Disk-Nutzung, letzte Audit-Log-Einträge, verfügbare Skripte.
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
        - Service-Status (timus-mcp, timus-dispatcher)
        - Disk-Auslastung
        - Letzte 5 Befehle aus Shell-Audit-Log
        - Verfügbare Skripte in scripts/
        - Bekannte Pfade + aktuelle Zeit
        """
        lines: list[str] = ["# SHELL-KONTEXT (automatisch geladen)"]

        # 1. Service-Status
        lines.append(await self._get_service_status())

        # 2. Disk-Nutzung
        disk = await self._get_disk_usage()
        if disk:
            lines.append(disk)

        # 3. Letzte Shell-Befehle aus Audit-Log
        history = self._get_recent_commands(n=5)
        if history:
            lines.append(f"Letzte Befehle: {history}")

        # 4. Verfügbare Skripte
        scripts = self._list_scripts()
        if scripts:
            lines.append(f"Skripte in scripts/: {scripts}")

        # 5. Bekannte Pfade & Zeit
        lines.append(f"Projektpfad: {_PROJECT_ROOT}")
        lines.append(f"Logs: {_LOGS_DIR}")
        lines.append(f"Audit-Log: {_AUDIT_LOG}")
        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

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

    async def _get_disk_usage(self) -> str:
        """Gibt Disk-Nutzung für das Home-Verzeichnis zurück."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["df", "-h", "--output=used,avail,pcent", str(_PROJECT_ROOT.parent)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 3:
                    return f"Disk /home: {parts[0]} verwendet, {parts[1]} frei ({parts[2]})"
        except Exception as exc:
            log.debug("Disk-Usage nicht abrufbar: %s", exc)
        return ""

    def _get_recent_commands(self, n: int = 5) -> str:
        """Liest die letzten n Befehle aus dem Shell-Audit-Log."""
        try:
            if not _AUDIT_LOG.exists():
                return ""
            recent = _AUDIT_LOG.read_text(encoding="utf-8").strip().splitlines()[-n:]
            cmds: list[str] = []
            for line in recent:
                if "cmd=" in line:
                    # Format: [TS] [STATUS] cmd=... duration=...
                    cmd_part = line.split("cmd=", 1)[-1].split(" ")[0][:60]
                    cmds.append(cmd_part)
            return " | ".join(cmds) if cmds else ""
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
