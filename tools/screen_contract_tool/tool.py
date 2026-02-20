# tools/screen_contract_tool/tool.py
"""
Screen Contract Tool - JSON-basiertes Vertragssystem für stabile Navigation.

Basiert auf GPT-5.2's Empfehlung: "Locate -> Verify -> Act -> Verify"

Hauptkonzepte:
1. ScreenState: Was ist auf dem Screen? (Anker, Elemente, Text)
2. ActionPlan: Was wird gemacht? (Steps mit Verify-Before/After)
3. Verträge: Keine Aktion ohne Bedingung, keine Aktion ohne Erwartung

Macht Navigation vorhersagbar und debugbar.
"""

import logging
import asyncio
import os
import httpx
from typing import List, Dict, Optional, Union, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
log = logging.getLogger("screen_contract_tool")

# MCP Server für Tool-Aufrufe
MCP_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:5000")
TIMEOUT = 180.0


# ==============================================================================
# DATA MODELS (JSON-Verträge)
# ==============================================================================

class ElementType(str, Enum):
    """UI-Element-Typen."""
    BUTTON = "button"
    TEXT_FIELD = "text_field"
    INPUT_FIELD = "input_field"
    SEARCH_BAR = "search_bar"
    ICON = "icon"
    LINK = "link"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    LABEL = "label"
    UNKNOWN = "unknown"


class DetectionMethod(str, Enum):
    """Erkennungsmethoden."""
    OCR = "ocr"
    OBJECT_DETECTION = "object_detection"
    TEMPLATE_MATCHING = "template_matching"
    HYBRID = "hybrid"
    MOONDREAM = "moondream"
    MOUSE_FEEDBACK = "mouse_feedback"


class VerificationType(str, Enum):
    """Verifikations-Typen."""
    ANCHOR_VISIBLE = "anchor_visible"
    ELEMENT_FOUND = "element_found"
    TEXT_CONTAINS = "text_contains"
    CURSOR_TYPE = "cursor_type"
    FIELD_CONTAINS = "field_contains"
    SCREEN_CHANGED = "screen_changed"
    SCREEN_UNCHANGED = "screen_unchanged"


@dataclass
class ScreenAnchor:
    """
    Anker-Element zum Screen-Erkennen.

    Anker beweisen: "Ich bin im richtigen Screen/Zustand"
    """
    name: str
    type: str  # "text", "icon", "template", "position"
    expected_location: Optional[str] = None  # "top_left", "center", etc.
    confidence: float = 0.0
    found: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UIElement:
    """
    Erkanntes UI-Element mit präzisen Koordinaten.
    """
    name: str
    element_type: ElementType
    x: int
    y: int
    bbox: Dict[str, int]  # {"x1": ..., "y1": ..., "x2": ..., "y2": ...}
    confidence: float
    method: DetectionMethod
    text: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenState:
    """
    Aktueller Screen-Zustand (Vertrag 1: Was ist da?).

    Wird von analyze_screen() zurückgegeben.
    """
    screen_id: str
    timestamp: float
    anchors: List[ScreenAnchor]
    elements: List[UIElement]
    ocr_text: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifyCondition:
    """
    Bedingung die erfüllt sein muss (vor oder nach Aktion).
    """
    type: VerificationType
    target: str  # Element-Name, Anker-Name, Text, etc.
    params: Dict[str, Any] = field(default_factory=dict)
    min_confidence: float = 0.8


@dataclass
class ActionStep:
    """
    Einzelner Aktionsschritt (Vertrag 2: Was wird gemacht?).

    Jeder Step hat:
    - op: Was tun (click, type, wait, verify)
    - target: Wo/Was
    - verify_before: Bedingungen VOR der Aktion
    - verify_after: Erwartungen NACH der Aktion
    """
    op: str  # "click", "type", "wait", "verify", "scroll"
    target: str  # Element-Name oder Spezifikation
    params: Dict[str, Any] = field(default_factory=dict)
    verify_before: List[VerifyCondition] = field(default_factory=list)
    verify_after: List[VerifyCondition] = field(default_factory=list)
    retries: int = 2
    timeout_ms: int = 5000


@dataclass
class ActionPlan:
    """
    Kompletter Aktionsplan (mehrere Steps).
    """
    goal: str
    screen_id: str
    steps: List[ActionStep]
    abort_conditions: List[VerifyCondition] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """
    Ergebnis einer Plan-Ausführung.
    """
    success: bool
    completed_steps: int
    total_steps: int
    failed_step: Optional[int] = None
    error_message: Optional[str] = None
    screen_state_after: Optional[ScreenState] = None
    execution_time_ms: float = 0.0
    logs: List[str] = field(default_factory=list)


