# agent/timus_consolidated.py (VERSION v4.4)
"""
Konsolidierte Agenten-Klassen für Timus.

VERSION v4.4 FEATURES:
- Multi-Provider Support (OpenAI, Anthropic, DeepSeek, Inception, NVIDIA, OpenRouter, Google)
- ReasoningAgent NEU mit Nemotron + enable_thinking Steuerung
- OpenRouter als primärer Nemotron-Provider
- NVIDIA NIM als Fallback-Option
- Parser-Fix für multiple JSON-Objekte
- Anthropic Vision Support für VisualAgent
- Agent-spezifische Model-Konfiguration
- Automatisches Fallback bei Provider-Fehlern

AUTOR: Timus Development
DATUM: Januar 2026
"""

import logging
import os
import json
import sys
import re
import asyncio
import base64
import subprocess
import platform
import io
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import httpx

# --- Pfad-Setup ---
try:
    CURRENT_SCRIPT_PATH = Path(__file__).resolve()
    PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path.cwd()

from dotenv import load_dotenv
from utils.openai_compat import prepare_openai_params

# [PERSONALITY_PATCH] - Import
try:
    from config.personality_loader import get_system_prompt_prefix, get_greeting, get_reaction
    PERSONALITY_ENABLED = True
except ImportError:
    PERSONALITY_ENABLED = False
    def get_system_prompt_prefix(): return ''
# [PERSONALITY_PATCH] - End Import

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s'
)
log = logging.getLogger("TimusAgent-v4.4")

load_dotenv()

MCP_URL = "http://127.0.0.1:5000"
IMAGE_MODEL_NAME = os.getenv("IMAGE_GENERATION_MODEL", "gpt-image-1.5-2025-12-16")


# ==============================================================================
# MULTI-PROVIDER INFRASTRUKTUR
# ==============================================================================

class ModelProvider(str, Enum):
    """Unterstützte LLM-Provider."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    INCEPTION = "inception"
    NVIDIA = "nvidia"
    OPENROUTER = "openrouter"
    GOOGLE = "google"


class MultiProviderClient:
    """
    Verwaltet API-Clients für verschiedene LLM-Provider.
    Lazy Initialization - Clients werden erst bei Bedarf erstellt.
    """
    
    # API Base URLs
    BASE_URLS = {
        ModelProvider.OPENAI: "https://api.openai.com/v1",
        ModelProvider.ANTHROPIC: "https://api.anthropic.com",
        ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
        ModelProvider.INCEPTION: "https://api.inceptionlabs.ai/v1",
        ModelProvider.NVIDIA: "https://integrate.api.nvidia.com/v1",
        ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
        ModelProvider.GOOGLE: "https://generativelanguage.googleapis.com/v1beta",
    }
    
    # API Key Environment Variable Names
    API_KEY_ENV = {
        ModelProvider.OPENAI: "OPENAI_API_KEY",
        ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
        ModelProvider.INCEPTION: "INCEPTION_API_KEY",
        ModelProvider.NVIDIA: "NVIDIA_API_KEY",
        ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
        ModelProvider.GOOGLE: "GOOGLE_API_KEY",
    }
    
    def __init__(self):
        self._clients: Dict[ModelProvider, Any] = {}
        self._api_keys: Dict[ModelProvider, str] = {}
        self._load_api_keys()
    
    def _load_api_keys(self):
        """Lädt alle verfügbaren API Keys."""
        for provider, env_var in self.API_KEY_ENV.items():
            key = os.getenv(env_var)
            if key:
                self._api_keys[provider] = key
                log.debug(f"✓ API Key geladen für: {provider.value}")
    
    def get_api_key(self, provider: ModelProvider) -> Optional[str]:
        """Gibt den API Key für einen Provider zurück."""
        return self._api_keys.get(provider)
    
    def get_base_url(self, provider: ModelProvider) -> str:
        """Gibt die Base URL für einen Provider zurück (mit env override)."""
        env_override = os.getenv(f"{provider.value.upper()}_API_BASE")
        return env_override or self.BASE_URLS.get(provider, "")
    
    def has_provider(self, provider: ModelProvider) -> bool:
        """Prüft ob ein Provider verfügbar ist (API Key vorhanden)."""
        return provider in self._api_keys
    
    def get_client(self, provider: ModelProvider):
        """
        Gibt einen Client für den Provider zurück.
        Lazy Initialization - Client wird erst bei erstem Aufruf erstellt.
        """
        if provider in self._clients:
            return self._clients[provider]
        
        # API Key prüfen
        api_key = self.get_api_key(provider)
        if not api_key:
            raise ValueError(f"Kein API Key für Provider '{provider.value}' gefunden. "
                           f"Setze {self.API_KEY_ENV[provider]} in .env")
        
        # Client erstellen
        if provider in [ModelProvider.OPENAI, ModelProvider.DEEPSEEK, 
                       ModelProvider.INCEPTION, ModelProvider.NVIDIA, 
                       ModelProvider.OPENROUTER]:
            client = self._init_openai_compatible(provider)
        elif provider == ModelProvider.ANTHROPIC:
            client = self._init_anthropic()
        elif provider == ModelProvider.GOOGLE:
            client = self._init_google()
        else:
            raise ValueError(f"Unbekannter Provider: {provider}")
        
        self._clients[provider] = client
        log.info(f"✓ Client initialisiert: {provider.value}")
        return client
    
    def _init_openai_compatible(self, provider: ModelProvider):
        """Initialisiert OpenAI-kompatiblen Client."""
        from openai import OpenAI
        return OpenAI(
            api_key=self.get_api_key(provider),
            base_url=self.get_base_url(provider)
        )
    
    def _init_anthropic(self):
        """Initialisiert Anthropic Client."""
        try:
            from anthropic import Anthropic
            return Anthropic(api_key=self.get_api_key(ModelProvider.ANTHROPIC))
        except ImportError:
            log.warning("anthropic Package nicht installiert, nutze httpx Fallback")
            return None  # Wird via httpx aufgerufen
    
    def _init_google(self):
        """Initialisiert Google Client (Placeholder)."""
        return None


class AgentModelConfig:
    """
    Konfiguration welches Modell/Provider jeder Agent-Typ nutzt.
    Lädt aus Environment Variables mit Fallbacks.
    """
    
    # Format: agent_type -> (model_env_key, provider_env_key, fallback_model, fallback_provider)
    AGENT_CONFIGS = {
        "executor": ("FAST_MODEL", "FAST_MODEL_PROVIDER", "gpt-5-mini", ModelProvider.OPENAI),
        "deep_research": ("RESEARCH_MODEL", "RESEARCH_MODEL_PROVIDER", "deepseek-reasoner", ModelProvider.DEEPSEEK),
        "creative": ("CREATIVE_MODEL", "CREATIVE_MODEL_PROVIDER", "gpt-5.2", ModelProvider.OPENAI),
        "developer": ("CODE_MODEL", "CODE_MODEL_PROVIDER", "mercury-coder-small", ModelProvider.INCEPTION),
        "meta": ("PLANNING_MODEL", "PLANNING_MODEL_PROVIDER", "claude-sonnet-4-5-20250929", ModelProvider.ANTHROPIC),
        "visual": ("VISION_MODEL", "VISION_MODEL_PROVIDER", "claude-sonnet-4-5-20250929", ModelProvider.ANTHROPIC),
        "reasoning": ("REASONING_MODEL", "REASONING_MODEL_PROVIDER", "nvidia/nemotron-3-nano-30b-a3b", ModelProvider.OPENROUTER),
    }
    
    @classmethod
    def get_model_and_provider(cls, agent_type: str) -> Tuple[str, ModelProvider]:
        """Gibt Modell und Provider für einen Agent-Typ zurück."""
        if agent_type not in cls.AGENT_CONFIGS:
            log.warning(f"Unbekannter Agent-Typ: {agent_type}, nutze Defaults")
            return "gpt-4o", ModelProvider.OPENAI
        
        model_env, provider_env, fallback_model, fallback_provider = cls.AGENT_CONFIGS[agent_type]
        
        model = os.getenv(model_env, fallback_model)
        provider_str = os.getenv(provider_env, fallback_provider.value)
        
        try:
            provider = ModelProvider(provider_str.lower())
        except ValueError:
            log.warning(f"Unbekannter Provider '{provider_str}', nutze Fallback")
            provider = fallback_provider
        
        return model, provider


# Globale Provider-Client Instanz
_provider_client: Optional[MultiProviderClient] = None

def get_provider_client() -> MultiProviderClient:
    """Gibt die globale Provider-Client Instanz zurück."""
    global _provider_client
    if _provider_client is None:
        _provider_client = MultiProviderClient()
    return _provider_client


# ==============================================================================
# SYSTEM PROMPTS
# ==============================================================================

SINGLE_ACTION_WARNING = """
⚠️ KRITISCHE EINSCHRÄNKUNG ⚠️
DU DARFST NUR EINE EINZIGE AKTION PRO ANTWORT SENDEN!
NIEMALS mehrere JSON-Objekte hintereinander!
NIEMALS mehrere Actions in einer Antwort!
"""

EXECUTOR_PROMPT_TEMPLATE = """
""" + (get_system_prompt_prefix() if PERSONALITY_ENABLED else "") + """
Du bist ein hochkompetenter KI-Assistent. Deine Aufgabe ist es, die Ziele des Nutzers effizient und zuverlässig zu erreichen, indem du die dir zur Verfügung stehenden Werkzeuge strategisch einsetzt.

