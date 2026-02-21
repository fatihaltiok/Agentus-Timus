# Visual Nemotronv4 Web Interaction Skill

## Kurzbeschreibung
Dieses Skill ermöglicht die Interaktion mit Web-Seiten über die Operationen **Scan**, **OCR** und **Click**. Es ist für die Verwendung in automatisierten Test- und Produktionsumgebungen konzipiert.

## Nutzung

from skills.visual_nemotronv4_web_interaction_skill import get_config, dry_run

# Konfiguration
cfg = get_config(url="https://example.com", timeout=10, retries=3)

# Dry‑Run durchführen (keine echten Änderungen)
steps, success = dry_run(**cfg)
print("Schritte:", steps)
print("Erfolg:", success)


## Konfigurierbare Parameter
| Parameter | Typ   | Standardwert | Beschreibung                               |
|-----------|-------|--------------|--------------------------------------------|
| `url`     | str   | erforderlich | Ziel-URL der Web‑Seite                      |
| `timeout` | int   | 5            | Timeout in Sekunden pro Schritt            |
| `retries` | int   | 1            | Anzahl der Wiederholungen bei Fehlern       |

## Tests ausführen
bash
# Skript im Projektverzeichnis
tools/run_skill_tests.sh

Das Skript führt Black, Flake8 und pytest aus, sammelt Coverage‑Berichte und speichert Logs in `reports/`.

---