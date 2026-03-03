# tools/shell_tool/tool.py
"""
Shell-Tool fuer den shell-Agenten mit mehrstufigem Policy-Layer.

Sicherheitsstufen:
  1. Blacklist  — sofortige Blockierung gefaehrlicher Muster
  2. Whitelist  — optional (SHELL_WHITELIST_MODE=1 in .env)
  3. Timeout    — max. 30 Sekunden, dann kill
  4. Audit-Log  — jede Ausfuehrung wird protokolliert
  5. Dry-Run    — Befehl anzeigen ohne auszufuehren
"""

import asyncio
import logging
import os
import re
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger(__name__)

_PROJECT_ROOT  = Path(__file__).resolve().parent.parent.parent
_AUDIT_LOG     = _PROJECT_ROOT / "logs" / "shell_audit.log"
_RESULTS_DIR   = _PROJECT_ROOT / "results"
_MAX_TIMEOUT   = int(os.getenv("SHELL_MAX_TIMEOUT", "300"))   # default 5 Minuten
_INSTALL_TIMEOUT = int(os.getenv("SHELL_INSTALL_TIMEOUT", "180"))  # default 3 Minuten

# Verzeichnis sicherstellen
_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

# ── Policy-Definitionen ────────────────────────────────────────────

# Muster die IMMER blockiert werden — kein Dry-Run, kein Override
_BLACKLIST: list[tuple[re.Pattern, str]] = [
    (re.compile(r"rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r", re.I),
     "rm -rf: destruktives rekursives Loeschen verboten"),
    (re.compile(r"rm\s+.*[/\\][*]",        re.I),
     "Wildcard-rm auf Verzeichnis verboten"),
    (re.compile(r":\s*\(\s*\)\s*\{.*:\|",  re.S),
     "Fork-Bomb erkannt"),
    (re.compile(r"dd\s+if=",               re.I),
     "dd if= kann Festplatten ueberschreiben — verboten"),
    (re.compile(r"mkfs",                   re.I),
     "mkfs: Dateisystem-Formatierung verboten"),
    (re.compile(r"\bshutdown\b|\breboot\b|\bpoweroff\b|\bhalt\b", re.I),
     "Systemabschalte-Befehle verboten"),
    (re.compile(r"chmod\s+[0-7]*7[0-7]{2}.*/(etc|bin|sbin|usr|boot)", re.I),
     "Systemdatei-chmod verboten"),
    (re.compile(r">\s*/dev/(sda|sdb|hda|nvme)",  re.I),
     "Direkte Block-Device Writes verboten"),
    (re.compile(r"curl.*\|\s*(bash|sh|python)", re.I),
     "Piped Remote-Execution verboten"),
    (re.compile(r"wget.*-O.*\|\s*(bash|sh)",    re.I),
     "Piped Remote-Execution verboten"),
    (re.compile(r"base64\s+-d.*\|\s*(bash|sh)", re.I),
     "Base64-decoded Execution verboten"),
]

# Standard-Whitelist (nur aktiv wenn SHELL_WHITELIST_MODE=1)
_DEFAULT_WHITELIST = [
    "ls", "pwd", "echo", "cat", "head", "tail", "grep", "find",
    "ps", "df", "du", "free", "uptime", "who", "id", "uname",
    "python", "python3", "pip", "pip3",
    "git", "curl", "wget", "mkdir", "cp", "mv", "touch", "chmod",
    "systemctl", "journalctl", "crontab",
]