DATUM: {current_date}

# DEINE HANDLUNGSPRIORITÄTEN (VON OBEN NACH UNTEN):

1. **DIREKTE, ATOMARE TOOLS (IMMER BEVORZUGEN):**
   - Wenn du Dateien lesen, schreiben oder auflisten sollst, benutze IMMER die entsprechenden file_system Tools
   - Wenn du Code ändern sollst, nutze implement_feature
   - Wenn du eine Websuche machen sollst, nutze search_web
   - Wenn du eine Aufgabe planen sollst, nutze add_task
   - **Grundregel:** Wenn es ein spezifisches, nicht-visuelles Werkzeug für eine Aufgabe gibt, benutze es! Es ist schneller und zuverlässiger.

2. **WEB-BROWSER-AUTOMATION (FÜR WEBSEITEN):**
   - Wenn das Ziel eine Webseite ist, nutze die browser_tool Methoden (open_url, click_by_text, get_text)

3. **ERLERNTE FÄHIGKEITEN (SKILLS):**
   - Wenn eine Aufgabe eine Fähigkeit erfordert, die du gelernt hast, nutze sie
   - Überprüfe mit list_available_skills(), welche du kennst
   - Führe Skills aus mit run_skill(name, params)

# DEIN DENKPROZESS:
1. **Verstehe das Ziel:** Was will der Nutzer wirklich erreichen?
2. **Konsultiere die Prioritätenliste:** Welches ist das direkteste und zuverlässigste Werkzeug?
3. **Plane den Schritt:** Formuliere die Action mit den korrekten Parametern
4. **Führe aus und bewerte:** Hat der Schritt funktioniert? Wenn nicht, wähle eine alternative Methode

Deine Aufgabe ist es, den **intelligentesten und kürzesten Weg zum Ziel** zu finden.

# VERFÜGBARE TOOLS
{tools_description}

# ANTWORTFORMAT
Thought: [Dein Plan für den nächsten einzelnen Schritt]
Action: {{"method": "tool_name", "params": {{"key": "value"}}}}

# REGELN
- Nutze die exakten Tool-Namen wie in der Liste
- Bei einfachen Fragen direkt antworten mit "Final Answer: ..."
- Wenn du FERTIG bist: "Final Answer: [Deine abschließende Zusammenfassung]"

""" + SINGLE_ACTION_WARNING

DEEP_RESEARCH_PROMPT_TEMPLATE = """
# IDENTITÄT
Du bist der Timus Deep Research Agent - ein Experte für Tiefenrecherche.
DATUM: {current_date}

# VERFÜGBARE TOOLS
{tools_description}

# WICHTIGE TOOLS
1. **start_deep_research** - {{"method": "start_deep_research", "params": {{"query": "...", "focus_areas": [...]}}}}
2. **generate_research_report** - {{"method": "generate_research_report", "params": {{"session_id": "...", "format": "markdown"}}}}
3. **search_web** - {{"method": "search_web", "params": {{"query": "...", "max_results": 10}}}}

# WORKFLOW
1. Analysiere die Anfrage
2. Rufe start_deep_research auf
3. Rufe generate_research_report auf  
4. Gib Final Answer

# ANTWORTFORMAT
Thought: [Deine Analyse]
Action: {{"method": "tool_name", "params": {{...}}}}

""" + SINGLE_ACTION_WARNING

REASONING_PROMPT_TEMPLATE = """
# IDENTITÄT
Du bist der Timus Reasoning Agent - spezialisiert auf komplexe Analyse und Multi-Step Reasoning.
DATUM: {current_date}

# DEINE STÄRKEN
- Komplexe Probleme in Denkschritten lösen
- Root-Cause Analyse und Debugging
- Architektur-Entscheidungen
- Mathematische und logische Problemlösung
- Multi-Step Planung

# VERFÜGBARE TOOLS
{tools_description}

# REASONING WORKFLOW
Bei komplexen Problemen:
1. **VERSTEHEN**: Was ist das Problem?
2. **ZERLEGEN**: Teilprobleme identifizieren
3. **ANALYSIEREN**: Schritt für Schritt
4. **OPTIONEN**: Lösungswege auflisten
5. **BEWERTEN**: Pro/Contra
6. **ENTSCHEIDEN**: Beste Lösung

# ANTWORTFORMAT
Für Tool-Aufrufe:
Thought: [Schrittweise Analyse]
Action: {{"method": "tool_name", "params": {{...}}}}

Für direkte Analyse:
Thought: [Ausführliche Analyse]
Final Answer: [Zusammenfassung und Empfehlung]

""" + SINGLE_ACTION_WARNING

VISUAL_SYSTEM_PROMPT = """
# WICHTIGE REGELN
- Browser: start_visual_browser(url="https://...")
- Apps: open_application(app_name="...")
- SoM nur für Elemente INNERHALB einer App

# MISSION
Du bist ein visueller Automatisierungs-Agent mit Screenshot-Analyse.

# WORKFLOW
1. scan_ui_elements() - UI scannen
2. capture_screen_before_action() - Screenshot vor Aktion
3. click_at(x, y) - Klicken
4. verify_action_result() - Verifizieren
5. type_text() - Text eingeben (nach Klick)

# VERFÜGBARE TOOLS
{tools_description}

# ABSCHLUSS
{{"method": "finish_task", "params": {{"message": "..."}}}}
ODER: Final Answer: [Beschreibung]

""" + SINGLE_ACTION_WARNING

CREATIVE_SYSTEM_PROMPT = """
Du bist C.L.A.I.R.E. - Kreativ-Agent für Bilder, Code, Texte.

# TOOLS
{tools_description}

# ⚠️ ABSOLUT KRITISCH - FORMAT ⚠️
DEINE ANTWORT MUSS EXAKT SO AUSSEHEN (MIT "Thought:" und "Action:" Labels!):

Thought: [Kurze Analyse der Anfrage]
Action: {{"method": "generate_image", "params": {{"prompt": "detailed english description", "size": "1024x1024", "quality": "high"}}}}

⚠️ STOPP! NICHTS MEHR NACH "Action:" SCHREIBEN!
⚠️ KEIN "Final Answer", KEIN zusätzlicher Text!
⚠️ DAS SYSTEM WIRD DIR EINE "Observation:" SENDEN!

Erst NACHDEM du "Observation:" erhältst, darfst du "Final Answer:" senden!

# BEISPIEL (GENAU SO MACHEN!)
User: male einen hund

DEINE ERSTE ANTWORT (ohne Final Answer!):
Thought: Ich erstelle ein Hundebild mit DALL-E.
Action: {{"method": "generate_image", "params": {{"prompt": "friendly golden retriever dog, sunny park, realistic photo", "size": "1024x1024", "quality": "high"}}}}

[SYSTEM]: Observation: {{"status": "success", "saved_as": "results/dog.png"}}

DEINE ZWEITE ANTWORT (nachdem Observation da ist):
Thought: Bild erfolgreich generiert.
Final Answer: Hundebild erstellt! Gespeichert unter: results/dog.png

# REGELN
- Bildprompts auf Englisch!
- Quality="high" für Details (Werte: "low", "medium", "high", "auto")
- Verwende IMMER "Thought:" und "Action:" Labels!
- NIEMALS "Final Answer" in erster Antwort!

""" + SINGLE_ACTION_WARNING

DEVELOPER_SYSTEM_PROMPT = """
Du bist D.A.V.E. (Developer). 
TOOLS: {tools_description}
Zuständig für: Code, Skripte, Dateien.

Format: Thought... Action: {{"method": "...", "params": {{...}}}}

""" + SINGLE_ACTION_WARNING

META_SYSTEM_PROMPT = """
Du bist T.I.M. (Meta-Agent) - Koordinator für komplexe Aufgaben.
DATUM: {current_date}

# REGEL
Du MUSST Tools ausführen! KEINE Final Answer ohne Aktion!

# SKILLS
- search_google, open_website, click_element_by_description
- type_in_field, take_screenshot, close_active_window

# TOOLS
{tools_description}

# FORMAT
Thought: [Analyse]
Action: {{"method": "run_skill", "params": {{"name": "...", "params": {{...}}}}}}

