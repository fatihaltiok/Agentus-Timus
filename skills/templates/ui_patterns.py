"""
UI Pattern Templates - Wiederverwendbare Patterns für häufige UI-Situationen.

Diese Templates dienen als Vorlage für automatisch generierte Tools.
Der SkillManager kann sie als Kontext an implement_feature übergeben.

VERFÜGBARE TEMPLATES:
- calendar_picker: Datum aus Calendar-Widget auswählen
- modal_handler: Modal-Dialoge behandeln
- form_filler: Formulare automatisch ausfüllen
- infinite_scroll: Infinite-Scroll Seiten vollständig laden
- login_handler: Login-Formulare ausfüllen und absenden
- cookie_banner: Cookie-Banner automatisch akzeptieren

AUTOR: Timus Development
DATUM: Februar 2026
"""

from typing import Dict, List, Any, Optional
import logging

log = logging.getLogger("SkillTemplates")


TEMPLATES: Dict[str, Dict[str, Any]] = {
    "calendar_picker": {
        "description": "Wählt ein Datum aus einem Calendar-Widget aus",
        "pattern": "Calendar Navigation + Date Selection",
        "tools_needed": ["click_by_selector", "get_text", "type_text"],
        "parameters": [
            {"name": "date", "type": "string", "description": "Ziel-Datum (DD.MM.YYYY)"},
            {"name": "calendar_selector", "type": "string", "description": "CSS-Selector des Calendar-Widgets"},
        ],
        "implementation_hints": [
            "Calendar öffnen durch Klick auf Input/Icon",
            "Zu richtigem Monat navigieren (Previous/Next Buttons)",
            "Tag auswählen durch Klick auf TD mit passendem Text",
        ],
    },
    
    "modal_handler": {
        "description": "Behandelt Modal-Dialoge (Cookie, Newsletter, Age-Verification)",
        "pattern": "Modal Detection + Button Click + Dismiss",
        "tools_needed": ["dismiss_overlays", "click_by_text", "click_by_selector"],
        "parameters": [
            {"name": "modal_type", "type": "string", "description": "Art des Modals (cookie/newsletter/age)"},
            {"name": "action", "type": "string", "description": "Aktion (accept/dismiss)", "default": "accept"},
        ],
        "implementation_hints": [
            "Modal erkennen durch role='dialog' oder aria-modal",
            "Accept/Dismiss Button finden durch Text oder Selector",
            "ESC als Fallback wenn kein Button gefunden",
        ],
    },
    
    "form_filler": {
        "description": "Füllt Formulare automatisch mit Daten aus",
        "pattern": "Field Detection + Type + Submit",
        "tools_needed": ["type_text", "click_by_selector", "get_page_content"],
        "parameters": [
            {"name": "form_data", "type": "object", "description": "Dict mit Feldnamen und Werten"},
            {"name": "submit_selector", "type": "string", "description": "Selector des Submit-Buttons"},
        ],
        "implementation_hints": [
            "Input-Felder anhand von name/id/label identifizieren",
            "Select-Dropdowns mit select_option behandeln",
            "Checkboxen mit check() setzen",
            "Submit Button klicken nach Ausfüllen",
        ],
    },
    
    "infinite_scroll": {
        "description": "Lädt Infinite-Scroll Seiten vollständig",
        "pattern": "Scroll + Wait + Check for new content",
        "tools_needed": ["scroll", "get_text", "get_page_content"],
        "parameters": [
            {"name": "max_scrolls", "type": "integer", "description": "Maximale Scroll-Iterationen", "default": 10},
            {"name": "wait_ms", "type": "integer", "description": "Wartezeit zwischen Scrolls (ms)", "default": 1000},
        ],
        "implementation_hints": [
            "Scroll to Bottom mit page.evaluate('window.scrollTo(0, document.body.scrollHeight)')",
            "Warten bis neue Elemente geladen sind",
            "Abbruch wenn keine neuen Elemente oder max_scrolls erreicht",
            "Content vor/nach Scroll vergleichen",
        ],
    },
    
    "login_handler": {
        "description": "Füllt Login-Formulare aus und sendet ab",
        "pattern": "Username + Password + Submit + Verify",
        "tools_needed": ["type_text", "click_by_selector", "get_text", "open_url"],
        "parameters": [
            {"name": "username", "type": "string", "description": "Benutzername"},
            {"name": "password", "type": "string", "description": "Passwort"},
            {"name": "login_url", "type": "string", "description": "Login-Seite URL"},
        ],
        "implementation_hints": [
            "Typische Input-Selector: input[name='username'], input[name='email']",
            "Passwort-Selector: input[type='password']",
            "Submit: button[type='submit'] oder input[type='submit']",
            "Verify Login durch URL-Check oder Element-Detection",
        ],
    },
    
    "cookie_banner": {
        "description": "Akzeptiert Cookie-Banner automatisch",
        "pattern": "Banner Detection + Accept Click",
        "tools_needed": ["dismiss_overlays", "click_by_text", "click_by_selector"],
        "parameters": [
            {"name": "accept_text", "type": "string", "description": "Text des Accept-Buttons", "default": "Accept"},
        ],
        "implementation_hints": [
            "Typische Selector: #onetrust-accept-btn, .fc-cta-consent",
            "Text-Varianten: 'Alle akzeptieren', 'Accept All', 'Agree'",
            "Frame-basierte Banner in iframes suchen",
        ],
    },
    
    "dropdown_selector": {
        "description": "Wählt Option aus Dropdown/Select aus",
        "pattern": "Click Dropdown + Select Option",
        "tools_needed": ["click_by_selector", "get_text"],
        "parameters": [
            {"name": "dropdown_selector", "type": "string", "description": "Selector des Dropdown"},
            {"name": "option_value", "type": "string", "description": "Wert oder Text der Option"},
        ],
        "implementation_hints": [
            "Native select: page.select_option(selector, value)",
            "Custom dropdown: Click öffnet Liste, dann Click auf Option",
            "Search-dropdown: Erst tippen, dann aus Vorschlägen wählen",
        ],
    },
    
    "table_extraction": {
        "description": "Extrahiert Daten aus HTML-Tabellen",
        "pattern": "Find Table + Parse Rows + Return Data",
        "tools_needed": ["get_page_content", "get_text"],
        "parameters": [
            {"name": "table_selector", "type": "string", "description": "Selector der Tabelle"},
            {"name": "headers", "type": "boolean", "description": "Erste Zeile als Headers", "default": True},
        ],
        "implementation_hints": [
            "Tabelle finden mit table-Tag oder CSS-Selector",
            "Headers aus thead/tr:first-child extrahieren",
            "Rows als Liste von Dicts zurückgeben",
            "Paginierung beachten falls vorhanden",
        ],
    },
}


