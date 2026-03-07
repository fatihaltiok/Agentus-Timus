# tools/save_results/tool.py (FIXED VERSION v2.0)
"""
Repariertes Save Results Tool.
Fixes:
1. Fehlende Union Import
2. Robustere Pfad-Behandlung
3. Bessere Fehlerbehandlung
"""

import os
import json
import logging
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# --- Setup ---
logger = logging.getLogger("save_results")

# Pfade bestimmen - mit Fallbacks
def _get_project_root() -> Path:
    """Ermittelt das Projekt-Root mit mehreren Fallbacks."""
    candidates = []

    # Methode 1: Relativ zu dieser Datei
    try:
        candidates.append(Path(__file__).resolve().parent.parent.parent)
    except Exception:
        pass

    # Methode 2: CWD
    candidates.append(Path.cwd())

    # Methode 3: Bekannte Pfade
    candidates.append(Path.home() / "dev" / "timus")
    candidates.append(Path("/home/fatih-ubuntu/dev/timus"))

    # Finde ersten gültigen Pfad
    for candidate in candidates:
        if candidate.exists() and (candidate / "tools").exists():
            return candidate

    # Fallback auf CWD
    return Path.cwd()

PROJECT_ROOT = _get_project_root()
RESULTS_DIR = PROJECT_ROOT / "results"

logger.info(f"📁 Save Results Tool initialisiert. PROJECT_ROOT={PROJECT_ROOT}, RESULTS_DIR={RESULTS_DIR}")


async def _notify_via_email(title: str, content: str, filename: str) -> None:
    """Sendet das gespeicherte Dokument per E-Mail."""
    try:
        recipient = os.getenv("USER_EMAIL_PRIMARY", "")
        if not recipient:
            return
        backend = os.getenv("EMAIL_BACKEND", "resend").lower()
        subject = f"Timus Dokument: {title[:80]}"
        body = f"Timus hat ein neues Dokument erstellt:\n\nDatei: {filename}\n\n{'='*60}\n\n{content[:8000]}"
        if len(content) > 8000:
            body += f"\n\n[... gekürzt — vollständig unter results/{filename}]"

        if backend == "resend":
            from utils.resend_email import send_email_resend
            await send_email_resend(to=recipient, subject=subject, body=body)
        else:
            from utils.smtp_email import send_email_smtp
            await send_email_smtp(to=recipient, subject=subject, body=body)
        logger.info(f"📧 Dokument '{filename}' per E-Mail gesendet")
    except Exception as e:
        logger.warning(f"E-Mail-Benachrichtigung fehlgeschlagen: {e}")


