# Standard-Bibliotheken
import logging
import json
import asyncio

# Drittanbieter-Bibliotheken
from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from jsonrpcserver import method, Success, Error
from dotenv import load_dotenv
from typing import Union 
import os

# Interne Tool-Aufrufe
# Wichtig: Stellt sicher, dass planner_helpers existiert und die async-Version von call_tool_internal hat.
from tools.planner.planner_helpers import call_tool_internal

log = logging.getLogger(__name__)

# --- Initialisierung ---
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- System-Prompt für den Kurator-Geist ---
CURATOR_PROMPT = """
Du bist der "Memory Curator" für den KI-Assistenten Timus. Deine Aufgabe ist es, zu entscheiden, welche Informationen wichtig genug sind, um im Langzeitgedächtnis gespeichert zu werden.

Du erhältst einen Text und eine Quelle. Bewerte die Information nach folgenden Kriterien:
1.  **Faktenwissen:** Ist es ein harter, wiederverwendbarer Fakt (z.B. "Die Hauptstadt von Frankreich ist Paris")? -> Hohe Priorität.
2.  **Nutzerpräferenz:** Lernt Timus etwas über den Nutzer (z.B. "Der Nutzer interessiert sich für Formel 1", "Der Nutzer bevorzugt kurze Antworten")? -> Sehr hohe Priorität.
3.  **Selbsterkenntnis:** Lernt Timus etwas über seine eigenen Fähigkeiten oder vergangene Erfolge/Fehler (z.B. "Meine letzte Recherche zu diesem Thema war sehr erfolgreich", "Ich habe Schwierigkeiten mit der Interpretation von PDF-Dateien")? -> Sehr hohe Priorität.
4.  **Konversationeller Kontext:** Ist es nur eine Floskel oder ein Teil einer laufenden, aber abgeschlossenen Diskussion (z.B. "Ja, das habe ich verstanden", "Wie kann ich dir sonst noch helfen?") -> Niedrige Priorität.

**Deine Antwort MUSS ein JSON-Objekt sein und sonst nichts.**
Das JSON-Objekt muss folgende Struktur haben:
{
  "is_memorable": boolean,
  "reason": "Eine kurze Begründung für deine Entscheidung.",
  "memory_text": "Der für die Speicherung optimierte, prägnante Text. Formuliere ihn aus Timus' Perspektive (z.B. 'Ich habe gelernt, dass der Nutzer X bevorzugt')."
}

Beispiel 1:
Input: "Zusammenfassung der Recherche: Der ITER-Reaktor hat 2024 einen neuen Meilenstein erreicht."
Output:
{
  "is_memorable": true,
  "reason": "Dies ist ein wichtiger, wiederverwendbarer Fakt über ein Thema von Interesse.",
  "memory_text": "Faktenspeicher: Der ITER-Fusionsreaktor hat im Jahr 2024 einen bedeutenden neuen Meilenstein erreicht."
}

Beispiel 2:
Input: "Nutzer: 'Danke, das war sehr hilfreich!'"
Output:
{
  "is_memorable": false,
  "reason": "Dies ist eine höfliche, aber kontextabhängige Floskel ohne langfristigen Wert.",
  "memory_text": ""
}

Beispiel 3:
Input: "Nutzer: 'Ich möchte, dass du deine Antworten immer mit einer kurzen Zusammenfassung beginnst.'"
Output:
{
  "is_memorable": true,
  "reason": "Dies ist eine klare Präferenz des Nutzers bezüglich meines Verhaltens.",
  "memory_text": "Nutzerpräferenz: Ich sollte meine Antworten immer mit einer kurzen Zusammenfassung der Kernaussagen beginnen."
}
"""

@method
# KORREKTUR: Ersetze '|' durch 'Union[Success, Error]'
async def curate_and_remember(text: str, source: str) -> Union[Success, Error]:
    """
    Lässt eine KI entscheiden, ob eine Information wichtig ist und speichert sie dann im Langzeitgedächtnis.
    Args:
        text (str): Die potentielle Erinnerung.
        source (str): Die Quelle der Information.
    """
    log.info(f"🧠 Kuratiere potenzielle Erinnerung: '{text[:60]}...'")
    try:
        # Schritt 1: Lasse den Kurator-Geist entscheiden
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o",
            messages=[
                {"role": "system", "content": CURATOR_PROMPT},
                {"role": "user", "content": f"Input: \"{text}\"\nSource: \"{source}\""}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        decision_str = response.choices[0].message.content
        decision = json.loads(decision_str)
        
        is_memorable = decision.get("is_memorable", False)
        reason = decision.get("reason", "Keine Begründung.")
        memory_text = decision.get("memory_text", "")

        log.info(f"   -> Kurator-Entscheidung: Erinnernswert? {is_memorable}. Grund: {reason}")

        # Schritt 2: Wenn die Information wichtig ist, speichere sie mit dem memory_tool
        if is_memorable and memory_text:
            # call_tool_internal ist async, also rufen wir es direkt mit await auf
            remember_result = await call_tool_internal(
                "remember", 
                {"text": memory_text, "source": source}
            )
            
            # Prüfen, ob der interne Aufruf selbst ein Fehler-Dict zurückgab
            if isinstance(remember_result, dict) and remember_result.get("error"):
                 error_msg = remember_result["error"].get("message", str(remember_result["error"]))
                 return Error(code=-32011, message=f"Kurator entschied zu speichern, aber Speichern schlug fehl: {error_msg}")
            
            return Success({
                "status": "success",
                "decision": "saved",
                "memory_id": remember_result.get("memory_id"),
                "message": "Information wurde als wichtig eingestuft und gespeichert."
            })
        else:
            return Success({
                "status": "success",
                "decision": "discarded",
                "message": "Information wurde als nicht wichtig genug eingestuft und verworfen."
            })

    except Exception as e:
        log.error(f"❌ Fehler im Kurationsprozess: {e}", exc_info=True)
        return Error(code=-32000, message=f"Interner Fehler im Kurator-Tool: {e}")