# tools/maintenance_tool/tool.py

import logging
import asyncio
import os
from datetime import datetime

# V2 Tool Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Interne Imports aus deinem Projekt
from tools.shared_context import memory_collection, openai_client
# Import für das Speichern der neuen Zusammenfassung
from tools.planner.planner_helpers import call_tool_internal

# Logger für dieses Modul
from utils.openai_compat import prepare_openai_params
log = logging.getLogger(__name__)

# Prompt für die Zusammenfassung von Erinnerungen
SUMMARIZER_PROMPT = """
Du bist ein "Memory Summarizer". Du erhältst eine Liste von alten, thematisch ähnlichen Erinnerungen.
Deine Aufgabe ist es, diese zu einer einzigen, prägnanten Meta-Erinnerung zusammenzufassen, die das Kernwissen bewahrt.
Die neue Erinnerung sollte die alten ersetzen.

Alte Erinnerungen:
---
{memories_text}
---

Gib NUR die neue, zusammengefasste Meta-Erinnerung als einzelne Textzeile zurück.
"""

@tool(
    name="run_memory_maintenance",
    description="Fuehrt eine Pflegeroutine fuer das Langzeitgedaechtnis durch. Fasst aehnliche, alte und selten genutzte Erinnerungen zusammen und archiviert oder loescht sehr alte, ungenutzte Erinnerungen.",
    parameters=[
        P("days_old_threshold", "integer", "Alter in Tagen, ab dem Erinnerungen als veraltet gelten", required=False, default=30),
        P("access_count_threshold", "integer", "Minimale Zugriffszahl, unter der Erinnerungen als ungenutzt gelten", required=False, default=5),
    ],
    capabilities=["memory", "maintenance"],
    category=C.MEMORY
)
async def run_memory_maintenance(days_old_threshold: int = 30, access_count_threshold: int = 5) -> dict:
    """
    Führt eine Pflegeroutine für das Langzeitgedächtnis durch.
    - Fasst ähnliche, alte und selten genutzte Erinnerungen zusammen (wenn OpenAI verfügbar ist).
    - Archiviert oder löscht sehr alte, ungenutzte Erinnerungen.
    """
    # Schritt 1: Überprüfe zur Laufzeit, ob die benötigten Ressourcen verfügbar sind.
    if not memory_collection:
        raise Exception("Langzeitgedächtnis ist für die Pflege nicht verfügbar.")

    # Prüfe, ob der OpenAI-Client für die Zusammenfassungen bereit ist.
    # Wenn nicht, läuft das Tool trotzdem weiter und führt nur die Löschungen durch.
    can_summarize = bool(openai_client)
    if not can_summarize:
        log.warning("OpenAI-Client nicht verfügbar. Überspringe den Zusammenfassungs-Schritt in der Gedächtnis-Pflege.")

    log.info("Starte Gedächtnis-Pflege-Routine...")

    try:
        # Schritt 2: Hole alle Erinnerungen aus der Datenbank.
        # .get() ist eine blockierende Operation, daher in einem Thread ausführen.
        all_memories = await asyncio.to_thread(
            memory_collection.get,
            include=["metadatas", "documents"]
        )

        if not all_memories or not all_memories.get("ids"):
            log.info("Gedächtnis ist leer. Keine Pflege notwendig.")
            return {"status": "no_memories", "message": "Gedächtnis ist leer."}

        now = datetime.now()
        ids_to_delete = []
        potential_summaries = {}

        # Schritt 3: Gehe alle Erinnerungen durch und identifiziere Kandidaten
        for i, memory_id in enumerate(all_memories["ids"]):
            metadata = all_memories["metadatas"][i]
            document = all_memories["documents"][i]

            created_at_str = metadata.get("timestamp_created", now.isoformat())
            access_count = metadata.get("access_count", 0)

            try:
                created_at = datetime.fromisoformat(created_at_str)
            except (ValueError, TypeError):
                created_at = now  # Fallback, falls Timestamp ungültig ist

            age = (now - created_at).days

            # Regel 1: Zum Löschen markieren (alt & ungenutzt)
            if age > days_old_threshold and access_count < access_count_threshold:
                ids_to_delete.append(memory_id)
                continue

            # Regel 2: Kandidaten für Zusammenfassung finden (nur wenn möglich)
            if age > (days_old_threshold / 2) and can_summarize:
                source = metadata.get("source", "unbekannt")
                if source not in potential_summaries:
                    potential_summaries[source] = []
                potential_summaries[source].append({"id": memory_id, "text": document})

        # Schritt 4: Verarbeite die Löschkandidaten
        if ids_to_delete:
            log.info(f"Lösche {len(ids_to_delete)} veraltete Erinnerungen...")
            await asyncio.to_thread(memory_collection.delete, ids=ids_to_delete)

        # Schritt 5: Verarbeite die Zusammenfassungs-Kandidaten
        summaries_created = 0
        if can_summarize:
            for source, memories in potential_summaries.items():
                if len(memories) > 2:  # Nur zusammenfassen, wenn es sich lohnt
                    log.info(f"  -> Fasse {len(memories)} Erinnerungen für Quelle '{source}' zusammen...")
                    memories_text = "\n".join([f"- {m['text']}" for m in memories])

                    response = await asyncio.to_thread(
                        openai_client.chat.completions.create,
                        model="gpt-4o",
                        messages=[{"role": "system", "content": SUMMARIZER_PROMPT}, {"role": "user", "content": memories_text}],
                        temperature=0.2
                    )
                    new_summary = response.choices[0].message.content.strip()

                    # Speichere die neue Zusammenfassung als neue Erinnerung
                    await call_tool_internal("remember", {"text": f"Zusammengefasste Erkenntnis ({source}): {new_summary}", "source": f"summary_of_{source}"})

                    # Lösche die alten Erinnerungen, die jetzt zusammengefasst sind
                    ids_to_delete_after_summary = [m['id'] for m in memories]
                    await asyncio.to_thread(memory_collection.delete, ids=ids_to_delete_after_summary)
                    summaries_created += 1

        # Schritt 6: Finale Statusmeldung
        final_count = await asyncio.to_thread(memory_collection.count)
        log.info("Gedächtnis-Pflege abgeschlossen.")
        return {
            "status": "complete",
            "deleted_count": len(ids_to_delete),
            "summaries_created": summaries_created,
            "current_total_memories": final_count,
            "summary_status": "executed" if can_summarize else "skipped_no_client"
        }

    except Exception as e:
        log.error(f"Schwerwiegender Fehler bei der Gedächtnis-Pflege: {e}", exc_info=True)
        raise Exception(f"Fehler bei der Gedächtnis-Pflege: {e}")