def _audit(command: str, dry_run: bool, blocked: bool, result: str, duration: float = 0.0):
    """Schreibt einen Eintrag in das Audit-Log."""
    ts     = datetime.now().isoformat(timespec="seconds")
    status = "BLOCKED" if blocked else ("DRY-RUN" if dry_run else "EXECUTED")
    entry  = f"[{ts}] [{status}] cmd={repr(command)} duration={duration:.2f}s result={repr(result[:200])}\n"
    try:
        with open(_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        log.warning(f"Audit-Log Schreiben fehlgeschlagen: {e}")


def _check_blacklist(command: str) -> str | None:
    """Gibt Blockierungsgrund zurueck, oder None wenn erlaubt."""
    for pattern, reason in _BLACKLIST:
        if pattern.search(command):
            return reason
    return None


def _check_whitelist(command: str) -> str | None:
    """Gibt Blockierungsgrund zurueck wenn Whitelist aktiv und Befehl nicht erlaubt."""
    if os.getenv("SHELL_WHITELIST_MODE", "0") != "1":
        return None
    # Ersten Token des Befehls extrahieren
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return "Leerer Befehl"
    cmd_name = Path(tokens[0]).name  # z.B. "/usr/bin/python3" → "python3"
    extra = [w.strip() for w in os.getenv("SHELL_WHITELIST_EXTRA", "").split(",") if w.strip()]
    allowed = _DEFAULT_WHITELIST + extra
    if cmd_name not in allowed:
        return f"'{cmd_name}' nicht in Whitelist. Setze SHELL_WHITELIST_EXTRA oder deaktiviere SHELL_WHITELIST_MODE."
    return None


# ── run_command ────────────────────────────────────────────────────

@tool(
    name="run_command",
    description=(
        "Fuehrt einen Bash-Befehl aus. "
        "Mehrstufige Sicherheitspruefung: Blacklist → Whitelist → Timeout (30s) → Audit-Log. "
        "dry_run=true zeigt den Befehl nur an ohne ihn auszufuehren. "
        "Gefaehrliche Befehle (rm -rf, dd, shutdown etc.) werden sofort blockiert."
    ),
    parameters=[
        P("command",  "string",  "Bash-Befehl der ausgefuehrt werden soll", required=True),
        P("dry_run",  "boolean", "Nur anzeigen, nicht ausfuehren (Standard: false)", required=False),
        P("timeout",  "integer", f"Max. Ausfuehrungs-Zeit in Sekunden (1–{_MAX_TIMEOUT}, Standard: 30)", required=False),
        P("workdir",  "string",  "Arbeitsverzeichnis (Standard: Projekt-Root)", required=False),
    ],
    capabilities=["shell"],
    category=C.SYSTEM
)
async def run_command(
    command: str,
    dry_run: bool = False,
    timeout: int = 30,
    workdir: str = "",
) -> dict:
    def _run():
        t_start = time.monotonic()

        # 1. Blacklist
        block_reason = _check_blacklist(command)
        if block_reason:
            _audit(command, dry_run=False, blocked=True, result=block_reason)
            return {
                "status":  "blocked",
                "reason":  block_reason,
                "command": command,
            }

        # 2. Whitelist
        wl_reason = _check_whitelist(command)
        if wl_reason:
            _audit(command, dry_run=False, blocked=True, result=wl_reason)
            return {
                "status":  "blocked",
                "reason":  wl_reason,
                "command": command,
            }

        # 3. Dry-Run
        if dry_run:
            _audit(command, dry_run=True, blocked=False, result="(dry-run)")
            return {
                "status":  "dry_run",
                "command": command,
                "message": "Dry-Run — Befehl wurde NICHT ausgefuehrt. Zum Ausfuehren: dry_run=false setzen.",
            }

        # 4. Ausfuehren
        t_limit = max(1, min(_MAX_TIMEOUT, int(timeout)))
        cwd = workdir if workdir else str(_PROJECT_ROOT)

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=t_limit,
                cwd=cwd,
            )
            duration = time.monotonic() - t_start
            output   = (proc.stdout + proc.stderr).strip()
            result   = {
                "status":      "success",
                "command":     command,
                "returncode":  proc.returncode,
                "stdout":      proc.stdout.strip()[:4000],
                "stderr":      proc.stderr.strip()[:1000],
                "duration_s":  round(duration, 2),
                "executed_at": datetime.now().isoformat(timespec="seconds"),
            }
            _audit(command, dry_run=False, blocked=False, result=output, duration=duration)
            return result

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - t_start
            msg = f"Timeout nach {t_limit}s — Prozess abgebrochen"
            _audit(command, dry_run=False, blocked=False, result=msg, duration=duration)
            return {
                "status":     "timeout",
                "command":    command,
                "message":    msg,
                "timeout_s":  t_limit,
            }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        log.error(f"run_command Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── run_script ─────────────────────────────────────────────────────

@tool(
    name="run_script",
    description=(
        "Fuehrt ein Python- oder Bash-Skript aus results/ oder dem Projekt-Verzeichnis aus. "
        "Nur Skripte im eigenen Projektverzeichnis erlaubt — keine absoluten Pfade ausserhalb. "
        "Dry-Run und Timeout gelten genauso wie bei run_command."
    ),
    parameters=[
        P("script_path", "string",  "Pfad zum Skript (relativ zu Projekt-Root oder results/)", required=True),
        P("args",        "string",  "Argumente als String (z.B. '--verbose --output test.csv')", required=False),
        P("dry_run",     "boolean", "Nur anzeigen, nicht ausfuehren (Standard: false)", required=False),
        P("timeout",     "integer", f"Max. Laufzeit in Sekunden (1–{_MAX_TIMEOUT}, Standard: 30)", required=False),
    ],
    capabilities=["shell"],
    category=C.SYSTEM
)
async def run_script(
    script_path: str,
    args: str = "",
    dry_run: bool = False,
    timeout: int = 30,
) -> dict:
    def _run():
        # Pfad auflösen und Sicherheit prüfen
        sp = Path(script_path)
        if sp.is_absolute():
            resolved = sp.resolve()
        else:
            # relativ zu results/ oder Projekt-Root versuchen
            candidates = [
                (_RESULTS_DIR / script_path).resolve(),
                (_PROJECT_ROOT / script_path).resolve(),
            ]
            resolved = next((c for c in candidates if c.exists()), candidates[-1])

        # Nur eigene Dateien erlaubt
        try:
            resolved.relative_to(_PROJECT_ROOT)
        except ValueError:
            reason = f"Skript ausserhalb des Projektverzeichnisses verboten: {resolved}"
            _audit(str(resolved), dry_run=False, blocked=True, result=reason)
            return {"status": "blocked", "reason": reason}

        if not resolved.exists():
            return {"status": "error", "message": f"Skript nicht gefunden: {resolved}"}

        # Interpreter bestimmen
        suffix = resolved.suffix.lower()
        if suffix == ".py":
            interpreter = "python3"
        elif suffix in (".sh", ".bash", ""):
            interpreter = "bash"
        else:
            return {"status": "error", "message": f"Unbekannter Skript-Typ: {suffix}"}

        command = f"{interpreter} {resolved} {args}".strip()

        # Blacklist auch fuer Script-Argumente
        full_check = f"{resolved} {args}"
        block_reason = _check_blacklist(full_check)
        if block_reason:
            _audit(command, dry_run=False, blocked=True, result=block_reason)
            return {"status": "blocked", "reason": block_reason, "command": command}

        if dry_run:
            _audit(command, dry_run=True, blocked=False, result="(dry-run)")
            return {
                "status":  "dry_run",
                "command": command,
                "message": "Dry-Run — Skript wurde NICHT ausgefuehrt.",
            }

        t_limit = max(1, min(_MAX_TIMEOUT, int(timeout)))
        t_start = time.monotonic()
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=t_limit, cwd=str(_PROJECT_ROOT),
            )
            duration = time.monotonic() - t_start
            output   = (proc.stdout + proc.stderr).strip()
            _audit(command, dry_run=False, blocked=False, result=output, duration=duration)
            return {
                "status":     "success",
                "command":    command,
                "returncode": proc.returncode,
                "stdout":     proc.stdout.strip()[:4000],
                "stderr":     proc.stderr.strip()[:1000],
                "duration_s": round(duration, 2),
            }
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - t_start
            msg = f"Timeout nach {t_limit}s"
            _audit(command, dry_run=False, blocked=False, result=msg, duration=duration)
            return {"status": "timeout", "command": command, "message": msg}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        log.error(f"run_script Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── install_package ────────────────────────────────────────────────

_ALLOWED_MANAGERS = {"pip", "pip3", "apt", "apt-get", "conda"}


@tool(
    name="install_package",
    description=(
        "Installiert ein Python- oder System-Paket via pip, apt oder conda. "
        "Längerer Timeout (3 Minuten) für Package-Manager. "
        "Audit-Log protokolliert jede Installation. "
        "Gefaehrliche Paket-Namen (Injection) werden blockiert."
    ),
    parameters=[
        P("package",  "string",  "Paket-Name oder Version (z.B. 'requests', 'numpy==1.26.4', 'curl')", required=True),
        P("manager",  "string",  "Package-Manager: pip (Standard) | pip3 | apt | apt-get | conda", required=False),
        P("extra_args", "string", "Zusaetzliche Argumente (z.B. '--upgrade', '--user')", required=False),
        P("dry_run",  "boolean", "Nur anzeigen, nicht installieren (Standard: false)", required=False),
    ],
    capabilities=["shell"],
    category=C.SYSTEM
)
async def install_package(
    package: str,
    manager: str = "pip",
    extra_args: str = "",
    dry_run: bool = False,
) -> dict:
    def _install():
        mgr = manager.strip().lower() if manager else "pip"
        if mgr not in _ALLOWED_MANAGERS:
            return {"status": "blocked", "reason": f"Unbekannter Package-Manager '{mgr}'. Erlaubt: {', '.join(sorted(_ALLOWED_MANAGERS))}"}

        pkg = package.strip()
        if not pkg:
            return {"status": "error", "message": "Kein Paket angegeben"}

        # Injection-Schutz: Paket-Name darf keine Shell-Sonderzeichen enthalten
        if re.search(r"[;&|`$<>]", pkg):
            reason = f"Ungueltige Zeichen im Paket-Namen: {pkg}"
            _audit(f"{mgr} install {pkg}", dry_run=False, blocked=True, result=reason)
            return {"status": "blocked", "reason": reason}

        # Befehl zusammenbauen
        if mgr in ("apt", "apt-get"):
            command = f"DEBIAN_FRONTEND=noninteractive {mgr} install -y {pkg}"
            if extra_args:
                command += f" {extra_args.strip()}"
        elif mgr == "conda":
            command = f"conda install -y {pkg}"
            if extra_args:
                command += f" {extra_args.strip()}"
        else:
            command = f"{mgr} install {pkg}"
            if extra_args:
                command += f" {extra_args.strip()}"

        # Blacklist pruefen (Schutz vor verschachtelten Injections)
        block_reason = _check_blacklist(command)
        if block_reason:
            _audit(command, dry_run=False, blocked=True, result=block_reason)
            return {"status": "blocked", "reason": block_reason, "command": command}

        if dry_run:
            _audit(command, dry_run=True, blocked=False, result="(dry-run)")
            return {
                "status":  "dry_run",
                "command": command,
                "message": "Dry-Run — Installation NICHT ausgefuehrt. Setze dry_run=false zur Bestaetigung.",
            }

        t_start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=_INSTALL_TIMEOUT,
                cwd=str(_PROJECT_ROOT),
            )
            duration = time.monotonic() - t_start
            output = (proc.stdout + proc.stderr).strip()
            _audit(command, dry_run=False, blocked=False, result=output[:200], duration=duration)
            return {
                "status":      "success" if proc.returncode == 0 else "error",
                "command":     command,
                "returncode":  proc.returncode,
                "stdout":      proc.stdout.strip()[:4000],
                "stderr":      proc.stderr.strip()[:1000],
                "duration_s":  round(duration, 2),
                "installed":   pkg,
                "manager":     mgr,
            }
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - t_start
            msg = f"Timeout nach {_INSTALL_TIMEOUT}s — Installation abgebrochen"
            _audit(command, dry_run=False, blocked=False, result=msg, duration=duration)
            return {"status": "timeout", "command": command, "message": msg}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    try:
        return await asyncio.to_thread(_install)
    except Exception as e:
        log.error(f"install_package Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── list_cron ──────────────────────────────────────────────────────

@tool(
    name="list_cron",
    description=(
        "Zeigt die aktuellen Cron-Jobs des Benutzers an (read-only). "
        "Gibt Zeitplan und Befehl jedes Jobs zurueck."
    ),
    parameters=[],
    capabilities=["shell"],
    category=C.SYSTEM
)
async def list_cron() -> dict:
    def _list():
        try:
            proc = subprocess.run(
                ["crontab", "-l"],
                capture_output=True, text=True, timeout=5
            )
            raw = proc.stdout.strip()
            if proc.returncode != 0 or "no crontab for" in proc.stderr:
                return {"status": "success", "jobs": [], "message": "Keine Cron-Jobs vorhanden"}

            jobs = []
            for line in raw.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    jobs.append(line)

            return {
                "status":    "success",
                "job_count": len(jobs),
                "jobs":      jobs,
                "raw":       raw,
            }
        except FileNotFoundError:
            return {"status": "error", "message": "crontab nicht gefunden"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    try:
        return await asyncio.to_thread(_list)
    except Exception as e:
        log.error(f"list_cron Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── add_cron ───────────────────────────────────────────────────────

@tool(
    name="add_cron",
    description=(
        "Fuegt einen neuen Cron-Job hinzu. "
        "Erfordert dry_run=false zur Bestaetigung — Standard ist IMMER Dry-Run. "
        "Blacklist gilt auch fuer Cron-Befehle. "
        "Format-Beispiele: '0 8 * * *' = taeglich 08:00, '*/30 * * * *' = alle 30 Minuten."
    ),
    parameters=[
        P("schedule", "string",  "Cron-Zeitplan (5 Felder: Min Std Tag Monat Wochentag)", required=True),
        P("command",  "string",  "Befehl der ausgefuehrt werden soll", required=True),
        P("dry_run",  "boolean", "Nur anzeigen (Standard: TRUE — muss explizit auf false gesetzt werden)", required=False),
    ],
    capabilities=["shell"],
    category=C.SYSTEM
)
async def add_cron(schedule: str, command: str, dry_run: bool = True) -> dict:
    def _add():
        # Blacklist
        block_reason = _check_blacklist(command)
        if block_reason:
            _audit(f"cron: {schedule} {command}", dry_run=False, blocked=True, result=block_reason)
            return {"status": "blocked", "reason": block_reason}

        cron_line = f"{schedule} {command}"

        # Dry-Run (Standard!)
        if dry_run:
            _audit(cron_line, dry_run=True, blocked=False, result="(dry-run)")
            return {
                "status":   "dry_run",
                "cron_line": cron_line,
                "message":  "Dry-Run — Cron-Job wurde NICHT angelegt. Setze dry_run=false zur Bestaetigung.",
            }

        try:
            # Bestehende Crons lesen
            existing = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True, timeout=5
            )
            current = existing.stdout if existing.returncode == 0 else ""

            # Doppelten Eintrag verhindern
            if cron_line in current:
                return {"status": "skipped", "message": "Cron-Job existiert bereits", "cron_line": cron_line}

            new_crontab = current.rstrip("\n") + f"\n{cron_line}\n"
            proc = subprocess.run(
                ["crontab", "-"],
                input=new_crontab, capture_output=True, text=True, timeout=5
            )
            if proc.returncode != 0:
                return {"status": "error", "message": proc.stderr.strip()}

            _audit(cron_line, dry_run=False, blocked=False, result="added")
            return {
                "status":    "success",
                "cron_line": cron_line,
                "message":   f"Cron-Job erfolgreich angelegt: {cron_line}",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    try:
        return await asyncio.to_thread(_add)
    except Exception as e:
        log.error(f"add_cron Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── read_audit_log ─────────────────────────────────────────────────

@tool(
    name="read_audit_log",
    description=(
        "Liest das Shell-Audit-Log — alle ausgefuehrten, abgelehnten und Dry-Run Befehle. "
        "Gibt die letzten N Eintraege zurueck."
    ),
    parameters=[
        P("lines", "integer", "Anzahl Eintraege (Standard: 50, Max: 500)", required=False),
    ],
    capabilities=["shell", "system"],
    category=C.SYSTEM
)
async def read_audit_log(lines: int = 50) -> dict:
    def _read():
        if not _AUDIT_LOG.exists():
            return {"status": "success", "entries": [], "message": "Audit-Log noch leer"}
        n = max(1, min(500, int(lines)))
        content = _AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = content[-n:]
        return {
            "status":       "success",
            "path":         str(_AUDIT_LOG),
            "total_entries": len(content),
            "returned":     len(tail),
            "entries":      tail,
        }

    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        log.error(f"read_audit_log Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── restart_timus ───────────────────────────────────────────────────

_MCP_SERVICE        = "timus-mcp.service"
_DISPATCHER_SERVICE = "timus-dispatcher.service"
_MCP_HEALTH_URL     = "http://127.0.0.1:5000/health"


@tool(
    name="restart_timus",
    description=(
        "Startet den Timus MCP-Server und/oder den Dispatcher neu. "
        "Nutze dies wenn Timus traege reagiert, Tools nicht laden oder der MCP-Server ausgefallen ist. "
        "Prueft nach dem Start automatisch die MCP-Health. "
        "Benoetigt: sudo NOPASSWD fuer systemctl (scripts/sudoers_timus einrichten)."
    ),
    parameters=[
        P(
            "mode",
            "string",
            "Neustart-Modus: full (MCP + Dispatcher, Standard) | mcp (nur MCP-Server) | dispatcher (nur Dispatcher) | status (nur Status anzeigen)",
            required=False,
        ),
    ],
    capabilities=["shell", "system"],
    category=C.SYSTEM
)
async def restart_timus(mode: str = "full") -> dict:
    def _restart():
        mode_clean = (mode or "full").strip().lower()
        if mode_clean not in ("full", "mcp", "dispatcher", "status"):
            mode_clean = "full"

        results: dict = {"mode": mode_clean, "steps": []}

        def _run_cmd(cmd: str) -> tuple[int, str]:
            try:
                proc = subprocess.run(
                    cmd, shell=True, capture_output=True,
                    text=True, timeout=30,
                )
                return proc.returncode, (proc.stdout + proc.stderr).strip()
            except subprocess.TimeoutExpired:
                return -1, "Timeout"
            except Exception as ex:
                return -1, str(ex)

        def _health_check(retries: int = 8, wait: int = 3) -> bool:
            import urllib.request
            for _ in range(retries):
                try:
                    with urllib.request.urlopen(_MCP_HEALTH_URL, timeout=2) as r:
                        if r.status == 200:
                            return True
                except Exception:
                    pass
                time.sleep(wait)
            return False

        def _stop(service: str):
            rc, out = _run_cmd(f"sudo systemctl stop {service}")
            results["steps"].append({"action": f"stop {service}", "rc": rc, "out": out[:200]})
            time.sleep(1)

        def _start(service: str):
            rc, out = _run_cmd(f"sudo systemctl start {service}")
            results["steps"].append({"action": f"start {service}", "rc": rc, "out": out[:200]})

        def _svc_status(service: str) -> str:
            rc, _ = _run_cmd(f"systemctl is-active {service}")
            _, active = _run_cmd(f"systemctl is-active {service}")
            return active.strip()

        if mode_clean == "status":
            results["mcp_active"]        = _svc_status(_MCP_SERVICE)
            results["dispatcher_active"] = _svc_status(_DISPATCHER_SERVICE)
            results["mcp_healthy"]       = _health_check(retries=1, wait=1)
            results["status"] = "ok"
            return results

        # full oder mcp: Dispatcher zuerst stoppen (haengt von MCP ab)
        if mode_clean in ("full", "mcp"):
            if mode_clean == "full":
                _stop(_DISPATCHER_SERVICE)
            _stop(_MCP_SERVICE)
            _start(_MCP_SERVICE)
            healthy = _health_check()
            results["mcp_healthy"] = healthy
            results["steps"].append({"action": "health_check", "healthy": healthy})
            if not healthy:
                results["status"] = "error"
                results["message"] = "MCP-Server antwortet nicht nach Neustart"
                _audit(f"restart_timus mode={mode_clean}", dry_run=False, blocked=False,
                       result="mcp_health_failed")
                return results

        if mode_clean in ("full", "dispatcher"):
            _start(_DISPATCHER_SERVICE)
            time.sleep(3)
            disp_active = _svc_status(_DISPATCHER_SERVICE)
            results["dispatcher_active"] = disp_active
            results["steps"].append({"action": "dispatcher_active_check", "active": disp_active})

        results["status"] = "ok"
        results["message"] = f"Timus neugestartet (Modus: {mode_clean})"
        _audit(f"restart_timus mode={mode_clean}", dry_run=False, blocked=False,
               result=results["message"])
        log.info("🔄 restart_timus abgeschlossen: %s", results["message"])
        return results

    try:
        return await asyncio.to_thread(_restart)
    except Exception as e:
        log.error(f"restart_timus Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
