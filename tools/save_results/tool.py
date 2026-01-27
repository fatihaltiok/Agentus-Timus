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
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Union

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

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

@method
async def save_research_result(
    title: str,
    content: str,
    format: str = "markdown",
    metadata: Optional[Dict[str, Any]] = None
) -> Union[Success, Error]:
    """
    Speichert Recherche-Ergebnisse oder Berichte als Datei.
    
    Args:
        title: Titel des Dokuments (wird für Dateinamen verwendet)
        content: Der zu speichernde Inhalt
        format: "markdown" oder "text"
        metadata: Optionale Metadaten als Dictionary
    
    Returns:
        Success mit Dateipfad oder Error
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
        
        return Success({
            "status": "success",
            "filepath": str(filepath),
            "filename": filename,
            "size_bytes": file_size,
            "format": format
        })
        
    except PermissionError:
        msg = f"Keine Schreibberechtigung für {RESULTS_DIR}"
        logger.error(msg)
        return Error(code=-32000, message=msg)
        
    except Exception as e:
        logger.error(f"Fehler beim Speichern: {e}", exc_info=True)
        return Error(code=-32000, message=f"Speicherfehler: {str(e)}")


@method
async def list_saved_results(
    limit: int = 20,
    file_types: Optional[List[str]] = None
) -> Union[Success, Error]:
    """
    Listet die zuletzt gespeicherten Dateien auf.
    
    Args:
        limit: Maximale Anzahl Dateien (Standard: 20)
        file_types: Filter für Dateitypen, z.B. [".md", ".txt"]
    
    Returns:
        Success mit Liste der Dateien
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
        
        return Success({
            "count": len(files),
            "files": files[:limit],
            "directory": str(RESULTS_DIR),
            "total_in_directory": len(files)
        })
        
    except Exception as e:
        logger.error(f"Fehler beim Auflisten: {e}")
        return Error(code=-32001, message=str(e))


@method
async def get_result_content(filename: str) -> Union[Success, Error]:
    """
    Liest den Inhalt einer gespeicherten Datei.
    
    Args:
        filename: Name der Datei
    
    Returns:
        Success mit Dateiinhalt
    """
    try:
        filepath = RESULTS_DIR / filename
        
        if not filepath.exists():
            return Error(code=-32602, message=f"Datei nicht gefunden: {filename}")
        
        if not filepath.is_file():
            return Error(code=-32602, message=f"Kein gültiger Dateipfad: {filename}")
        
        # Sicherheitsprüfung: Datei muss im RESULTS_DIR sein
        if RESULTS_DIR not in filepath.resolve().parents and filepath.resolve() != RESULTS_DIR:
            if not str(filepath.resolve()).startswith(str(RESULTS_DIR)):
                return Error(code=-32602, message="Ungültiger Dateipfad")
        
        content = filepath.read_text(encoding="utf-8")
        
        return Success({
            "filename": filename,
            "content": content,
            "size_bytes": len(content)
        })
        
    except UnicodeDecodeError:
        return Error(code=-32000, message=f"Datei ist keine Textdatei: {filename}")
    except Exception as e:
        return Error(code=-32000, message=str(e))


@method
async def delete_result(filename: str) -> Union[Success, Error]:
    """
    Löscht eine gespeicherte Datei.
    
    Args:
        filename: Name der zu löschenden Datei
    
    Returns:
        Success bei Erfolg
    """
    try:
        filepath = RESULTS_DIR / filename
        
        if not filepath.exists():
            return Error(code=-32602, message=f"Datei nicht gefunden: {filename}")
        
        # Sicherheitsprüfung
        if not str(filepath.resolve()).startswith(str(RESULTS_DIR.resolve())):
            return Error(code=-32602, message="Ungültiger Dateipfad")
        
        filepath.unlink()
        
        logger.info(f"🗑️ Datei gelöscht: {filename}")
        
        return Success({
            "status": "deleted",
            "filename": filename
        })
        
    except PermissionError:
        return Error(code=-32000, message=f"Keine Berechtigung zum Löschen: {filename}")
    except Exception as e:
        return Error(code=-32000, message=str(e))


# --- Registrierung ---
register_tool("save_research_result", save_research_result)
register_tool("list_saved_results", list_saved_results)
register_tool("get_result_content", get_result_content)
register_tool("delete_result", delete_result)

logger.info(f"✅ Save Results Tool v2.0 registriert (Ziel: {RESULTS_DIR})")
