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
import math
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from utils.location_presence import enrich_location_presence_snapshot
from utils.location_route import (
    normalize_route_travel_mode,
    parse_google_routes_compute_route,
    parse_serpapi_google_maps_directions,
)

# --- Logging Setup ---
logger = logging.getLogger("search_tool")

# --- Umgebungsvariablen ---
load_dotenv()
DATAFORSEO_USER = os.getenv("DATAFORSEO_USER")
DATAFORSEO_PASS = os.getenv("DATAFORSEO_PASS")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_ROUTES_API_KEY = os.getenv("GOOGLE_ROUTES_API_KEY") or GOOGLE_MAPS_API_KEY

if not (DATAFORSEO_USER and DATAFORSEO_PASS):
    logger.warning("⚠️ DATAFORSEO_USER oder DATAFORSEO_PASS fehlt. Websuche wird fehlschlagen.")

# --- API Konstanten ---
DATAFORSEO_BASE_URL = "https://api.dataforseo.com"
SERPAPI_BASE_URL = "https://serpapi.com/search.json"
GOOGLE_ROUTES_BASE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
DEFAULT_API_TIMEOUT = 45
DEFAULT_STANDARD_TIMEOUT = 90
DEFAULT_STANDARD_POLL_INTERVAL = 2.0
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_LOCATION_SNAPSHOT_PATH = _PROJECT_ROOT / "data" / "runtime_location_snapshot.json"

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

LANGUAGE_TO_LOCATION_CODE = {
    "de": 2276,
    "en": 2840,
    "fr": 2250,
    "es": 2724,
    "it": 2380,
}

SERPAPI_DIRECTIONS_TRAVEL_MODE = {
    "driving": "0",
    "transit": "1",
    "walking": "2",
    "bicycling": "3",
}

GOOGLE_ROUTES_TRAVEL_MODE = {
    "driving": "DRIVE",
    "transit": "TRANSIT",
    "walking": "WALK",
    "bicycling": "BICYCLE",
}

GOOGLE_ROUTES_FIELD_MASK = ",".join(
    (
        "routes.description",
        "routes.distanceMeters",
        "routes.duration",
        "routes.polyline.encodedPolyline",
        "routes.legs.distanceMeters",
        "routes.legs.duration",
        "routes.legs.startLocation",
        "routes.legs.endLocation",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.startLocation",
        "routes.legs.steps.endLocation",
        "routes.legs.steps.polyline.encodedPolyline",
        "routes.legs.steps.navigationInstruction.instructions",
    )
)


class DataForSEORetrievalMode(str, Enum):
    LIVE = "live"
    STANDARD = "standard"


class YouTubeRequestType(str, Enum):
    ORGANIC_SEARCH = "youtube_organic_search"
    VIDEO_INFO = "youtube_video_info"
    SUBTITLES = "youtube_subtitles"
    COMMENTS = "youtube_comments"


@dataclass(frozen=True)
class YouTubeRequestSpec:
    request_type: YouTubeRequestType
    query: str = ""
    video_id: str = ""
    language_code: str = "de"
    location_code: Optional[int] = None
    max_results: int = 5
    device: str = "desktop"
    device_os: str = "windows"
    mode: DataForSEORetrievalMode = DataForSEORetrievalMode.LIVE


def parse_dataforseo_mode(value: str) -> DataForSEORetrievalMode:
    raw = str(value or "live").strip().lower()
    try:
        return DataForSEORetrievalMode(raw)
    except ValueError as exc:
        raise ValueError(f"Ungueltiger DataForSEO-Modus: {value!r}. Erlaubt: live, standard") from exc


def _youtube_location_code(language_code: str) -> int:
    lang = str(language_code or "de").strip().lower()
    return LANGUAGE_TO_LOCATION_CODE.get(lang, 2276)


def validate_youtube_request(spec: YouTubeRequestSpec) -> YouTubeRequestSpec:
    """Validiert und normalisiert einen typisierten YouTube-Request."""
    language_code = str(spec.language_code or "de").strip().lower() or "de"
    device = str(spec.device or "desktop").strip().lower() or "desktop"
    device_os = str(spec.device_os or "windows").strip().lower() or "windows"
    query = str(spec.query or "").strip()
    video_id = str(spec.video_id or "").strip()
    max_results = max(1, min(int(spec.max_results or 1), 10))
    location_code = spec.location_code or _youtube_location_code(language_code)

    if spec.request_type == YouTubeRequestType.ORGANIC_SEARCH:
        if not query:
            raise ValueError("youtube_organic_search erfordert query")
        if device not in {"desktop", "mobile"}:
            raise ValueError("youtube_organic_search erlaubt nur desktop oder mobile")
        if device == "desktop" and device_os not in {"windows", "macos"}:
            raise ValueError("youtube_organic_search desktop erfordert windows oder macos")
        if device == "mobile" and device_os not in {"android", "ios"}:
            raise ValueError("youtube_organic_search mobile erfordert android oder ios")
    else:
        if not video_id:
            raise ValueError(f"{spec.request_type.value} erfordert video_id")
        if device != "desktop":
            raise ValueError(f"{spec.request_type.value} ist desktop-only")
        if device_os not in {"windows", "macos"}:
            raise ValueError(f"{spec.request_type.value} erlaubt nur windows oder macos")

    return YouTubeRequestSpec(
        request_type=spec.request_type,
        query=query,
        video_id=video_id,
        language_code=language_code,
        location_code=location_code,
        max_results=max_results,
        device=device,
        device_os=device_os,
        mode=spec.mode,
    )


def build_youtube_organic_payload(spec: YouTubeRequestSpec) -> list[dict[str, Any]]:
    spec = validate_youtube_request(spec)
    if spec.request_type != YouTubeRequestType.ORGANIC_SEARCH:
        raise ValueError("Falscher Request-Typ fuer build_youtube_organic_payload")
    payload = {
        "keyword": spec.query,
        "location_code": spec.location_code,
        "language_code": spec.language_code,
        "depth": spec.max_results,
    }
    # Konservativ: Default-Desktop/Windows unverändert lassen, um bestehende Live-Calls nicht zu riskieren.
    if spec.device != "desktop" or spec.device_os != "windows":
        payload["device"] = spec.device
        payload["os"] = spec.device_os
    return [payload]


