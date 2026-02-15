# utils/policy_gate.py
"""
Leichtgewichtiger Policy-Gate fuer destruktive Aktionen.
Kein vollstaendiges RBAC — nur Blocklist/Allowlist + Muster-Erkennung.
"""
import logging
import re
from typing import Tuple, Optional

log = logging.getLogger("policy_gate")

# Destruktive Tool-Aufrufe (Methoden-Namen)
BLOCKED_ACTIONS = [
    "delete_file", "remove_file", "rm_file",
    "submit_payment", "buy", "purchase", "checkout",
    "submit_form",
    "shutdown", "reboot", "format_disk",
    "drop_table", "delete_database",
]

# Muster in User-Anfragen die Bestaetigung erfordern
DANGEROUS_QUERY_PATTERNS = [
    r"\bl[oö]sche?\b.*\bdatei",
    r"\bdelete\b.*\bfile",
    r"\bkaufe?\b",
    r"\bbestell",
    r"\bbezahl",
    r"\bformat\b.*\bdisk",
    r"\bsudo\s+rm\b",
    r"\brm\s+-rf\b",
    r"\bdrop\s+table\b",
]

# Immer erlaubt (Whitelist ueberschreibt Blocklist)
ALWAYS_ALLOWED = [
    "search_web", "get_text", "read_file", "list_files",
    "scan_ui_elements", "screenshot", "describe_screen",
    "describe_screen_elements", "get_element_coordinates",
    "save_annotated_screenshot", "get_supported_element_types",
    "verify_fact", "verify_multiple_facts",
    "get_all_screen_text", "should_analyze_screen",
    "run_plan", "run_skill", "list_available_skills",
]


def check_tool_policy(method_name: str, params: dict = None) -> Tuple[bool, Optional[str]]:
    """
    Prueft ob ein Tool-Aufruf erlaubt ist.

    Returns:
        (allowed, reason) — wenn nicht erlaubt, erklaert reason warum.
    """
    if method_name in ALWAYS_ALLOWED:
        return True, None

    if method_name in BLOCKED_ACTIONS:
        reason = f"Policy blockiert: '{method_name}' ist eine destruktive Aktion und erfordert Bestaetigung."
        log.warning(f"[policy] {reason}")
        return False, reason

    return True, None


def check_query_policy(user_query: str) -> Tuple[bool, Optional[str]]:
    """
    Prueft ob eine User-Anfrage potenziell gefaehrlich ist.

    Returns:
        (safe, warning) — wenn nicht safe, sollte der Dispatcher Bestaetigung einholen.
    """
    query_lower = user_query.lower()

    for pattern in DANGEROUS_QUERY_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            warning = f"Potenziell destruktive Anfrage erkannt ('{match.group()}'). Bestaetigung empfohlen."
            log.warning(f"[policy] {warning}")
            return False, warning

    return True, None
