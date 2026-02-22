# tools/data_tool/tool.py
"""
Datenanalyse-Tools für den data-Agenten.

Liest CSV, XLSX und JSON ein und berechnet Statistiken.
Gibt strukturierte Dicts zurück, die der Agent direkt
in create_pdf / create_xlsx weiterverarbeiten kann.
"""

import asyncio
import json
import logging
from pathlib import Path

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    # relativ zu HOME versuchen, dann zu Projekt-Root
    home_p = Path.home() / path
    if home_p.exists():
        return home_p
    return (_PROJECT_ROOT / path).resolve()


# ── read_data_file ────────────────────────────────────────────────

@tool(
    name="read_data_file",
    description=(
        "Liest eine CSV-, XLSX- oder JSON-Datei ein und gibt die Daten "
        "als strukturierte Tabelle zurück (Spalten + Zeilen). "
        "Unterstützt absolute und relative Pfade (relativ zu HOME)."
    ),
    parameters=[
        P("path", "string", "Pfad zur Datei (CSV, XLSX oder JSON)", required=True),
        P("sheet", "string", "Excel-Tabellenblatt-Name (nur bei XLSX, Standard: erstes Blatt)", required=False),
        P("limit", "integer", "Maximale Anzahl Zeilen (Standard: 1000)", required=False),
    ],
    capabilities=["data", "file"],
    category=C.FILE
)
async def read_data_file(path: str, sheet: str = None, limit: int = 1000) -> dict:
    def _read():
        import pandas as pd

        fp = _resolve(path)
        if not fp.exists():
            return {"status": "error", "message": f"Datei nicht gefunden: {fp}"}

        ext = fp.suffix.lower()
        limit_n = max(1, min(10_000, int(limit)))

        if ext == ".csv":
            # Trennzeichen automatisch erkennen
            df = pd.read_csv(fp, sep=None, engine="python", nrows=limit_n, dtype=str)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(fp, sheet_name=sheet or 0, nrows=limit_n, dtype=str)
        elif ext == ".json":
            with open(fp, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                df = pd.DataFrame(raw).head(limit_n)
            elif isinstance(raw, dict):
                df = pd.DataFrame([raw])
            else:
                return {"status": "error", "message": "JSON-Format nicht erkannt (erwartet Liste oder Objekt)"}
        else:
            return {"status": "error", "message": f"Nicht unterstütztes Format: {ext}"}

        columns  = list(df.columns)
        rows     = df.fillna("").values.tolist()
        total    = len(rows)

        return {
            "status": "success",
            "path": str(fp),
            "format": ext.lstrip("."),
            "columns": columns,
            "rows": rows,
            "total_rows": total,
            "truncated": total >= limit_n,
        }

    try:
        result = await asyncio.to_thread(_read)
        log.info(f"read_data_file: {path} → {result.get('total_rows', '?')} Zeilen")
        return result
    except Exception as e:
        log.error(f"read_data_file Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ── analyze_data ──────────────────────────────────────────────────

@tool(
    name="analyze_data",
    description=(
        "Berechnet Statistiken für eine Datentabelle: Summe, Durchschnitt, Min, Max, "
        "Anzahl, eindeutige Werte pro Spalte. "
        "Eingabe ist das Ergebnis von read_data_file (columns + rows). "
        "Gibt einen Statistik-Dict zurück der direkt in einen Bericht einfließen kann."
    ),
    parameters=[
        P("columns", "array",  "Spaltennamen (aus read_data_file)", required=True),
        P("rows",    "array",  "Datenzeilen (aus read_data_file)", required=True),
        P("numeric_columns", "array", "Welche Spalten numerisch auswerten (leer = automatisch erkennen)", required=False),
    ],
    capabilities=["data"],
    category=C.FILE
)
async def analyze_data(columns: list, rows: list, numeric_columns: list = None) -> dict:
    def _analyze():
        import pandas as pd

        df = pd.DataFrame(rows, columns=columns)

        # Numerische Spalten bestimmen
        if numeric_columns:
            num_cols = [c for c in numeric_columns if c in df.columns]
        else:
            # Automatisch: Spalten die zu Zahlen konvertierbar sind
            num_cols = []
            for col in df.columns:
                try:
                    pd.to_numeric(df[col].str.replace(",", "."), errors="raise")
                    num_cols.append(col)
                except Exception:
                    pass

        stats = {}
        for col in num_cols:
            series = pd.to_numeric(df[col].str.replace(",", "."), errors="coerce")
            stats[col] = {
                "summe":       round(float(series.sum()), 2),
                "durchschnitt": round(float(series.mean()), 2),
                "min":         round(float(series.min()), 2),
                "max":         round(float(series.max()), 2),
                "anzahl":      int(series.count()),
                "fehlend":     int(series.isna().sum()),
            }

        # Kategorische Spalten
        cat_stats = {}
        cat_cols = [c for c in df.columns if c not in num_cols]
        for col in cat_cols[:10]:  # max 10 kategorische Spalten
            vc = df[col].value_counts().head(5)
            cat_stats[col] = {
                "eindeutige_werte": int(df[col].nunique()),
                "top5": {str(k): int(v) for k, v in vc.items()},
            }

        return {
            "status": "success",
            "gesamt_zeilen": len(df),
            "gesamt_spalten": len(df.columns),
            "numerisch": stats,
            "kategorisch": cat_stats,
        }

    try:
        result = await asyncio.to_thread(_analyze)
        log.info(f"analyze_data: {result.get('gesamt_zeilen')} Zeilen, {len(result.get('numerisch', {}))} num. Spalten")
        return result
    except Exception as e:
        log.error(f"analyze_data Fehler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