# ==============================================================================
# SCREEN CONTRACT ENGINE
# ==============================================================================

class ScreenContractEngine:
    """
    Engine für Screen-Analyse und Action-Plan-Ausführung.

    Prinzip: "Kein Klick ohne Beweis dass es richtig ist"
    """

    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=TIMEOUT)
        self.current_screen_state: Optional[ScreenState] = None

    @staticmethod
    def _map_detection_method(raw_method: Optional[str]) -> DetectionMethod:
        method = (raw_method or "").lower()
        if "opencv" in method or "template" in method:
            return DetectionMethod.TEMPLATE_MATCHING
        if "ocr" in method:
            return DetectionMethod.OCR
        if "mouse_feedback" in method:
            return DetectionMethod.MOUSE_FEEDBACK
        if "som" in method or "object" in method:
            return DetectionMethod.OBJECT_DETECTION
        return DetectionMethod.HYBRID

    async def _call_tool(self, method: str, params: Dict = None) -> Optional[Dict]:
        """Ruft ein Tool über MCP-Server auf."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": "contract-1"
        }

        try:
            response = await self.http_client.post(MCP_URL, json=payload)
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                log.warning(f"Tool-Fehler ({method}): {result['error']}")
                return None

            return result.get("result")

        except Exception as e:
            log.error(f"Tool-Call fehlgeschlagen ({method}): {e}")
            return None

    async def find_screen_anchors(
        self,
        screen_id: str,
        anchor_specs: List[Dict]
    ) -> List[ScreenAnchor]:
        """
        Sucht Anker-Elemente auf dem Screen.

        Args:
            screen_id: Screen-ID (z.B. "login_screen", "search_form")
            anchor_specs: Liste von Anker-Spezifikationen
                [{"name": "logo", "type": "icon", "text": "App Logo"},
                 {"name": "title", "type": "text", "text": "Anmeldung"}]

        Returns:
            Liste von ScreenAnchors mit found=True/False
        """
        anchors = []

        for spec in anchor_specs:
            anchor_name = spec.get("name", "unknown")
            anchor_type = spec.get("type", "text")
            search_text = spec.get("text")

            if anchor_type == "text" and search_text:
                # OCR-basierte Suche
                result = await self._call_tool(
                    "find_text_coordinates",
                    {"text_to_find": search_text}
                )

                if result and result.get("found"):
                    anchors.append(ScreenAnchor(
                        name=anchor_name,
                        type=anchor_type,
                        confidence=result.get("confidence", 0.9),
                        found=True,
                        details=result
                    ))
                else:
                    anchors.append(ScreenAnchor(
                        name=anchor_name,
                        type=anchor_type,
                        found=False
                    ))

            elif anchor_type == "icon":
                # Object Detection oder Template Matching
                # TODO: Implementierung je nach verfügbaren Tools
                anchors.append(ScreenAnchor(
                    name=anchor_name,
                    type=anchor_type,
                    found=False,
                    details={"error": "Icon detection not implemented yet"}
                ))

        return anchors

    async def find_screen_elements(
        self,
        element_specs: List[Dict]
    ) -> List[UIElement]:
        """
        Sucht UI-Elemente auf dem Screen.

        Args:
            element_specs: Liste von Element-Spezifikationen
                [{"name": "username_field", "type": "text_field", "text": "Benutzername"},
                 {"name": "password_field", "type": "text_field", "text": "Passwort"},
                 {"name": "login_button", "type": "button", "text": "Anmelden"}]

        Returns:
            Liste von UIElements
        """
        elements = []

        for spec in element_specs:
            elem_name = spec.get("name", "unknown")
            elem_type = spec.get("type", ElementType.UNKNOWN)
            search_text = spec.get("text")

            # Hybrid-Suche (Text + Typ)
            result = await self._call_tool(
                "hybrid_find_element",
                {
                    "text": search_text,
                    "element_type": elem_type,
                    "template_name": spec.get("template_name"),
                    "enable_template_fallback": spec.get("enable_template_fallback", True),
                    "refine": True,
                }
            )

            if result and result.get("found"):
                elements.append(UIElement(
                    name=elem_name,
                    element_type=ElementType(elem_type) if isinstance(elem_type, str) else elem_type,
                    x=result.get("x", 0),
                    y=result.get("y", 0),
                    bbox=result.get("bounds", {}),
                    confidence=result.get("confidence", 0.8),
                    method=self._map_detection_method(result.get("method")),
                    text=search_text,
                    metadata=result.get("metadata", {})
                ))

        return elements

    async def analyze_screen(
        self,
        screen_id: str,
        anchor_specs: List[Dict],
        element_specs: Optional[List[Dict]] = None,
        extract_ocr: bool = False
    ) -> ScreenState:
        """
        Analysiert den aktuellen Screen und gibt ScreenState zurück.

        Args:
            screen_id: Screen-Identifikator
            anchor_specs: Anker-Spezifikationen (Liste)
            element_specs: Element-Spezifikationen (optional)
            extract_ocr: Gesamten OCR-Text extrahieren?

        Returns:
            ScreenState
        """
        import time
        start_time = time.time()

        log.info(f"🔍 Analysiere Screen: '{screen_id}'")

        # 0. Prüfe ob Screen-Analyse nötig (Change-Gate)
        change_check = await self._call_tool("should_analyze_screen")
        if change_check and not change_check.get("changed"):
            log.info("⏭️ Screen unverändert - nutze Cache")
            if self.current_screen_state and self.current_screen_state.screen_id == screen_id:
                return self.current_screen_state

        # 1. Anker finden
        anchors = await self.find_screen_anchors(screen_id, anchor_specs)

        # 2. Elemente finden (optional)
        elements = []
        if element_specs:
            elements = await self.find_screen_elements(element_specs)

        # 3. OCR-Text extrahieren (optional)
        ocr_text = None
        if extract_ocr:
            ocr_result = await self._call_tool("get_all_screen_text")
            if ocr_result:
                texts = ocr_result.get("texts", [])
                ocr_text = "\n".join(texts)

        # 4. Warnungen und fehlende Elemente
        warnings = []
        missing = []

        # Prüfe ob wichtige Anker gefunden wurden
        for anchor in anchors:
            if not anchor.found:
                missing.append(f"Anker '{anchor.name}' nicht gefunden")

        # Prüfe ob Elemente gefunden wurden
        if element_specs:
            for spec in element_specs:
                elem_name = spec.get("name")
                found = any(e.name == elem_name for e in elements)
                if not found:
                    missing.append(f"Element '{elem_name}' nicht gefunden")

        # ScreenState erstellen
        state = ScreenState(
            screen_id=screen_id,
            timestamp=time.time(),
            anchors=anchors,
            elements=elements,
            ocr_text=ocr_text,
            warnings=warnings,
            missing=missing,
            metadata={
                "analysis_time_ms": round((time.time() - start_time) * 1000, 2)
            }
        )

        # Cache für nächsten Check
        self.current_screen_state = state

        log.info(f"✅ Screen analysiert: {len(anchors)} Anker, {len(elements)} Elemente")
        if missing:
            log.warning(f"⚠️ Fehlende Elemente: {missing}")

        return state

    async def verify_condition(
        self,
        condition: VerifyCondition,
        screen_state: Optional[ScreenState] = None
    ) -> bool:
        """
        Verifiziert eine Bedingung.

        Args:
            condition: VerifyCondition
            screen_state: Optional - aktueller ScreenState (sonst neuer Check)

        Returns:
            bool - True wenn erfüllt
        """
        if condition.type == VerificationType.ANCHOR_VISIBLE:
            # Prüfe ob Anker vorhanden
            if not screen_state:
                return False

            anchor = next((a for a in screen_state.anchors if a.name == condition.target), None)
            if not anchor:
                return False

            return anchor.found and anchor.confidence >= condition.min_confidence

        elif condition.type == VerificationType.ELEMENT_FOUND:
            # Prüfe ob Element vorhanden
            if not screen_state:
                return False

            element = next((e for e in screen_state.elements if e.name == condition.target), None)
            if not element:
                return False

            return element.confidence >= condition.min_confidence

        elif condition.type == VerificationType.TEXT_CONTAINS:
            # Prüfe ob Text auf Screen enthalten ist
            text_to_find = condition.params.get("text")
            result = await self._call_tool("find_text_coordinates", {"text_to_find": text_to_find})
            return result and result.get("found", False)

        elif condition.type == VerificationType.CURSOR_TYPE:
            # Prüfe Cursor-Typ (via Mouse Feedback)
            # TODO: Implementierung
            return True  # Placeholder

        elif condition.type == VerificationType.SCREEN_CHANGED:
            # Prüfe ob Screen sich geändert hat
            change_check = await self._call_tool("should_analyze_screen", {"force_pixel_diff": True})
            return change_check and change_check.get("changed", False)

        elif condition.type == VerificationType.SCREEN_UNCHANGED:
            # Prüfe ob Screen unverändert
            change_check = await self._call_tool("should_analyze_screen")
            return change_check and not change_check.get("changed", True)

        # Unbekannter Typ
        log.warning(f"Unbekannter Verify-Typ: {condition.type}")
        return False

    async def execute_step(
        self,
        step: ActionStep,
        screen_state: ScreenState
    ) -> tuple[bool, Optional[str]]:
        """
        Führt einen einzelnen ActionStep aus.

        Returns:
            (success: bool, error_message: Optional[str])
        """
        log.info(f"▶️ Step: {step.op} auf '{step.target}'")

        # 1. Verify-Before
        for condition in step.verify_before:
            verified = await self.verify_condition(condition, screen_state)
            if not verified:
                error = f"Verify-Before fehlgeschlagen: {condition.type} für '{condition.target}'"
                log.error(f"❌ {error}")
                return False, error

        # 2. Aktion ausführen
        if step.op == "click":
            # Element aus ScreenState holen
            element = next((e for e in screen_state.elements if e.name == step.target), None)
            if not element:
                return False, f"Element '{step.target}' nicht in ScreenState"

            # Klick ausführen
            result = await self._call_tool("click_at", {"x": element.x, "y": element.y})
            if not result or not result.get("success", False):
                return False, "Klick fehlgeschlagen"

        elif step.op == "type":
            # Text tippen
            text = step.params.get("text", "")
            press_enter = step.params.get("press_enter", False)

            result = await self._call_tool("type_text", {"text_to_type": text, "press_enter_after": press_enter})
            if not result or not result.get("success", False):
                return False, "Tippen fehlgeschlagen"

        elif step.op == "wait":
            # Warten
            wait_ms = step.params.get("duration_ms", 1000)
            await asyncio.sleep(wait_ms / 1000.0)

        elif step.op == "verify":
            # Nur Verifikation (z.B. als Check-Step)
            pass

        # 3. Verify-After
        for condition in step.verify_after:
            # Kurz warten (UI braucht Zeit zu reagieren)
            await asyncio.sleep(0.3)

            verified = await self.verify_condition(condition, None)  # Neuer Check
            if not verified:
                error = f"Verify-After fehlgeschlagen: {condition.type} für '{condition.target}'"
                log.error(f"❌ {error}")
                return False, error

        log.info(f"✅ Step erfolgreich: {step.op} auf '{step.target}'")
        return True, None

    async def execute_plan(self, plan: ActionPlan) -> ExecutionResult:
        """
        Führt einen kompletten ActionPlan aus.

        Returns:
            ExecutionResult
        """
        import time
        start_time = time.time()

        log.info(f"🚀 Starte Plan: '{plan.goal}' ({len(plan.steps)} Steps)")

        logs = []
        completed_steps = 0

        # Initial Screen-Analyse
        # (Nutzt Screen-Change-Gate automatisch)
        anchor_specs = []  # TODO: Aus Plan ableiten
        screen_state = await self.analyze_screen(plan.screen_id, anchor_specs)

        # Steps ausführen
        for i, step in enumerate(plan.steps):
            logs.append(f"Step {i+1}/{len(plan.steps)}: {step.op} auf '{step.target}'")

            # Abort-Conditions prüfen
            for abort_cond in plan.abort_conditions:
                if await self.verify_condition(abort_cond, screen_state):
                    error_msg = f"Abort-Condition erfüllt: {abort_cond.type}"
                    log.error(f"🛑 {error_msg}")
                    return ExecutionResult(
                        success=False,
                        completed_steps=completed_steps,
                        total_steps=len(plan.steps),
                        failed_step=i,
                        error_message=error_msg,
                        execution_time_ms=round((time.time() - start_time) * 1000, 2),
                        logs=logs
                    )

            # Step ausführen (mit Retries)
            success = False
            error_msg = None

            for retry in range(step.retries):
                if retry > 0:
                    logs.append(f"  Retry {retry}/{step.retries}")
                    await asyncio.sleep(1)  # Kurz warten vor Retry

                success, error_msg = await self.execute_step(step, screen_state)

                if success:
                    completed_steps += 1
                    break

            if not success:
                log.error(f"❌ Step {i+1} fehlgeschlagen nach {step.retries} Versuchen: {error_msg}")
                return ExecutionResult(
                    success=False,
                    completed_steps=completed_steps,
                    total_steps=len(plan.steps),
                    failed_step=i,
                    error_message=error_msg,
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    logs=logs
                )

            # Screen-State aktualisieren (wenn sich etwas geändert haben könnte)
            if step.op in ["click", "type"]:
                screen_state = await self.analyze_screen(plan.screen_id, anchor_specs)

        # Erfolgreich!
        execution_time = round((time.time() - start_time) * 1000, 2)
        log.info(f"✅ Plan erfolgreich abgeschlossen in {execution_time}ms")

        return ExecutionResult(
            success=True,
            completed_steps=completed_steps,
            total_steps=len(plan.steps),
            screen_state_after=screen_state,
            execution_time_ms=execution_time,
            logs=logs
        )


# Globale Engine-Instanz
contract_engine = ScreenContractEngine()


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@tool(
    name="analyze_screen_state",
    description="Analysiert den aktuellen Screen und gibt ScreenState zurück (Anker, Elemente, OCR-Text).",
    parameters=[
        P("screen_id", "string", "Screen-ID (z.B. 'login_screen', 'search_form')", required=True),
        P("anchor_specs", "array", "Liste von Anker-Specs [{'name': 'logo', 'type': 'text', 'text': 'MyApp'}]", required=True),
        P("element_specs", "array", "Liste von Element-Specs (optional)", required=False, default=None),
        P("extract_ocr", "boolean", "Gesamten Text extrahieren?", required=False, default=False),
    ],
    capabilities=["vision", "ui", "automation"],
    category=C.UI
)
async def analyze_screen_state(
    screen_id: str,
    anchor_specs: List[Dict],
    element_specs: Optional[List[Dict]] = None,
    extract_ocr: bool = False
) -> dict:
    """
    Analysiert den aktuellen Screen und gibt ScreenState zurück.

    Args:
        screen_id: Screen-ID (z.B. "login_screen", "search_form")
        anchor_specs: Liste von Anker-Specs
                     [{"name": "logo", "type": "text", "text": "MyApp"}]
        element_specs: Liste von Element-Specs (optional)
                      [{"name": "login_btn", "type": "button", "text": "Anmelden"}]
        extract_ocr: Gesamten Text extrahieren?

    Returns:
        dict mit ScreenState

    Beispiel:
        state = await analyze_screen_state(
            screen_id="login_screen",
            anchor_specs=[
                {"name": "logo", "type": "text", "text": "MyApp"},
                {"name": "title", "type": "text", "text": "Anmeldung"}
            ],
            element_specs=[
                {"name": "username", "type": "text_field", "text": "Benutzername"},
                {"name": "password", "type": "text_field", "text": "Passwort"},
                {"name": "login_btn", "type": "button", "text": "Anmelden"}
            ]
        )
    """
    try:
        state = await contract_engine.analyze_screen(
            screen_id=screen_id,
            anchor_specs=anchor_specs,
            element_specs=element_specs,
            extract_ocr=extract_ocr
        )

        return asdict(state)

    except Exception as e:
        log.error(f"Screen-Analyse fehlgeschlagen: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="execute_action_plan",
    description="Führt einen ActionPlan aus (ROBUST VERSION). Akzeptiert sowohl komplexes als auch vereinfachtes Format.",
    parameters=[
        P("plan_dict", "object", "ActionPlan als Dict mit goal, screen_id, steps", required=True),
    ],
    capabilities=["vision", "ui", "automation"],
    category=C.UI
)
async def execute_action_plan(plan_dict: Dict) -> dict:
    """
    Führt einen ActionPlan aus (ROBUST VERSION).

    Args:
        plan_dict: ActionPlan als Dict - akzeptiert sowohl komplexes Format
                  als auch vereinfachtes Format vom ExecutorAgent

    Returns:
        dict mit ExecutionResult
    """
    try:
        # ROBUST: Input-Validierung
        if not plan_dict:
            raise Exception("Empty plan_dict received")

        if not isinstance(plan_dict, dict):
            raise Exception(f"Expected dict, got {type(plan_dict)}")

        # Dict zu ActionPlan konvertieren (vereinfacht)
        goal = plan_dict.get("goal", "unknown")
        screen_id = plan_dict.get("screen_id", "unknown")
        steps_data = plan_dict.get("steps", [])

        # ROBUST: Steps-Validierung
        if not steps_data:
            raise Exception("No steps in plan")

        if not isinstance(steps_data, list):
            raise Exception(f"Steps must be list, got {type(steps_data)}")

        # Steps konvertieren (ROBUST)
        steps = []
        for i, step_data in enumerate(steps_data):
            # ROBUST: Safe key access mit Defaults
            op = step_data.get("op") or step_data.get("action") or step_data.get("type", "unknown")
            target = step_data.get("target") or step_data.get("element") or step_data.get("selector", "")
            params = step_data.get("params", {})

            # ROBUST: Verification Conditions (optional)
            verify_before = []
            verify_after = []

            try:
                verify_before = [
                    VerifyCondition(
                        type=VerificationType(v.get("type", "element_found")),
                        target=v.get("target", target),
                        params=v.get("params", {}),
                        min_confidence=v.get("min_confidence", 0.8)
                    )
                    for v in step_data.get("verify_before", [])
                    if isinstance(v, dict) and "type" in v
                ]
            except Exception as ve:
                log.warning(f"Step {i}: verify_before parsing failed: {ve}")

            try:
                verify_after = [
                    VerifyCondition(
                        type=VerificationType(v.get("type", "element_found")),
                        target=v.get("target", target),
                        params=v.get("params", {}),
                        min_confidence=v.get("min_confidence", 0.8)
                    )
                    for v in step_data.get("verify_after", [])
                    if isinstance(v, dict) and "type" in v
                ]
            except Exception as ve:
                log.warning(f"Step {i}: verify_after parsing failed: {ve}")

            # ROBUST: ActionStep erstellen (immer, auch bei unvollständigen Daten)
            steps.append(ActionStep(
                op=op,
                target=target,
                params=params,
                verify_before=verify_before,
                verify_after=verify_after,
                retries=step_data.get("retries", 2),
                timeout_ms=step_data.get("timeout_ms", 5000)
            ))

            log.debug(f"Step {i}: op={op}, target={target}")

        # ROBUST: Warnung wenn keine Steps erstellt wurden
        if not steps:
            raise Exception("No valid steps could be parsed from plan")

        # Abort-Conditions (optional)
        abort_conditions = [
            VerifyCondition(
                type=VerificationType(a["type"]),
                target=a["target"],
                params=a.get("params", {}),
                min_confidence=a.get("min_confidence", 0.8)
            )
            for a in plan_dict.get("abort_conditions", [])
        ]

        plan = ActionPlan(
            goal=goal,
            screen_id=screen_id,
            steps=steps,
            abort_conditions=abort_conditions,
            metadata=plan_dict.get("metadata", {})
        )

        # Plan ausführen
        result = await contract_engine.execute_plan(plan)

        return asdict(result)

    except Exception as e:
        log.error(f"Plan-Ausführung fehlgeschlagen: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="verify_screen_condition",
    description="Verifiziert eine einzelne Bedingung auf dem aktuellen Screen.",
    parameters=[
        P("condition_dict", "object", "VerifyCondition als Dict", required=True),
        P("screen_state_dict", "object", "Optional - ScreenState als Dict", required=False, default=None),
    ],
    capabilities=["vision", "ui", "automation"],
    category=C.UI
)
async def verify_screen_condition(
    condition_dict: Dict,
    screen_state_dict: Optional[Dict] = None
) -> dict:
    """
    Verifiziert eine einzelne Bedingung.

    Args:
        condition_dict: VerifyCondition als Dict
        screen_state_dict: Optional - ScreenState als Dict

    Returns:
        dict mit {"verified": bool}
    """
    try:
        condition = VerifyCondition(
            type=VerificationType(condition_dict["type"]),
            target=condition_dict["target"],
            params=condition_dict.get("params", {}),
            min_confidence=condition_dict.get("min_confidence", 0.8)
        )

        # ScreenState rekonstruieren (wenn gegeben)
        screen_state = None
        if screen_state_dict:
            # Vereinfachte Rekonstruktion
            screen_state = ScreenState(
                screen_id=screen_state_dict.get("screen_id", "unknown"),
                timestamp=screen_state_dict.get("timestamp", 0),
                anchors=[],  # TODO: Rekonstruieren
                elements=[]  # TODO: Rekonstruieren
            )

        verified = await contract_engine.verify_condition(condition, screen_state)

        return {"verified": verified}

    except Exception as e:
        log.error(f"Verifikation fehlgeschlagen: {e}", exc_info=True)
        raise Exception(str(e))
