# tools/file_system_tool/tool.py
"""
Filesystem-Tools für Timus.

Erlaubt Timus den Zugriff auf das gesamte Dateisystem des Benutzers.
- Lesen:    überall erlaubt (außer system-kritische Pfade)
- Schreiben: nur /home und /tmp (Schutz vor versehentlichem System-Schreiben)
- Relative Pfade werden relativ zu HOME (/home/fatih-ubuntu/) aufgelöst
"""

import logging
import asyncio
import fnmatch
from pathlib import Path

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger(__name__)

# Pfade die nie gelesen werden dürfen (Kernel-Memory etc.)
_READ_BLACKLIST = {
    "/proc/kcore", "/proc/kmem", "/dev/mem",
    "/etc/shadow", "/etc/gshadow",
}

# Beim Schreiben: nur diese Präfixe erlaubt
_WRITE_ALLOWED_PREFIXES = [
    str(Path.home()),
    "/tmp",
]


def _resolve_path(path: str) -> Path:
    """
    Löst einen Pfad auf.
    - Absoluter Pfad (/home/...) → direkt
    - Relativer Pfad            → relativ zu HOME
    """
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    return (Path.home() / path).resolve()


def _check_read(full_path: Path):
    """Wirft Exception wenn der Pfad nicht gelesen werden darf."""
    if str(full_path) in _READ_BLACKLIST:
        raise PermissionError(f"Zugriff auf '{full_path}' verweigert.")


def _check_write(full_path: Path):
    """Wirft Exception wenn der Pfad nicht geschrieben werden darf."""
    allowed = any(str(full_path).startswith(p) for p in _WRITE_ALLOWED_PREFIXES)
    if not allowed:
        raise PermissionError(
            f"Schreiben nach '{full_path}' verweigert. "
            f"Erlaubt: {', '.join(_WRITE_ALLOWED_PREFIXES)}"
        )


# ── list_directory ────────────────────────────────────────────────────────────

@tool(
    name="list_directory",
    description=(
        "Listet den Inhalt eines Verzeichnisses auf. "
        "Absolute Pfade (/home/fatih-ubuntu/...) und relative Pfade (Dokumente/) werden unterstützt. "
        "Relative Pfade werden relativ zum Home-Verzeichnis aufgelöst."
    ),
    parameters=[
        P("path", "string", "Pfad zum Verzeichnis (absolut oder relativ zu HOME)", required=True),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def list_directory(path: str) -> dict:
    try:
        full_path = _resolve_path(path)
        _check_read(full_path)

        if not full_path.is_dir():
            raise FileNotFoundError(f"'{full_path}' ist kein Verzeichnis oder existiert nicht.")

        def _list():
            items = []
            for item in sorted(full_path.iterdir()):
                items.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                })
            return items

        contents = await asyncio.to_thread(_list)
        log.info(f"list_directory: {full_path} ({len(contents)} Einträge)")
        return {"status": "success", "path": str(full_path), "contents": contents}

    except (FileNotFoundError, PermissionError) as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"list_directory Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── get_directory_tree ────────────────────────────────────────────────────────

