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
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

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
DEFAULT_STANDARD_TIMEOUT = 90
DEFAULT_STANDARD_POLL_INTERVAL = 2.0

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


def _call_dataforseo_youtube(endpoint: str, payload: list) -> dict:
    """Führt einen DataForSEO YouTube-API-Aufruf durch und gibt die rohe Response zurück."""
    return _call_dataforseo_json("POST", endpoint, payload=payload, timeout=DEFAULT_API_TIMEOUT)


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
            return _call_dataforseo_youtube_standard(spec)
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
    description="Ruft Untertitel/Transkript eines YouTube-Videos via DataForSEO ab.",
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
    if not (DATAFORSEO_USER and DATAFORSEO_PASS):
        raise Exception("DataForSEO Credentials nicht konfiguriert.")

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

    # Erst gewünschte Sprache, Fallback auf Englisch
    data = None
    for lang in ([language_code] if language_code != "en" else []) + ["en"]:
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
    return {"video_id": video_id, "full_text": full_text, "items": items}
