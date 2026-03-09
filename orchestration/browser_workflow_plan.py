"""Structured browser workflow plans for meta->visual execution."""

from __future__ import annotations

import re
from typing import List


def build_browser_workflow_plan(task: str, url: str) -> List[str]:
    """Turns a natural-language browser task into explicit, verifiable steps."""
    safe_task = (task or "").strip()
    safe_url = (url or "").strip()
    task_lower = safe_task.lower()
    steps: List[str] = []

    if safe_url:
        domain = safe_url.replace("https://", "").replace("http://", "").split("/")[0]
        steps.append(f"Navigiere zu {domain}")
        steps.append("Verifiziere, dass die Zielseite geladen ist und der Hauptinhalt sichtbar ist")
        steps.append(
            "Akzeptiere Cookies NUR falls ein Cookie-Banner sichtbar ist — sonst direkt weiter"
        )

    search_match = re.search(
        r"(?:suche(?:\s+nach)?|schau(?:\s+nach)?|finde)\s+(?:hotels?\s+in\s+)?(.+?)"
        r"(?:\s+(?:für\s+den|für|am|vom|ab|und\s+dann|dann|anschließend|anschliessend)|\s+\d{1,2}[./]|$)",
        task_lower,
    )
    if search_match:
        start, end = search_match.span(1)
        destination = safe_task[start:end].strip().rstrip(",")
        steps.append(
            f"Klicke auf das Suchfeld und tippe NUR: '{destination}'"
        )
        steps.append(
            f"Wähle den ersten passenden Autocomplete-Vorschlag für '{destination}' "
            "(falls kein Dropdown erscheint: drücke Enter)"
        )
        steps.append(
            "Verifiziere, dass das Ziel im Suchfeld gesetzt ist oder als ausgewählte Destination sichtbar bleibt"
        )

    date_matches = re.findall(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", safe_task)
    if len(date_matches) >= 2:
        steps.append("Öffne den Datepicker bzw. Kalender falls er noch nicht sichtbar ist")
        steps.append(
            f"Wähle im Kalender das Anreisedatum {date_matches[0]}"
        )
        steps.append(
            f"Wähle im Kalender das Abreisedatum {date_matches[1]}"
        )
        steps.append("Verifiziere, dass beide Daten im Datepicker oder Feld markiert sind")
    elif len(date_matches) == 1:
        steps.append("Öffne den Datepicker bzw. Kalender")
        steps.append(f"Wähle im Kalender das Datum {date_matches[0]}")
        steps.append("Verifiziere, dass das Datum im Feld sichtbar ist")

    persons_match = re.search(
        r"(\d+)\s*(?:person(?:en)?|erwachsene?|gäste?|reisende?)",
        task_lower,
    )
    if persons_match:
        steps.append("Öffne den Gäste-/Personen-Dialog")
        steps.append(
            f"Setze die Anzahl auf {persons_match.group(1)} Erwachsene"
        )
        steps.append("Verifiziere, dass die Gästeanzahl korrekt angezeigt wird")

    login_markers = (
        "login",
        "log in",
        "sign in",
        "anmelden",
        "einloggen",
        "logge dich ein",
    )
    if any(marker in task_lower for marker in login_markers):
        steps.append("Öffne die Login-Maske oder fokussiere das sichtbare Login-Formular")
        if any(token in task_lower for token in ("benutzername", "username", "email", "e-mail")):
            steps.append("Fülle das Feld für Benutzername oder E-Mail aus")
            steps.append("Verifiziere, dass der Benutzername oder die E-Mail im Feld sichtbar ist")
        if "passwort" in task_lower or "password" in task_lower:
            steps.append("Fülle das Passwort-Feld aus")
            steps.append("Verifiziere, dass das Passwort-Feld befüllt wirkt ohne Klartext anzuzeigen")
        steps.append("Klicke auf den Login-/Sign-in-Button")
        steps.append("Verifiziere, dass ein eingeloggter Zustand, Dashboard oder eine Erfolgs-/Fehlermeldung sichtbar ist")

    form_markers = (
        "formular",
        "kontaktformular",
        "contact form",
        "fülle",
        "fuelle",
        "trage",
        "absenden",
        "sende ab",
    )
    if any(marker in task_lower for marker in form_markers):
        steps.append("Fokussiere das relevante Formular und prüfe, dass alle Pflichtfelder sichtbar sind")
        if "name" in task_lower:
            steps.append("Fülle das Namensfeld aus")
            steps.append("Verifiziere, dass der Name im Feld sichtbar ist")
        if any(token in task_lower for token in ("email", "e-mail")):
            steps.append("Fülle das E-Mail-Feld aus")
            steps.append("Verifiziere, dass die E-Mail im Feld sichtbar ist")
        if any(token in task_lower for token in ("nachricht", "message", "kommentar")):
            steps.append("Fülle das Nachrichten- oder Textfeld aus")
            steps.append("Verifiziere, dass der Nachrichtentext im Textfeld sichtbar ist")
        if any(token in task_lower for token in ("sende", "absenden", "submit")):
            steps.append("Klicke auf den Absenden-/Submit-Button")
            steps.append("Verifiziere, dass eine Bestätigung, Success-Meldung oder Fehlermeldung sichtbar ist")

    click_match = re.search(
        r"(?:klicke\s+auf|extrahiere|zeige\s+(?:mir)?)\s+(.+?)(?:\s+(?:und|dann)|$)",
        task_lower,
    )
    if search_match:
        steps.append("Klicke auf den Suche-Button oder löse die Suche per Enter aus")
        steps.append("Verifiziere, dass Suchergebnisse oder eine Ergebnisseite sichtbar sind")
    if click_match:
        start, end = click_match.span(1)
        steps.append(f"Interagiere gezielt mit: {safe_task[start:end].strip()}")

    if len(steps) <= 3:
        steps.append(f"Führe den Browser-Workflow strukturiert aus: {safe_task}")
        steps.append("Verifiziere nach jedem Schritt, dass die erwartete UI-Reaktion eingetreten ist")

    steps.append("Beende Task und berichte Ergebnisse")
    return steps
