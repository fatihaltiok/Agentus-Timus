# tools/system_tool/tool.py
"""
System-Monitoring Tools fuer den system-Agenten.

Alle Tools sind READ-ONLY — kein Schreiben, kein Ausfuehren.
Liest Logs, Prozesse, Systemressourcen und Service-Status.
"""

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Bekannte Timus-Logdateien (Kurzname → Pfad)
_KNOWN_LOGS = {
    "timus":    str(_PROJECT_ROOT / "timus_server.log"),
    "server":   str(_PROJECT_ROOT / "timus_server.log"),
    "debug":    str(_PROJECT_ROOT / "server_debug.log"),
    "mcp":      str(_PROJECT_ROOT / "mcp_server_new.log"),
    "restart":  str(_PROJECT_ROOT / "mcp_server_restart.log"),
}


def _resolve_log(path_or_name: str) -> Path:
    """Kurzname oder Pfad → absoluter Pfad."""
    key = path_or_name.lower().strip()
    if key in _KNOWN_LOGS:
        return Path(_KNOWN_LOGS[key])
    p = Path(path_or_name)
    if p.is_absolute():
        return p
    # relativ zu PROJECT_ROOT versuchen
    candidate = _PROJECT_ROOT / path_or_name
    if candidate.exists():
        return candidate
    # relativ zu HOME
    return (Path.home() / path_or_name).resolve()


# ── read_log ───────────────────────────────────────────────────────

