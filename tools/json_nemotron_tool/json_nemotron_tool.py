"""JSON-Nemotron Tool - AI-gestützte JSON-Verarbeitung.

Dieses Tool nutzt Nemotron (via OpenRouter) für:
A. JSON-Repair - Repariert fehlerhafte/broken JSON
B. NumPy→JSON Converter - Konvertiert komplexe Datenstrukturen
C. JSON-Validierung - Schema-Validierung & Optimierung

Autor: Timus v4.4
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

import httpx

log = logging.getLogger("TimusAgent-v4.4")

# Nemotron Konfiguration
NEMOTRON_MODEL = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Prompts für die verschiedenen Modi
JSON_REPAIR_PROMPT = """Du bist ein JSON-Repair-Experte. Deine Aufgabe ist es, fehlerhaftes oder broken JSON zu analysieren und zu reparieren.

REGELN:
1. Identifiziere den Fehler (fehlende Klammern, ungültige Zeichen, etc.)
2. Erstelle valides, wohlgeformtes JSON
3. Versuche den ursprünglichen Inhalt/Wert so gut wie möglich zu erhalten
4. Wenn der Input gar nicht JSON-ähnlich ist, erstelle ein sinnvolles JSON-Objekt mit error-Meldung

EINGABE:
```
{broken_json}
```

ANTWORTE NUR mit dem reparierten JSON, ohne Erklärungen, ohne Markdown-Code-Blocks, nur reiner JSON-Text."""

NUMPY_CONVERT_PROMPT = """Du bist ein Daten-Konverter-Experte. Deine Aufgabe ist es, Python/NumPy-Datenstrukturen in sauberes JSON zu konvertieren.

REGELN:
1. Konvertiere NumPy-Typen (bool_, int64, float64, ndarray) zu nativen JSON-Typen
2. Ersetze numpy.bool_ mit true/false
3. Ersetze numpy.int*/float* mit Zahlen
4. Konvertiere numpy.ndarray zu Arrays
5. Entferne alle nicht-JSON-serialisierbaren Objekte oder konvertiere sie zu Strings
6. Das Ergebnis MUSS 100% valides JSON sein

EINGABE-DATEN:
```python
{data}
```

ANTWORTE NUR mit dem JSON-Output, ohne Erklärungen, ohne Markdown-Code-Blocks, nur reiner JSON-Text."""

JSON_VALIDATE_PROMPT = """Du bist ein JSON-Validierungs-Experte. Prüfe und optimiere JSON auf Schema-Korrektheit.

REGELN:
1. Validiere strikt nach JSON-Standard (RFC 8259)
2. Prüfe auf: korrekte Syntax, valide Datentypen, keine doppelten Keys
3. Wenn ein Schema angegeben ist: Validiere gegen das Schema
4. Optimiere: Entferne unnötige Whitespaces, normalisiere Zahlenformate
5. Berichte über alle gefundenen Probleme

EINGABE-JSON:
```json
{json_data}
```

SCHEMA (optional):
```json
{schema}
```

ANTWORTE im folgenden JSON-Format:
```json
{{
  "valid": true/false,
  "optimized_json": "...",
  "errors": ["Fehler 1", "Fehler 2"],
  "warnings": ["Warnung 1"],
  "statistics": {{
    "original_size": 123,
    "optimized_size": 100,
    "compression_ratio": 0.81
  }}
}}
```