def build_youtube_video_info_payload(spec: YouTubeRequestSpec) -> list[dict[str, Any]]:
    spec = validate_youtube_request(spec)
    if spec.request_type != YouTubeRequestType.VIDEO_INFO:
        raise ValueError("Falscher Request-Typ fuer build_youtube_video_info_payload")
    return [{"video_id": spec.video_id}]


def build_youtube_subtitles_payload(spec: YouTubeRequestSpec) -> list[dict[str, Any]]:
    spec = validate_youtube_request(spec)
    if spec.request_type != YouTubeRequestType.SUBTITLES:
        raise ValueError("Falscher Request-Typ fuer build_youtube_subtitles_payload")
    return [{"video_id": spec.video_id, "language_code": spec.language_code}]


def build_youtube_comments_payload(spec: YouTubeRequestSpec) -> list[dict[str, Any]]:
    spec = validate_youtube_request(spec)
    if spec.request_type != YouTubeRequestType.COMMENTS:
        raise ValueError("Falscher Request-Typ fuer build_youtube_comments_payload")
    return [{"video_id": spec.video_id, "depth": spec.max_results}]


def build_youtube_request(spec: YouTubeRequestSpec) -> tuple[str, list[dict[str, Any]]]:
    """Baut Endpoint + Payload für einen typisierten YouTube-Request."""
    spec = validate_youtube_request(spec)
    base_path = _youtube_base_path(spec.request_type)
    payload = _youtube_payload_for_spec(spec)

    if spec.mode == DataForSEORetrievalMode.LIVE:
        if spec.request_type == YouTubeRequestType.ORGANIC_SEARCH and payload:
            # Der aktuelle YouTube live/advanced Endpoint lehnt `depth` ab.
            # Wir slicen danach lokal auf `max_results`, daher lassen wir das Feld im Live-Pfad weg.
            payload[0].pop("depth", None)
        return f"{base_path}/live/advanced", payload
    if spec.mode == DataForSEORetrievalMode.STANDARD:
        return f"{base_path}/task_post", payload
    raise ValueError(f"Unbekannter YouTube Request-Typ: {spec.request_type}")


def build_youtube_task_get_endpoint(spec: YouTubeRequestSpec, task_id: str) -> str:
    spec = validate_youtube_request(spec)
    task_id = str(task_id or "").strip()
    if not task_id:
        raise ValueError("task_id ist erforderlich")
    return f"{_youtube_base_path(spec.request_type)}/task_get/advanced/{task_id}"


def _youtube_base_path(request_type: YouTubeRequestType) -> str:
    if request_type == YouTubeRequestType.ORGANIC_SEARCH:
        return "/v3/serp/youtube/organic"
    if request_type == YouTubeRequestType.VIDEO_INFO:
        return "/v3/serp/youtube/video_info"
    if request_type == YouTubeRequestType.SUBTITLES:
        return "/v3/serp/youtube/video_subtitles"
    if request_type == YouTubeRequestType.COMMENTS:
        return "/v3/serp/youtube/video_comments"
    raise ValueError(f"Unbekannter YouTube Request-Typ: {request_type}")


def _youtube_payload_for_spec(spec: YouTubeRequestSpec) -> list[dict[str, Any]]:
    if spec.request_type == YouTubeRequestType.ORGANIC_SEARCH:
        return build_youtube_organic_payload(spec)
    if spec.request_type == YouTubeRequestType.VIDEO_INFO:
        return build_youtube_video_info_payload(spec)
    if spec.request_type == YouTubeRequestType.SUBTITLES:
        return build_youtube_subtitles_payload(spec)
    if spec.request_type == YouTubeRequestType.COMMENTS:
        return build_youtube_comments_payload(spec)
    raise ValueError(f"Unbekannter YouTube Request-Typ: {spec.request_type}")


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