""" + SINGLE_ACTION_WARNING


# ==============================================================================
# BASIS AGENT MIT MULTI-PROVIDER SUPPORT
# ==============================================================================

class BaseAgent:
    """Basisklasse für alle Agenten mit Multi-Provider Support."""
    
    def __init__(
        self,
        system_prompt_template: str,
        tools_description_string: str,
        max_iterations: int = 30,
        agent_type: str = "executor"
    ):
        self.max_iterations = max_iterations
        self.agent_type = agent_type
        self.http_client = httpx.AsyncClient(timeout=300.0)
        self.recent_actions = []

        # Multi-Provider Setup
        self.provider_client = get_provider_client()
        self.model, self.provider = AgentModelConfig.get_model_and_provider(agent_type)

        log.info(f"🔹 {self.__class__.__name__} | {self.model} | {self.provider.value}")

        self.system_prompt = (
            system_prompt_template
            .replace("{current_date}", datetime.now().strftime("%d.%m.%Y"))
            .replace("{tools_description}", tools_description_string)
        )

        # Screen-Change-Gate Support (v1.0)
        self.use_screen_change_gate = os.getenv("USE_SCREEN_CHANGE_GATE", "false").lower() == "true"
        self.cached_screen_state: Optional[Dict] = None
        self.last_screen_analysis_time: float = 0

        # ROI (Region of Interest) Support (v2.0)
        self.roi_stack: List[Dict] = []  # Stack für verschachtelte ROIs
        self.current_roi: Optional[Dict] = None

        if self.use_screen_change_gate:
            log.info(f"✅ Screen-Change-Gate AKTIV für {self.__class__.__name__}")

    def _sanitize_observation(self, obs: Any) -> Any:
        """Kürzt lange Observations."""
        if isinstance(obs, dict):
            clean = obs.copy()
            for k, v in clean.items():
                if isinstance(v, str) and len(v) > 500:
                    clean[k] = f"<{len(v)} chars>"
                elif isinstance(v, list) and len(v) > 10:
                    clean[k] = v[:10] + [f"... +{len(v)-10}"]
            return clean
        elif isinstance(obs, str) and len(obs) > 2000:
            return obs[:2000] + "..."
        return obs

    def should_skip_action(self, action_name: str, params: dict) -> Tuple[bool, Optional[str]]:
        """
        Loop-Detection mit verbessertem Handling.

        Returns:
            Tuple[bool, str]: (should_skip, reason)
                - should_skip: True wenn Action übersprungen werden soll
                - reason: Grund für Skip (z.B. "Loop detected 3x")
        """
        action_key = f"{action_name}:{json.dumps(params, sort_keys=True)}"
        count = self.recent_actions.count(action_key)

        # Count ist: Wie oft ist dieser Key BEREITS in der Liste
        # count=0: Erster Call
        # count=1: Zweiter Call (Loop-Warnung)
        # count=2: Dritter Call (Kritisch)

        if count >= 2:
            # Kritischer Loop (3. Call): Action überspringen
            reason = f"Loop detected: {action_name} wurde bereits {count+1}x aufgerufen mit denselben Parametern. KRITISCH: Aktion wird übersprungen. Versuche anderen Ansatz!"
            log.error(f"❌ Kritischer Loop ({count+1}x): {action_name} - Aktion wird übersprungen")
            # NICHT appenden - Action wird nicht ausgeführt
            return True, reason

        elif count >= 1:
            # Loop-Warnung (2. Call): Action ausführen, aber warnen
            reason = f"Loop detected: {action_name} wurde bereits {count+1}x aufgerufen mit denselben Parametern. Versuche andere Parameter oder anderen Ansatz."
            log.warning(f"⚠️ Loop ({count+1}x): {action_name} - Warnung an Agent")
            self.recent_actions.append(action_key)
            return False, reason

        # Kein Loop (1. Call)
        self.recent_actions.append(action_key)
        if len(self.recent_actions) > 20:
            self.recent_actions.pop(0)

        return False, None

    def _refine_tool_call(self, method: str, params: dict) -> Tuple[str, dict]:
        """Korrigiert Tool-Aufrufe."""
        if method == "Image Generation":
            params.setdefault("model", IMAGE_MODEL_NAME)
            params.setdefault("size", "1024x1024")
            params.setdefault("quality", "high")

        corrections = {
            "URL Viewer": "start_visual_browser",
            "start_app": "open_application",
            "click": "click_at",
            "deep_research": "start_deep_research",
        }
        if method in corrections:
            method = corrections[method]
        
        if method == "start_deep_research" and "topic" in params:
            params["query"] = params.pop("topic")
        
        if method == "click_at" and "x" in params:
            params["x"] = int(params["x"])
            params["y"] = int(params["y"])
        
        return method, params

    def _handle_file_artifacts(self, observation: dict):
        """Öffnet generierte Dateien."""
        if not isinstance(observation, dict):
            return
        if os.getenv("AUTO_OPEN_FILES", "true").lower() != "true":
            return
        
        file_path = observation.get("file_path") or observation.get("saved_as") or observation.get("filepath")
        if file_path and os.path.exists(file_path):
            log.info(f"📂 Öffne: {file_path}")
            try:
                if platform.system() == "Windows":
                    os.startfile(file_path)
                elif platform.system() == "Darwin":
                    subprocess.call(["open", file_path])
                else:
                    subprocess.call(["xdg-open", file_path])
            except Exception as e:
                log.warning(f"Öffnen fehlgeschlagen: {e}")

    async def _call_tool(self, method: str, params: dict) -> dict:
        """Ruft Tool via MCP auf."""
        method, params = self._refine_tool_call(method, params)

        # Loop-Detection mit Reason
        should_skip, loop_reason = self.should_skip_action(method, params)

        if should_skip:
            # Kritischer Loop → Aktion überspringen
            log.error(f"❌ Tool-Call übersprungen: {method} (Loop)")
            return {"skipped": True, "reason": loop_reason or "Loop detected"}

        if loop_reason:
            # Warnung (aber Action wird ausgeführt)
            log.warning(f"⚠️ Loop-Warnung für {method}: {loop_reason}")

        log.info(f"📡 {method} -> {str(params)[:100]}")

        try:
            resp = await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": "1"}
            )
            data = resp.json()

            if "result" in data:
                result = data["result"]

                # Füge Loop-Warnung zur Response hinzu
                if loop_reason:
                    if isinstance(result, dict):
                        result["_loop_warning"] = loop_reason
                    else:
                        # Wenn result kein Dict ist, wrappen wir es
                        result = {
                            "value": result,
                            "_loop_warning": loop_reason
                        }

                return result

            if "error" in data:
                return {"error": str(data["error"])}
            return {"error": "Invalid response"}
        except Exception as e:
            return {"error": str(e)}

    async def _should_analyze_screen(self, roi: Optional[Dict] = None, force: bool = False) -> bool:
        """
        Screen-Change-Gate: Prüft ob Screen-Analyse nötig ist.

        Args:
            roi: Optional - Region of Interest (nur bestimmten Bereich prüfen)
            force: Analyse erzwingen (Gate überspringen)

        Returns:
            True wenn Analyse nötig, False wenn Cache genutzt werden kann
        """
        if not self.use_screen_change_gate or force:
            return True  # Immer analysieren wenn Gate deaktiviert oder force=True

        try:
            # Screen-Change-Check
            params = {}
            if roi:
                params["roi"] = roi

            result = await self._call_tool("should_analyze_screen", params)

            if result and result.get("changed"):
                log.debug(f"🔄 Screen geändert - {result.get('info', {}).get('reason', 'unknown')}")
                return True
            else:
                log.debug(f"⏭️ Screen unverändert - Cache nutzen")
                return False

        except Exception as e:
            log.warning(f"Screen-Change-Gate Fehler: {e}, analysiere sicherheitshalber")
            return True  # Bei Fehler sicherheitshalber analysieren

    async def _get_screen_state(
        self,
        screen_id: str = "current",
        anchor_specs: Optional[List[Dict]] = None,
        element_specs: Optional[List[Dict]] = None,
        force_analysis: bool = False
    ) -> Optional[Dict]:
        """
        Holt ScreenState (mit Screen-Change-Gate Optimization).

        Args:
            screen_id: Screen-Identifikator
            anchor_specs: Anker-Spezifikationen
            element_specs: Element-Spezifikationen
            force_analysis: Analyse erzwingen (Cache überspringen)

        Returns:
            ScreenState als Dict oder None bei Fehler
        """
        # Prüfe ob Analyse nötig
        if not force_analysis and not await self._should_analyze_screen():
            # Cache nutzen
            if self.cached_screen_state:
                log.debug("✅ Nutze gecachten ScreenState")
                return self.cached_screen_state

        # Screen analysieren
        try:
            import time
            self.last_screen_analysis_time = time.time()

            params = {
                "screen_id": screen_id,
                "anchor_specs": anchor_specs or [],
                "element_specs": element_specs or [],
                "extract_ocr": False
            }

            result = await self._call_tool("analyze_screen_state", params)

            if result and not result.get("error"):
                # Cache aktualisieren
                self.cached_screen_state = result
                log.debug(f"✅ ScreenState analysiert: {len(result.get('elements', []))} Elemente")
                return result
            else:
                log.warning(f"Screen-Analyse fehlgeschlagen: {result.get('error', 'unknown')}")
                return None

        except Exception as e:
            log.error(f"Screen-State Fehler: {e}")
            return None

    # ==================================================================
    # STRUKTURIERTE NAVIGATION (v2.0)
    # ==================================================================

    async def _analyze_current_screen(self) -> Optional[Dict]:
        """
        Analysiert den aktuellen Screen und gibt Elemente zurück.

        Nutzt Auto-Discovery:
        1. OCR für Text-Elemente
        2. SOM für interaktive Elemente (Buttons, Links, etc.)

        Returns:
            Dict mit {"screen_id": str, "elements": List[Dict]} oder None
        """
        try:
            elements = []

            # 1. OCR: Alle Text-Elemente finden
            ocr_result = await self._call_tool("get_all_screen_text", {})
            if ocr_result and ocr_result.get("texts"):
                for i, text_item in enumerate(ocr_result["texts"][:20]):  # Max 20 Text-Elemente
                    if isinstance(text_item, dict):
                        elements.append({
                            "name": f"text_{i}",
                            "type": "text",
                            "text": text_item.get("text", ""),
                            "x": text_item.get("x", 0),
                            "y": text_item.get("y", 0),
                            "confidence": text_item.get("confidence", 0.0)
                        })

            # 2. SOM: Interaktive Elemente finden (Buttons, Links, etc.)
            # TODO: Wenn SOM-Tool verfügbar ist, hier nutzen
            # som_result = await self._call_tool("get_clickable_elements", {})

            if not elements:
                log.debug("📋 Screen-Analyse: Keine Elemente gefunden")
                return None

            log.info(f"📋 Screen-Analyse: {len(elements)} Elemente gefunden")

            return {
                "screen_id": "current_screen",
                "elements": elements,
                "anchors": []
            }

        except Exception as e:
            log.error(f"❌ Screen-Analyse fehlgeschlagen: {e}")
            return None

    async def _create_navigation_plan_with_llm(self, task: str, screen_state: Dict) -> Optional[Dict]:
        """
        Erstellt einen ActionPlan basierend auf Task und Screen-State mit LLM.

        Args:
            task: Die zu erfüllende Aufgabe
            screen_state: Der analysierte Screen-State mit Elementen

        Returns:
            ActionPlan Dict oder None bei Fehler
        """
        try:
            # Extrahiere verfügbare Elemente
            elements = screen_state.get("elements", [])
            if not elements:
                log.warning("⚠️ Keine Elemente für ActionPlan verfügbar")
                return None

            # Erstelle Element-Liste mit Text-Content
            element_list = []
            for i, elem in enumerate(elements[:15]):  # Max 15 Elemente
                text = elem.get("text", "").strip()
                if text:  # Nur Elemente mit Text
                    element_list.append({
                        "name": elem.get("name", f"elem_{i}"),
                        "text": text[:50],  # Kürze lange Texte
                        "x": elem.get("x", 0),
                        "y": elem.get("y", 0),
                        "type": elem.get("type", "unknown")
                    })

            if not element_list:
                log.warning("⚠️ Keine Elemente mit Text gefunden")
                return None

            # Vereinfachtes Prompt (weniger komplex)
            element_summary = "\n".join([
                f"{i+1}. {e['name']}: \"{e['text']}\" at ({e['x']}, {e['y']})"
                for i, e in enumerate(element_list)
            ])

            prompt = f"""Erstelle einen ACTION-PLAN für diese Aufgabe:

