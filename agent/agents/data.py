"""
DataAgent — CSV, XLSX, JSON Analyse, Berichte, Statistiken.

Erweiterungen gegenüber BaseAgent:
  - Kontext: Bekannte Datenpfade + letzte Datendateien automatisch geladen
  - max_iterations=25 für mehrstufige Analyse-Workflows
  - _build_data_context(): scannt Downloads/, data/, results/ nach Datendateien
  - Große Datensätze: Sampling-Hinweis (> 5.000 Zeilen)
  - Kodierungs-Fallback: UTF-8 → Latin-1 → CP1252 bekannt
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from agent.base_agent import BaseAgent
from agent.prompts import DATA_PROMPT_TEMPLATE

log = logging.getLogger("DataAgent")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR     = _PROJECT_ROOT / "data"
_RESULTS_DIR  = _PROJECT_ROOT / "results"
_HOME         = Path.home()
_DOWNLOADS    = _HOME / "Downloads"
_DOCUMENTS    = _HOME / "Documents"

_DATA_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".tsv"}
_MAX_SCAN_FILES  = 10


class DataAgent(BaseAgent):
    """
    Datenanalyst von Timus.

    Liest CSV, XLSX und JSON ein, berechnet Statistiken und erstellt
    strukturierte Berichte (XLSX, PDF, DOCX).

    Vor jedem Task wird automatisch ein Daten-Kontext geladen:
    bekannte Datenpfade, zuletzt geänderte Datendateien, Größenhinweise.
    """

    def __init__(self, tools_description_string: str) -> None:
        super().__init__(
            DATA_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=25,
            agent_type="data",
        )

    # ------------------------------------------------------------------
    # Erweiterter run()-Einstieg: Daten-Kontext injizieren
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        """Reichert den Task mit bekannten Datenpfaden und aktuellen Dateien an."""
        context = await self._build_data_context()
        enriched_task = task + "\n\n" + context
        return await super().run(enriched_task)

    # ------------------------------------------------------------------
    # Daten-Kontext aufbauen
    # ------------------------------------------------------------------

    async def _build_data_context(self) -> str:
        """
        Erstellt Kontext für den Data-Agent:
        - Bekannte Datenpfade
        - Zuletzt geänderte Datendateien in Downloads/, data/, results/
        - Aktuelle Zeit
        """
        lines: list[str] = ["# DATEN-KONTEXT (automatisch geladen)"]

        # 1. Bekannte Pfade
        lines.append(f"Projektpfad: {_PROJECT_ROOT}")
        lines.append(f"Daten-Ordner: {_DATA_DIR}")
        lines.append(f"Ergebnisse: {_RESULTS_DIR}")
        lines.append(f"Downloads: {_DOWNLOADS}")

        # 2. Aktuelle Datendateien (parallel scannen)
        recent_files = await asyncio.to_thread(self._scan_recent_data_files)
        if recent_files:
            lines.append("Zuletzt geänderte Datendateien:")
            for entry in recent_files:
                lines.append(f"  {entry}")
        else:
            lines.append("Keine Datendateien in Standardpfaden gefunden.")

        # 3. Ergebnis-Dateien (letzte 3)
        recent_results = await asyncio.to_thread(self._scan_results)
        if recent_results:
            lines.append("Letzte Ergebnisse in results/:")
            for entry in recent_results:
                lines.append(f"  {entry}")

        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    def _scan_recent_data_files(self) -> list[str]:
        """Scannt bekannte Ordner nach Datendateien, sortiert nach Änderungsdatum."""
        scan_dirs = [_DOWNLOADS, _DATA_DIR, _DOCUMENTS]
        found: list[tuple[float, Path]] = []

        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            try:
                for f in scan_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in _DATA_EXTENSIONS:
                        found.append((f.stat().st_mtime, f))
            except Exception:
                continue

        # Neueste zuerst, max 10
        found.sort(key=lambda x: x[0], reverse=True)
        result = []
        for mtime, f in found[:_MAX_SCAN_FILES]:
            size_kb = f.stat().st_size // 1024
            size_str = f"{size_kb:,} KB" if size_kb < 1024 else f"{size_kb // 1024:,} MB"
            result.append(f"{f} ({size_str})")
        return result

    def _scan_results(self) -> list[str]:
        """Gibt die 3 zuletzt erstellten Ergebnisdateien zurück."""
        if not _RESULTS_DIR.exists():
            return []
        try:
            files = sorted(
                [f for f in _RESULTS_DIR.iterdir() if f.is_file()],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            return [str(f.name) for f in files[:3]]
        except Exception:
            return []