@tool(
    name="read_log",
    description=(
        "Liest die letzten N Zeilen einer Logdatei. "
        "Bekannte Kurznamen: 'timus', 'server', 'debug', 'mcp', 'restart'. "
        "Alternativ absoluten oder relativen Pfad angeben. "
        "Gibt Zeitstempel, Zeilenanzahl und Inhalt zurueck."
    ),
    parameters=[
        P("log_name", "string", "Logdatei-Name oder Pfad (z.B. 'timus', '/var/log/syslog')", required=True),
        P("lines",    "integer", "Anzahl Zeilen von Ende (Standard: 100, Max: 2000)", required=False),
    ],
    capabilities=["system"],
    category=C.SYSTEM
)
async def read_log(log_name: str, lines: int = 100) -> dict:
    def _read():
        fp = _resolve_log(log_name)
        if not fp.exists():
            return {"status": "error", "message": f"Logdatei nicht gefunden: {fp}"}

        n = max(1, min(2000, int(lines)))
        content_lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = content_lines[-n:] if len(content_lines) > n else content_lines

        return {
            "status":      "success",
            "path":        str(fp),
            "total_lines": len(content_lines),
            "returned":    len(tail),
            "content":     "\n".join(tail),
            "read_at":     datetime.now().isoformat(timespec="seconds"),
        }

    try:
        result = await asyncio.to_thread(_read)
        log.info(f"read_log: {log_name} → {result.get('returned', '?')} Zeilen")
        return result
    except Exception as e:
        log.error(f"read_log Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── search_log ─────────────────────────────────────────────────────

@tool(
    name="search_log",
    description=(
        "Sucht nach einem Keyword oder Muster in einer Logdatei. "
        "Gibt alle passenden Zeilen mit Zeilennummer zurueck. "
        "Ideal fuer Fehlersuche: keyword='ERROR', keyword='Exception', keyword='Traceback'."
    ),
    parameters=[
        P("log_name", "string", "Logdatei-Name oder Pfad", required=True),
        P("keyword",  "string", "Suchbegriff (Gross/Kleinschreibung egal)", required=True),
        P("max_results", "integer", "Maximale Treffer (Standard: 200)", required=False),
        P("context_lines", "integer", "Zeilen Kontext vor/nach Treffer (Standard: 2)", required=False),
    ],
    capabilities=["system"],
    category=C.SYSTEM
)
async def search_log(
    log_name: str,
    keyword: str,
    max_results: int = 200,
    context_lines: int = 2,
) -> dict:
    def _search():
        fp = _resolve_log(log_name)
        if not fp.exists():
            return {"status": "error", "message": f"Logdatei nicht gefunden: {fp}"}

        kw_lower = keyword.lower()
        n_ctx    = max(0, min(10, int(context_lines)))
        max_r    = max(1, min(500, int(max_results)))

        all_lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        matches = []
        for i, line in enumerate(all_lines):
            if kw_lower in line.lower():
                start = max(0, i - n_ctx)
                end   = min(len(all_lines), i + n_ctx + 1)
                block = {
                    "line_number": i + 1,
                    "match":       line,
                    "context":     all_lines[start:end],
                }
                matches.append(block)
                if len(matches) >= max_r:
                    break

        return {
            "status":      "success",
            "path":        str(fp),
            "keyword":     keyword,
            "total_lines": len(all_lines),
            "found":       len(matches),
            "truncated":   len(matches) >= max_r,
            "matches":     matches,
        }

    try:
        result = await asyncio.to_thread(_search)
        log.info(f"search_log: '{keyword}' in {log_name} → {result.get('found', 0)} Treffer")
        return result
    except Exception as e:
        log.error(f"search_log Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── get_processes ──────────────────────────────────────────────────

@tool(
    name="get_processes",
    description=(
        "Listet laufende Prozesse auf dem System. "
        "Optional filterbar nach Name (z.B. 'python', 'timus', 'chrome'). "
        "Gibt PID, Name, CPU%, RAM%, Status und Startzeit zurueck."
    ),
    parameters=[
        P("filter_name", "string", "Prozessname-Filter (leer = alle, z.B. 'python')", required=False),
        P("limit",       "integer", "Max. Anzahl Prozesse (Standard: 50)", required=False),
        P("sort_by",     "string",  "Sortierung: 'cpu' oder 'memory' (Standard: 'cpu')", required=False),
    ],
    capabilities=["system"],
    category=C.SYSTEM
)
async def get_processes(
    filter_name: str = "",
    limit: int = 50,
    sort_by: str = "cpu",
) -> dict:
    def _get():
        import psutil

        procs = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status", "create_time"]
        ):
            try:
                info = proc.info
                name = info.get("name", "") or ""
                if filter_name and filter_name.lower() not in name.lower():
                    continue
                procs.append({
                    "pid":       info["pid"],
                    "name":      name,
                    "cpu_pct":   round(info.get("cpu_percent") or 0.0, 2),
                    "mem_pct":   round(info.get("memory_percent") or 0.0, 3),
                    "status":    info.get("status", "?"),
                    "started":   datetime.fromtimestamp(
                        info.get("create_time") or 0
                    ).strftime("%Y-%m-%d %H:%M"),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sortieren
        key = "mem_pct" if sort_by == "memory" else "cpu_pct"
        procs.sort(key=lambda p: p[key], reverse=True)

        max_n = max(1, min(200, int(limit)))
        return {
            "status":        "success",
            "filter":        filter_name or "(alle)",
            "total_found":   len(procs),
            "returned":      min(len(procs), max_n),
            "processes":     procs[:max_n],
            "read_at":       datetime.now().isoformat(timespec="seconds"),
        }

    try:
        result = await asyncio.to_thread(_get)
        log.info(f"get_processes: Filter='{filter_name}' → {result.get('returned')} Prozesse")
        return result
    except Exception as e:
        log.error(f"get_processes Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── get_system_stats ───────────────────────────────────────────────

@tool(
    name="get_system_stats",
    description=(
        "Gibt aktuelle Systemressourcen zurueck: CPU, RAM, Disk und Netzwerk. "
        "Ideal fuer eine schnelle Systemuebersicht oder Performance-Diagnose."
    ),
    parameters=[],
    capabilities=["system"],
    category=C.SYSTEM
)
async def get_system_stats() -> dict:
    def _stats():
        import psutil

        cpu_pct  = psutil.cpu_percent(interval=0.5)
        cpu_freq = psutil.cpu_freq()
        ram      = psutil.virtual_memory()
        swap     = psutil.swap_memory()
        disk     = psutil.disk_usage("/")
        net      = psutil.net_io_counters()

        return {
            "status": "success",
            "read_at": datetime.now().isoformat(timespec="seconds"),
            "cpu": {
                "percent":    cpu_pct,
                "cores":      psutil.cpu_count(logical=True),
                "freq_mhz":   round(cpu_freq.current, 0) if cpu_freq else None,
            },
            "ram": {
                "total_gb":   round(ram.total / 1e9, 2),
                "used_gb":    round(ram.used  / 1e9, 2),
                "free_gb":    round(ram.available / 1e9, 2),
                "percent":    ram.percent,
            },
            "swap": {
                "total_gb":   round(swap.total / 1e9, 2),
                "used_gb":    round(swap.used  / 1e9, 2),
                "percent":    swap.percent,
            },
            "disk": {
                "path":       "/",
                "total_gb":   round(disk.total / 1e9, 2),
                "used_gb":    round(disk.used  / 1e9, 2),
                "free_gb":    round(disk.free  / 1e9, 2),
                "percent":    disk.percent,
            },
            "network": {
                "bytes_sent_mb":  round(net.bytes_sent / 1e6, 2),
                "bytes_recv_mb":  round(net.bytes_recv / 1e6, 2),
                "packets_sent":   net.packets_sent,
                "packets_recv":   net.packets_recv,
            },
        }

    try:
        result = await asyncio.to_thread(_stats)
        log.info(
            f"get_system_stats: CPU={result['cpu']['percent']}% "
            f"RAM={result['ram']['percent']}% "
            f"Disk={result['disk']['percent']}%"
        )
        return result
    except Exception as e:
        log.error(f"get_system_stats Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── get_service_status ─────────────────────────────────────────────

@tool(
    name="get_service_status",
    description=(
        "Liest den Status eines systemd-Services (read-only). "
        "Gibt zurueck ob der Service aktiv/inaktiv/fehlgeschlagen ist, "
        "Startzeit, PID und die letzten Log-Zeilen des Services."
    ),
    parameters=[
        P("service_name", "string", "systemd-Service-Name (z.B. 'timus', 'nginx', 'ssh')", required=True),
        P("log_lines",    "integer", "Anzahl Journal-Zeilen (Standard: 30)", required=False),
    ],
    capabilities=["system"],
    category=C.SYSTEM
)
async def get_service_status(service_name: str, log_lines: int = 30) -> dict:
    def _status():
        # .service Suffix hinzufuegen falls nicht vorhanden
        svc = service_name if service_name.endswith(".service") else f"{service_name}.service"
        n   = max(1, min(200, int(log_lines)))

        # systemctl is-active
        try:
            active_result = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True, timeout=5
            )
            active = active_result.stdout.strip()
        except Exception:
            active = "unknown"

        # systemctl status (kurz)
        try:
            status_result = subprocess.run(
                ["systemctl", "status", svc, "--no-pager", "-l"],
                capture_output=True, text=True, timeout=5
            )
            status_text = status_result.stdout.strip()
        except Exception as e:
            status_text = f"Fehler: {e}"

        # journalctl (letzte N Zeilen)
        try:
            journal_result = subprocess.run(
                ["journalctl", "-u", svc, f"-n{n}", "--no-pager", "--output=short"],
                capture_output=True, text=True, timeout=5
            )
            journal = journal_result.stdout.strip()
        except Exception as e:
            journal = f"journalctl nicht verfuegbar: {e}"

        return {
            "status":        "success",
            "service":       svc,
            "active":        active,
            "is_running":    active == "active",
            "status_output": status_text,
            "journal":       journal,
            "read_at":       datetime.now().isoformat(timespec="seconds"),
        }

    try:
        result = await asyncio.to_thread(_status)
        log.info(f"get_service_status: {service_name} → {result.get('active')}")
        return result
    except Exception as e:
        log.error(f"get_service_status Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