AUFGABE: {task}

VERFÜGBARE ELEMENTE:
{element_summary}

BEISPIEL ACTION-PLAN:
{{
  "task_id": "search_task",
  "description": "Google suchen nach Python",
  "steps": [
    {{"op": "type", "target": "elem_2", "value": "Python", "retries": 2}},
    {{"op": "click", "target": "elem_5", "retries": 2}}
  ]
}}

Antworte NUR mit JSON (keine Markdown, keine Erklärung):"""

            # LLM-Call (ohne Vision) - nutze Nemotron für ActionPlan
            # Nemotron ist speziell für strukturierte JSON-Outputs trainiert!
            old_model = self.model
            old_provider = self.provider

            # Temporär auf Nemotron wechseln (bestes Modell für JSON-Generation)
            self.model = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
            self.provider = ModelProvider.OPENROUTER

            # Aktiviere Reasoning für bessere ActionPlan-Qualität
            old_thinking = os.environ.get("NEMOTRON_ENABLE_THINKING")
            os.environ["NEMOTRON_ENABLE_THINKING"] = "true"

            try:
                response = await self._call_llm([
                    {"role": "user", "content": prompt}
                ])
            finally:
                # Stelle Original-Modell wieder her
                self.model = old_model
                self.provider = old_provider
                if old_thinking is not None:
                    os.environ["NEMOTRON_ENABLE_THINKING"] = old_thinking
                else:
                    os.environ.pop("NEMOTRON_ENABLE_THINKING", None)

            # Extrahiere JSON (robuster)
            import re

            # Entferne Markdown-Code-Blocks
            response = re.sub(r'```json\s*', '', response)
            response = re.sub(r'```\s*', '', response)

            # Finde JSON
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if not json_match:
                log.warning(f"⚠️ Kein JSON gefunden in Response: {response[:200]}")
                return None

            plan = json.loads(json_match.group(0))

            # Validiere Plan
            if not plan.get("steps") or not isinstance(plan["steps"], list):
                log.warning("⚠️ ActionPlan hat keine Steps")
                return None

            # Konvertiere zu kompatiblem Format
            # Tool erwartet: {"goal": str, "screen_id": str, "steps": [...]}
            compatible_plan = {
                "goal": plan.get("description", task),
                "screen_id": screen_state.get("screen_id", "current_screen"),
                "steps": []
            }

            for step in plan["steps"]:
                # Konvertiere Step zu kompatiblem Format
                compatible_step = {
                    "op": step.get("op", "click"),
                    "target": step.get("target", ""),
                    "params": {},
                    "verify_before": [],
                    "verify_after": [],
                    "retries": step.get("retries", 2)
                }

                # Füge value zu params hinzu (für type-operation)
                if "value" in step:
                    compatible_step["params"]["text"] = step["value"]

                compatible_plan["steps"].append(compatible_step)

            log.info(f"📝 ActionPlan erstellt: {compatible_plan['goal']} ({len(compatible_plan['steps'])} Steps)")
            return compatible_plan

        except json.JSONDecodeError as e:
            log.error(f"❌ JSON-Parsing fehlgeschlagen: {e}")
            return None
        except Exception as e:
            log.error(f"❌ ActionPlan-Erstellung fehlgeschlagen: {e}")
            return None

    async def _try_structured_navigation(self, task: str) -> Optional[Dict]:
        """
        Versucht strukturierte Navigation mit Screen-Contract-Tool.

        Strategie:
        1. Analysiere aktuellen Screen (Screen-State holen)
        2. Erstelle ActionPlan mit LLM basierend auf Screen-State + Task
        3. Führe ActionPlan aus
        4. Bei Fehler → None (Agent nutzt regulären Flow)

        Returns:
            Dict mit {"success": bool, "result": str, "state": Dict} oder None bei Fehler
        """
        try:
            log.info("📋 Versuche strukturierte Navigation...")

            # 1. Screen-State analysieren
            screen_state = await self._analyze_current_screen()
            if not screen_state or not screen_state.get("elements"):
                log.info("⚠️ Keine Elemente gefunden - nutze regulären Flow")
                return None

            # 2. ActionPlan mit LLM erstellen
            action_plan = await self._create_navigation_plan_with_llm(task, screen_state)
            if not action_plan:
                log.info("⚠️ ActionPlan-Erstellung fehlgeschlagen - nutze regulären Flow")
                return None

            # 3. ActionPlan ausführen
            log.info(f"🎯 Führe ActionPlan aus: {action_plan.get('goal', 'N/A')}")
            result = await self._call_tool("execute_action_plan", {"plan_dict": action_plan})

            if result and result.get("success"):
                return {
                    "success": True,
                    "result": action_plan.get("goal", "Aufgabe erfolgreich"),
                    "state": screen_state
                }
            else:
                log.warning(f"⚠️ ActionPlan fehlgeschlagen: {result.get('error', 'Unknown')}")
                return None

        except Exception as e:
            log.error(f"❌ Strukturierte Navigation fehlgeschlagen: {e}")
            return None

    # ==================================================================
    # ROI (REGION OF INTEREST) MANAGEMENT (v2.0)
    # ==================================================================

    def _set_roi(self, x: int, y: int, width: int, height: int, name: str = "custom"):
        """
        Setzt eine Region of Interest für Screen-Change-Gate.

        Args:
            x, y: Top-left Koordinaten
            width, height: Dimensionen
            name: ROI-Name für Debugging
        """
        roi = {"x": x, "y": y, "width": width, "height": height, "name": name}
        self.current_roi = roi
        log.info(f"🔲 ROI gesetzt: {name} ({x},{y} {width}x{height})")

    def _clear_roi(self):
        """Löscht die aktuelle ROI."""
        self.current_roi = None
        log.info("🔲 ROI gelöscht")

    def _push_roi(self, x: int, y: int, width: int, height: int, name: str = "custom"):
        """Fügt eine ROI zum Stack hinzu (für verschachtelte ROIs)."""
        if self.current_roi:
            self.roi_stack.append(self.current_roi)
        self._set_roi(x, y, width, height, name)

    def _pop_roi(self):
        """Entfernt die aktuelle ROI und stellt die vorherige wieder her."""
        if self.roi_stack:
            self.current_roi = self.roi_stack.pop()
            log.info(f"🔲 ROI wiederhergestellt: {self.current_roi['name']}")
        else:
            self._clear_roi()

    async def _detect_dynamic_ui_and_set_roi(self, task: str) -> bool:
        """
        Erkennt dynamische UIs und setzt automatisch passende ROI.

        Args:
            task: Die aktuelle Aufgabe

        Returns:
            True wenn ROI gesetzt wurde, False sonst
        """
        task_lower = task.lower()

        # Google-Erkennung
        if "google" in task_lower and ("such" in task_lower or "search" in task_lower):
            # ROI auf Suchleiste beschränken (nicht Suchergebnisse/Ads)
            self._set_roi(x=200, y=100, width=800, height=150, name="google_searchbar")
            log.info("🔍 Dynamische UI erkannt: Google Search - ROI auf Suchleiste gesetzt")
            return True

        # Booking.com-Erkennung
        elif "booking" in task_lower:
            # ROI auf Haupt-Suchformular
            self._set_roi(x=100, y=150, width=1000, height=400, name="booking_search_form")
            log.info("🏨 Dynamische UI erkannt: Booking.com - ROI auf Suchformular gesetzt")
            return True

        # Amazon-Erkennung
        elif "amazon" in task_lower:
            self._set_roi(x=200, y=50, width=900, height=200, name="amazon_search_bar")
            log.info("🛒 Dynamische UI erkannt: Amazon - ROI auf Suchleiste gesetzt")
            return True

        # Weitere dynamische UIs können hier hinzugefügt werden

        return False

    async def _call_llm(self, messages: List[Dict]) -> str:
        """Routet zum richtigen Provider."""
        try:
            if self.provider in [ModelProvider.OPENAI, ModelProvider.DEEPSEEK, 
                                ModelProvider.INCEPTION, ModelProvider.NVIDIA,
                                ModelProvider.OPENROUTER]:
                return await self._call_openai_compatible(messages)
            elif self.provider == ModelProvider.ANTHROPIC:
                return await self._call_anthropic(messages)
            else:
                return f"Error: Provider {self.provider} nicht unterstützt"
        except Exception as e:
            log.error(f"LLM Fehler: {e}")
            return f"Error: {e}"

    async def _call_openai_compatible(self, messages: List[Dict]) -> str:
        """OpenAI-kompatible APIs mit automatischer Kompatibilität."""
        client = self.provider_client.get_client(self.provider)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2000
        }

        # Mercury Diffusing
        if self.provider == ModelProvider.INCEPTION:
            if os.getenv("MERCURY_DIFFUSING", "false").lower() == "true":
                kwargs["extra_body"] = {"diffusing": True}

        # Nemotron enable_thinking
        if "nemotron" in self.model.lower():
            enable = os.getenv("NEMOTRON_ENABLE_THINKING", "true").lower() == "true"
            if not enable:
                kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
                kwargs["temperature"] = 0.6
                kwargs["top_p"] = 0.95
            else:
                kwargs["temperature"] = 1.0
                kwargs["top_p"] = 1.0

        # Automatische API-Kompatibilität (max_tokens vs max_completion_tokens, temperature)
        kwargs = prepare_openai_params(kwargs)

        resp = await asyncio.to_thread(client.chat.completions.create, **kwargs)
        return resp.choices[0].message.content.strip()

    async def _call_anthropic(self, messages: List[Dict]) -> str:
        """Anthropic Claude API."""
        client = self.provider_client.get_client(ModelProvider.ANTHROPIC)
        
        system_content = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                chat_messages.append(msg)
        
        if client:
            resp = await asyncio.to_thread(
                client.messages.create,
                model=self.model,
                max_tokens=2000,
                system=system_content,
                messages=chat_messages
            )
            return resp.content[0].text.strip()
        else:
            # httpx Fallback
            api_key = self.provider_client.get_api_key(ModelProvider.ANTHROPIC)
            async with httpx.AsyncClient(timeout=120.0) as http:
                resp = await http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 2000,
                        "system": system_content,
                        "messages": chat_messages
                    }
                )
                return resp.json()["content"][0]["text"].strip()

    def _parse_action(self, text: str) -> Tuple[Optional[dict], Optional[str]]:
        """Extrahiert Action (FIX: Nur erste bei multiple JSON)."""
        text = text.strip()

        # PRIORITÄT 1: Versuche direktes JSON-Parsing für mehrzeiliges/verschachteltes JSON (Nemotron)
        if text.startswith('{') and text.endswith('}'):
            try:
                data = json.loads(text)
                if "action" in data:
                    return data["action"], None
                if "method" in data:
                    return data, None
            except json.JSONDecodeError:
                pass  # Fallback zu anderen Methoden

        # PRIORITÄT 2: Zeilenweise suchen (einzeiliges JSON)
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    data = json.loads(line)
                    if "action" in data:
                        return data["action"], None
                    if "method" in data:
                        return data, None
                except json.JSONDecodeError:
                    continue

        # PRIORITÄT 3: Regex Fallback für komplexere Fälle
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'Action:\s*(\{[\s\S]*?\})\s*(?:\n|$)',
            r'(\{[^{}]*"method"[^{}]*\})',
            r'(\{[^{}]+\})'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    json_str = re.sub(r',\s*([\}\]])', r'\1', match.group(1).strip())
                    data = json.loads(json_str)
                    if "action" in data:
                        return data["action"], None
                    if "method" in data:
                        return data, None
                except:
                    continue

        return None, "Kein JSON gefunden"

    async def run(self, task: str) -> str:
        """Führt Agent aus."""
        log.info(f"▶️ {self.__class__.__name__} ({self.provider.value})")

        # ROI-Management: Erkenne dynamische UIs und setze ROI
        roi_set = await self._detect_dynamic_ui_and_set_roi(task)

        # Versuche strukturierte Navigation ZUERST (nur für Screen-Tasks)
        # Erkenne ob Task Screen-Navigation erfordert
        task_lower = task.lower()
        is_navigation_task = any(keyword in task_lower for keyword in [
            "browser", "website", "url", "klick", "click", "such", "search",
            "booking", "google", "amazon", "navigate", "öffne", "gehe zu"
        ])

        if is_navigation_task:
            structured_result = await self._try_structured_navigation(task)
            if structured_result and structured_result.get("success"):
                log.info(f"✅ Strukturierte Navigation erfolgreich: {structured_result['result']}")
                # Clear ROI nach erfolgreichem Task
                if roi_set:
                    self._clear_roi()
                return structured_result["result"]
            else:
                log.info("📋 Strukturierte Navigation nicht möglich - nutze regulären Flow")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task}
        ]

        for step in range(1, self.max_iterations + 1):
            reply = await self._call_llm(messages)
            
            if reply.startswith("Error"):
                # Clear ROI bei Error
                if roi_set:
                    self._clear_roi()
                return reply
            if "Final Answer:" in reply:
                # Clear ROI bei Success
                if roi_set:
                    self._clear_roi()
                return reply.split("Final Answer:")[1].strip()
            
            action, err = self._parse_action(reply)
            messages.append({"role": "assistant", "content": reply})
            
            if not action:
                messages.append({"role": "user", "content": f"Fehler: {err}. Korrektes JSON senden."})
                continue
            
            obs = await self._call_tool(action.get("method", ""), action.get("params", {}))
            self._handle_file_artifacts(obs)
            messages.append({"role": "user", "content": f"Observation: {json.dumps(self._sanitize_observation(obs), ensure_ascii=False)}"})

        # Clear ROI am Ende (auch bei Max Iterations)
        if roi_set:
            self._clear_roi()

        return "Limit erreicht."


# ==============================================================================
# SPEZIALISIERTE AGENTEN
# ==============================================================================

class ExecutorAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(EXECUTOR_PROMPT_TEMPLATE, tools_description_string, 30, "executor")


class DeepResearchAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(DEEP_RESEARCH_PROMPT_TEMPLATE, tools_description_string, 8, "deep_research")
        self.http_client = httpx.AsyncClient(timeout=600.0)
        self.current_session_id: Optional[str] = None
    
    async def _call_tool(self, method: str, params: dict) -> dict:
        result = await super()._call_tool(method, params)
        if isinstance(result, dict) and "session_id" in result:
            self.current_session_id = result["session_id"]
        if method == "generate_research_report" and self.current_session_id:
            params.setdefault("session_id", self.current_session_id)
        return result


class ReasoningAgent(BaseAgent):
    """NEU: Reasoning Agent mit Nemotron + enable_thinking."""
    
    def __init__(self, tools_description_string: str, enable_thinking: bool = True):
        # Override env vor super().__init__
        os.environ["NEMOTRON_ENABLE_THINKING"] = "true" if enable_thinking else "false"
        super().__init__(REASONING_PROMPT_TEMPLATE, tools_description_string, 10, "reasoning")
        log.info(f"🧠 ReasoningAgent | enable_thinking={enable_thinking}")
    
    async def analyze(self, problem: str, context: str = "") -> str:
        """Convenience für reine Analyse."""
        prompt = f"Analysiere:\n\nPROBLEM:\n{problem}"
        if context:
            prompt += f"\n\nKONTEXT:\n{context}"
        return await self.run(prompt)


class CreativeAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(CREATIVE_SYSTEM_PROMPT, tools_description_string, 8, "creative")
        # Speichere tools_description für später
        self.tools_description = tools_description_string
        # Nemotron Client für strukturierte Tool-Calls
        self.nemotron_client = None
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            from openai import OpenAI as OpenRouterClient
            self.nemotron_client = OpenRouterClient(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1"
            )

    async def _generate_image_prompt_with_gpt(self, user_request: str) -> str:
        """Phase 1: GPT-5.1 generiert ausführlichen, kreativen Bildprompt."""
        log.info("🎨 Phase 1: GPT-5.1 generiert detaillierten Bildprompt")

        prompt = f"""Du bist ein Experte für DALL-E Bildprompts.
