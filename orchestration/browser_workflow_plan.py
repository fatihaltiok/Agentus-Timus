"""Structured browser workflow plans for meta->visual execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List


ALLOWED_ACTIONS = {
    "navigate",
    "dismiss_cookie",
    "focus_input",
    "type_text",
    "select_option",
    "open_panel",
    "click_target",
    "submit",
    "verify_state",
}
ALLOWED_TARGET_TYPES = {
    "page",
    "banner",
    "input",
    "autocomplete",
    "datepicker",
    "button",
    "form",
    "modal",
    "results",
    "status",
    "timeline",
    "composer",
    "video",
}
ALLOWED_EVIDENCE_TYPES = {"url_contains", "visible_text", "dom_selector", "visual_marker"}
ALLOWED_RECOVERY_TYPES = {
    "dom_lookup",
    "ocr_lookup",
    "vision_scan",
    "roi_shift",
    "state_backtrack",
    "abort_with_handoff",
}
ALLOWED_STATES = {
    "landing",
    "cookie_banner",
    "search_form",
    "autocomplete_open",
    "datepicker_open",
    "results_loaded",
    "login_modal",
    "form_ready",
    "form_submitted",
    "authenticated",
    "timeline_ready",
    "compose_ready",
    "video_page",
}


@dataclass(frozen=True)
class BrowserStateEvidence:
    evidence_type: str
    value: str


@dataclass(frozen=True)
class BrowserWorkflowStep:
    action: str
    target_type: str
    target_text: str
    expected_state: str
    success_signal: List[BrowserStateEvidence] = field(default_factory=list)
    timeout: float = 8.0
    retry_strategy: str = "same_step_once"
    fallback_strategy: str = "dom_lookup"


@dataclass(frozen=True)
class BrowserWorkflowPlan:
    flow_type: str
    initial_state: str
    steps: List[BrowserWorkflowStep]


def _evidence(*pairs: tuple[str, str]) -> List[BrowserStateEvidence]:
    return [
        BrowserStateEvidence(evidence_type=evidence_type, value=value)
        for evidence_type, value in pairs
        if value
    ]


def _step(
    action: str,
    target_type: str,
    target_text: str,
    expected_state: str,
    success_signal: Iterable[BrowserStateEvidence],
    *,
    timeout: float,
    retry_strategy: str = "same_step_once",
    fallback_strategy: str = "dom_lookup",
) -> BrowserWorkflowStep:
    return BrowserWorkflowStep(
        action=action,
        target_type=target_type,
        target_text=target_text,
        expected_state=expected_state,
        success_signal=list(success_signal),
        timeout=timeout,
        retry_strategy=retry_strategy,
        fallback_strategy=fallback_strategy,
    )


def _ensure_valid_step(step: BrowserWorkflowStep) -> BrowserWorkflowStep:
    action = step.action if step.action in ALLOWED_ACTIONS else "verify_state"
    target_type = step.target_type if step.target_type in ALLOWED_TARGET_TYPES else "status"
    expected_state = step.expected_state if step.expected_state in ALLOWED_STATES else "landing"
    fallback_strategy = (
        step.fallback_strategy
        if step.fallback_strategy in ALLOWED_RECOVERY_TYPES
        else "abort_with_handoff"
    )
    timeout = float(step.timeout or 0.0)
    timeout = timeout if timeout > 0 else 8.0
    success_signal = [
        evidence
        for evidence in step.success_signal
        if evidence.evidence_type in ALLOWED_EVIDENCE_TYPES and str(evidence.value or "").strip()
    ]
    if not success_signal:
        success_signal = [BrowserStateEvidence(evidence_type="visible_text", value=step.target_text or expected_state)]
    return BrowserWorkflowStep(
        action=action,
        target_type=target_type,
        target_text=str(step.target_text or "").strip(),
        expected_state=expected_state,
        success_signal=success_signal,
        timeout=timeout,
        retry_strategy=str(step.retry_strategy or "same_step_once"),
        fallback_strategy=fallback_strategy,
    )


def validate_browser_workflow_plan(plan: BrowserWorkflowPlan) -> BrowserWorkflowPlan:
    steps = [_ensure_valid_step(step) for step in list(plan.steps or [])]
    if not steps:
        steps = [
            _step(
                "verify_state",
                "status",
                "Task abgeschlossen",
                "landing",
                _evidence(("visible_text", "Task abgeschlossen")),
                timeout=4.0,
                fallback_strategy="abort_with_handoff",
            )
        ]
    initial_state = plan.initial_state if plan.initial_state in ALLOWED_STATES else "landing"
    flow_type = str(plan.flow_type or "generic_browser_flow").strip() or "generic_browser_flow"
    return BrowserWorkflowPlan(flow_type=flow_type, initial_state=initial_state, steps=steps)


def _extract_domain(url: str) -> str:
    return (url or "").replace("https://", "").replace("http://", "").split("/")[0]


def _extract_destination(task: str) -> str:
    search_match = re.search(
        r"(?:suche(?:\s+nach)?|schau(?:\s+nach)?|finde)\s+(?:hotels?\s+in\s+)?(.+?)"
        r"(?:\s+(?:für\s+den|für|am|vom|ab|und\s+dann|dann|anschließend|anschliessend)|\s+\d{1,2}[./]|$)",
        task.lower(),
    )
    if not search_match:
        return ""
    start, end = search_match.span(1)
    return task[start:end].strip().rstrip(",")


def _build_booking_flow(task: str, url: str) -> BrowserWorkflowPlan:
    safe_task = (task or "").strip()
    safe_url = (url or "").strip()
    domain = _extract_domain(safe_url)
    destination = _extract_destination(safe_task)
    date_matches = re.findall(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", safe_task)

    steps: List[BrowserWorkflowStep] = [
        _step(
            "navigate",
            "page",
            domain or safe_url or "booking",
            "landing",
            _evidence(
                ("url_contains", domain),
                ("visible_text", "booking"),
            ),
            timeout=18.0,
            fallback_strategy="abort_with_handoff",
        ),
        _step(
            "dismiss_cookie",
            "banner",
            "Cookie-Banner nur falls sichtbar",
            "search_form",
            _evidence(
                ("dom_selector", "input"),
                ("visible_text", "Suche"),
            ),
            timeout=6.0,
            fallback_strategy="vision_scan",
        ),
    ]

    if destination:
        steps.extend(
            [
                _step(
                    "focus_input",
                    "input",
                    destination,
                    "search_form",
                    _evidence(
                        ("dom_selector", "input"),
                        ("visible_text", destination),
                    ),
                    timeout=6.0,
                    fallback_strategy="dom_lookup",
                ),
                _step(
                    "type_text",
                    "input",
                    destination,
                    "search_form",
                    _evidence(
                        ("visible_text", destination),
                        ("dom_selector", destination),
                    ),
                    timeout=8.0,
                    fallback_strategy="ocr_lookup",
                ),
                _step(
                    "select_option",
                    "autocomplete",
                    destination,
                    "autocomplete_open",
                    _evidence(
                        ("visible_text", destination),
                        ("dom_selector", "autocomplete"),
                    ),
                    timeout=6.0,
                    fallback_strategy="vision_scan",
                ),
            ]
        )

    if len(date_matches) >= 2:
        steps.extend(
            [
                _step(
                    "open_panel",
                    "datepicker",
                    "Datepicker",
                    "datepicker_open",
                    _evidence(
                        ("visible_text", date_matches[0]),
                        ("visual_marker", "calendar"),
                    ),
                    timeout=8.0,
                    fallback_strategy="roi_shift",
                ),
                _step(
                    "select_option",
                    "datepicker",
                    date_matches[0],
                    "datepicker_open",
                    _evidence(
                        ("visible_text", date_matches[0]),
                        ("visual_marker", date_matches[0]),
                    ),
                    timeout=8.0,
                    fallback_strategy="vision_scan",
                ),
                _step(
                    "select_option",
                    "datepicker",
                    date_matches[1],
                    "datepicker_open",
                    _evidence(
                        ("visible_text", date_matches[1]),
                        ("visual_marker", date_matches[1]),
                    ),
                    timeout=8.0,
                    fallback_strategy="vision_scan",
                ),
            ]
        )

    steps.extend(
        [
            _step(
                "submit",
                "button",
                "Suche",
                "results_loaded",
                _evidence(
                    ("visible_text", "Ergebnisse"),
                    ("url_contains", "search"),
                    ("dom_selector", "results"),
                ),
                timeout=16.0,
                fallback_strategy="state_backtrack",
            ),
            _step(
                "verify_state",
                "results",
                "Suchergebnisse sichtbar",
                "results_loaded",
                _evidence(
                    ("visible_text", "Ergebnisse"),
                    ("dom_selector", "results"),
                ),
                timeout=10.0,
                fallback_strategy="abort_with_handoff",
            ),
        ]
    )
    return validate_browser_workflow_plan(
        BrowserWorkflowPlan(flow_type="booking_search", initial_state="landing", steps=steps)
    )


def _build_login_flow(task: str, url: str) -> BrowserWorkflowPlan:
    safe_task = (task or "").strip()
    safe_url = (url or "").strip()
    domain = _extract_domain(safe_url)
    task_lower = safe_task.lower()
    steps: List[BrowserWorkflowStep] = [
        _step(
            "navigate",
            "page",
            domain or safe_url or "login page",
            "landing",
            _evidence(
                ("url_contains", domain),
                ("visible_text", "login"),
            ),
            timeout=18.0,
            fallback_strategy="abort_with_handoff",
        ),
        _step(
            "verify_state",
            "modal",
            "Login-Maske oder Login-Formular",
            "login_modal",
            _evidence(
                ("visible_text", "login"),
                ("dom_selector", "password"),
            ),
            timeout=8.0,
            fallback_strategy="dom_lookup",
        ),
    ]
    if any(token in task_lower for token in ("benutzername", "username", "email", "e-mail")):
        steps.extend(
            [
                _step(
                    "focus_input",
                    "input",
                    "Benutzername oder E-Mail",
                    "login_modal",
                    _evidence(
                        ("visible_text", "email"),
                        ("dom_selector", "input"),
                    ),
                    timeout=6.0,
                    fallback_strategy="dom_lookup",
                ),
                _step(
                    "type_text",
                    "input",
                    "Benutzername oder E-Mail",
                    "login_modal",
                    _evidence(
                        ("dom_selector", "input"),
                        ("visible_text", "@"),
                    ),
                    timeout=8.0,
                    fallback_strategy="ocr_lookup",
                ),
            ]
        )
    if "passwort" in task_lower or "password" in task_lower:
        steps.extend(
            [
                _step(
                    "focus_input",
                    "input",
                    "Passwort",
                    "login_modal",
                    _evidence(
                        ("dom_selector", "password"),
                        ("visible_text", "password"),
                    ),
                    timeout=6.0,
                    fallback_strategy="dom_lookup",
                ),
                _step(
                    "type_text",
                    "input",
                    "Passwort",
                    "login_modal",
                    _evidence(
                        ("dom_selector", "password"),
                        ("visual_marker", "password-filled"),
                    ),
                    timeout=8.0,
                    fallback_strategy="ocr_lookup",
                ),
            ]
        )
    steps.extend(
        [
            _step(
                "submit",
                "button",
                "Login oder Sign in",
                "authenticated",
                _evidence(
                    ("visible_text", "dashboard"),
                    ("url_contains", "dashboard"),
                    ("visible_text", "falsch"),
                ),
                timeout=12.0,
                fallback_strategy="state_backtrack",
            ),
            _step(
                "verify_state",
                "status",
                "Eingeloggter Zustand oder sichtbare Fehlermeldung",
                "authenticated",
                _evidence(
                    ("visible_text", "dashboard"),
                    ("visible_text", "profil"),
                    ("visible_text", "falsch"),
                ),
                timeout=8.0,
                fallback_strategy="abort_with_handoff",
            ),
        ]
    )
    return validate_browser_workflow_plan(
        BrowserWorkflowPlan(flow_type="login_flow", initial_state="landing", steps=steps)
    )


def _build_simple_form_flow(task: str, url: str) -> BrowserWorkflowPlan:
    safe_task = (task or "").strip()
    safe_url = (url or "").strip()
    domain = _extract_domain(safe_url)
    task_lower = safe_task.lower()
    steps: List[BrowserWorkflowStep] = [
        _step(
            "navigate",
            "page",
            domain or safe_url or "formular",
            "landing",
            _evidence(
                ("url_contains", domain),
                ("visible_text", "formular"),
            ),
            timeout=18.0,
            fallback_strategy="abort_with_handoff",
        ),
        _step(
            "verify_state",
            "form",
            "Formular mit sichtbaren Pflichtfeldern",
            "form_ready",
            _evidence(
                ("dom_selector", "form"),
                ("visible_text", "pflicht"),
            ),
            timeout=8.0,
            fallback_strategy="dom_lookup",
        ),
    ]
    if "name" in task_lower:
        steps.extend(
            [
                _step(
                    "focus_input",
                    "input",
                    "Namensfeld",
                    "form_ready",
                    _evidence(("visible_text", "name"), ("dom_selector", "name")),
                    timeout=6.0,
                ),
                _step(
                    "type_text",
                    "input",
                    "Namensfeld",
                    "form_ready",
                    _evidence(("visible_text", "name"), ("dom_selector", "name")),
                    timeout=8.0,
                    fallback_strategy="ocr_lookup",
                ),
            ]
        )
    if any(token in task_lower for token in ("email", "e-mail")):
        steps.extend(
            [
                _step(
                    "focus_input",
                    "input",
                    "E-Mail-Feld",
                    "form_ready",
                    _evidence(("visible_text", "email"), ("dom_selector", "email")),
                    timeout=6.0,
                ),
                _step(
                    "type_text",
                    "input",
                    "E-Mail-Feld",
                    "form_ready",
                    _evidence(("visible_text", "@"), ("dom_selector", "email")),
                    timeout=8.0,
                    fallback_strategy="ocr_lookup",
                ),
            ]
        )
    if any(token in task_lower for token in ("nachricht", "message", "kommentar")):
        steps.extend(
            [
                _step(
                    "focus_input",
                    "input",
                    "Nachrichtenfeld",
                    "form_ready",
                    _evidence(("visible_text", "nachricht"), ("dom_selector", "textarea")),
                    timeout=6.0,
                ),
                _step(
                    "type_text",
                    "input",
                    "Nachrichtenfeld",
                    "form_ready",
                    _evidence(("dom_selector", "textarea"), ("visible_text", "nachricht")),
                    timeout=8.0,
                    fallback_strategy="ocr_lookup",
                ),
            ]
        )
    if any(token in task_lower for token in ("sende", "absenden", "submit")):
        steps.extend(
            [
                _step(
                    "submit",
                    "button",
                    "Absenden oder Submit",
                    "form_submitted",
                    _evidence(
                        ("visible_text", "erfolgreich"),
                        ("visible_text", "bestätigung"),
                        ("visible_text", "fehler"),
                    ),
                    timeout=12.0,
                    fallback_strategy="state_backtrack",
                ),
                _step(
                    "verify_state",
                    "status",
                    "Bestätigung, Success-Meldung oder Fehlermeldung",
                    "form_submitted",
                    _evidence(
                        ("visible_text", "erfolgreich"),
                        ("visible_text", "bestätigung"),
                        ("visible_text", "fehler"),
                    ),
                    timeout=8.0,
                    fallback_strategy="abort_with_handoff",
                ),
            ]
        )
    return validate_browser_workflow_plan(
        BrowserWorkflowPlan(flow_type="simple_form", initial_state="landing", steps=steps)
    )


def _build_youtube_flow(task: str, url: str) -> BrowserWorkflowPlan:
    safe_task = (task or "").strip()
    safe_url = (url or "").strip()
    domain = _extract_domain(safe_url)
    task_lower = safe_task.lower()
    query_match = re.search(
        r"(?:suche(?:\s+nach)?|finde)\s+(.+?)(?:\s+(?:auf|bei)\s+youtube|\s+dann|\s+und|$)",
        task_lower,
    )
    query_text = safe_task[query_match.start(1):query_match.end(1)].strip() if query_match else "Suchbegriff"

    steps: List[BrowserWorkflowStep] = [
        _step(
            "navigate",
            "page",
            domain or safe_url or "youtube.com",
            "landing",
            _evidence(
                ("url_contains", "youtube"),
                ("visible_text", "youtube"),
            ),
            timeout=18.0,
            fallback_strategy="abort_with_handoff",
        ),
        _step(
            "dismiss_cookie",
            "banner",
            "Cookie-Banner nur falls sichtbar",
            "search_form",
            _evidence(
                ("visible_text", "Suche"),
                ("dom_selector", "input"),
            ),
            timeout=6.0,
            fallback_strategy="vision_scan",
        ),
        _step(
            "focus_input",
            "input",
            "YouTube-Suche",
            "search_form",
            _evidence(
                ("visible_text", "Suche"),
                ("dom_selector", "input"),
            ),
            timeout=6.0,
            fallback_strategy="dom_lookup",
        ),
        _step(
            "type_text",
            "input",
            query_text,
            "search_form",
            _evidence(
                ("visible_text", query_text),
                ("dom_selector", "input"),
            ),
            timeout=8.0,
            fallback_strategy="ocr_lookup",
        ),
        _step(
            "submit",
            "button",
            "Suche",
            "results_loaded",
            _evidence(
                ("url_contains", "results"),
                ("visible_text", query_text),
                ("dom_selector", "results"),
            ),
            timeout=14.0,
            fallback_strategy="state_backtrack",
        ),
        _step(
            "click_target",
            "video",
            "Erstes relevantes Video",
            "video_page",
            _evidence(
                ("url_contains", "watch"),
                ("visible_text", query_text),
            ),
            timeout=10.0,
            fallback_strategy="vision_scan",
        ),
        _step(
            "verify_state",
            "video",
            "Videoseite sichtbar",
            "video_page",
            _evidence(
                ("url_contains", "watch"),
                ("visible_text", query_text),
            ),
            timeout=8.0,
            fallback_strategy="abort_with_handoff",
        ),
    ]
    return validate_browser_workflow_plan(
        BrowserWorkflowPlan(flow_type="youtube_search", initial_state="landing", steps=steps)
    )


def _build_x_compose_flow(task: str, url: str) -> BrowserWorkflowPlan:
    safe_task = (task or "").strip()
    safe_url = (url or "").strip()
    domain = _extract_domain(safe_url)
    task_lower = safe_task.lower()
    post_text_match = re.search(
        r"(?:schreibe|verfasse|poste|poste auf x|tweet(?:e)?)\s+(.+?)(?:\s+dann|\s+und|$)",
        safe_task,
        flags=re.IGNORECASE,
    )
    post_text = post_text_match.group(1).strip() if post_text_match else "Beitrag"
    needs_login = any(token in task_lower for token in ("login", "anmelden", "sign in", "einloggen"))

    steps: List[BrowserWorkflowStep] = [
        _step(
            "navigate",
            "page",
            domain or safe_url or "x.com",
            "landing",
            _evidence(
                ("url_contains", "x.com"),
                ("visible_text", "X"),
            ),
            timeout=18.0,
            fallback_strategy="abort_with_handoff",
        ),
        _step(
            "dismiss_cookie",
            "banner",
            "Cookie-Banner nur falls sichtbar",
            "timeline_ready" if not needs_login else "login_modal",
            _evidence(
                ("visible_text", "Passwort" if needs_login else "Was gibt's Neues"),
                ("url_contains", "login" if needs_login else "x.com"),
            ),
            timeout=6.0,
            fallback_strategy="vision_scan",
        ),
    ]
    if needs_login:
        steps.extend(
            [
                _step(
                    "verify_state",
                    "modal",
                    "Login-Maske sichtbar",
                    "login_modal",
                    _evidence(
                        ("visible_text", "Passwort"),
                        ("visible_text", "Telefon"),
                    ),
                    timeout=8.0,
                    fallback_strategy="dom_lookup",
                ),
                _step(
                    "verify_state",
                    "timeline",
                    "Timeline nach Login sichtbar",
                    "timeline_ready",
                    _evidence(
                        ("visible_text", "Was gibt's Neues"),
                        ("visible_text", "Startseite"),
                    ),
                    timeout=8.0,
                    fallback_strategy="abort_with_handoff",
                ),
            ]
        )
    else:
        steps.append(
            _step(
                "verify_state",
                "timeline",
                "Timeline sichtbar",
                "timeline_ready",
                _evidence(
                    ("visible_text", "Was gibt's Neues"),
                    ("visible_text", "Startseite"),
                ),
                timeout=8.0,
                fallback_strategy="dom_lookup",
            )
        )

    steps.extend(
        [
            _step(
                "click_target",
                "composer",
                "Post verfassen",
                "compose_ready",
                _evidence(
                    ("visible_text", "Was passiert"),
                    ("visible_text", "Post"),
                ),
                timeout=8.0,
                fallback_strategy="vision_scan",
            ),
            _step(
                "type_text",
                "composer",
                post_text,
                "compose_ready",
                _evidence(
                    ("visible_text", post_text),
                    ("visible_text", "Post"),
                ),
                timeout=8.0,
                fallback_strategy="ocr_lookup",
            ),
            _step(
                "verify_state",
                "composer",
                "Composer mit Beitrag sichtbar",
                "compose_ready",
                _evidence(
                    ("visible_text", post_text),
                    ("visible_text", "Post"),
                ),
                timeout=8.0,
                fallback_strategy="abort_with_handoff",
            ),
        ]
    )
    return validate_browser_workflow_plan(
        BrowserWorkflowPlan(flow_type="x_compose", initial_state="landing", steps=steps)
    )


def build_structured_browser_workflow_plan(task: str, url: str) -> BrowserWorkflowPlan:
    safe_task = (task or "").strip()
    safe_url = (url or "").strip()
    task_lower = safe_task.lower()
    if "booking" in task_lower or "booking." in safe_url:
        return _build_booking_flow(safe_task, safe_url)
    if "youtube" in task_lower or "youtube." in safe_url or "youtu.be" in safe_url:
        return _build_youtube_flow(safe_task, safe_url)
    if any(marker in task_lower for marker in ("x.com", "twitter", "tweet", "poste auf x", "beitrag auf x")) or "x.com" in safe_url:
        return _build_x_compose_flow(safe_task, safe_url)
    login_markers = ("login", "log in", "sign in", "anmelden", "einloggen")
    if any(marker in task_lower for marker in login_markers) or "login" in safe_url:
        return _build_login_flow(safe_task, safe_url)
    form_markers = ("formular", "kontaktformular", "contact form", "fülle", "fuelle", "trage", "absenden", "sende ab")
    if any(marker in task_lower for marker in form_markers):
        return _build_simple_form_flow(safe_task, safe_url)
    return validate_browser_workflow_plan(
        BrowserWorkflowPlan(
            flow_type="generic_browser_flow",
            initial_state="landing",
            steps=[
                _step(
                    "navigate",
                    "page",
                    _extract_domain(safe_url) or safe_url or "webseite",
                    "landing",
                    _evidence(
                        ("url_contains", _extract_domain(safe_url)),
                        ("visible_text", _extract_domain(safe_url) or "webseite"),
                    ),
                    timeout=18.0,
                    fallback_strategy="abort_with_handoff",
                ),
                _step(
                    "verify_state",
                    "status",
                    safe_task or "Browser-Workflow ausführen",
                    "landing",
                    _evidence(("visible_text", "sichtbar")),
                    timeout=8.0,
                    fallback_strategy="abort_with_handoff",
                ),
            ],
        )
    )


def render_browser_workflow_step(step: BrowserWorkflowStep) -> str:
    summary = f"{step.action}: {step.target_text}".strip(": ")
    evidence = ", ".join(f"{item.evidence_type}={item.value}" for item in step.success_signal[:2])
    return (
        f"{summary} -> erwarte Zustand '{step.expected_state}'"
        + (f" | Signal: {evidence}" if evidence else "")
    )


def build_browser_workflow_plan(task: str, url: str) -> List[str]:
    """Turns a natural-language browser task into explicit, verifiable steps."""
    plan = build_structured_browser_workflow_plan(task, url)
    steps = [render_browser_workflow_step(step) for step in plan.steps]
    steps.append("Beende Task und berichte Ergebnisse")
    return steps