def get_template(pattern_name: str) -> Optional[Dict[str, Any]]:
    """
    Gibt ein Template zurück falls vorhanden.
    
    Args:
        pattern_name: Name des Patterns (z.B. 'calendar_picker')
    
    Returns:
        Template-Dict oder None
    """
    return TEMPLATES.get(pattern_name)


def find_matching_templates(description: str) -> List[Dict[str, Any]]:
    """
    Findet passende Templates basierend auf Beschreibung.
    
    Args:
        description: Beschreibung der gewünschten Funktionalität
    
    Returns:
        Liste passender Templates mit Match-Score
    """
    matches = []
    description_lower = description.lower()
    
    for name, template in TEMPLATES.items():
        score = 0
        template_desc = template.get("description", "").lower()
        template_pattern = template.get("pattern", "").lower()
        
        # Keyword matching
        keywords = description_lower.split()
        for keyword in keywords:
            if keyword in template_desc:
                score += 2
            if keyword in template_pattern:
                score += 1
            if keyword in name:
                score += 1
        
        if score > 0:
            matches.append({
                "name": name,
                "score": score,
                "template": template
            })
    
    # Sort by score
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:3]  # Top 3


def get_all_templates() -> Dict[str, Dict[str, Any]]:
    """Gibt alle Templates zurück."""
    return TEMPLATES.copy()


def get_template_as_context(pattern_name: str) -> str:
    """
    Formatiert ein Template als Kontext-String für LLM.
    
    Args:
        pattern_name: Name des Templates
    
    Returns:
        Formatierter String für implement_feature instruction
    """
    template = get_template(pattern_name)
    if not template:
        return ""
    
    params_str = ", ".join(
        f"{p['name']}: {p['type']}"
        for p in template.get("parameters", [])
    )
    
    hints_str = "\n".join(
        f"  - {h}"
        for h in template.get("implementation_hints", [])
    )
    
    return f"""
TEMPLATE: {pattern_name}
Beschreibung: {template.get('description')}
Pattern: {template.get('pattern')}
Parameter: {params_str}
Benötigte Tools: {', '.join(template.get('tools_needed', []))}
Implementation-Hinweise:
{hints_str}
"""
