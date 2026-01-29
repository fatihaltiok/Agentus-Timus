# agent/reasoning_agent.py
# -*- coding: utf-8 -*-
"""
ReasoningAgent - Spezialisiert auf komplexe Analyse mit Nemotron.

Features:
- Multi-Step Reasoning (Chain-of-Thought)
- enable_thinking Steuerung
- Debugging, Root-Cause Analyse
- Architektur-Entscheidungen
- Trade-off Analyse
- Mathematische/logische Problemlösung

Provider: OpenRouter (nvidia/nemotron-3-nano-30b-a3b)
Fallback: NVIDIA NIM
"""

import logging
import os
import json
import textwrap
import requests
import sys
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

# -----------------------------------------------------------------------------
# Pfade & Module
# -----------------------------------------------------------------------------
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# -----------------------------------------------------------------------------
# Konfiguration & Clients
# -----------------------------------------------------------------------------
from dotenv import load_dotenv
from openai import OpenAI
from utils.openai_compat import prepare_openai_params

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000")
DEBUG = os.getenv("REASONING_DEBUG", "1") == "1"

# Provider-Konfiguration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

# Modell-Konfiguration
REASONING_MODEL = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
REASONING_PROVIDER = os.getenv("REASONING_MODEL_PROVIDER", "openrouter")

# Nemotron Reasoning Toggle
ENABLE_THINKING = os.getenv("NEMOTRON_ENABLE_THINKING", "true").lower() == "true"

# -----------------------------------------------------------------------------
# Client Setup
# -----------------------------------------------------------------------------
def get_client() -> Tuple[OpenAI, str]:
    """Erstellt Client basierend auf Provider-Konfiguration."""
    
    if REASONING_PROVIDER == "openrouter" and OPENROUTER_API_KEY:
        return OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        ), "openrouter"
    
    elif REASONING_PROVIDER == "nvidia" and NVIDIA_API_KEY:
        return OpenAI(
            api_key=NVIDIA_API_KEY,
            base_url="https://integrate.api.nvidia.com/v1"
        ), "nvidia"
    
    # Fallback: OpenRouter wenn Key vorhanden
    elif OPENROUTER_API_KEY:
        return OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        ), "openrouter"
    
    # Fallback: NVIDIA wenn Key vorhanden
    elif NVIDIA_API_KEY:
        return OpenAI(
            api_key=NVIDIA_API_KEY,
            base_url="https://integrate.api.nvidia.com/v1"
        ), "nvidia"
    
    else:
        raise RuntimeError(
            "Kein API Key für ReasoningAgent gefunden!\n"
            "Setze OPENROUTER_API_KEY oder NVIDIA_API_KEY in .env"
        )

client, active_provider = get_client()

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger("reasoning_agent")
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

logger.info(f"🧠 ReasoningAgent initialisiert | Provider: {active_provider} | Modell: {REASONING_MODEL}")
logger.info(f"   enable_thinking: {ENABLE_THINKING}")

