# agent/developer_agent.py
# -*- coding: utf-8 -*-
import logging
import os
import json
import textwrap
import requests
import sys
import re
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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TEXT_MODEL = os.getenv("MAIN_LLM_MODEL", "gpt-5")
REQUIRE_INCEPTION = os.getenv("REQUIRE_INCEPTION", "1") == "1"
DEBUG = os.getenv("DEV_AGENT_DEBUG", "1") == "1"

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY fehlt in der Umgebung.")

client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger("developer_agent")
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

# -----------------------------------------------------------------------------
# System Prompt
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = """Du bist D.A.V.E., ein Dev-Agent, der Code ausschließlich über:

Action: {"method": "generate_and_integrate", "params": {"instruction": "<vollständige Spezifikation>", "dest_folder": "<Zielordner>", "context_file_path": "<optional>"}} 

arbeitet.

Regeln:
- Nur EINE Action pro Runde.
- 'instruction' enthält die komplette Spezifikation.
- 'dest_folder' ist ein Projektpfad relativ zur Repo-Wurzel (z. B. "test_project" oder ".").
- 'context_file_path' nur angeben, wenn nötig.

Antwortformat (exakt eins):
Thought: <kurzer Plan>
Action: {"method":"generate_and_integrate","params":{...}}

ODER (nur nach erfolgreicher Observation):
Thought: erledigt
Final Answer: <kurze Abschlussmeldung>
"""

# -----------------------------------------------------------------------------
# Tool-Call Helper
# -----------------------------------------------------------------------------
def call_tool(method: str, params: Optional[dict] = None, timeout: int = 300) -> dict:
    params = params or {}
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

def inception_ready() -> Tuple[bool, str]:
    """
    Prüft, ob Inception/implement_feature verfügbar ist.
    - Bevorzugt: spezieller Health-Endpunkt 'inception_health'
    - Fallback: implement_feature dry_run
    """
    probe = call_tool("inception_health", {})
    if isinstance(probe, dict) and not probe.get("error"):
        return True, "ok"
    ping = call_tool("implement_feature", {
        "file_paths": ["__inception_ping__.txt"],
        "instruction": "NOOP/PING – do not write any file.",
        "dry_run": True
    })
    if isinstance(ping, dict) and not ping.get("error"):
        return True, "ok"
    msg = ""
    err = ping.get("error") if isinstance(ping, dict) else probe
    if isinstance(err, dict):
        msg = err.get("message") or str(err)
    else:
        msg = str(err)
    return False, msg or "Inception nicht bereit"

