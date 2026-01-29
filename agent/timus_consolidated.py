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
DATUM: {current_date}.

# VERFÜGBARE TOOLS
{tools_description}

# ANTWORTFORMAT
Thought: [Deine Überlegung]
Action: {{"method": "tool_name", "params": {{"key": "value"}}}}

# REGELN
- Nutze die exakten Tool-Namen wie in der Liste
- Bei einfachen Fragen direkt antworten mit "Final Answer: ..."

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
Du bist C.L.A.I.R.E. (Creative). 
TOOLS: {tools_description}
Bildmodell: """ + IMAGE_MODEL_NAME + """
Size: "1024x1024", Quality: "high"

ANTWORT:
{{ "thought": "...", "action": {{ "method": "Image Generation", "params": {{ "prompt": "..." }} }} }}

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

    def should_skip_action(self, action_name: str, params: dict) -> bool:
        """Loop-Detection."""
        action_key = f"{action_name}:{json.dumps(params, sort_keys=True)}"
        count = self.recent_actions.count(action_key)
        if count >= 2:
            log.warning(f"⚠️ Loop ({count}x): {action_name}")
            return True
        self.recent_actions.append(action_key)
        if len(self.recent_actions) > 20:
            self.recent_actions.pop(0)
        return False

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
        if self.should_skip_action(method, params):
            return {"skipped": True, "reason": "Loop"}
        
        log.info(f"📡 {method} -> {str(params)[:100]}")
        
        try:
            resp = await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": "1"}
            )
            data = resp.json()
            if "result" in data:
                return data["result"]
            if "error" in data:
                return {"error": str(data["error"])}
            return {"error": "Invalid response"}
        except Exception as e:
            return {"error": str(e)}

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
        # Zeilenweise suchen
        for line in text.strip().split('\n'):
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
        
        # Regex Fallback
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
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task}
        ]
        
        for step in range(1, self.max_iterations + 1):
            reply = await self._call_llm(messages)
            
            if reply.startswith("Error"):
                return reply
            if "Final Answer:" in reply:
                return reply.split("Final Answer:")[1].strip()
            
            action, err = self._parse_action(reply)
            messages.append({"role": "assistant", "content": reply})
            
            if not action:
                messages.append({"role": "user", "content": f"Fehler: {err}. Korrektes JSON senden."})
                continue
            
            obs = await self._call_tool(action.get("method", ""), action.get("params", {}))
            self._handle_file_artifacts(obs)
            messages.append({"role": "user", "content": f"Observation: {json.dumps(self._sanitize_observation(obs), ensure_ascii=False)}"})
        
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
        super().__init__(CREATIVE_SYSTEM_PROMPT, tools_description_string, 5, "creative")


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

    async def run(self, task: str) -> str:
        log.info(f"▶️ VisualAgent: {task}")
        self.history = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": f"AUFGABE: {task}"}]
        
        for _ in range(self.max_iterations):
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
                return reply.split("Final Answer:")[1].strip()
            
            action, err = self._parse_action(reply)
            if not action:
                self.history.append({"role": "user", "content": f"Fehler: {err}"})
                continue
            
            method = action.get("method", "")
            params = action.get("params", {})
            
            if method == "finish_task":
                return params.get("message", "Fertig")
            
            if method in ["click_at", "type_text", "start_visual_browser", "open_application"]:
                await self._capture_before()
            
            obs = await self._call_tool(method, params)
            
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
        
        return "Max Iterationen."


# ==============================================================================
# EXPORT
# ==============================================================================

__all__ = [
    "ModelProvider", "MultiProviderClient", "AgentModelConfig", "get_provider_client",
    "BaseAgent", "ExecutorAgent", "DeepResearchAgent", "ReasoningAgent",
    "CreativeAgent", "DeveloperAgent", "MetaAgent", "VisualAgent"
]