# -----------------------------------------------------------------------------
# System Prompt
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = f"""
Du bist der Timus Reasoning Agent - spezialisiert auf komplexe Analyse und Multi-Step Reasoning.
DATUM: {time.strftime("%d.%m.%Y")}

# DEINE STÄRKEN
- Komplexe Probleme in Denkschritten lösen
- Root-Cause Analyse und Debugging
- Architektur-Entscheidungen und Trade-off Analyse
- Mathematische und logische Problemlösung
- Multi-Step Planung
- Vergleiche (A vs B, Pro/Contra)

# REASONING WORKFLOW
Bei komplexen Problemen folge diesem Schema:

1. **VERSTEHEN**: Was ist das eigentliche Problem?
2. **ZERLEGEN**: In welche Teilprobleme lässt es sich aufteilen?
3. **ANALYSIEREN**: Schritt für Schritt durchdenken
4. **OPTIONEN**: Welche Lösungswege gibt es?
5. **BEWERTEN**: Pro/Contra jeder Option
6. **ENTSCHEIDEN**: Beste Lösung mit Begründung

# VERFÜGBARE TOOLS (optional)
Falls du Tools brauchst, nutze diese:
- search_web: Aktuelle Informationen suchen
- read_file: Datei lesen für Kontext
- execute_code: Code ausführen zum Testen

# ANTWORTFORMAT

**Für Tool-Aufrufe:**
Thought: [Deine schrittweise Analyse]
Action: {{"method": "tool_name", "params": {{...}}}}

**Für direkte Analyse (ohne Tools):**
Thought: [Ausführliche schrittweise Analyse]
Final Answer: [Zusammenfassung und Empfehlung]

# BEISPIEL: Debugging

User: Mein VisualAgent gibt Parse-Fehler und führt keine Actions aus.

Thought:
**Schritt 1 - Problem identifizieren:**
- Parse-Fehler deutet auf JSON-Problem hin
- Keine Actions = Parser findet keine gültigen Actions

**Schritt 2 - Mögliche Ursachen:**
a) Malformed JSON vom LLM
b) Mehrere JSON-Objekte statt eines
c) Falsches Format (fehlendes "action" key)

**Schritt 3 - Wahrscheinlichste Ursache:**
"Extra data: line 2" = Mehrere JSON-Objekte
→ LLM gibt mehrere Actions auf einmal zurück

**Schritt 4 - Lösung:**
- Parser anpassen: Nur erste Action nehmen
- System Prompt verstärken: "NUR EINE Aktion"

Final Answer: Das Problem ist, dass das LLM mehrere JSON-Actions pro Antwort zurückgibt. 
Lösung: 1) Parser-Fix (nur erste Action), 2) System Prompt mit strikter Einschränkung.

# BEISPIEL: Architektur-Vergleich

User: asyncio vs threading für 100 API-Calls?

Thought:
**Schritt 1 - Anforderung verstehen:**
- 100 parallele API-Calls
- Frage: asyncio oder threading?

**Schritt 2 - asyncio analysieren:**
- Single-threaded, Event-Loop basiert
- Ideal für I/O-bound Tasks (Netzwerk!)
- Wenig Overhead (kein Thread-Wechsel)
- Skaliert gut (tausende Connections)
- Benötigt async/await Syntax

**Schritt 3 - threading analysieren:**
- Multi-threaded, OS-managed
- Für CPU-bound besser (GIL-Problem bei Python!)
- Mehr Overhead (Thread-Erstellung, Context-Switch)
- Begrenzt durch OS (meist ~1000 Threads max)
- Einfachere Syntax (kein async/await)

**Schritt 4 - Für API-Calls bewerten:**
- API-Calls = I/O-bound ✓
- 100 Calls = asyncio locker schaffbar
- threading: 100 Threads = unnötiger Overhead

**Schritt 5 - Entscheidung:**
→ asyncio ist klar besser für diesen Use-Case

Final Answer: Für 100 parallele API-Calls: **asyncio**.

Begründung:
1. API-Calls sind I/O-bound → asyncio's Stärke
2. Weniger Overhead als 100 Threads
3. Besser skalierbar (auch für 1000+ Calls)
4. Ressourcenschonender (ein Thread statt 100)

Threading wäre nur sinnvoll bei CPU-bound Tasks oder wenn du blocking Libraries ohne async-Support nutzen musst.

# WICHTIG
- Denke IMMER Schritt für Schritt
- Zeige deinen Denkprozess
- Gib klare, begründete Empfehlungen
- Bei Unsicherheit: Optionen mit Pro/Contra auflisten
"""