@tool(
    name="get_directory_tree",
    description=(
        "Gibt die Baumstruktur eines Verzeichnisses zurück (wie der 'tree'-Befehl). "
        "Ideal um sich einen Überblick über einen Ordner und seine Unterordner zu verschaffen. "
        "max_depth steuert wie tief der Baum geht (Standard: 3)."
    ),
    parameters=[
        P("path",      "string",  "Pfad zum Verzeichnis (absolut oder relativ zu HOME)", required=True),
        P("max_depth", "integer", "Maximale Tiefe des Baums (1–6, Standard: 3)", required=False),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def get_directory_tree(path: str, max_depth: int = 3) -> dict:
    try:
        full_path = _resolve_path(path)
        _check_read(full_path)

        if not full_path.is_dir():
            raise FileNotFoundError(f"'{full_path}' ist kein Verzeichnis oder existiert nicht.")

        max_depth = max(1, min(6, int(max_depth)))

        def _build_tree(current: Path, depth: int, prefix: str = "") -> list[str]:
            if depth == 0:
                return []
            lines = []
            try:
                entries = sorted(current.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            except PermissionError:
                return [prefix + "  [Zugriff verweigert]"]

            for i, entry in enumerate(entries):
                is_last = (i == len(entries) - 1)
                connector = "└── " if is_last else "├── "
                suffix = "/" if entry.is_dir() else ""
                lines.append(prefix + connector + entry.name + suffix)
                if entry.is_dir() and depth > 1:
                    extension = "    " if is_last else "│   "
                    lines.extend(_build_tree(entry, depth - 1, prefix + extension))
            return lines

        def _run():
            lines = [str(full_path) + "/"]
            lines.extend(_build_tree(full_path, max_depth))
            return lines

        tree_lines = await asyncio.to_thread(_run)
        tree_str = "\n".join(tree_lines)
        log.info(f"get_directory_tree: {full_path} depth={max_depth}")
        return {"status": "success", "path": str(full_path), "tree": tree_str}

    except (FileNotFoundError, PermissionError) as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"get_directory_tree Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── search_files ──────────────────────────────────────────────────────────────

@tool(
    name="search_files",
    description=(
        "Sucht Dateien nach einem Glob-Muster (z.B. '*.py', '**/*.txt', 'Bericht*'). "
        "Gibt eine Liste aller gefundenen Dateipfade zurück. "
        "Nützlich um Dateien nach Name oder Typ zu finden."
    ),
    parameters=[
        P("path",    "string", "Startverzeichnis für die Suche (absolut oder relativ zu HOME)", required=True),
        P("pattern", "string", "Glob-Suchmuster, z.B. '*.pdf', '**/*.py', 'Rechnung*'", required=True),
        P("limit",   "integer", "Maximale Anzahl Ergebnisse (Standard: 100)", required=False),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def search_files(path: str, pattern: str, limit: int = 100) -> dict:
    try:
        full_path = _resolve_path(path)
        _check_read(full_path)

        if not full_path.is_dir():
            raise FileNotFoundError(f"'{full_path}' ist kein Verzeichnis oder existiert nicht.")

        limit = max(1, min(500, int(limit)))

        def _search():
            results = []
            for match in full_path.glob(pattern):
                results.append({
                    "path": str(match),
                    "type": "dir" if match.is_dir() else "file",
                    "size": match.stat().st_size if match.is_file() else None,
                })
                if len(results) >= limit:
                    break
            return results

        results = await asyncio.to_thread(_search)
        log.info(f"search_files: {full_path} pattern='{pattern}' → {len(results)} Treffer")
        return {
            "status": "success",
            "path": str(full_path),
            "pattern": pattern,
            "count": len(results),
            "results": results,
        }

    except (FileNotFoundError, PermissionError) as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"search_files Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── search_in_files ───────────────────────────────────────────────────────────

@tool(
    name="search_in_files",
    description=(
        "Sucht einen Text oder Begriff in Dateien (wie grep). "
        "Gibt Dateipfade und die passenden Zeilen zurück. "
        "file_pattern filtert welche Dateien durchsucht werden (z.B. '*.txt', '*.py')."
    ),
    parameters=[
        P("path",         "string", "Startverzeichnis (absolut oder relativ zu HOME)", required=True),
        P("text",         "string", "Der zu suchende Text (Groß-/Kleinschreibung egal)", required=True),
        P("file_pattern", "string", "Nur diese Dateitypen durchsuchen, z.B. '*.txt' (Standard: '*')", required=False),
        P("limit",        "integer", "Maximale Anzahl gefundener Dateien (Standard: 50)", required=False),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def search_in_files(path: str, text: str, file_pattern: str = "*", limit: int = 50) -> dict:
    try:
        full_path = _resolve_path(path)
        _check_read(full_path)

        if not full_path.is_dir():
            raise FileNotFoundError(f"'{full_path}' ist kein Verzeichnis oder existiert nicht.")

        limit = max(1, min(200, int(limit)))
        needle = text.lower()

        def _search():
            hits = []
            for filepath in full_path.rglob(file_pattern):
                if not filepath.is_file():
                    continue
                # Binärdateien überspringen
                if filepath.suffix.lower() in {
                    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
                    ".pdf", ".zip", ".tar", ".gz", ".exe", ".bin",
                    ".mp3", ".mp4", ".mkv", ".avi", ".mov", ".db",
                    ".pyc", ".so", ".o",
                }:
                    continue
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                matching_lines = []
                for lineno, line in enumerate(content.splitlines(), 1):
                    if needle in line.lower():
                        matching_lines.append({"line": lineno, "content": line.strip()[:200]})

                if matching_lines:
                    hits.append({
                        "file": str(filepath),
                        "matches": matching_lines[:10],  # max 10 Zeilen pro Datei
                    })
                    if len(hits) >= limit:
                        break
            return hits

        results = await asyncio.to_thread(_search)
        log.info(f"search_in_files: '{text}' in {full_path} → {len(results)} Dateien")
        return {
            "status": "success",
            "path": str(full_path),
            "text": text,
            "files_found": len(results),
            "results": results,
        }

    except (FileNotFoundError, PermissionError) as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"search_in_files Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── read_file ─────────────────────────────────────────────────────────────────

@tool(
    name="read_file",
    description=(
        "Liest den Inhalt einer Datei. "
        "Absolute und relative Pfade (relativ zu HOME) werden unterstützt. "
        "Gibt bei großen Dateien nur die ersten 50.000 Zeichen zurück."
    ),
    parameters=[
        P("path", "string", "Dateipfad (absolut oder relativ zu HOME)", required=True),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def read_file(path: str) -> dict:
    try:
        full_path = _resolve_path(path)
        _check_read(full_path)

        if not full_path.is_file():
            raise FileNotFoundError(f"'{full_path}' existiert nicht oder ist kein File.")

        def _read():
            content = full_path.read_text(encoding="utf-8", errors="replace")
            truncated = False
            if len(content) > 50_000:
                content = content[:50_000]
                truncated = True
            return content, truncated

        content, truncated = await asyncio.to_thread(_read)
        log.info(f"read_file: {full_path} ({len(content)} Zeichen)")
        return {
            "status": "success",
            "path": str(full_path),
            "content": content,
            "truncated": truncated,
        }

    except (FileNotFoundError, PermissionError) as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"read_file Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── write_file ────────────────────────────────────────────────────────────────

@tool(
    name="write_file",
    description=(
        "Schreibt Inhalt in eine Datei. "
        "Erlaubt nur Pfade unter /home und /tmp (kein versehentliches System-Schreiben). "
        "Erstellt fehlende Verzeichnisse automatisch."
    ),
    parameters=[
        P("path",    "string", "Dateipfad (absolut oder relativ zu HOME)", required=True),
        P("content", "string", "Der zu schreibende Inhalt", required=True),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def write_file(path: str, content: str) -> dict:
    try:
        full_path = _resolve_path(path)
        _check_write(full_path)

        def _write():
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        await asyncio.to_thread(_write)
        log.info(f"write_file: {full_path} ({len(content)} Zeichen)")
        return {
            "status": "success",
            "path": str(full_path),
            "bytes_written": len(content.encode("utf-8")),
        }

    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"write_file Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
