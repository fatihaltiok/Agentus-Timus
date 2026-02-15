# debug_import.py
import logging

# Richte ein einfaches Logging ein, um alles zu sehen
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger("DEBUG_TEST")

log.info("Starte den Import-Test für die 'transformers'-Bibliothek...")

try:
    from transformers import SamModel, SamProcessor, CLIPProcessor, ClipModel
    
    log.info("✅ SUCCESS: Alle Transformer-Komponenten konnten erfolgreich importiert werden.")
    log.info("Das Problem liegt NICHT in der Python-Umgebung, sondern in der Art, wie der Server gestartet wird.")
    
except ImportError as e:
    log.error("❌ FAILURE: Ein ImportError ist aufgetreten. Das ist der Beweis, dass eine Abhängigkeit fehlt oder kaputt ist.")
    log.error("Die genaue Fehlermeldung lautet:")
    # Gib den gesamten Traceback aus, das ist der wichtigste Hinweis!
    import traceback
    traceback.print_exc()

except Exception as e:
    log.error("Ein unerwarteter Fehler ist aufgetreten:")
    import traceback
    traceback.print_exc()