# -----------------------------------------------------------------------------
# Tool-Call Helper
# -----------------------------------------------------------------------------
def call_tool(method: str, params: Optional[dict] = None, timeout: int = 120) -> dict:
    """RPC zum MCP-Server."""
    params = params or {}
    logger.info(f"🔧 Tool-Aufruf: {method} mit {params}")
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": os.urandom(4).hex()}
    try:
        resp = requests.post(MCP_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return {"error": data.get("error", "Unbekannter Tool-Fehler")}
        return data.get("result", {})
    except Exception as e:
        return {"error": f"RPC/HTTP-Fehler: {e}"}

# -----------------------------------------------------------------------------
# LLM Wrapper mit Nemotron-Optimierung
# -----------------------------------------------------------------------------
def chat(messages: List[Dict[str, Any]], enable_thinking: bool = True) -> str:
    """
    Ruft Nemotron via OpenRouter/NVIDIA auf.
    
    Args:
        messages: Chat-Nachrichten
        enable_thinking: True = Chain-of-Thought (langsamer, besser)
                        False = Direkte Antwort (schneller)
    """
    kwargs: Dict[str, Any] = {
        "model": REASONING_MODEL,
        "messages": messages,
        "max_tokens": 4000,  # Nemotron braucht mehr für Reasoning
    }
    
    # Nemotron-spezifische Parameter
    if enable_thinking:
        # Reasoning Mode: höhere Temperatur für kreatives Denken
        kwargs["temperature"] = 1.0
        kwargs["top_p"] = 1.0
    else:
        # Direct Mode: niedrigere Temperatur, präziser
        kwargs["temperature"] = 0.6
        kwargs["top_p"] = 0.95
        # Disable thinking via extra_body (wenn Provider es unterstützt)
        if "nemotron" in REASONING_MODEL.lower():
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False}
            }
    
    try:
        logger.debug(f"🔮 LLM Request | enable_thinking={enable_thinking}")
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        return content.strip()
    except Exception as e:
        logger.error(f"LLM API Fehler: {e}")
        return f"Error: LLM API Fehler - {e}"

# -----------------------------------------------------------------------------
# Parsing-Helfer
# -----------------------------------------------------------------------------
ACTION_PATTERNS = [
    r'Action:\s*```json\s*({[\s\S]*?})\s*```',
    r'Action:\s*({[\s\S]*?})\s*(?:\n|$)',
    r'({[^{}]*"method"[^{}]*})',
]

def extract_action_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """Extrahiert Action-JSON aus LLM-Antwort."""
    for pat in ACTION_PATTERNS:
        m = re.search(pat, text, re.DOTALL)
        if not m:
            continue
        raw = m.group(1).strip()
        try:
            # Trailing commas entfernen
            raw = re.sub(r',\s*([\}\]])', r'\1', raw)
            data = json.loads(raw)
            if isinstance(data, dict) and "method" in data:
                return data, None
            return None, "Action-Objekt ohne 'method'."
        except json.JSONDecodeError as je:
            return None, f"JSON-Fehler: {je}"
    return None, None  # Keine Action gefunden (OK für reine Analyse)

# -----------------------------------------------------------------------------
# Haupt-Loop
# -----------------------------------------------------------------------------
def run_reasoning_task(
    user_query: str, 
    max_steps: int = 10,
    enable_thinking: bool = None
) -> str:
    """
    Führt eine Reasoning-Aufgabe aus.
    
    Args:
        user_query: Die Anfrage/das Problem
        max_steps: Maximale Iterationen
        enable_thinking: Override für Nemotron Reasoning
                        None = nutze ENV-Variable
    """
    # enable_thinking bestimmen
    thinking = enable_thinking if enable_thinking is not None else ENABLE_THINKING
    
    logger.info(f"🧠 Starte ReasoningAgent | enable_thinking={thinking}")
    logger.info(f"   Anfrage: {user_query[:100]}...")
    
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]
    
    for step in range(1, max_steps + 1):
        logger.info(f"\n--- ⚙️ Schritt {step}/{max_steps} ---")
        
        reply = chat(messages, enable_thinking=thinking)
        
        if not isinstance(reply, str) or reply.startswith("Error:"):
            logger.error(f"LLM-Fehler: {reply}")
            return f"Fehler bei der Analyse: {reply}"
        
        logger.info(f"🧠 Antwort:\n{reply[:500]}...")
        
        # Final Answer Check
        if "Final Answer:" in reply:
            final = reply.split("Final Answer:", 1)[1].strip()
            logger.info("✅ Analyse abgeschlossen.")
            return final
        
        messages.append({"role": "assistant", "content": reply})
        
        # Action Check (optional - Reasoning kann auch ohne Tools arbeiten)
        action, err = extract_action_json(reply)
        
        if action:
            method = action.get("method", "")
            params = action.get("params", {})
            
            logger.info(f"🔧 Tool-Aufruf: {method}")
            obs = call_tool(method, params)
            
            messages.append({
                "role": "user", 
                "content": f"Observation: {json.dumps(obs, ensure_ascii=False)}"
            })
        else:
            # Keine Action = reine Analyse, weiter prompten
            if step < max_steps:
                messages.append({
                    "role": "user",
                    "content": "Bitte fahre mit deiner Analyse fort und gib eine 'Final Answer:' wenn du fertig bist."
                })
    
    # Fallback: Letzte Antwort als Ergebnis
    logger.warning("Max Schritte erreicht ohne Final Answer.")
    return reply if reply else "Analyse konnte nicht abgeschlossen werden."