Nur JSON-Output, keine zusätzlichen Erklärungen."""


class NemotronJSONClient:
    """Client für Nemotron-basierte JSON-Operationen."""

    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL
        self.model = NEMOTRON_MODEL
        self.http_client = httpx.AsyncClient(timeout=60.0)

        if not self.api_key:
            log.warning("OPENROUTER_API_KEY nicht gesetzt - Nemotron nicht verfügbar")

    async def _call_nemotron(self, prompt: str, temperature: float = 0.1) -> str:
        """Ruft Nemotron via OpenRouter API auf."""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY nicht konfiguriert")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://timus.local",
            "X-Title": "Timus JSON Nemotron Tool"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Du bist ein JSON-Experte. Antworte nur mit validem JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 4096
        }

        try:
            response = await self.http_client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.error(f"Nemotron API Fehler: {e}")
            raise

    async def repair_json(self, broken_json: str) -> Dict[str, Any]:
        """A. Repariert fehlerhaftes/broken JSON.

        Args:
            broken_json: Der fehlerhafte JSON-String

        Returns:
            Dict mit repaired_json, success-Flag und error-Info
        """
        log.info("JSON-Repair gestartet")

        try:
            # Zuerst versuchen wir es mit nativem Python Parser
            try:
                parsed = json.loads(broken_json)
                log.info("JSON war bereits valide - keine Reparatur nötig")
                return {
                    "success": True,
                    "repaired_json": json.dumps(parsed, ensure_ascii=False),
                    "was_already_valid": True,
                    "method": "native"
                }
            except json.JSONDecodeError:
                pass  # Weiter zu Nemotron

            # Nemotron für Reparatur nutzen
            prompt = JSON_REPAIR_PROMPT.format(broken_json=broken_json)
            repaired = await self._call_nemotron(prompt, temperature=0.1)

            # Bereinige die Antwort (entferne Markdown-Code-Blocks)
            repaired = self._clean_json_response(repaired)

            # Validiere das Ergebnis
            try:
                parsed = json.loads(repaired)
                return {
                    "success": True,
                    "repaired_json": json.dumps(parsed, ensure_ascii=False, indent=2),
                    "was_already_valid": False,
                    "method": "nemotron"
                }
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Reparatur fehlgeschlagen: {str(e)}",
                    "raw_output": repaired[:500]
                }

        except Exception as e:
            log.error(f"JSON-Repair Fehler: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def convert_numpy_to_json(self, data: Any) -> Dict[str, Any]:
        """B. Konvertiert NumPy/Komplexe Datenstrukturen zu JSON.

        Args:
            data: Python-Daten mit potenziellen NumPy-Typen

        Returns:
            Dict mit converted_json und info über Typ-Konvertierungen
        """
        log.info("NumPy→JSON Konvertierung gestartet")

        try:
            # Daten als String repräsentieren
            data_str = repr(data)

            # Versuche zuerst native Konvertierung
            try:
                converted = self._native_numpy_convert(data)
                json_str = json.dumps(converted, ensure_ascii=False, cls=NumpyEncoder)
                return {
                    "success": True,
                    "converted_json": json_str,
                    "method": "native",
                    "types_converted": ["native_numpy_types"]
                }
            except (TypeError, ValueError):
                pass  # Weiter zu Nemotron

            # Nemotron für komplexe Konvertierung
            prompt = NUMPY_CONVERT_PROMPT.format(data=data_str[:10000])  # Limit für Token
            converted = await self._call_nemotron(prompt, temperature=0.1)

            # Bereinige die Antwort
            converted = self._clean_json_response(converted)

            try:
                parsed = json.loads(converted)
                return {
                    "success": True,
                    "converted_json": json.dumps(parsed, ensure_ascii=False, indent=2),
                    "method": "nemotron",
                    "types_converted": ["complex_numpy_structures"]
                }
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Konvertierung fehlgeschlagen: {str(e)}",
                    "raw_output": converted[:500]
                }

        except Exception as e:
            log.error(f"NumPy→JSON Fehler: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def validate_json(self, json_data: str, schema: Optional[str] = None) -> Dict[str, Any]:
        """C. Validiert und optimiert JSON.

        Args:
            json_data: Der zu validierende JSON-String
            schema: Optionales JSON-Schema für Validierung

        Returns:
            Dict mit valid-Flag, optimized_json, errors, warnings, statistics
        """
        log.info("JSON-Validierung gestartet")

        try:
            prompt = JSON_VALIDATE_PROMPT.format(
                json_data=json_data[:8000],
                schema=schema if schema else "Kein Schema angegeben"
            )

            result = await self._call_nemotron(prompt, temperature=0.1)
            result = self._clean_json_response(result)

            try:
                parsed = json.loads(result)
                return {
                    "success": True,
                    **parsed
                }
            except json.JSONDecodeError:
                # Fallback: Native Validierung
                return self._native_validate(json_data)

        except Exception as e:
            log.error(f"JSON-Validierung Fehler: {e}")
            return {
                "success": False,
                "valid": False,
                "error": str(e)
            }

    def _clean_json_response(self, response: str) -> str:
        """Entfernt Markdown-Code-Blocks und bereinigt JSON-Antwort."""
        # Entferne ```json und ```
        lines = response.strip().split('\n')
        cleaned_lines = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue
            if not in_code_block or line.strip():
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    def _native_numpy_convert(self, data: Any) -> Any:
        """Native Python-Konvertierung von NumPy-Typen."""
        import numpy as np

        if isinstance(data, np.ndarray):
            return data.tolist()
        elif isinstance(data, np.bool_):
            return bool(data)
        elif isinstance(data, (np.integer, np.int64, np.int32)):
            return int(data)
        elif isinstance(data, (np.floating, np.float64, np.float32)):
            return float(data)
        elif isinstance(data, dict):
            return {k: self._native_numpy_convert(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._native_numpy_convert(item) for item in data]
        return data

    def _native_validate(self, json_data: str) -> Dict[str, Any]:
        """Fallback: Native JSON-Validierung ohne Nemotron."""
        try:
            parsed = json.loads(json_data)
            optimized = json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))

            return {
                "success": True,
                "valid": True,
                "optimized_json": optimized,
                "errors": [],
                "warnings": [],
                "statistics": {
                    "original_size": len(json_data),
                    "optimized_size": len(optimized),
                    "compression_ratio": len(optimized) / len(json_data) if json_data else 1.0
                },
                "method": "native_fallback"
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "valid": False,
                "error": str(e),
                "method": "native_fallback"
            }


class NumpyEncoder(json.JSONEncoder):
    """JSON Encoder der NumPy Typen zu nativen Python Typen konvertiert."""

    def default(self, obj):
        # NumPy boolean
        if hasattr(obj, 'dtype') and obj.dtype == bool:
            return bool(obj)
        # NumPy integer
        if hasattr(obj, 'dtype') and 'int' in str(obj.dtype):
            return int(obj)
        # NumPy float
        if hasattr(obj, 'dtype') and 'float' in str(obj.dtype):
            return float(obj)
        # NumPy ndarray
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        # Generischer Fallback
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


# Singleton-Instanz
_nemotron_client: Optional[NemotronJSONClient] = None


def get_nemotron_client() -> NemotronJSONClient:
    """Gibt die Singleton-Instanz des Nemotron-Clients zurück."""
    global _nemotron_client
    if _nemotron_client is None:
        _nemotron_client = NemotronJSONClient()
    return _nemotron_client


# ═══════════════════════════════════════════════════════════════════════════════
# JSON-RPC METHODEN (Für MCP Server Registration)
# ═══════════════════════════════════════════════════════════════════════════════

async def repair_broken_json(broken_json: str) -> Dict[str, Any]:
    """Repariert fehlerhaftes/broken JSON.

    JSON-RPC Methode für den MCP Server.

    Args:
        broken_json: Der fehlerhafte JSON-String

    Returns:
        Dict mit repaired_json, success, etc.
    """
    client = get_nemotron_client()
    return await client.repair_json(broken_json)


async def convert_numpy_to_json(data: Any) -> Dict[str, Any]:
    """Konvertiert NumPy-Datenstrukturen zu JSON.

    JSON-RPC Methode für den MCP Server.

    Args:
        data: Python-Daten mit potenziellen NumPy-Typen

    Returns:
        Dict mit converted_json und Info
    """
    client = get_nemotron_client()
    return await client.convert_numpy_to_json(data)


async def validate_and_optimize_json(json_data: str, schema: Optional[str] = None) -> Dict[str, Any]:
    """Validiert und optimiert JSON.

    JSON-RPC Methode für den MCP Server.

    Args:
        json_data: Der zu validierende JSON-String
        schema: Optionales JSON-Schema

    Returns:
        Dict mit valid, optimized_json, errors, warnings
    """
    client = get_nemotron_client()
    return await client.validate_json(json_data, schema)


async def sanitize_api_response(response_data: Any) -> str:
    """Universal-Methode: Bereinigt beliebige API-Responses für JSON-Serialisierung.

    Dies ist die Hauptmethode für den mcp_server.py Fix - sie versucht
    zuerst native Konvertierung, dann Nemotron als Fallback.

    Args:
        response_data: Beliebige Python-Datenstruktur

    Returns:
        JSON-String, garantiert serialisierbar
    """
    # Schnell-Check: Ist es bereits serialisierbar?
    try:
        return json.dumps(response_data, ensure_ascii=False, cls=NumpyEncoder)
    except (TypeError, ValueError):
        pass

    # Nemotron Konvertierung
    try:
        client = get_nemotron_client()
        result = await client.convert_numpy_to_json(response_data)
        if result.get("success"):
            return result["converted_json"]
    except Exception as e:
        log.warning(f"Nemotron Konvertierung fehlgeschlagen: {e}")

    # Letzter Fallback: String-Konvertierung
    try:
        return json.dumps({"_sanitized_data": str(response_data)})
    except:
        return json.dumps({"_error": "Konvertierung nicht möglich"})


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRATION (MCP Server Integration)
# ═══════════════════════════════════════════════════════════════════════════════

# Lazy import für Tool-Registration
try:
    from tools.tool_registry_v2 import registry_v2, ToolParameter as P, ToolCategory as C

    @registry_v2.register(
        name="repair_broken_json",
        description="Repariert fehlerhaftes/broken JSON mit Nemotron AI. Identifiziert Syntax-Fehler und erstellt valides JSON.",
        parameters=[
            P("broken_json", "string", "Der fehlerhafte JSON-String der repariert werden soll", required=True)
        ],
        capabilities=["json", "repair", "ai"],
        category=C.ANALYSIS,
        returns="dict"
    )
    async def _repair_broken_json_tool(broken_json: str) -> Dict[str, Any]:
        """Tool-Wrapper für repair_broken_json."""
        return await repair_broken_json(broken_json)

    @registry_v2.register(
        name="convert_numpy_to_json",
        description="Konvertiert NumPy-Datenstrukturen (bool_, int64, float64, ndarray) zu sauberem JSON. Nutzt Nemotron für komplexe Fälle.",
        parameters=[
            P("data", "object", "Python-Daten mit potenziellen NumPy-Typen", required=True)
        ],
        capabilities=["json", "numpy", "conversion"],
        category=C.ANALYSIS,
        returns="dict"
    )
    async def _convert_numpy_tool(data: Any) -> Dict[str, Any]:
        """Tool-Wrapper für convert_numpy_to_json."""
        return await convert_numpy_to_json(data)

    @registry_v2.register(
        name="validate_and_optimize_json",
        description="Validiert JSON gegen Schema und optimiert Format/Größe. Reduziert Dateigröße, prüft Syntax.",
        parameters=[
            P("json_data", "string", "Der zu validierende JSON-String", required=True),
            P("schema", "string", "Optionales JSON-Schema für Validierung", required=False, default=None)
        ],
        capabilities=["json", "validation", "optimization"],
        category=C.ANALYSIS,
        returns="dict"
    )
    async def _validate_json_tool(json_data: str, schema: Optional[str] = None) -> Dict[str, Any]:
        """Tool-Wrapper für validate_and_optimize_json."""
        return await validate_and_optimize_json(json_data, schema)

    @registry_v2.register(
        name="sanitize_api_response",
        description="Universal-Methode zur Bereinigung beliebiger API-Responses für JSON-Serialisierung. Fallback für NumPy/broken JSON.",
        parameters=[
            P("response_data", "object", "Beliebige Python-Datenstruktur die serialisiert werden muss", required=True)
        ],
        capabilities=["json", "sanitization", "api"],
        category=C.ANALYSIS,
        returns="string"
    )
    async def _sanitize_response_tool(response_data: Any) -> str:
        """Tool-Wrapper für sanitize_api_response."""
        return await sanitize_api_response(response_data)

    log.info("✅ JSON-Nemotron Tools registriert: repair_broken_json, convert_numpy_to_json, validate_and_optimize_json, sanitize_api_response")

except ImportError as e:
    log.warning(f"⚠️ Tool-Registry nicht verfügbar - JSON-Nemotron Tools nicht registriert: {e}")
except Exception as e:
    log.error(f"❌ Fehler bei JSON-Nemotron Tool-Registration: {e}")
