# agent/creative_agent.py

import logging
import os
import json
import time
import textwrap
import requests
import sys
import re
import subprocess
import base64
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------------------------
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", PROJECT_ROOT / "results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000")
DEBUG = True

# --- MODELL-WAHL ---

# 1. Text-Modell: Wir nutzen das schnelle Modell (FAST_MODEL) für die Logik
TEXT_MODEL = os.getenv("FAST_MODEL", os.getenv("MAIN_LLM_MODEL", "gpt-4.1-2025-04-14"))

# 2. Bild-Modell: Das High-End Modell für die Generierung
IMAGE_MODEL = os.getenv("IMAGE_GENERATION_MODEL", "gpt-image-1.5")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Logging
script_logger = logging.getLogger("creative_agent")
if not script_logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    script_logger.addHandler(handler)
script_logger.setLevel(logging.INFO if not DEBUG else logging.DEBUG)


# ------------------------------------------------------------------------------
# Prompt
# ------------------------------------------------------------------------------
SYSTEM_PROMPT = f"""Du bist C.L.A.I.R.E. (Creative Language and Image Response Engine), ein spezialisierter KI-Agent.

DEINE FÄHIGKEITEN (TOOLS):
  • generate_image(prompt, size, quality) - Erstellt ein Bild.
    - Das Bildmodell ({IMAGE_MODEL}) wird vom System automatisch hinzugefügt.
    - size ∈ {{"1024x1024","1024x1536","1536x1024"}}
    - quality ∈ {{"low","medium","high","auto"}}
    - Werte IMMER auf ENGLISCH (z. B. "high", NICHT "hoch").
  • generate_code(prompt, language, context) - Schreibt Code.
  • generate_text(prompt, style, max_length) - Verfasst Texte.

DEIN AUFTRAG:
1) Analysiere die Anfrage.
2) Wähle das passende Tool.
3) Formuliere die Parameter präzise.
4) Nach der Ausführung formulierst du eine hilfreiche, finale Antwort.

ANTWORTFORMAT (EXAKT so):
Thought: <Deine Analyse und Tool-Entscheidung.>
Action: {{"method": "tool_name", "params": {{...}}}}
Observation: <Tool-Antwort vom System>

ODER bei Abschluss:
Thought: <Die Aktion wurde ausgeführt. Ich formuliere nun die finale Antwort.>
Final Answer: <Die finale, gut formatierte Antwort für den Nutzer.>
"""