@tool(
    name="search_web",
    description="Führt eine Websuche mit DataForSEO durch.",
    parameters=[
        P("query", "string", "Die Suchanfrage"),
        P("engine", "string", "Suchmaschine - google, bing, duckduckgo, yahoo", required=False, default="google"),
        P("vertical", "string", "Suchtyp - organic, news, images, scholar, maps", required=False, default="organic"),
        P("max_results", "integer", "Maximale Anzahl Ergebnisse (1-100)", required=False, default=10),
        P("language_code", "string", "Sprachcode z.B. de, en", required=False, default="de"),
        P("location_code", "integer", "DataForSEO Location Code (2276 = Deutschland)", required=False, default=2276),
        P("device", "string", "desktop oder mobile", required=False, default="desktop"),
    ],
    capabilities=["search", "web"],
    category=C.SEARCH
)
async def search_web(
    query: str,
    engine: str = "google",
    vertical: str = "organic",
    max_results: int = 10,
    language_code: str = "de",
    location_code: int = 2276,
    device: str = "desktop"
) -> dict:
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
        Liste von Suchergebnissen
    """
    logger.info(f"🔍 search_web: '{query}' ({engine}/{vertical})")

    # Credentials prüfen
    if not (DATAFORSEO_USER and DATAFORSEO_PASS):
        raise Exception(
            "DataForSEO Credentials nicht konfiguriert. "
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
        return results

    except ValueError as e:
        logger.warning(f"Validierungsfehler: {e}")
        raise Exception(str(e))

    except ConnectionError as e:
        logger.error(f"Verbindungsfehler: {e}")
        raise Exception(str(e))

    except Exception as e:
        logger.error(f"Unerwarteter Fehler: {e}", exc_info=True)
        raise Exception(f"Interner Fehler: {str(e)}")


@tool(
    name="search_news",
    description="Convenience-Methode für News-Suche.",
    parameters=[
        P("query", "string", "Suchanfrage"),
        P("max_results", "integer", "Maximale Ergebnisse", required=False, default=10),
        P("language_code", "string", "Sprache", required=False, default="de"),
    ],
    capabilities=["search", "web"],
    category=C.SEARCH
)
async def search_news(
    query: str,
    max_results: int = 10,
    language_code: str = "de"
) -> dict:
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


@tool(
    name="search_images",
    description="Convenience-Methode für Bildersuche.",
    parameters=[
        P("query", "string", "Suchanfrage"),
        P("max_results", "integer", "Maximale Ergebnisse", required=False, default=10),
    ],
    capabilities=["search", "web"],
    category=C.SEARCH
)
async def search_images(
    query: str,
    max_results: int = 10
) -> dict:
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


@tool(
    name="search_scholar",
    description="Convenience-Methode für Google Scholar Suche.",
    parameters=[
        P("query", "string", "Suchanfrage (wissenschaftlich)"),
        P("max_results", "integer", "Maximale Ergebnisse", required=False, default=10),
    ],
    capabilities=["search", "web"],
    category=C.SEARCH
)
async def search_scholar(
    query: str,
    max_results: int = 10
) -> dict:
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


@tool(
    name="get_current_location_context",
    description=(
        "Gibt den zuletzt vom Handy synchronisierten GPS-Standort zurueck. "
        "Nuetzlich fuer Fragen wie 'wo bin ich' oder als Basis fuer lokale Maps-Suche."
    ),
    parameters=[],
    capabilities=["location", "maps", "context"],
    category=C.SEARCH,
)
async def get_current_location_context() -> dict:
    snapshot = _load_runtime_location_snapshot()
    if not snapshot:
        return {
            "has_location": False,
            "location": None,
            "presence_status": "unknown",
            "source_provider": "runtime_snapshot",
        }
    return {
        "has_location": True,
        "location": snapshot,
        "presence_status": str(snapshot.get("presence_status") or "unknown"),
        "source_provider": "runtime_snapshot",
    }


@tool(
    name="search_google_maps_places",
    description=(
        "Durchsucht Google Maps via SerpApi in der Naehe des zuletzt synchronisierten Handy-Standorts "
        "oder expliziter Koordinaten und liefert lokale Orte normalisiert zurueck."
    ),
    parameters=[
        P("query", "string", "Orts- oder Kategorienanfrage, z.B. 'Cafe', 'Apotheke', 'Supermarkt'"),
        P("max_results", "integer", "Maximale Anzahl Orte", required=False, default=5),
        P("latitude", "number", "Explizite Breite; wenn leer, wird der aktuelle Handy-Standort genutzt", required=False, default=None),
        P("longitude", "number", "Explizite Laenge; wenn leer, wird der aktuelle Handy-Standort genutzt", required=False, default=None),
        P("zoom", "integer", "Google-Maps-Zoom fuer lokalen Kontext", required=False, default=15),
        P("language_code", "string", "Sprachcode fuer lokalisierte Ergebnisse", required=False, default="de"),
    ],
    capabilities=["search", "maps", "location"],
    category=C.SEARCH,
)
async def search_google_maps_places(
    query: str,
    max_results: int = 5,
    latitude: float | None = None,
    longitude: float | None = None,
    zoom: int = 15,
    language_code: str = "de",
) -> dict:
    if not SERPAPI_API_KEY:
        raise Exception("SERPAPI_API_KEY nicht konfiguriert.")
    safe_query = str(query or "").strip()
    if not safe_query:
        raise ValueError("Google-Maps-Suche erfordert eine Query.")

    origin, origin_latitude, origin_longitude = _resolve_maps_origin(
        latitude=latitude,
        longitude=longitude,
    )
    safe_max_results = max(1, min(int(max_results or 5), 10))
    params = {
        "engine": "google_maps",
        "type": "search",
        "q": safe_query,
        "hl": str(language_code or "de").strip() or "de",
        "ll": _serpapi_maps_ll(origin_latitude, origin_longitude, zoom),
    }
    data = await asyncio.to_thread(_call_serpapi_json, params)
    return _serpapi_maps_search_result(
        data,
        query=safe_query,
        origin=origin,
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        max_results=safe_max_results,
    )


@tool(
    name="get_google_maps_place",
    description=(
        "Liefert Detailinformationen zu einem Google-Maps-Ort via SerpApi. "
        "Nutze place_id oder data_cid aus vorherigen Maps-Suchergebnissen."
    ),
    parameters=[
        P("place_id", "string", "Google Maps place_id", required=False, default=""),
        P("data_cid", "string", "Google Maps data_cid", required=False, default=""),
        P("language_code", "string", "Sprachcode fuer lokalisierte Details", required=False, default="de"),
    ],
    capabilities=["search", "maps", "location"],
    category=C.SEARCH,
)
async def get_google_maps_place(
    place_id: str = "",
    data_cid: str = "",
    language_code: str = "de",
) -> dict:
    if not SERPAPI_API_KEY:
        raise Exception("SERPAPI_API_KEY nicht konfiguriert.")
    safe_place_id = str(place_id or "").strip()
    safe_data_cid = str(data_cid or "").strip()
    if not safe_place_id and not safe_data_cid:
        raise ValueError("get_google_maps_place erfordert place_id oder data_cid.")

    params = {
        "engine": "google_maps",
        "hl": str(language_code or "de").strip() or "de",
    }
    if safe_place_id:
        params["place_id"] = safe_place_id
    if safe_data_cid:
        params["data_cid"] = safe_data_cid

    snapshot = _load_runtime_location_snapshot()
    if isinstance(snapshot, dict):
        latitude = _as_float(snapshot.get("latitude"))
        longitude = _as_float(snapshot.get("longitude"))
        if latitude is not None and longitude is not None:
            params["ll"] = _serpapi_maps_ll(latitude, longitude, 15)

    data = await asyncio.to_thread(_call_serpapi_json, params)
    return _serpapi_maps_place_result(data)


@tool(
    name="get_google_maps_route",
    description=(
        "Berechnet eine Route vom zuletzt synchronisierten Handy-Standort zu einem Ziel "
        "via Google Maps Directions / SerpApi und liefert ETA, Distanz und Schrittfolge."
    ),
    parameters=[
        P("destination_query", "string", "Zieladresse oder Ortsname, z.B. 'Alexanderplatz Berlin'"),
        P("travel_mode", "string", "Route-Modus: driving, walking, bicycling, transit", required=False, default="driving"),
        P("language_code", "string", "Sprachcode fuer lokalisierte Routentexte", required=False, default="de"),
        P("latitude", "number", "Explizite Start-Breite; wenn leer, wird der aktuelle Handy-Standort genutzt", required=False, default=None),
        P("longitude", "number", "Explizite Start-Laenge; wenn leer, wird der aktuelle Handy-Standort genutzt", required=False, default=None),
    ],
    capabilities=["search", "maps", "location", "route"],
    category=C.SEARCH,
)
async def get_google_maps_route(
    destination_query: str,
    travel_mode: str = "driving",
    language_code: str = "de",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict:
    if not GOOGLE_ROUTES_API_KEY and not SERPAPI_API_KEY:
        raise Exception("Weder GOOGLE_ROUTES_API_KEY noch SERPAPI_API_KEY sind konfiguriert.")
    safe_destination = str(destination_query or "").strip()
    if not safe_destination:
        raise ValueError("Google-Maps-Route erfordert ein Ziel.")

    origin, origin_latitude, origin_longitude = _resolve_maps_origin(
        latitude=latitude,
        longitude=longitude,
    )
    origin_presence = str(origin.get("presence_status") or "unknown").strip().lower()
    if origin_presence not in {"live", "recent"} or not bool(origin.get("usable_for_context")):
        raise ValueError("Der aktuelle Mobil-Standort ist nicht frisch genug fuer verlaessliches Routing.")
    normalized_mode = normalize_route_travel_mode(travel_mode)
    last_error: Exception | None = None

    if GOOGLE_ROUTES_API_KEY:
        for destination_variant in _route_destination_variants(safe_destination):
            try:
                google_payload = {
                    "origin": {
                        "location": {
                            "latLng": {
                                "latitude": origin_latitude,
                                "longitude": origin_longitude,
                            }
                        }
                    },
                    "destination": {
                        "address": destination_variant,
                    },
                    "travelMode": GOOGLE_ROUTES_TRAVEL_MODE.get(normalized_mode, "DRIVE"),
                    "languageCode": str(language_code or "de").strip() or "de",
                    "units": "METRIC",
                    "computeAlternativeRoutes": False,
                    "polylineQuality": "OVERVIEW",
                    "polylineEncoding": "ENCODED_POLYLINE",
                }
                data = await asyncio.to_thread(_call_google_routes_json, google_payload)
                result = parse_google_routes_compute_route(
                    data,
                    origin=origin,
                    destination_query=destination_variant,
                    travel_mode=normalized_mode,
                )
                result["language_code"] = str(language_code or "de").strip() or "de"
                result["requested_destination_query"] = safe_destination
                return result
            except Exception as exc:
                last_error = exc

    if SERPAPI_API_KEY:
        params = {
            "engine": "google_maps_directions",
            "start_coords": f"{origin_latitude},{origin_longitude}",
            "travel_mode": SERPAPI_DIRECTIONS_TRAVEL_MODE.get(normalized_mode, "0"),
            "hl": str(language_code or "de").strip() or "de",
        }
        for destination_variant in _route_destination_variants(safe_destination):
            try:
                params["end_addr"] = destination_variant
                data = await asyncio.to_thread(_call_serpapi_json, params)
                result = parse_serpapi_google_maps_directions(
                    data,
                    origin=origin,
                    destination_query=destination_variant,
                    travel_mode=normalized_mode,
                )
                result["language_code"] = str(language_code or "de").strip() or "de"
                result["requested_destination_query"] = safe_destination
                return result
            except Exception as exc:
                last_error = exc
                continue
    if last_error is not None:
        raise last_error
    raise ValueError("Google-Maps-Route erfordert ein Ziel.")


def _call_google_routes_json(payload: dict[str, Any], timeout: float = DEFAULT_API_TIMEOUT) -> dict:
    """Fuehrt einen Google Routes API computeRoutes-Aufruf aus und gibt JSON zurueck."""
    if not GOOGLE_ROUTES_API_KEY:
        raise ValueError("GOOGLE_ROUTES_API_KEY nicht konfiguriert.")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_ROUTES_API_KEY,
        "X-Goog-FieldMask": GOOGLE_ROUTES_FIELD_MASK,
    }
    response = requests.post(
        GOOGLE_ROUTES_BASE_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    try:
        data = response.json()
    except Exception:
        data = {}
    if response.status_code >= 400:
        error_message = (
            data.get("error", {}).get("message")
            if isinstance(data.get("error"), dict)
            else data.get("error")
        )
        if error_message:
            raise ValueError(f"Google Routes API Fehler: {error_message}")
        response.raise_for_status()
    if isinstance(data.get("error"), dict):
        raise ValueError(f"Google Routes API Fehler: {data['error'].get('message') or data['error']}")
    if data.get("error"):
        raise ValueError(f"Google Routes API Fehler: {data['error']}")
    return data


def _call_dataforseo_youtube(endpoint: str, payload: list) -> dict:
    """Führt einen DataForSEO YouTube-API-Aufruf durch und gibt die rohe Response zurück."""
    return _call_dataforseo_json("POST", endpoint, payload=payload, timeout=DEFAULT_API_TIMEOUT)


def _call_serpapi_json(params: dict[str, Any], timeout: float = DEFAULT_API_TIMEOUT) -> dict:
    """Fuehrt einen SerpApi-Aufruf aus und gibt die JSON-Antwort zurueck."""
    if not SERPAPI_API_KEY:
        raise ValueError("SERPAPI_API_KEY nicht konfiguriert.")

    request_params = dict(params)
    request_params["api_key"] = SERPAPI_API_KEY
    response = requests.get(SERPAPI_BASE_URL, params=request_params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise ValueError(f"SerpApi Fehler: {data['error']}")
    return data


def _load_runtime_location_snapshot() -> dict[str, Any] | None:
    if not _RUNTIME_LOCATION_SNAPSHOT_PATH.exists():
        return None
    try:
        with open(_RUNTIME_LOCATION_SNAPSHOT_PATH, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return None
        return enrich_location_presence_snapshot(payload)
    except Exception as exc:
        logger.warning("Runtime-Standort konnte nicht geladen werden: %s", exc)
        return None


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except Exception:
        return None


def _resolve_maps_origin(
    *,
    latitude: float | None = None,
    longitude: float | None = None,
) -> tuple[dict[str, Any], float, float]:
    snapshot = _load_runtime_location_snapshot()
    resolved_latitude = _as_float(latitude)
    resolved_longitude = _as_float(longitude)
    has_explicit_origin = resolved_latitude is not None and resolved_longitude is not None

    if resolved_latitude is None or resolved_longitude is None:
        if not snapshot:
            raise ValueError("Kein aktueller Mobil-Standort verfuegbar. Bitte Standort im Handy zuerst synchronisieren.")
        resolved_latitude = _as_float(snapshot.get("latitude"))
        resolved_longitude = _as_float(snapshot.get("longitude"))

    if resolved_latitude is None or resolved_longitude is None:
        raise ValueError("Runtime-Standort ist unvollstaendig und enthaelt keine gueltigen Koordinaten.")

    origin = {
        "latitude": resolved_latitude,
        "longitude": resolved_longitude,
        "display_name": str((snapshot or {}).get("display_name") or ""),
        "locality": str((snapshot or {}).get("locality") or ""),
        "admin_area": str((snapshot or {}).get("admin_area") or ""),
        "country_name": str((snapshot or {}).get("country_name") or ""),
        "country_code": str((snapshot or {}).get("country_code") or ""),
        "accuracy_meters": _as_float((snapshot or {}).get("accuracy_meters")),
        "captured_at": str((snapshot or {}).get("captured_at") or ""),
        "received_at": str((snapshot or {}).get("received_at") or ""),
        "source": str((snapshot or {}).get("source") or ("explicit_origin" if has_explicit_origin else "runtime_snapshot")),
        "presence_status": (
            "live"
            if has_explicit_origin
            else str((snapshot or {}).get("presence_status") or "unknown")
        ),
        "usable_for_context": (
            True
            if has_explicit_origin
            else bool((snapshot or {}).get("usable_for_context"))
        ),
        "maps_url": str((snapshot or {}).get("maps_url") or f"https://www.google.com/maps/search/?api=1&query={resolved_latitude},{resolved_longitude}"),
    }
    return origin, resolved_latitude, resolved_longitude


def _route_destination_variants(destination_query: str) -> list[str]:
    safe_destination = str(destination_query or "").strip()
    if not safe_destination:
        return []

    variants: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        normalized = re.sub(r"\s+", " ", str(value or "").strip())
        if not normalized:
            return
        key = normalized.casefold()
        if key in seen:
            return
        seen.add(key)
        variants.append(normalized)

    _add(safe_destination)

    tokens = safe_destination.split()
    for index, token in enumerate(tokens):
        lower = token.casefold().strip(",")
        if index == 0:
            continue
        if re.fullmatch(r"in[a-zäöüß-]{4,}", lower):
            remainder = token[2:]
            if remainder:
                split_tokens = list(tokens)
                split_tokens[index:index + 1] = ["in", remainder]
                _add(" ".join(split_tokens))

                compact_tokens = list(tokens)
                compact_tokens[index] = remainder
                _add(" ".join(compact_tokens))

    return variants


def _serpapi_maps_ll(latitude: float, longitude: float, zoom: int) -> str:
    safe_zoom = max(3, min(int(zoom or 15), 20))
    return f"@{latitude},{longitude},{safe_zoom}z"


def _distance_meters(origin_lat: float, origin_lon: float, target_lat: float | None, target_lon: float | None) -> int | None:
    if target_lat is None or target_lon is None:
        return None
    radius_m = 6_371_000
    lat1 = math.radians(origin_lat)
    lon1 = math.radians(origin_lon)
    lat2 = math.radians(target_lat)
    lon2 = math.radians(target_lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(radius_m * c)


def _maps_search_url(query: str, *, place_id: str = "", latitude: float | None = None, longitude: float | None = None) -> str:
    encoded_query = quote_plus(str(query or "").strip())
    if place_id:
        if encoded_query:
            return f"https://www.google.com/maps/search/?api=1&query={encoded_query}&query_place_id={quote_plus(place_id)}"
        return f"https://www.google.com/maps/search/?api=1&query_place_id={quote_plus(place_id)}"
    if latitude is not None and longitude is not None and not encoded_query:
        return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    return f"https://www.google.com/maps/search/?api=1&query={encoded_query}"


def _serpapi_maps_hours(raw: dict[str, Any]) -> str:
    for key in ("hours", "open_state", "service_options"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    operating_hours = raw.get("operating_hours")
    if isinstance(operating_hours, dict):
        summary = operating_hours.get("hours")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return ""


def _serpapi_maps_search_result(
    data: dict[str, Any],
    *,
    query: str,
    origin: dict[str, Any],
    origin_latitude: float,
    origin_longitude: float,
    max_results: int,
) -> dict[str, Any]:
    raw_results = data.get("local_results") or []
    if not raw_results and isinstance(data.get("place_results"), dict):
        raw_results = [data.get("place_results")]

    results: list[dict[str, Any]] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("name") or "").strip()
        if not title:
            continue
        coords = raw.get("gps_coordinates") if isinstance(raw.get("gps_coordinates"), dict) else {}
        place_latitude = _as_float(coords.get("latitude"))
        place_longitude = _as_float(coords.get("longitude"))
        place_id = str(raw.get("place_id") or "").strip()
        website = raw.get("website")
        if not website and isinstance(raw.get("links"), dict):
            website = raw["links"].get("website")
        result = {
            "position": _as_int(raw.get("position")) or (len(results) + 1),
            "title": title,
            "type": str(raw.get("type") or "").strip(),
            "address": str(raw.get("address") or raw.get("full_address") or "").strip(),
            "rating": _as_float(raw.get("rating")),
            "reviews": _as_int(raw.get("reviews")) or 0,
            "price": str(raw.get("price") or "").strip(),
            "phone": str(raw.get("phone") or raw.get("phone_number") or "").strip(),
            "website": str(website or "").strip(),
            "hours_summary": _serpapi_maps_hours(raw),
            "place_id": place_id,
            "data_id": str(raw.get("data_id") or "").strip(),
            "data_cid": str(raw.get("data_cid") or "").strip(),
            "thumbnail_url": str(raw.get("thumbnail") or raw.get("serpapi_thumbnail") or "").strip(),
            "gps_coordinates": {
                "latitude": place_latitude,
                "longitude": place_longitude,
            },
            "distance_meters": _distance_meters(
                origin_latitude,
                origin_longitude,
                place_latitude,
                place_longitude,
            ),
            "maps_url": _maps_search_url(
                title,
                place_id=place_id,
                latitude=place_latitude,
                longitude=place_longitude,
            ),
        }
        results.append(result)
        if len(results) >= max_results:
            break

    return {
        "query": query,
        "origin": origin,
        "results": results,
        "source_provider": "serpapi",
        "engine": "google_maps",
    }


def _serpapi_maps_place_result(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("place_results") or data.get("place_result") or {}
    if not isinstance(raw, dict):
        raw = {}
    coords = raw.get("gps_coordinates") if isinstance(raw.get("gps_coordinates"), dict) else {}
    latitude = _as_float(coords.get("latitude"))
    longitude = _as_float(coords.get("longitude"))
    title = str(raw.get("title") or raw.get("name") or "").strip()
    place_id = str(raw.get("place_id") or "").strip()
    website = raw.get("website")
    if not website and isinstance(raw.get("links"), dict):
        website = raw["links"].get("website")
    reviews_link = ""
    if isinstance(raw.get("reviews_link"), str):
        reviews_link = raw.get("reviews_link") or ""
    elif isinstance(raw.get("links"), dict):
        reviews_link = str(raw["links"].get("reviews") or "")
    return {
        "title": title,
        "type": str(raw.get("type") or "").strip(),
        "address": str(raw.get("address") or raw.get("full_address") or "").strip(),
        "rating": _as_float(raw.get("rating")),
        "reviews": _as_int(raw.get("reviews")) or 0,
        "price": str(raw.get("price") or "").strip(),
        "phone": str(raw.get("phone") or raw.get("phone_number") or "").strip(),
        "website": str(website or "").strip(),
        "hours_summary": _serpapi_maps_hours(raw),
        "description": str(raw.get("description") or "").strip(),
        "place_id": place_id,
        "data_id": str(raw.get("data_id") or "").strip(),
        "data_cid": str(raw.get("data_cid") or "").strip(),
        "reviews_link": reviews_link,
        "maps_url": _maps_search_url(title, place_id=place_id, latitude=latitude, longitude=longitude),
        "gps_coordinates": {"latitude": latitude, "longitude": longitude},
        "source_provider": "serpapi",
        "engine": "google_maps",
    }


def _call_dataforseo_json(
    method: str,
    endpoint: str,
    payload: Optional[list | dict] = None,
    timeout: float = DEFAULT_API_TIMEOUT,
) -> dict:
    url = DATAFORSEO_BASE_URL + endpoint
    headers = _get_auth_header()
    response = requests.request(method, url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") != 20000:
        raise ValueError(f"DataForSEO API Fehler: {data.get('status_message', 'Unbekannt')}")
    return data


def _first_dataforseo_task(data: dict) -> dict:
    tasks = data.get("tasks", [])
    if not tasks or not isinstance(tasks[0], dict):
        raise ValueError("DataForSEO Antwort enthält keinen Task")
    return tasks[0]


def _task_is_pending(task: dict) -> bool:
    status_message = str(task.get("status_message", "")).lower()
    if task.get("result"):
        return False
    return any(token in status_message for token in ("queue", "queued", "progress", "pending", "created"))


def _call_dataforseo_youtube_standard(
    spec: YouTubeRequestSpec,
    timeout: float = DEFAULT_STANDARD_TIMEOUT,
    poll_interval: float = DEFAULT_STANDARD_POLL_INTERVAL,
) -> dict:
    spec = validate_youtube_request(spec)
    endpoint, payload = build_youtube_request(spec)
    post_data = _call_dataforseo_json("POST", endpoint, payload=payload, timeout=DEFAULT_API_TIMEOUT)
    first_task = _first_dataforseo_task(post_data)
    task_id = str(first_task.get("id", "")).strip()
    if not task_id:
        raise ValueError("DataForSEO task_post lieferte keine task_id")

    task_get_endpoint = build_youtube_task_get_endpoint(spec, task_id)
    deadline = time.monotonic() + timeout
    last_task = first_task

    while time.monotonic() < deadline:
        get_data = _call_dataforseo_json("GET", task_get_endpoint, timeout=DEFAULT_API_TIMEOUT)
        task = _first_dataforseo_task(get_data)
        last_task = task
        if task.get("result"):
            return get_data
        if not _task_is_pending(task):
            raise ValueError(f"DataForSEO Task nicht erfolgreich: {task.get('status_message', 'Unbekannt')}")
        time.sleep(poll_interval)

    raise TimeoutError(
        f"Timeout bei DataForSEO Standard-Task ({timeout}s): {last_task.get('status_message', 'keine Antwort')}"
    )


def _is_dataforseo_task_not_found(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return "task not found" in message


def _serpapi_transcript_result(data: dict, video_id: str) -> dict:
    """Normalisiert SerpApi-Transcriptdaten auf das bestehende Untertitel-Format."""
    raw_segments = data.get("transcript") or data.get("transcripts") or []
    items: list[dict[str, Any]] = []

    for raw in raw_segments:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("snippet", "")).strip()
        if not text:
            continue

        start_ms = raw.get("start_ms")
        end_ms = raw.get("end_ms")
        start_time = float(start_ms) / 1000.0 if isinstance(start_ms, (int, float)) else 0.0
        end_time = float(end_ms) / 1000.0 if isinstance(end_ms, (int, float)) else start_time

        items.append(
            {
                "text": text,
                "start_time": start_time,
                "end_time": end_time,
                "start_time_text": str(raw.get("start_time_text", "")).strip(),
            }
        )

    full_text = " ".join(item["text"] for item in items)
    if len(full_text) > 8000:
        full_text = full_text[:8000]

    return {
        "video_id": video_id,
        "full_text": full_text,
        "items": items,
        "available_transcripts": data.get("available_transcripts", []),
        "chapters": data.get("chapters", []),
        "source_provider": "serpapi",
    }


def _serpapi_video_info_result(data: dict, video_id: str) -> dict:
    """Normalisiert SerpApi-Video-Details auf ein Timus-freundliches Format."""
    video_results = data.get("video_results")
    if not isinstance(video_results, dict):
        video_results = {}

    channel = video_results.get("channel")
    if not isinstance(channel, dict):
        channel = {}

    thumbnails = video_results.get("thumbnail") or video_results.get("thumbnails") or []
    if isinstance(thumbnails, list):
        thumbnail_url = thumbnails[0] if thumbnails else ""
    else:
        thumbnail_url = str(thumbnails or "")

    comments: list[dict[str, str]] = []
    for raw in data.get("comments", [])[:5]:
        if not isinstance(raw, dict):
            continue
        comments.append(
            {
                "author": str(raw.get("author", "")).strip(),
                "text": str(raw.get("content", raw.get("text", ""))).strip(),
            }
        )

    related_videos: list[dict[str, str]] = []
    for raw in data.get("related_videos", [])[:5]:
        if not isinstance(raw, dict):
            continue
        related_id = str(raw.get("id", raw.get("video_id", ""))).strip()
        related_videos.append(
            {
                "video_id": related_id,
                "title": str(raw.get("title", "")).strip(),
                "url": raw.get("link") or (f"https://www.youtube.com/watch?v={related_id}" if related_id else ""),
            }
        )

    return {
        "video_id": video_id,
        "title": str(video_results.get("title", "")).strip(),
        "url": video_results.get("link") or f"https://www.youtube.com/watch?v={video_id}",
        "description": str(video_results.get("description", "")).strip(),
        "channel_name": str(channel.get("name", video_results.get("channel_name", ""))).strip(),
        "channel_url": str(channel.get("link", "")).strip(),
        "thumbnail_url": thumbnail_url,
        "duration": str(video_results.get("duration", "")).strip(),
        "views": video_results.get("views") or video_results.get("views_count") or 0,
        "published_date": str(video_results.get("published_date", video_results.get("date", ""))).strip(),
        "chapters": data.get("chapters", []),
        "comments": comments,
        "related_videos": related_videos,
        "source_provider": "serpapi",
    }


def _dataforseo_video_info_result(data: dict, video_id: str) -> dict:
    """Konservativer Parser fuer DataForSEO video_info-Antworten."""
    task = _first_dataforseo_task(data)
    result_wrappers = task.get("result", [])
    wrapper = result_wrappers[0] if result_wrappers else {}
    if not isinstance(wrapper, dict):
        wrapper = {}
    item = wrapper.get("items", [{}])[0] if isinstance(wrapper.get("items"), list) and wrapper.get("items") else wrapper
    if not isinstance(item, dict):
        item = {}

    return {
        "video_id": video_id,
        "title": str(item.get("title", wrapper.get("title", ""))).strip(),
        "url": item.get("url") or wrapper.get("url") or f"https://www.youtube.com/watch?v={video_id}",
        "description": str(item.get("description", wrapper.get("description", ""))).strip(),
        "channel_name": str(item.get("channel_name", item.get("channel", ""))).strip(),
        "channel_url": "",
        "thumbnail_url": item.get("thumbnail_url") or item.get("thumbnail", ""),
        "duration": str(item.get("duration", item.get("duration_time", ""))).strip(),
        "views": item.get("views_count") or item.get("views") or 0,
        "published_date": str(item.get("published_date", item.get("date", ""))).strip(),
        "chapters": [],
        "comments": [],
        "related_videos": [],
        "source_provider": "dataforseo",
    }


@tool(
    name="search_youtube",
    description="Sucht YouTube-Videos via DataForSEO und gibt Metadaten zurück.",
    parameters=[
        P("query", "string", "Suchanfrage"),
        P("max_results", "integer", "Maximale Anzahl Videos (1-10)", required=False, default=5),
        P("language_code", "string", "Sprachcode z.B. de, en", required=False, default="de"),
        P("mode", "string", "DataForSEO Modus: live oder standard", required=False, default="live"),
    ],
    capabilities=["search", "youtube"],
    category=C.SEARCH
)
async def search_youtube(
    query: str,
    max_results: int = 5,
    language_code: str = "de",
    mode: str = "live",
) -> list:
    """
    Sucht YouTube-Videos via DataForSEO.

    Returns:
        Liste mit Dicts: {video_id, title, url, description,
                          thumbnail_url, channel_name, duration_time_seconds, views_count}
    """
    if not (DATAFORSEO_USER and DATAFORSEO_PASS):
        raise Exception("DataForSEO Credentials nicht konfiguriert.")

    spec = YouTubeRequestSpec(
        request_type=YouTubeRequestType.ORGANIC_SEARCH,
        query=query,
        language_code=language_code,
        max_results=max_results,
        mode=parse_dataforseo_mode(mode),
    )

    def _call():
        if spec.mode == DataForSEORetrievalMode.STANDARD:
            try:
                return _call_dataforseo_youtube_standard(spec)
            except Exception as exc:
                if not _is_dataforseo_task_not_found(exc):
                    raise
                logger.warning(
                    "search_youtube: DataForSEO standard task fehlgeschlagen (%s) — Fallback auf live",
                    exc,
                )
                live_spec = YouTubeRequestSpec(
                    request_type=spec.request_type,
                    query=spec.query,
                    video_id=spec.video_id,
                    language_code=spec.language_code,
                    location_code=spec.location_code,
                    max_results=spec.max_results,
                    device=spec.device,
                    device_os=spec.device_os,
                    mode=DataForSEORetrievalMode.LIVE,
                )
                endpoint, payload = build_youtube_request(live_spec)
                return _call_dataforseo_youtube(endpoint, payload)
        endpoint, payload = build_youtube_request(spec)
        return _call_dataforseo_youtube(endpoint, payload)

    data = await asyncio.to_thread(_call)

    results = []
    try:
        tasks = data.get("tasks", [])
        if not tasks:
            return results
        task = tasks[0]
        if task.get("status_code") != 20000:
            logger.warning(f"YouTube-Task Fehler: {task.get('status_message')}")
            return results
        for result_wrapper in task.get("result", []):
            for item in result_wrapper.get("items", []):
                if len(results) >= max_results:
                    break
                if not isinstance(item, dict):
                    continue
                video_id = item.get("video_id") or item.get("id", "")
                if not video_id:
                    continue
                results.append({
                    "video_id": video_id,
                    "title": str(item.get("title", "")).strip(),
                    "url": item.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                    "description": str(item.get("description", "")).strip(),
                    "thumbnail_url": item.get("thumbnail_url") or item.get("thumbnail", ""),
                    "channel_name": item.get("channel_name") or item.get("channel", ""),
                    "duration_time_seconds": item.get("duration_time_seconds") or item.get("duration", 0),
                    "views_count": item.get("views_count") or item.get("views", 0),
                })
    except Exception as e:
        logger.error(f"Fehler beim Parsen der YouTube-Ergebnisse: {e}")

    logger.info(f"📺 search_youtube: {len(results)} Videos für '{query}'")
    return results


@tool(
    name="get_youtube_subtitles",
    description="Ruft Untertitel/Transkript eines YouTube-Videos via SerpApi oder DataForSEO ab.",
    parameters=[
        P("video_id", "string", "YouTube Video-ID (z.B. dQw4w9WgXcQ)"),
        P("language_code", "string", "Bevorzugte Sprache, Fallback auf 'en'", required=False, default="de"),
        P("mode", "string", "DataForSEO Modus: live oder standard", required=False, default="live"),
    ],
    capabilities=["search", "youtube"],
    category=C.SEARCH
)
async def get_youtube_subtitles(
    video_id: str,
    language_code: str = "de",
    mode: str = "live",
) -> dict:
    """
    Ruft YouTube-Untertitel via DataForSEO ab.

    Returns:
        {video_id, full_text, items: [{text, start_time, end_time}]}
    """
    if not (SERPAPI_API_KEY or (DATAFORSEO_USER and DATAFORSEO_PASS)):
        raise Exception("Weder SERPAPI_API_KEY noch DataForSEO Credentials sind konfiguriert.")

    preferred_languages: list[str] = []
    for lang in [language_code, "en"]:
        lang = str(lang or "").strip().lower()
        if lang and lang not in preferred_languages:
            preferred_languages.append(lang)

    if SERPAPI_API_KEY:
        for lang in preferred_languages:
            try:
                data = await asyncio.to_thread(
                    _call_serpapi_json,
                    {
                        "engine": "youtube_video_transcript",
                        "v": video_id,
                        "language_code": lang,
                    },
                )
                result = _serpapi_transcript_result(data, video_id)
                if result["items"]:
                    logger.info(
                        "📺 get_youtube_subtitles: %s Segmente via SerpApi (%s)",
                        len(result["items"]),
                        lang,
                    )
                    return result
            except Exception as e:
                logger.warning(f"SerpApi Transcript ({lang}) fehlgeschlagen: {e}")

    if not (DATAFORSEO_USER and DATAFORSEO_PASS):
        return {"video_id": video_id, "full_text": "", "items": [], "source_provider": "none"}

    async def _fetch(lang: str) -> dict:
        spec = YouTubeRequestSpec(
            request_type=YouTubeRequestType.SUBTITLES,
            video_id=video_id,
            language_code=lang,
            mode=parse_dataforseo_mode(mode),
        )

        def _call():
            if spec.mode == DataForSEORetrievalMode.STANDARD:
                return _call_dataforseo_youtube_standard(spec)
            endpoint, payload = build_youtube_request(spec)
            return _call_dataforseo_youtube(endpoint, payload)
        return await asyncio.to_thread(_call)

    data = None
    for lang in preferred_languages:
        try:
            data = await _fetch(lang)
            break
        except Exception as e:
            logger.warning(f"Untertitel-Abruf ({lang}) fehlgeschlagen: {e}")

    if not data:
        return {"video_id": video_id, "full_text": "", "items": []}

    items = []
    try:
        tasks = data.get("tasks", [])
        if tasks and tasks[0].get("status_code") == 20000:
            for result_wrapper in tasks[0].get("result", []):
                for item in result_wrapper.get("items", []):
                    if isinstance(item, dict) and item.get("text"):
                        items.append({
                            "text": item["text"],
                            "start_time": item.get("start_time", 0),
                            "end_time": item.get("end_time", 0),
                        })
    except Exception as e:
        logger.error(f"Fehler beim Parsen der Untertitel: {e}")

    # Zusammengesetzter Text, max 8000 Zeichen
    full_text = " ".join(i["text"] for i in items)
    if len(full_text) > 8000:
        full_text = full_text[:8000]

    logger.info(f"📺 get_youtube_subtitles: {len(items)} Segmente, {len(full_text)} Zeichen")
    return {"video_id": video_id, "full_text": full_text, "items": items, "source_provider": "dataforseo"}


@tool(
    name="get_youtube_video_info",
    description="Ruft Detailinformationen zu einem YouTube-Video via SerpApi oder DataForSEO ab.",
    parameters=[
        P("video_id", "string", "YouTube Video-ID (z.B. dQw4w9WgXcQ)"),
        P("language_code", "string", "Bevorzugte Sprache fuer lokalisierte Metadaten", required=False, default="de"),
        P("mode", "string", "DataForSEO Modus: live oder standard", required=False, default="live"),
    ],
    capabilities=["search", "youtube"],
    category=C.SEARCH
)
async def get_youtube_video_info(
    video_id: str,
    language_code: str = "de",
    mode: str = "live",
) -> dict:
    """Liefert Detailinformationen, Beschreibung, Kommentare und verwandte Videos."""
    if SERPAPI_API_KEY:
        try:
            data = await asyncio.to_thread(
                _call_serpapi_json,
                {
                    "engine": "youtube_video",
                    "v": video_id,
                    "hl": language_code,
                },
            )
            result = _serpapi_video_info_result(data, video_id)
            if result.get("title") or result.get("description") or result.get("comments"):
                return result
        except Exception as e:
            logger.warning(f"SerpApi Video-Info fehlgeschlagen ({video_id}): {e}")

    if not (DATAFORSEO_USER and DATAFORSEO_PASS):
        raise Exception("Weder SERPAPI_API_KEY noch DataForSEO Credentials sind konfiguriert.")

    spec = YouTubeRequestSpec(
        request_type=YouTubeRequestType.VIDEO_INFO,
        video_id=video_id,
        language_code=language_code,
        mode=parse_dataforseo_mode(mode),
    )

    def _call():
        if spec.mode == DataForSEORetrievalMode.STANDARD:
            return _call_dataforseo_youtube_standard(spec)
        endpoint, payload = build_youtube_request(spec)
        return _call_dataforseo_youtube(endpoint, payload)

    data = await asyncio.to_thread(_call)
    return _dataforseo_video_info_result(data, video_id)
