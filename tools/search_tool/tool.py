# tools/search_tool/tool.py (FIXED VERSION v2.0)
"""
Repariertes Search Tool für DataForSEO API.
Fixes:
1. Robustere Fehlerbehandlung
2. Besseres Response-Parsing
3. Fallback bei API-Fehlern
4. Konsistente Rückgabetypen
"""

import os
import json
import logging
import asyncio
import base64
from typing import List, Dict, Any, Optional, Union

import requests
from dotenv import load_dotenv
from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool

# --- Logging Setup ---
logger = logging.getLogger("search_tool")

# --- Umgebungsvariablen ---
load_dotenv()
DATAFORSEO_USER = os.getenv("DATAFORSEO_USER")
DATAFORSEO_PASS = os.getenv("DATAFORSEO_PASS")

if not (DATAFORSEO_USER and DATAFORSEO_PASS):
    logger.warning("⚠️ DATAFORSEO_USER oder DATAFORSEO_PASS fehlt. Websuche wird fehlschlagen.")

# --- API Konstanten ---
DATAFORSEO_BASE_URL = "https://api.dataforseo.com"
DEFAULT_API_TIMEOUT = 45

# Endpunkt-Mapping
API_ENDPOINTS = {
    # Google
    ("google", "organic"): "/v3/serp/google/organic/live/advanced",
    ("google", "news"): "/v3/serp/google/news/live/advanced",
    ("google", "images"): "/v3/serp/google/images/live/advanced",
    ("google", "scholar"): "/v3/serp/google/scholar/live/organic",
    ("google", "maps"): "/v3/serp/google/maps/live/advanced",
    
    # Bing
    ("bing", "organic"): "/v3/serp/bing/organic/live/regular",
    ("bing", "news"): "/v3/serp/bing/news/live/regular",
    
    # DuckDuckGo
    ("duckduckgo", "organic"): "/v3/serp/duckduckgo/organic/live/advanced",
    
    # Yahoo
    ("yahoo", "organic"): "/v3/serp/yahoo/organic/live/advanced",
}

# Location Codes (häufig verwendet)
LOCATION_CODES = {
    "de": 2276,      # Deutschland
    "at": 2040,      # Österreich
    "ch": 2756,      # Schweiz
    "us": 2840,      # USA
    "uk": 2826,      # UK
    "fr": 2250,      # Frankreich
}


def _get_auth_header() -> Dict[str, str]:
    """Erstellt den Authorization Header für DataForSEO."""
    if not (DATAFORSEO_USER and DATAFORSEO_PASS):
        logger.error("DataForSEO Credentials fehlen!")
        return {"Content-Type": "application/json"}
    
    credentials = f"{DATAFORSEO_USER}:{DATAFORSEO_PASS}"
    encoded = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json"
    }


def _parse_search_results(api_response: Dict, max_results: int) -> List[Dict[str, Any]]:
    """
    Parst die DataForSEO API Response und extrahiert Suchergebnisse.
    
    Args:
        api_response: Die rohe API-Antwort
        max_results: Maximale Anzahl Ergebnisse
    
    Returns:
        Liste von Suchergebnis-Dictionaries
    """
    results: List[Dict[str, Any]] = []
    
    try:
        tasks = api_response.get("tasks", [])
        if not tasks:
            return results
        
        first_task = tasks[0]
        
        # Prüfe Task-Status
        if first_task.get("status_code") != 20000:
            logger.warning(f"Task-Fehler: {first_task.get('status_message')}")
            return results
        
        # Extrahiere Items
        task_results = first_task.get("result", [])
        
        for result_wrapper in task_results:
            if not isinstance(result_wrapper, dict):
                continue
            
            items = result_wrapper.get("items", [])
            
            for item in items:
                if len(results) >= max_results:
                    break
                
                if not isinstance(item, dict):
                    continue
                
                # URL validieren
                url = item.get("url", "")
                if not url or not url.startswith(("http://", "https://")):
                    continue
                
                # Ergebnis formatieren
                result_entry = {
                    "title": str(item.get("title", "Ohne Titel")).strip(),
                    "url": url,
                    "snippet": str(item.get("description", item.get("snippet", ""))).strip(),
                    "type": item.get("type", "organic"),
                    "position": item.get("rank_absolute", item.get("position", 0)),
                }
                
                # Zusätzliche Felder je nach Typ
                if item.get("domain"):
                    result_entry["domain"] = item["domain"]
                if item.get("breadcrumb"):
                    result_entry["breadcrumb"] = item["breadcrumb"]
                
                results.append(result_entry)
        
    except Exception as e:
        logger.error(f"Fehler beim Parsen der Suchergebnisse: {e}")
    
    return results