# -----------------------------------------------------------------------------
# LLM Wrapper (korrekter Token-Parameter je nach Modell)
# -----------------------------------------------------------------------------
def chat(messages: List[Dict[str, Any]], temperature: float = 1.0, token_budget: int = 1500) -> str:
    kwargs: Dict[str, Any] = {
        "model": TEXT_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if ("gpt-5" in TEXT_MODEL) or ("gpt-4o" in TEXT_MODEL):
        kwargs["max_completion_tokens"] = token_budget
    else:
        kwargs["max_tokens"] = token_budget
    try:
        resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Error: LLM API Fehler - {e}"

# -----------------------------------------------------------------------------
# Parsing-Helfer
# -----------------------------------------------------------------------------
ACTION_PATTERNS = [
    r'Action:\s*```json\s*({[\s\S]*?})\s*```',
    r'Action:\s*({[\s\S]*?})\s*(?:\n|$)',
]
def extract_action_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    for pat in ACTION_PATTERNS:
        m = re.search(pat, text, re.DOTALL)
        if not m:
            continue
        raw = m.group(1).strip()
        try:
            # trailing commas entfernen
            raw = re.sub(r',\s*([\}\]])', r'\1', raw)
            data = json.loads(raw)
            if isinstance(data, dict) and "method" in data:
                return data, None
            return None, "Action-Objekt ohne 'method'."
        except json.JSONDecodeError as je:
            return None, f"JSON-Fehler in Action: {je}"
    return None, "Keine 'Action:' gefunden."
CODEBLOCK = re.compile(r"```(?:python)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
def extract_code(text: str) -> Optional[str]:
    m = CODEBLOCK.search(text)
    if m:
        return m.group(1)
    return None

# -----------------------------------------------------------------------------
# Haupt-Loop
# -----------------------------------------------------------------------------
def run_developer_task(user_query: str, max_steps: int = 8) -> str:
    logger.info(f"👨‍💻 Starte Developer-Agent für: {user_query!r}")

    # Preflight: Inception-Check
    ok, why = inception_ready()
    if not ok:
        if REQUIRE_INCEPTION:
            logger.error(f"Inception nicht bereit: {why}")
            return ("Inception/implement_feature ist nicht bereit: "
                    f"{why}. Bitte prüfe ENV (INCEPTION_*, MCP_URL) und den Serverstart. "
                    "Fallback ist deaktiviert (REQUIRE_INCEPTION=1).")
        else:
            logger.warning(f"Inception nicht bereit: {why} – Fahre ohne Inception fort (REQUIRE_INCEPTION=0).")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]

    failures = 0
    last_action_str = ""
    for step in range(1, max_steps + 1):
        logger.info(f"⚙️ Schritt {step}/{max_steps} (Fehler: {failures})")

        # LLM beauftragen, genau EINE Action zu setzen
        reply = chat(messages, temperature=1.0, token_budget=2000)
        if not isinstance(reply, str):
            failures += 1
            last_action_str = f"Ungültige LLM-Antwort (Typ {type(reply)})"
            messages.append({"role": "user", "content": f"Observation: {json.dumps({'error':'Ungültige LLM-Antwort'})}"})
            continue

        messages.append({"role": "assistant", "content": reply})
        logger.debug(f"🧠 LLM:\n{reply}")

        # Sofortiger Abschluss?
        if "Final Answer:" in reply:
            final = reply.split("Final Answer:", 1)[1].strip()
            logger.info("✅ Aufgabe abgeschlossen.")
            call_tool("log_learning_entry", {
                "goal": user_query, "outcome": "success",
                "details": {"final_step_count": step, "final_message": final},
                "learning": "Inception-gestützte Entwicklung erfolgreich abgeschlossen."
            })
            return final

        # Action extrahieren
        action, perr = extract_action_json(reply)
        if perr or not action:
            failures += 1
            last_action_str = reply
            logger.warning(f"Keine gültige Action erkannt: {perr}")
            messages.append({"role": "user", "content": f"Observation: {json.dumps({'error': perr or 'no_action'})}"})
            continue

        method = action.get("method")
        params = action.get("params", {}) if isinstance(action.get("params"), dict) else {}
        last_action_str = json.dumps(action, ensure_ascii=False)

        # Schutz: Inception erzwingen
        if method != "implement_feature" and REQUIRE_INCEPTION:
            failures += 1
            msg = "Dieser Agent erfordert implement_feature als ersten Schritt."
            logger.warning(msg)
            messages.append({"role": "user", "content": f"Observation: {json.dumps({'error': msg})}"})
            continue

        # Tool ausführen
        obs = call_tool(method, params, timeout=420)

        # typischer Inception-Verfügbarkeitsfehler?
        if isinstance(obs, dict) and obs.get("error"):
            err = obs["error"]
            err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            logger.error(f"Tool-Fehler: {err_msg}")
            if REQUIRE_INCEPTION and ("inception" in err_msg.lower() or "implement_feature" in err_msg.lower() or "nicht initialisiert" in err_msg.lower()):
                failures += 1
                messages.append({"role": "user", "content": f"Observation: {json.dumps({'error':'Inception unavailable','detail': err_msg})}"})
                continue
            # sonst normaler Fehler
            failures += 1
            messages.append({"role": "user", "content": f"Observation: {json.dumps(obs)}"})
            continue

        # Erfolg: Observation weitergeben
        messages.append({"role": "user", "content": f"Observation: {json.dumps(obs)}"})

        # Häufige Pfade: Inception liefert generated_code oder diff/patch
        # -> Wir speichern aktiv, falls die Observation es mitliefert.
        try:
            if isinstance(obs, dict):
                generated = obs.get("generated_code")
                target = obs.get("file_path") or (params.get("file_paths")[0] if isinstance(params.get("file_paths"), list) and params["file_paths"] else None)
                patch = obs.get("patch") or obs.get("diff")

                if generated and target:
                    wr = call_tool("write_file", {"path": target, "content": generated})
                    if isinstance(wr, dict) and wr.get("error"):
                        failures += 1
                        messages.append({"role": "user", "content": f"Observation: {json.dumps({'error':'write_file_failed','detail': wr})}"})
                        continue
                    # Direkt finalisieren
                    final = f"Die Datei '{target}' wurde erstellt/aktualisiert."
                    messages.append({"role": "assistant", "content": f"Thought: erledigt\nFinal Answer: {final}"})
                    logger.info("✅ Datei geschrieben & abgeschlossen.")
                    call_tool("log_learning_entry", {
                        "goal": user_query, "outcome": "success",
                        "details": {"final_step_count": step, "file": target},
                        "learning": "Code via implement_feature generiert und gespeichert."
                    })
                    return final

                if patch and target:
                    # Falls dein Server einen Patch-Handler hat:
                    pr = call_tool("apply_patch", {"path": target, "patch": patch})
                    if isinstance(pr, dict) and pr.get("error"):
                        failures += 1
                        messages.append({"role": "user", "content": f"Observation: {json.dumps({'error':'apply_patch_failed','detail': pr})}"})
                        continue
                    final = f"Patch auf '{target}' angewandt."
                    messages.append({"role": "assistant", "content": f"Thought: erledigt\nFinal Answer: {final}"})
                    logger.info("✅ Patch angewandt & abgeschlossen.")
                    call_tool("log_learning_entry", {
                        "goal": user_query, "outcome": "success",
                        "details": {"final_step_count": step, "file": target},
                        "learning": "Patch via implement_feature angewandt."
                    })
                    return final
        except Exception as e:
            failures += 1
            logger.warning(f"Nachbearbeitung der Observation fehlgeschlagen: {e}")
            messages.append({"role": "user", "content": f"Observation: {json.dumps({'error':'post_observation_failed','detail': str(e)})}"})
            continue

        if failures >= 3:
            logger.error("Zu viele Fehlversuche; breche ab.")
            call_tool("log_learning_entry", {
                "goal": user_query, "outcome": "failure_escalation",
                "details": {"error": "Max retries exceeded", "last_action": last_action_str},
                "learning": "Inception genutzt, aber der Prozess ist in einer Fehlerschleife gelandet."
            })
            return "Ich konnte die Aufgabe nicht abschließen (Max retries). Details wurden geloggt."

    return "⚠️ Maximale Anzahl an Schritten erreicht, ohne eine finale Antwort zu geben."

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = run_developer_task(query)
        print("\n" + "="*80)
        print("💡 FINALE ANTWORT DES DEVELOPER-AGENTEN:")
        print("="*80)
        print(textwrap.fill(result, width=80))
        print("="*80)
    else:
        print("Dieses Skript wird vom Master-Dispatcher aufgerufen.")
        # Das return Statement hier entfernt, da es außerhalb einer Funktion steht