def _ensure_results_dir() -> Path:
    """Stellt sicher, dass das Ergebnis-Verzeichnis existiert."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR


def _sanitize_filename(text: str, max_length: int = 60) -> str:
    """Bereinigt einen String für die Verwendung als Dateiname."""
    # Nur alphanumerische Zeichen, Leerzeichen, Unterstriche und Bindestriche
    safe = "".join(c if c.isalnum() or c in (' ', '_', '-') else '' for c in text)
    safe = safe.strip().replace(" ", "_")
    return safe[:max_length]


def _artifact_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".md", ".txt", ".doc", ".docx"}:
        return "document"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    return "file"


def _build_file_artifact(path: Path) -> Dict[str, Any]:
    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return {
        "type": _artifact_type_for_path(path),
        "path": str(path.resolve()),
        "label": path.name,
        "mime": mime_type,
        "source": "save_results",
        "origin": "tool",
    }


def _format_markdown(title: str, content: str, metadata: Optional[Dict] = None) -> str:
    """Erstellt Markdown-formatierten Inhalt."""
    output_lines = [f"# {title}", ""]

    if metadata:
        output_lines.append("---")
        output_lines.append("**Metadaten:**")
        for key, value in metadata.items():
            val_str = str(value)
            if len(val_str) > 100:
                val_str = val_str[:100] + "..."
            output_lines.append(f"- **{key}:** {val_str}")
        output_lines.append("---")
        output_lines.append("")

    output_lines.append(content)

    return "\n".join(output_lines)


def _format_text(title: str, content: str, metadata: Optional[Dict] = None) -> str:
    """Erstellt Plain-Text-formatierten Inhalt."""
    output_lines = [
        f"TITEL: {title}",
        f"DATUM: {datetime.now().isoformat()}",
        "=" * 60,
        ""
    ]

    if metadata:
        output_lines.append("METADATEN:")
        for key, value in metadata.items():
            output_lines.append(f"  {key}: {value}")
        output_lines.append("-" * 60)
        output_lines.append("")

    output_lines.append(content)

    return "\n".join(output_lines)


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@tool(
    name="save_research_result",
    description="Speichert Recherche-Ergebnisse oder Berichte als Datei.",
    parameters=[
        P("title", "string", "Titel des Dokuments (wird für Dateinamen verwendet)", required=True),
        P("content", "string", "Der zu speichernde Inhalt", required=True),
        P("format", "string", "Dateiformat: 'markdown' oder 'text'", required=False, default="markdown"),
        P("metadata", "object", "Optionale Metadaten als Dictionary", required=False, default=None),
    ],
    capabilities=["file", "results"],
    category=C.FILE
)
async def save_research_result(
    title: str,
    content: str,
    format: str = "markdown",
    metadata: Optional[Dict[str, Any]] = None
) -> dict:
    """
    Speichert Recherche-Ergebnisse oder Berichte als Datei.

    Args:
        title: Titel des Dokuments (wird für Dateinamen verwendet)
        content: Der zu speichernde Inhalt
        format: "markdown" oder "text"
        metadata: Optionale Metadaten als Dictionary

    Returns:
        Dict mit Dateipfad oder Fehlermeldung
    """
    logger.info(f"📝 save_research_result aufgerufen: title='{title[:50]}...', format={format}, content_length={len(content)}")

    try:
        results_path = _ensure_results_dir()
        logger.info(f"📁 Results-Verzeichnis: {results_path}")

        # Dateinamen erstellen
        safe_title = _sanitize_filename(title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Extension basierend auf Format
        ext = "md" if format.lower() == "markdown" else "txt"
        filename = f"{timestamp}_{safe_title}.{ext}"
        filepath = results_path / filename

        logger.info(f"📄 Schreibe Datei: {filepath}")

        # Inhalt formatieren
        if format.lower() == "markdown":
            final_content = _format_markdown(title, content, metadata)
        else:
            final_content = _format_text(title, content, metadata)

        # Datei schreiben
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(final_content)

        file_size = len(final_content)

        # Prüfen ob Datei existiert
        if filepath.exists():
            logger.info(f"✅ Datei erfolgreich gespeichert: {filename} ({file_size} Bytes)")
        else:
            logger.error(f"❌ Datei wurde geschrieben aber existiert nicht: {filepath}")

        # E-Mail-Benachrichtigung mit Dokument-Inhalt
        await _notify_via_email(title, final_content, filename)

        return {
            "status": "success",
            "filepath": str(filepath),
            "filename": filename,
            "size_bytes": file_size,
            "format": format,
            "artifacts": [_build_file_artifact(filepath)],
        }

    except PermissionError:
        msg = f"Keine Schreibberechtigung für {RESULTS_DIR}"
        logger.error(msg)
        return {"status": "error", "message": msg}

    except Exception as e:
        logger.error(f"Fehler beim Speichern: {e}", exc_info=True)
        return {"status": "error", "message": f"Speicherfehler: {str(e)}"}


@tool(
    name="list_saved_results",
    description="Listet die zuletzt gespeicherten Dateien auf.",
    parameters=[
        P("limit", "integer", "Maximale Anzahl Dateien", required=False, default=20),
        P("file_types", "array", "Filter für Dateitypen, z.B. ['.md', '.txt']", required=False, default=None),
    ],
    capabilities=["file", "results"],
    category=C.FILE
)
async def list_saved_results(
    limit: int = 20,
    file_types: Optional[List[str]] = None
) -> dict:
    """
    Listet die zuletzt gespeicherten Dateien auf.

    Args:
        limit: Maximale Anzahl Dateien (Standard: 20)
        file_types: Filter für Dateitypen, z.B. [".md", ".txt"]

    Returns:
        Dict mit Liste der Dateien
    """
    try:
        _ensure_results_dir()

        # Standard-Dateitypen
        if file_types is None:
            file_types = ['.md', '.txt', '.json', '.png', '.pdf']

        files: List[Dict[str, Any]] = []

        for item in RESULTS_DIR.iterdir():
            if not item.is_file():
                continue

            if item.suffix.lower() not in file_types:
                continue

            try:
                stat = item.stat()
                files.append({
                    "filename": item.name,
                    "filepath": str(item),
                    "size_bytes": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": item.suffix
                })
            except Exception as e:
                logger.warning(f"Konnte Datei-Info nicht lesen: {item.name}: {e}")
                continue

        # Nach Erstellungsdatum sortieren (neueste zuerst)
        files.sort(key=lambda x: x["created"], reverse=True)

        return {
            "count": len(files),
            "files": files[:limit],
            "directory": str(RESULTS_DIR),
            "total_in_directory": len(files)
        }

    except Exception as e:
        logger.error(f"Fehler beim Auflisten: {e}")
        return {"status": "error", "message": str(e)}


@tool(
    name="get_result_content",
    description="Liest den Inhalt einer gespeicherten Datei.",
    parameters=[
        P("filename", "string", "Name der Datei", required=True),
    ],
    capabilities=["file", "results"],
    category=C.FILE
)
async def get_result_content(filename: str) -> dict:
    """
    Liest den Inhalt einer gespeicherten Datei.

    Args:
        filename: Name der Datei

    Returns:
        Dict mit Dateiinhalt
    """
    try:
        filepath = RESULTS_DIR / filename

        if not filepath.exists():
            raise Exception(f"Datei nicht gefunden: {filename}")

        if not filepath.is_file():
            raise Exception(f"Kein gültiger Dateipfad: {filename}")

        # Sicherheitsprüfung: Datei muss im RESULTS_DIR sein
        if RESULTS_DIR not in filepath.resolve().parents and filepath.resolve() != RESULTS_DIR:
            if not str(filepath.resolve()).startswith(str(RESULTS_DIR)):
                raise Exception("Ungültiger Dateipfad")

        content = filepath.read_text(encoding="utf-8")

        return {
            "filename": filename,
            "content": content,
            "size_bytes": len(content)
        }

    except UnicodeDecodeError:
        return {"status": "error", "message": f"Datei ist keine Textdatei: {filename}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@tool(
    name="delete_result",
    description="Löscht eine gespeicherte Datei.",
    parameters=[
        P("filename", "string", "Name der zu löschenden Datei", required=True),
    ],
    capabilities=["file", "results"],
    category=C.FILE
)
async def delete_result(filename: str) -> dict:
    """
    Löscht eine gespeicherte Datei.

    Args:
        filename: Name der zu löschenden Datei

    Returns:
        Dict bei Erfolg
    """
    try:
        filepath = RESULTS_DIR / filename

        if not filepath.exists():
            raise Exception(f"Datei nicht gefunden: {filename}")

        # Sicherheitsprüfung
        if not str(filepath.resolve()).startswith(str(RESULTS_DIR.resolve())):
            raise Exception("Ungültiger Dateipfad")

        filepath.unlink()

        logger.info(f"🗑️ Datei gelöscht: {filename}")

        return {
            "status": "deleted",
            "filename": filename
        }

    except PermissionError:
        return {"status": "error", "message": f"Keine Berechtigung zum Löschen: {filename}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