def _search_sync(
    query: str,
    engine: str = "google",
    vertical: str = "organic",
    max_results: int = 10,
    language_code: str = "de",
    location_code: int = 2276,
    device: str = "desktop"
) -> List[Dict[str, Any]]:
    """
    Synchrone Suchfunktion für DataForSEO.
    
    Args:
        query: Suchanfrage
        engine: Suchmaschine (google, bing, duckduckgo, yahoo)
        vertical: Suchtyp (organic, news, images)
        max_results: Maximale Ergebnisse (1-100)
        language_code: Sprachcode (de, en, etc.)
        location_code: DataForSEO Location Code
        device: desktop oder mobile
    
    Returns:
        Liste von Suchergebnissen
    
    Raises:
        ValueError: Bei ungültigen Parametern
        ConnectionError: Bei Netzwerkproblemen
    """
    # Validierung
    if not query or not isinstance(query, str):
        raise ValueError(f"Ungültige Suchanfrage: '{query}'")
    
    query = query.strip()
    if not query:
        raise ValueError("Suchanfrage darf nicht leer sein")
    
    # Endpunkt ermitteln
    endpoint_key = (engine.lower(), vertical.lower())
    api_path = API_ENDPOINTS.get(endpoint_key)
    
    if not api_path:
        # Fallback auf Google Organic
        logger.warning(f"Unbekannte Kombination {endpoint_key}, verwende Google Organic")
        api_path = API_ENDPOINTS[("google", "organic")]
    
    url = DATAFORSEO_BASE_URL + api_path
    
    # Request-Payload
    payload = [{
        "keyword": query,
        "location_code": location_code,
        "language_code": language_code,
        "device": device,
        "depth": min(max_results, 100)  # DataForSEO limit
    }]
    
    headers = _get_auth_header()
    
    logger.info(f"🔍 Suche: '{query}' ({engine}/{vertical})")
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=DEFAULT_API_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        
        # API-Level Status prüfen
        if data.get("status_code") != 20000:
            error_msg = data.get("status_message", "Unbekannter API-Fehler")
            raise ValueError(f"DataForSEO API Fehler: {error_msg}")
        
        # Ergebnisse parsen
        results = _parse_search_results(data, max_results)
        
        logger.info(f"✅ {len(results)} Ergebnisse gefunden")
        return results
        
    except requests.exceptions.Timeout:
        raise ConnectionError(f"Timeout bei DataForSEO-Anfrage ({DEFAULT_API_TIMEOUT}s)")
    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(f"Verbindungsfehler: {e}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise ValueError("DataForSEO Authentifizierung fehlgeschlagen - Credentials prüfen")
        elif e.response.status_code == 402:
            raise ValueError("DataForSEO Guthaben aufgebraucht")
        raise ConnectionError(f"HTTP-Fehler: {e}")


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@method
async def search_web(
    query: str,
    engine: str = "google",
    vertical: str = "organic",
    max_results: int = 10,
    language_code: str = "de",
    location_code: int = 2276,
    device: str = "desktop"
) -> Union[Success, Error]:
    """
    Führt eine Websuche mit DataForSEO durch.
    
    Args:
        query: Die Suchanfrage
        engine: Suchmaschine - "google", "bing", "duckduckgo", "yahoo"
        vertical: Suchtyp - "organic", "news", "images", "scholar", "maps"
        max_results: Maximale Anzahl Ergebnisse (1-100)
        language_code: Sprachcode z.B. "de", "en"
        location_code: DataForSEO Location Code (2276 = Deutschland)
        device: "desktop" oder "mobile"
    
    Returns:
        Success mit Liste von Suchergebnissen oder Error
    """
    logger.info(f"🔍 search_web: '{query}' ({engine}/{vertical})")
    
    # Credentials prüfen
    if not (DATAFORSEO_USER and DATAFORSEO_PASS):
        return Error(
            code=-32002,
            message="DataForSEO Credentials nicht konfiguriert. "
                   "Bitte DATAFORSEO_USER und DATAFORSEO_PASS in .env setzen."
        )
    
    try:
        # Synchrone Suche in Thread ausführen
        results = await asyncio.to_thread(
            _search_sync,
            query=query,
            engine=engine,
            vertical=vertical,
            max_results=max_results,
            language_code=language_code,
            location_code=location_code,
            device=device
        )
        
        # FIX: Immer Liste zurückgeben, nicht Success-wrapped
        # Das ist wichtig für call_tool_internal Kompatibilität
        return Success(results)
        
    except ValueError as e:
        logger.warning(f"Validierungsfehler: {e}")
        return Error(code=-32602, message=str(e))
        
    except ConnectionError as e:
        logger.error(f"Verbindungsfehler: {e}")
        return Error(code=-32000, message=str(e))
        
    except Exception as e:
        logger.error(f"Unerwarteter Fehler: {e}", exc_info=True)
        return Error(code=-32000, message=f"Interner Fehler: {str(e)}")


@method
async def search_news(
    query: str,
    max_results: int = 10,
    language_code: str = "de"
) -> Union[Success, Error]:
    """
    Convenience-Methode für News-Suche.
    
    Args:
        query: Suchanfrage
        max_results: Maximale Ergebnisse
        language_code: Sprache
    """
    return await search_web(
        query=query,
        engine="google",
        vertical="news",
        max_results=max_results,
        language_code=language_code
    )


@method
async def search_images(
    query: str,
    max_results: int = 10
) -> Union[Success, Error]:
    """
    Convenience-Methode für Bildersuche.
    
    Args:
        query: Suchanfrage
        max_results: Maximale Ergebnisse
    """
    return await search_web(
        query=query,
        engine="google",
        vertical="images",
        max_results=max_results
    )


@method
async def search_scholar(
    query: str,
    max_results: int = 10
) -> Union[Success, Error]:
    """
    Convenience-Methode für Google Scholar Suche.
    
    Args:
        query: Suchanfrage (wissenschaftlich)
        max_results: Maximale Ergebnisse
    """
    return await search_web(
        query=query,
        engine="google",
        vertical="scholar",
        max_results=max_results,
        language_code="en"  # Scholar ist meist englisch
    )


# --- Registrierung ---
register_tool("search_web", search_web)
register_tool("search_news", search_news)
register_tool("search_images", search_images)
register_tool("search_scholar", search_scholar)

logger.info("✅ Search Tool v2.0 (DataForSEO) registriert.")