# ------------------------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------------------------
def call_tool(method: str, params: dict | None = None) -> dict:
    """RPC zum MCP-Server."""
    params = params or {}
    script_logger.info(f"🔧 Tool-Aufruf: {method} mit {params}")
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": os.urandom(4).hex()}
    try:
        response = requests.post(MCP_URL, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            error_info = data["error"]
            error_msg = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
            return {"error": f"Tool-Fehler: {error_msg}"}
        return data.get("result", {})
    except Exception as e:
        return {"error": str(e)}


def _dynamic_chat(messages: list, temperature: float = 1, token_budget: int = 1000) -> str:
    kwargs: Dict[str, Any] = {
        "model": TEXT_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    # Neue Modelle nutzen max_completion_tokens
    if "gpt-5" in TEXT_MODEL or "gpt-4o" in TEXT_MODEL or "gpt-4.1" in TEXT_MODEL:
        kwargs["max_completion_tokens"] = token_budget
    else:
        kwargs["max_tokens"] = token_budget

    try:
        resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Error: LLM API Fehler - {e}"


_ALLOWED_SIZES = {"1024x1024", "1024x1536", "1536x1024"}
_ALLOWED_QUALITIES = {"low", "medium", "high", "auto"}

_GERMAN_TO_EN_QUALITY = {
    "niedrig": "low",
    "gering": "low",
    "mittel": "medium",
    "hoch": "high",
    "auto": "auto",
    "automatisch": "auto",
}

def sanitize_image_params(p: dict) -> dict:
    """
    Erzwingt gültige Werte und injiziert das korrekte Modell.
    """
    prompt = str(p.get("prompt", "")).strip()
    size = str(p.get("size", "1024x1024")).lower()
    quality = str(p.get("quality", "high")).lower()

    # Deutsch → Englisch für quality
    quality = _GERMAN_TO_EN_QUALITY.get(quality, quality)

    if size not in _ALLOWED_SIZES:
        size = "1024x1024"
    if quality not in _ALLOWED_QUALITIES:
        quality = "high"

    cleaned = {
        "prompt": prompt,
        "size": size,
        "quality": quality,
        # HIER IST DER FIX: Wir senden das Modell explizit mit!
        "model": IMAGE_MODEL 
    }
    script_logger.info(f"🎨 Bild-Generierung konfiguriert für Modell: {IMAGE_MODEL}")
    return cleaned


def _save_b64_to_results(b64_str: str, stem_hint: str = "image", size: str = "1024x1024", quality: str = "high") -> str:
    """Speichert Base64-PNG nach results/ mit robustem Dateinamen. Gibt Pfad (str) zurück."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{stem_hint}_{ts}_{size}_{quality}.png"
    out_path = RESULTS_DIR / fname
    try:
        raw = base64.b64decode(b64_str)
        with open(out_path, "wb") as f:
            f.write(raw)
        return str(out_path)
    except Exception as e:
        raise RuntimeError(f"Fehler beim lokalen Speichern der Bilddaten: {e}")


def _extract_b64_from_observation(obs: dict) -> Optional[str]:
    if not isinstance(obs, dict):
        return None
    for key in ("b64", "b64_json", "image_base64"):
        if isinstance(obs.get(key), str):
            return obs[key]
    data = obs.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and isinstance(first.get("b64_json"), str):
            return first["b64_json"]
    return None


# ------------------------------------------------------------------------------
# LLM-Wrapper für den Agentenfluss
# ------------------------------------------------------------------------------
def llm(messages: list) -> str:
    return _dynamic_chat(messages, temperature=1, token_budget=1000)


# ------------------------------------------------------------------------------
# Hauptlogik
# ------------------------------------------------------------------------------

def llm_with_format_retry(messages: list, tries: int = 2) -> str:
    """
    Ruft llm() auf. Wenn keine 'Action:' ODER 'Final Answer:' enthalten ist,
    hängt einen harten Format-Hinweis an und versucht es erneut.
    """
    reply = llm(messages)
    if isinstance(reply, str) and ("Action:" in reply or "Final Answer:" in reply):
        return reply

    # Format-Reminder anhängen und erneut versuchen
    reminder = (
        "BITTE HALTE DICH STRIKT AN DAS FORMAT.\n"
        "Antworte NUR mit:\n"
        "Thought: ...\n"
        "Action: {\"method\": \"<tool>\", \"params\": { ... }}\n"
        "ODER (NUR nach Observation) mit:\n"
        "Thought: ...\n"
        "Final Answer: ...\n"
    )
    messages.append({"role": "user", "content": reminder})
    return llm(messages)


def run_creative_task(user_query: str):
    script_logger.info(f"🎨 Verarbeite kreative Anfrage: '{user_query}'")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]

    # 1) LLM-Entscheidung (Thought + Action)
    llm_reply = llm_with_format_retry(messages, tries=2)
    messages.append({"role": "assistant", "content": llm_reply})
    script_logger.info(f"🧠 Gedanke & Aktion: {llm_reply}")

    # Falls das Modell direkt beendet (Final Answer)
    if "Final Answer:" in llm_reply:
        return llm_reply.split("Final Answer:", 1)[1].strip()

    # 2) Action extrahieren
    action_match = re.search(r'Action:\s*({[\s\S]*?})\s*(?:\n|$)', llm_reply, re.DOTALL)
    if not action_match:
        return "Fehler: Konnte keine gültige 'Action:' in der LLM-Antwort finden."

    try:
        action_str = action_match.group(1).strip()
        action_dict = json.loads(action_str)
        method = action_dict["method"]
        params = action_dict.get("params", {})
    except (json.JSONDecodeError, KeyError) as e:
        return f"Fehler: Ungültiges JSON in der 'Action'. ({e}) - String war: '{action_str}'"

    # 3) Vor Ausführung auf bekannte Methoden reagieren
    if method == "generate_image":
        params = sanitize_image_params(params)

    # 4) Tool ausführen
    observation = call_tool(method, params)
    if isinstance(observation, dict) and "error" in observation:
        return f"Fehler beim Ausführen des Tools '{method}': {observation['error']}"

    filepath_to_open = None

    # 4a) Bevorzugt: Server liefert Speicherpfad
    if isinstance(observation, dict) and observation.get("saved_as"):
        filepath_to_open = observation["saved_as"]
        script_logger.info(f"✅ Tool meldet gespeicherte Datei: {filepath_to_open}")
    else:
        # 4b) Fallback: selbst speichern, wenn B64 vorhanden
        b64 = _extract_b64_from_observation(observation if isinstance(observation, dict) else {})
        if b64:
            size = str(params.get("size", "1024x1024"))
            quality = str(params.get("quality", "high"))
            try:
                filepath_to_open = _save_b64_to_results(b64, stem_hint="image", size=size, quality=quality)
                script_logger.info(f"💾 Lokal gespeichert unter: {filepath_to_open}")
                # Observation anreichern, damit das LLM einen Pfad sieht
                observation = {**(observation or {}), "saved_as": filepath_to_open}
            except Exception as e:
                script_logger.warning(f"Konnte Bild nicht lokal speichern: {e}")
        else:
            script_logger.warning("Weder 'saved_as' noch Base64-Daten im Tool-Result gefunden.")

    # 5) Observation zurück an LLM zur Finalisierung
    messages.append({"role": "user", "content": f"Observation: {json.dumps(observation)}"})
    script_logger.info(f"📋 Beobachtung: {str(observation)[:200]}...")
    final_reply = llm(messages)
    script_logger.info(f"✅ Finale LLM-Antwort: {final_reply}")

    # 6) Finale Antwort extrahieren/erzeugen
    if "Final Answer:" in final_reply:
        final_answer_text = final_reply.split("Final Answer:", 1)[1].strip()
    else:
        final_answer_text = f"Die Aktion wurde ausgeführt.\nErgebnis: {json.dumps(observation, indent=2, ensure_ascii=False)}"

    # 7) Optional: Bild öffnen
    if filepath_to_open:
        try:
            script_logger.info(f"Versuche, Ergebnisdatei zu öffnen: {filepath_to_open}")
            if sys.platform == "win32":
                os.startfile(filepath_to_open)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.run(["open", filepath_to_open], check=True)
            else:
                subprocess.run(["xdg-open", filepath_to_open], check=True)
            final_answer_text += f"\n\nGespeichert unter: {filepath_to_open}"
        except Exception as e:
            script_logger.warning(f"Konnte Bild nicht automatisch öffnen: {e}")
            final_answer_text += f"\n(Gespeichert unter: {filepath_to_open})"

    return final_answer_text


# ------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        final_answer = run_creative_task(query)
        print("\n" + "="*80)
        print("💡 FINALE ANTWORT DES KREATIV-AGENTEN:")
        print("="*80)
        for line in textwrap.wrap(str(final_answer), width=80):
            print(line)
        print("="*80)
    else:
        print("Dieses Skript wird vom Master-Dispatcher mit einer Anfrage aufgerufen.")
        print("Beispiel: python agent/creative_agent.py \"male ein futuristisches Raumschiff\"")