Erstelle einen DETAILLIERTEN, AUSFÜHRLICHEN englischen Bildprompt für folgende Anfrage:

"{user_request}"

ANFORDERUNGEN:
- Mindestens 20-30 Wörter
- Beschreibe: Hauptmotiv, Stil, Beleuchtung, Komposition, Details, Stimmung
- Sei spezifisch und inspirierend
- Nutze visuelle Adjektive (z.B. "soft golden lighting", "elegant composition")
- Auf ENGLISCH!

BEISPIEL:
Input: "male eine Katze"
Output: "elegant grey tabby cat sitting on a sunlit windowsill, soft natural lighting streaming through white curtains, detailed fur texture, peaceful expression, minimalist modern interior, shallow depth of field, professional photography style, warm and cozy atmosphere"

NUR DEN PROMPT AUSGEBEN, KEINE ERKLÄRUNGEN!"""

        try:
            response = await asyncio.to_thread(
                self.provider_client.get_client(ModelProvider.OPENAI).chat.completions.create,
                model="gpt-5.1",
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                max_completion_tokens=200
            )
            generated_prompt = response.choices[0].message.content.strip()
            log.info(f"✓ GPT-5.1 Prompt: {generated_prompt[:80]}...")
            return generated_prompt
        except Exception as e:
            log.error(f"❌ GPT-5.1 Prompt-Generierung fehlgeschlagen: {e}")
            # Fallback: Nutze User-Request direkt
            return f"detailed image of {user_request}, high quality, professional"

    async def _execute_with_nemotron(self, image_prompt: str, size: str = "1024x1024", quality: str = "high") -> dict:
        """Phase 2: Nemotron strukturiert Tool-Call und führt aus."""
        log.info("🔧 Phase 2: Nemotron strukturiert Tool-Call")

        if not self.nemotron_client:
            log.warning("Nemotron nicht verfügbar, Fallback auf direkte Tool-Ausführung")
            return await self._call_tool("generate_image", {
                "prompt": image_prompt,
                "size": size,
                "quality": quality
            })

        nemotron_system = f"""Du bist ein präziser Tool-Executor.