# -----------------------------------------------------------------------------
# Convenience-Funktionen
# -----------------------------------------------------------------------------
def analyze(problem: str, context: str = "", enable_thinking: bool = True) -> str:
    """
    Convenience-Funktion für reine Analyse ohne Tool-Calls.
    
    Args:
        problem: Das zu analysierende Problem
        context: Optionaler Kontext (Code, Logs, etc.)
        enable_thinking: Chain-of-Thought aktivieren
    """
    prompt = f"Analysiere folgendes Problem Schritt für Schritt:\n\n**PROBLEM:**\n{problem}"
    if context:
        prompt += f"\n\n**KONTEXT:**\n{context}"
    
    return run_reasoning_task(prompt, enable_thinking=enable_thinking)


def compare(option_a: str, option_b: str, criteria: str = "") -> str:
    """
    Vergleicht zwei Optionen.
    
    Args:
        option_a: Erste Option
        option_b: Zweite Option
        criteria: Optionale Bewertungskriterien
    """
    prompt = f"Vergleiche {option_a} vs {option_b}."
    if criteria:
        prompt += f"\n\nBewertungskriterien: {criteria}"
    prompt += "\n\nGib Pro/Contra für beide und eine klare Empfehlung."
    
    return run_reasoning_task(prompt, enable_thinking=True)


def debug(error_description: str, code: str = "", logs: str = "") -> str:
    """
    Debugging-Analyse.
    
    Args:
        error_description: Fehlerbeschreibung
        code: Relevanter Code
        logs: Fehlerlogs
    """
    prompt = f"**DEBUGGING-ANFRAGE:**\n\n{error_description}"
    if code:
        prompt += f"\n\n**CODE:**\n```\n{code}\n```"
    if logs:
        prompt += f"\n\n**LOGS:**\n```\n{logs}\n```"
    prompt += "\n\nIdentifiziere die Ursache und schlage eine Lösung vor."
    
    return run_reasoning_task(prompt, enable_thinking=True)

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = run_reasoning_task(query)
        
        print("\n" + "=" * 80)
        print("🧠 FINALE ANTWORT DES REASONING-AGENTEN:")
        print("=" * 80)
        print(textwrap.fill(result, width=80))
        print("=" * 80)
    else:
        print("\n🧠 Timus ReasoningAgent")
        print(f"   Provider: {active_provider}")
        print(f"   Modell: {REASONING_MODEL}")
        print(f"   enable_thinking: {ENABLE_THINKING}")
        print("\nBeispiele:")
        print("  python reasoning_agent.py \"asyncio vs threading für API-Calls?\"")
        print("  python reasoning_agent.py \"Warum gibt mein Parser Fehler?\"")
        print("  python reasoning_agent.py \"Pro und Contra von Microservices\"")