DEINE AUFGABE:
Führe generate_image mit den gegebenen Parametern aus.

VERFÜGBARE TOOLS:
{self.tools_description}

FORMAT (EXAKT):
Thought: Ich führe generate_image aus.
Action: {{"method": "generate_image", "params": {{"prompt": "...", "size": "...", "quality": "..."}}}}

WICHTIG: NUR das Action-JSON ausgeben, KEINE zusätzlichen Erklärungen!"""

        user_message = f"""Führe generate_image aus mit:
- prompt: "{image_prompt}"
- size: "{size}"
- quality: "{quality}"

Gib NUR das Action-JSON zurück!"""

        try:
            # Nemotron API-Call
            response = await asyncio.to_thread(
                self.nemotron_client.chat.completions.create,
                model="nvidia/nemotron-3-nano-30b-a3b",
                messages=[
                    {"role": "system", "content": nemotron_system},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.0,
                max_tokens=1500  # Erhöht von 500: Für vollständige JSON-Responses mit langen Prompts
            )

            nemotron_reply = response.choices[0].message.content.strip() if response.choices[0].message.content else ""

            if not nemotron_reply:
                log.warning("⚠️ Nemotron gab leeren Response zurück (möglicherweise OpenRouter Rate Limit). Fallback zu direktem Call.")
                return await self._call_tool("generate_image", {
                    "prompt": image_prompt,
                    "size": size,
                    "quality": quality
                })

            log.info(f"🧠 Nemotron Output ({len(nemotron_reply)} chars):\n{nemotron_reply[:500]}")

            # Parse Action aus Nemotron Response
            action, err = self._parse_action(nemotron_reply)

            if not action:
                log.warning(f"❌ Nemotron Action-Parse fehlgeschlagen: {err}")
                log.debug(f"Nemotron vollständiger Output: {nemotron_reply}")
                log.info("→ Fallback zu direktem Tool-Call")
                return await self._call_tool("generate_image", {
                    "prompt": image_prompt,
                    "size": size,
                    "quality": quality
                })

            # Tool ausführen
            log.info(f"✓ Tool-Call: {action.get('method')} mit params")
            obs = await self._call_tool(action.get("method", ""), action.get("params", {}))
            return obs

        except Exception as e:
            log.error(f"❌ Nemotron-Ausführung fehlgeschlagen: {e}")
            # Fallback: Direkter Tool-Call
            return await self._call_tool("generate_image", {
                "prompt": image_prompt,
                "size": size,
                "quality": quality
            })

    async def run(self, task: str) -> str:
        """HYBRID: GPT-5.1 (Kreativität) → Nemotron (Struktur) → Tool-Ausführung."""
        log.info(f"▶️ {self.__class__.__name__} - HYBRID MODE (GPT-5.1 + Nemotron)")

        # Prüfe ob es eine Bildgenerierungs-Anfrage ist
        task_lower = task.lower()
        is_image_request = any(kw in task_lower for kw in ["mal", "bild", "generiere bild", "erstelle bild", "zeichne", "image"])

        if not is_image_request:
            # Fallback auf normale Logik für nicht-Bild-Anfragen
            log.info("Keine Bild-Anfrage, nutze Standard-Logik")
            return await super().run(task)

        # === HYBRID WORKFLOW FÜR BILDER ===

        # Phase 1: GPT-5.1 generiert ausführlichen Prompt
        detailed_prompt = await self._generate_image_prompt_with_gpt(task)

        # Phase 2: Nemotron strukturiert und führt Tool aus
        observation = await self._execute_with_nemotron(detailed_prompt, size="1024x1024", quality="high")

        # Handle File Artifacts
        self._handle_file_artifacts(observation)

        # Erstelle finale Antwort
        if isinstance(observation, dict):
            if "error" in observation:
                return f"Fehler bei der Bildgenerierung: {observation['error']}"

            saved_path = observation.get("saved_as", "")
            image_url = observation.get("image_url", "")

            final_answer = "Ich habe das Bild erfolgreich generiert!"
            if saved_path:
                final_answer += f"\n\n📁 Gespeichert unter: {saved_path}"
            if image_url:
                final_answer += f"\n🔗 URL: {image_url}"

            # Detaillierter Prompt-Info (optional)
            final_answer += f"\n\n🎨 Verwendeter Prompt: {detailed_prompt[:100]}..."

            return final_answer

        return "Bildgenerierung abgeschlossen, aber unerwartetes Antwortformat."


class DeveloperAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(DEVELOPER_SYSTEM_PROMPT, tools_description_string, 15, "developer")


class MetaAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(META_SYSTEM_PROMPT, tools_description_string, 30, "meta")


class VisualAgent(BaseAgent):
    """Visual Agent mit Screenshot-Analyse."""

    def __init__(self, tools_description_string: str):
        super().__init__(VISUAL_SYSTEM_PROMPT, tools_description_string, 30, "visual")

        try:
            import mss
            from PIL import Image
            self.mss = mss
            self.Image = Image
        except ImportError:
            self.mss = None
            self.Image = None

        self.history = []
        self.last_clicked_element_type = None

        # ROI (Region of Interest) für dynamische UIs
        self.roi_stack: List[Dict] = []  # Stack für verschachtelte ROIs
        self.current_roi: Optional[Dict] = None

    def _get_screenshot_as_base64(self) -> str:
        if not self.mss or not self.Image:
            return ""
        try:
            with self.mss.mss() as sct:
                mon = int(os.getenv("ACTIVE_MONITOR", "1"))
                monitor = sct.monitors[mon] if mon < len(sct.monitors) else sct.monitors[1]
                img = self.Image.frombytes("RGB", sct.grab(monitor).size, sct.grab(monitor).bgra, "raw", "BGRX")
            img.thumbnail((1280, 720))
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except:
            return ""

    async def _capture_before(self):
        try:
            await self.http_client.post(MCP_URL, json={"jsonrpc": "2.0", "method": "capture_screen_before_action", "params": {}, "id": "1"})
        except:
            pass

    async def _verify_action(self, method: str) -> bool:
        if method not in ["click_at", "type_text", "start_visual_browser", "open_application"]:
            return True
        try:
            resp = await self.http_client.post(MCP_URL, json={"jsonrpc": "2.0", "method": "verify_action_result", "params": {"timeout": 5.0}, "id": "1"})
            return resp.json().get("result", {}).get("success", False)
        except:
            return False

    async def _wait_stable(self):
        try:
            await self.http_client.post(MCP_URL, json={"jsonrpc": "2.0", "method": "wait_until_stable", "params": {"timeout": 3.0}, "id": "1"})
        except:
            pass

    async def _call_llm(self, messages: List[Dict]) -> str:
        """Überschrieben für Vision bei Anthropic."""
        if self.provider == ModelProvider.ANTHROPIC:
            return await self._call_anthropic_vision(messages)
        return await super()._call_llm(messages)

    async def _call_anthropic_vision(self, messages: List[Dict]) -> str:
        """Anthropic Vision mit Bild-Konvertierung."""
        client = self.provider_client.get_client(ModelProvider.ANTHROPIC)
        
        system_content = ""
        chat_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            elif msg["role"] == "user":
                content = msg.get("content")
                if isinstance(content, list):
                    converted = []
                    for item in content:
                        if item.get("type") == "text":
                            converted.append({"type": "text", "text": item["text"]})
                        elif item.get("type") == "image_url":
                            url = item["image_url"]["url"]
                            if url.startswith("data:image"):
                                parts = url.split(",", 1)
                                media_type = parts[0].split(";")[0].replace("data:", "")
                                converted.append({
                                    "type": "image",
                                    "source": {"type": "base64", "media_type": media_type, "data": parts[1]}
                                })
                    chat_messages.append({"role": "user", "content": converted})
                else:
                    chat_messages.append(msg)
            else:
                chat_messages.append(msg)
        
        if client:
            resp = await asyncio.to_thread(
                client.messages.create,
                model=self.model, max_tokens=2000, system=system_content, messages=chat_messages
            )
            return resp.content[0].text.strip()
        else:
            api_key = self.provider_client.get_api_key(ModelProvider.ANTHROPIC)
            async with httpx.AsyncClient(timeout=120.0) as http:
                resp = await http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": self.model, "max_tokens": 2000, "system": system_content, "messages": chat_messages}
                )
                return resp.json()["content"][0]["text"].strip()

    def _set_roi(self, x: int, y: int, width: int, height: int, name: str = "custom"):
        """
        Setzt eine Region of Interest für Screen-Change-Gate.

        Args:
            x, y: Top-left Koordinaten
            width, height: Dimensionen
            name: ROI-Name für Debugging
        """
        roi = {"x": x, "y": y, "width": width, "height": height, "name": name}
        self.current_roi = roi
        log.info(f"🔲 ROI gesetzt: {name} ({x},{y} {width}x{height})")

    def _clear_roi(self):
        """Löscht die aktuelle ROI."""
        self.current_roi = None
        log.info("🔲 ROI gelöscht")

    def _push_roi(self, x: int, y: int, width: int, height: int, name: str = "custom"):
        """Fügt eine ROI zum Stack hinzu (für verschachtelte ROIs)."""
        if self.current_roi:
            self.roi_stack.append(self.current_roi)
        self._set_roi(x, y, width, height, name)

    def _pop_roi(self):
        """Entfernt die aktuelle ROI und stellt die vorherige wieder her."""
        if self.roi_stack:
            self.current_roi = self.roi_stack.pop()
            log.info(f"🔲 ROI wiederhergestellt: {self.current_roi['name']}")
        else:
            self._clear_roi()

    async def _detect_dynamic_ui_and_set_roi(self, task: str) -> bool:
        """
        Erkennt dynamische UIs und setzt automatisch passende ROI.

        Args:
            task: Die aktuelle Aufgabe

        Returns:
            True wenn ROI gesetzt wurde, False sonst
        """
        task_lower = task.lower()

        # Google-Erkennung
        if "google" in task_lower and ("such" in task_lower or "search" in task_lower):
            # ROI auf Suchleiste beschränken (nicht Suchergebnisse/Ads)
            # Typische Google-Suchleiste: zentriert, obere Hälfte
            self._set_roi(x=200, y=100, width=800, height=150, name="google_searchbar")
            log.info("🔍 Dynamische UI erkannt: Google Search - ROI auf Suchleiste gesetzt")
            return True

        # Booking.com-Erkennung
        elif "booking" in task_lower:
            # ROI auf Haupt-Suchformular
            self._set_roi(x=100, y=150, width=1000, height=400, name="booking_search_form")
            log.info("🏨 Dynamische UI erkannt: Booking.com - ROI auf Suchformular gesetzt")
            return True

        # Weitere dynamische UIs können hier hinzugefügt werden
        # z.B. Amazon, Twitter, etc.

        return False

    async def _analyze_current_screen(self) -> Optional[Dict]:
        """
        Analysiert den aktuellen Screen und gibt Elemente zurück.

        Nutzt Auto-Discovery:
        1. OCR für Text-Elemente
        2. SOM für interaktive Elemente (Buttons, Links, etc.)

        Returns:
            Dict mit {"screen_id": str, "elements": List[Dict]} oder None
        """
        try:
            elements = []

            # 1. OCR: Alle Text-Elemente finden
            ocr_result = await self._call_tool("get_all_screen_text", {})
            if ocr_result and ocr_result.get("texts"):
                for i, text_item in enumerate(ocr_result["texts"][:20]):  # Max 20 Text-Elemente
                    if isinstance(text_item, dict):
                        elements.append({
                            "name": f"text_{i}",
                            "type": "text",
                            "text": text_item.get("text", ""),
                            "x": text_item.get("x", 0),
                            "y": text_item.get("y", 0),
                            "confidence": text_item.get("confidence", 0.0)
                        })

            # 2. SOM: Interaktive Elemente finden (Buttons, Links, etc.)
            # TODO: Wenn SOM-Tool verfügbar ist, hier nutzen
            # som_result = await self._call_tool("get_clickable_elements", {})

            if not elements:
                log.debug("📋 Screen-Analyse: Keine Elemente gefunden")
                return None

            log.info(f"📋 Screen-Analyse: {len(elements)} Elemente gefunden")

            return {
                "screen_id": "current_screen",
                "elements": elements,
                "anchors": []
            }

        except Exception as e:
            log.error(f"❌ Screen-Analyse fehlgeschlagen: {e}")
            return None

    async def _create_navigation_plan_with_llm(self, task: str, screen_state: Dict) -> Optional[Dict]:
        """
        Erstellt einen ActionPlan basierend auf Task und Screen-State mit LLM.

        Args:
            task: Die zu erfüllende Aufgabe
            screen_state: Der analysierte Screen-State mit Elementen

        Returns:
            ActionPlan Dict oder None bei Fehler
        """
        try:
            # Extrahiere verfügbare Elemente
            elements = screen_state.get("elements", [])
            if not elements:
                log.warning("⚠️ Keine Elemente für ActionPlan verfügbar")
                return None

            # Erstelle Element-Liste mit Text-Content
            element_list = []
            for i, elem in enumerate(elements[:15]):  # Max 15 Elemente
                text = elem.get("text", "").strip()
                if text:  # Nur Elemente mit Text
                    element_list.append({
                        "name": elem.get("name", f"elem_{i}"),
                        "text": text[:50],  # Kürze lange Texte
                        "x": elem.get("x", 0),
                        "y": elem.get("y", 0),
                        "type": elem.get("type", "unknown")
                    })

            if not element_list:
                log.warning("⚠️ Keine Elemente mit Text gefunden")
                return None

            # Vereinfachtes Prompt (weniger komplex)
            element_summary = "\n".join([
                f"{i+1}. {e['name']}: \"{e['text']}\" at ({e['x']}, {e['y']})"
                for i, e in enumerate(element_list)
            ])

            prompt = f"""Erstelle einen ACTION-PLAN für diese Aufgabe:

AUFGABE: {task}

VERFÜGBARE ELEMENTE:
{element_summary}

BEISPIEL ACTION-PLAN:
{{
  "task_id": "search_task",
  "description": "Google suchen nach Python",
  "steps": [
    {{"op": "type", "target": "elem_2", "value": "Python", "retries": 2}},
    {{"op": "click", "target": "elem_5", "retries": 2}}
  ]
}}

Antworte NUR mit JSON (keine Markdown, keine Erklärung):"""

            # LLM-Call (ohne Vision) - nutze Nemotron für ActionPlan
            # Nemotron ist speziell für strukturierte JSON-Outputs trainiert!
            old_model = self.model
            old_provider = self.provider

            # Temporär auf Nemotron wechseln (bestes Modell für JSON-Generation)
            self.model = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
            self.provider = ModelProvider.OPENROUTER

            # Aktiviere Reasoning für bessere ActionPlan-Qualität
            old_thinking = os.environ.get("NEMOTRON_ENABLE_THINKING")
            os.environ["NEMOTRON_ENABLE_THINKING"] = "true"

            try:
                response = await self._call_llm([
                    {"role": "user", "content": prompt}
                ])
            finally:
                # Stelle Original-Modell wieder her
                self.model = old_model
                self.provider = old_provider
                if old_thinking is not None:
                    os.environ["NEMOTRON_ENABLE_THINKING"] = old_thinking
                else:
                    os.environ.pop("NEMOTRON_ENABLE_THINKING", None)

            # Extrahiere JSON (robuster)
            import re

            # Entferne Markdown-Code-Blocks
            response = re.sub(r'```json\s*', '', response)
            response = re.sub(r'```\s*', '', response)

            # Finde JSON
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if not json_match:
                log.warning(f"⚠️ Kein JSON gefunden in Response: {response[:200]}")
                return None

            plan = json.loads(json_match.group(0))

            # Validiere Plan
            if not plan.get("steps") or not isinstance(plan["steps"], list):
                log.warning("⚠️ ActionPlan hat keine Steps")
                return None

            # Konvertiere zu kompatiblem Format
            # Tool erwartet: {"goal": str, "screen_id": str, "steps": [...]}
            compatible_plan = {
                "goal": plan.get("description", task),
                "screen_id": screen_state.get("screen_id", "current_screen"),
                "steps": []
            }

            for step in plan["steps"]:
                # Konvertiere Step zu kompatiblem Format
                compatible_step = {
                    "op": step.get("op", "click"),
                    "target": step.get("target", ""),
                    "params": {},
                    "verify_before": [],
                    "verify_after": [],
                    "retries": step.get("retries", 2)
                }

                # Füge value zu params hinzu (für type-operation)
                if "value" in step:
                    compatible_step["params"]["text"] = step["value"]

                compatible_plan["steps"].append(compatible_step)

            log.info(f"📝 ActionPlan erstellt: {compatible_plan['goal']} ({len(compatible_plan['steps'])} Steps)")
            return compatible_plan

        except json.JSONDecodeError as e:
            log.error(f"❌ JSON-Parsing fehlgeschlagen: {e}")
            return None
        except Exception as e:
            log.error(f"❌ ActionPlan-Erstellung fehlgeschlagen: {e}")
            return None

    async def _try_structured_navigation(self, task: str) -> Optional[Dict]:
        """
        Versucht strukturierte Navigation mit Screen-Contract-Tool.

        Strategie:
        1. Analysiere aktuellen Screen (Screen-State holen)
        2. Erstelle ActionPlan mit LLM basierend auf Screen-State + Task
        3. Führe ActionPlan aus
        4. Bei Fehler → Fallback zu Vision

        Returns:
            Dict mit {"success": bool, "result": str, "state": Dict} oder None bei Fehler
        """
        try:
            log.info("📋 Versuche strukturierte Navigation...")

            # 1. Screen-State analysieren
            screen_state = await self._analyze_current_screen()
            if not screen_state or not screen_state.get("elements"):
                log.info("⚠️ Keine Elemente gefunden, Fallback zu Vision")
                return None

            # 2. ActionPlan mit LLM erstellen
            action_plan = await self._create_navigation_plan_with_llm(task, screen_state)
            if not action_plan:
                log.info("⚠️ ActionPlan-Erstellung fehlgeschlagen, Fallback zu Vision")
                return None

            # 3. ActionPlan ausführen
            log.info(f"🎯 Führe ActionPlan aus: {action_plan.get('description', 'N/A')}")
            result = await self._call_tool("execute_action_plan", {"plan_dict": action_plan})

            if result and result.get("success"):
                return {
                    "success": True,
                    "result": action_plan.get("description", "Aufgabe erfolgreich"),
                    "state": screen_state
                }
            else:
                log.warning(f"⚠️ ActionPlan fehlgeschlagen: {result.get('error', 'Unknown')}")
                return None

        except Exception as e:
            log.error(f"❌ Strukturierte Navigation fehlgeschlagen: {e}")
            return None

    async def run(self, task: str) -> str:
        log.info(f"▶️ VisualAgent: {task}")
        self.history = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": f"AUFGABE: {task}"}]

        # ROI-Management: Erkenne dynamische UIs und setze ROI
        roi_set = await self._detect_dynamic_ui_and_set_roi(task)

        # Loop-Recovery: Tracke consecutive Loops
        consecutive_loops = 0
        force_vision_mode = False

        # NEU: Versuche strukturierte Navigation ZUERST
        structured_result = await self._try_structured_navigation(task)
        if structured_result and structured_result.get("success"):
            log.info(f"✅ Strukturierte Navigation erfolgreich: {structured_result['result']}")
            # Clear ROI nach erfolgreichem Task
            if roi_set:
                self._clear_roi()
            return structured_result["result"]
        else:
            log.info("📸 Fallback zu Vision-basierter Navigation")

        for iteration in range(self.max_iterations):
            # Loop-Recovery: Bei zu vielen Loops → Strategy wechseln
            if consecutive_loops >= 2:
                log.warning(f"⚠️ Loop-Recovery: {consecutive_loops} consecutive Loops - forciere Vision-Mode")
                force_vision_mode = True
                consecutive_loops = 0  # Reset nach Recovery

            # Screen-Change-Gate: Prüfe ob Screenshot nötig (mit ROI falls gesetzt)
            # (nur ab 2. Iteration - erster Screenshot immer nötig)
            if iteration > 0 and self.use_screen_change_gate and not force_vision_mode:
                should_analyze = await self._should_analyze_screen(roi=self.current_roi)
                if not should_analyze:
                    log.debug(f"⏭️ Iteration {iteration+1}: Screen unverändert, überspringe Screenshot")
                    # Nutze letzten Screenshot aus History
                    # Kurze Pause und weiter
                    await asyncio.sleep(0.2)
                    continue

            # Force-Vision-Mode: Überschreibe Screen-Change-Gate
            if force_vision_mode:
                log.info("🔄 Force-Vision-Mode: Screenshot erzwingen trotz Screen-Change-Gate")
                force_vision_mode = False  # Nur einmal forcieren

            screenshot = await asyncio.to_thread(self._get_screenshot_as_base64)
            if not screenshot:
                return "Screenshot-Fehler"

            messages = self.history + [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Aktueller Screenshot. Nächster Schritt?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot}"}}
                ]
            }]

            reply = await self._call_llm(messages)

            if "Final Answer:" in reply:
                # Clear ROI bei Success
                if roi_set:
                    self._clear_roi()
                return reply.split("Final Answer:")[1].strip()

            action, err = self._parse_action(reply)
            if not action:
                self.history.append({"role": "user", "content": f"Fehler: {err}"})
                continue

            method = action.get("method", "")
            params = action.get("params", {})

            if method == "finish_task":
                # Clear ROI bei Success
                if roi_set:
                    self._clear_roi()
                return params.get("message", "Fertig")

            if method in ["click_at", "type_text", "start_visual_browser", "open_application"]:
                await self._capture_before()

            obs = await self._call_tool(method, params)

            # Loop-Detection: Prüfe ob Loop-Warnung in Observation
            if isinstance(obs, dict) and "_loop_warning" in obs:
                consecutive_loops += 1
                log.warning(f"⚠️ Loop-Warnung erhalten ({consecutive_loops}x): {obs['_loop_warning']}")
                # Füge Warnung zur History hinzu
                obs["_info"] = f"⚠️ LOOP-WARNUNG: {obs['_loop_warning']} Versuche anderen Ansatz!"
            else:
                consecutive_loops = 0  # Reset bei erfolgreichem Call

            if method in ["click_at", "type_text", "start_visual_browser", "open_application"]:
                if not await self._verify_action(method):
                    self.history.append({"role": "assistant", "content": reply})
                    self.history.append({"role": "user", "content": "⚠️ Nicht verifiziert. Anderen Ansatz versuchen."})
                    continue
                await self._wait_stable()

            self._handle_file_artifacts(obs)
            self.history.append({"role": "assistant", "content": reply})
            self.history.append({"role": "user", "content": f"Observation: {json.dumps(self._sanitize_observation(obs), ensure_ascii=False)}"})
            await asyncio.sleep(0.5)

        # Clear ROI am Ende (auch bei Max Iterationen)
        if roi_set:
            self._clear_roi()

        return "Max Iterationen."


# ==============================================================================
# EXPORT
# ==============================================================================

__all__ = [
    "ModelProvider", "MultiProviderClient", "AgentModelConfig", "get_provider_client",
    "BaseAgent", "ExecutorAgent", "DeepResearchAgent", "ReasoningAgent",
    "CreativeAgent", "DeveloperAgent", "MetaAgent", "VisualAgent"
]
