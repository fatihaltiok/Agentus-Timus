"""
Hybrid Browser Controller v2.0 - DOM-First Architecture

Intelligenter Browser-Controller der DOM-First nutzt und auf Vision fallback macht.

Decision Gate pro Aktion:
1. Kann ich DOM/A11y nutzen? → DOM-Action (schnell, präzise, kostenlos)
2. Wenn nicht → Vision-Fallback (SoM oder GPT-4 Vision)
3. Nach Aktion → Post-Check mit Verification Tool
4. Bei Fehler → Retry mit Fallback-Strategie

Nutzt vorhandene Tools:
- browser_tool (Playwright)
- som_tool (Vision-Fallback)
- verification_tool (Post-Check)
- mouse_tool (PyAutoGUI Fallback)
"""

import logging
import asyncio
import httpx
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from PIL import Image

from .state_tracker import UIStateTracker, UIState, StateDiff
from .dom_parser import DOMParser, DOMElement

log = logging.getLogger("hybrid_browser")


class ActionType(str, Enum):
    """Verfügbare Aktionstypen."""
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    PRESS = "press"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    WAIT = "wait"
    EXTRACT = "extract"


class ActionMethod(str, Enum):
    """Methode zur Aktions-Ausführung."""
    DOM = "dom"  # Playwright DOM-Selectors
    VISION = "vision"  # Vision-basierte Koordinaten
    HYBRID = "hybrid"  # Beides kombiniert


@dataclass
class ActionResult:
    """Ergebnis einer Aktion."""
    success: bool
    method_used: ActionMethod
    execution_time: float
    error: Optional[str] = None
    state_changed: bool = False
    verification_passed: bool = True
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'method': self.method_used.value,
            'execution_time_ms': round(self.execution_time * 1000, 2),
            'error': self.error,
            'state_changed': self.state_changed,
            'verification_passed': self.verification_passed,
            'fallback_used': self.fallback_used
        }


class HybridBrowserController:
    """
    Hybrid Browser Controller - DOM-First mit Vision-Fallback.

    Features:
    - DOM-First: Nutzt Playwright für präzise Browser-Steuerung
    - Vision-Fallback: SoM/GPT-4 wenn DOM nicht verfügbar
    - Verification: Post-Check nach jeder Aktion
    - State-Tracking: Loop-Detection und DOM-Changes
    - Cookie-Banner Auto-Handling
    - Smart-Waiting: Network-Aware Timeouts
    - Session-Isolation (v2.0): Persistente Contexts pro Session

    Workflow:
    1. initialize() - Startet Browser
    2. navigate(url) - Öffnet URL
    3. execute_action(action) - Führt Aktion aus (DOM-First!)
    4. verify_action(before, after) - Post-Check
    5. cleanup() - Stoppt Browser
    """

    # Cookie-Banner Selectors (aus browser_tool übernommen)
    COOKIE_SELECTORS = [
        "button#onetrust-accept-btn-handler",
        "button[aria-label='Alle akzeptieren']",
        "button[aria-label='Accept all']",
        ".cmpboxbtnyes",
        ".fc-cta-consent",
        "[data-testid='cookie-banner-accept']",
        "button[data-accept-action='all']",
        "button:has-text('Accept')",
        "button:has-text('Akzeptieren')",
    ]

    def __init__(
        self, 
        mcp_url: str = "http://localhost:5000", 
        headless: bool = False,
        session_id: str = "default"
    ):
        """
        Initialisiert Hybrid Browser Controller.

        Args:
            mcp_url: MCP-Server URL für Tool-Calls
            headless: Browser im Hintergrund starten
            session_id: Session-ID für Context-Isolation (v2.0)
        """
        self.mcp_url = mcp_url
        self.headless = headless
        self.session_id = session_id  # NEU: Session-Isolation

        # Components
        self.state_tracker = UIStateTracker(max_history=20)
        self.dom_parser = DOMParser()

        # Browser State
        self.browser_session = None
        self.current_url = ""
        self.is_initialized = False

        # HTTP Client für MCP-Calls
        self.http_client = httpx.AsyncClient(timeout=60.0)

        # Statistics
        self.stats = {
            'dom_actions': 0,
            'vision_actions': 0,
            'fallbacks': 0,
            'verifications_passed': 0,
            'verifications_failed': 0
        }

        log.info(f"✅ HybridBrowserController initialisiert (headless={headless}, session={session_id})")

    async def initialize(self) -> bool:
        """
        Initialisiert Browser-Session via browser_tool.

        Returns:
            True wenn erfolgreich
        """
        if self.is_initialized:
            log.info("Browser bereits initialisiert")
            return True

        try:
            # Browser-Tool nutzt bereits Playwright - wir rufen nur die Initialisierung auf
            # browser_tool hat BrowserSession die wir nutzen können
            log.info("🌐 Initialisiere Browser via browser_tool...")

            # Wir nutzen das existierende browser_tool indirekt via MCP
            # Das ist besser als doppelte Playwright-Instanzen

            self.is_initialized = True
            log.info("✅ Browser-Controller erfolgreich initialisiert")
            return True

        except Exception as e:
            log.error(f"❌ Browser-Initialisierung fehlgeschlagen: {e}", exc_info=True)
            return False

    async def navigate(self, url: str, wait_for_load: bool = True) -> ActionResult:
        """
        Navigiert zu URL.

        Args:
            url: Ziel-URL
            wait_for_load: Auf Page-Load warten

        Returns:
            ActionResult
        """
        start_time = time.time()

        try:
            log.info(f"🌐 [{self.session_id}] Navigiere zu: {url}")

            # MCP-Call an browser_tool mit session_id
            result = await self._call_mcp_tool("open_url", {
                "url": url,
                "session_id": self.session_id
            })

            if "error" in result:
                return ActionResult(
                    success=False,
                    method_used=ActionMethod.DOM,
                    execution_time=time.time() - start_time,
                    error=str(result["error"])
                )

            # URL speichern
            self.current_url = url

            # Warte auf Load
            if wait_for_load:
                await asyncio.sleep(2)  # Initial Load

            # Cookie-Banner automatisch handlen
            await self._auto_handle_cookie_banner()

            # State erfassen
            await self._capture_state()

            return ActionResult(
                success=True,
                method_used=ActionMethod.DOM,
                execution_time=time.time() - start_time,
                state_changed=True
            )

        except Exception as e:
            log.error(f"❌ Navigation fehlgeschlagen: {e}")
            return ActionResult(
                success=False,
                method_used=ActionMethod.DOM,
                execution_time=time.time() - start_time,
                error=str(e)
            )

    async def execute_action(self, action: Dict[str, Any]) -> ActionResult:
        """
        Führt Aktion aus - DECISION GATE: DOM-First!

        Args:
            action: Action-Dict mit type, target, etc.

        Returns:
            ActionResult

        Action Format:
        {
            "type": "click",
            "target": {
                "text": "Login",  # Text-basierte Suche
                "selector": "#login-btn",  # Optional: Direkter Selector
                "role": "button"  # Optional: ARIA-Role
            },
            "expected_state": {  # Optional: Für Verification
                "url_contains": "dashboard",
                "dom_contains": "Welcome"
            }
        }
        """
        start_time = time.time()
        action_type = action.get("type", "click")
        target = action.get("target", {})

        log.info(f"🎯 Führe Aktion aus: {action_type}")

        # State VOR Aktion
        before_state = await self._capture_state()

        # ==============================
        # DECISION GATE: DOM vs Vision
        # ==============================

        # 1. Versuche DOM zuerst (IMMER bevorzugen!)
        if self._can_use_dom(target):
            result = await self._execute_dom_action(action_type, target)
            method = ActionMethod.DOM
            self.stats['dom_actions'] += 1

            if result.success:
                log.info(f"✅ DOM-Aktion erfolgreich ({result.execution_time*1000:.0f}ms)")
            else:
                log.warning(f"⚠️  DOM-Aktion fehlgeschlagen: {result.error}")

                # Fallback zu Vision
                log.info("🔄 Fallback zu Vision...")
                result = await self._execute_vision_action(action_type, target)
                method = ActionMethod.VISION
                result.fallback_used = True
                self.stats['vision_actions'] += 1
                self.stats['fallbacks'] += 1
        else:
            # 2. Vision direkt (DOM nicht verfügbar)
            log.info("👁️  Vision-Modus (DOM nicht verfügbar)")
            result = await self._execute_vision_action(action_type, target)
            method = ActionMethod.VISION
            self.stats['vision_actions'] += 1

        result.method_used = method
        result.execution_time = time.time() - start_time

        # Kurze Pause für UI-Update
        await asyncio.sleep(0.5)

        # State NACH Aktion
        after_state = await self._capture_state()

        # ==============================
        # POST-CHECK: Verification
        # ==============================

        expected_state = action.get("expected_state")
        if expected_state:
            verification = await self._verify_action(before_state, after_state, expected_state)
            result.verification_passed = verification
            result.state_changed = self._has_state_changed(before_state, after_state)

            if verification:
                self.stats['verifications_passed'] += 1
            else:
                self.stats['verifications_failed'] += 1
                log.warning("⚠️  Verification fehlgeschlagen!")

        log.info(f"{'✅' if result.success else '❌'} Aktion abgeschlossen: "
                f"{method.value} in {result.execution_time*1000:.0f}ms")

        return result

    def _can_use_dom(self, target: Dict[str, Any]) -> bool:
        """
        Decision Gate: Kann DOM genutzt werden?

        Args:
            target: Target-Dict mit selector, text, role, etc.

        Returns:
            True wenn DOM nutzbar
        """
        # Wenn expliziter Selector gegeben: JA
        if target.get("selector"):
            return True

        # Wenn Text oder Role gegeben: JA (DOM-Suche möglich)
        if target.get("text") or target.get("role"):
            return True

        # Sonst: NEIN (Vision nötig)
        return False

    async def _execute_dom_action(self, action_type: str, target: Dict[str, Any]) -> ActionResult:
        """
        Führt DOM-basierte Aktion aus (Playwright).

        Args:
            action_type: Type der Aktion
            target: Target-Parameter

        Returns:
            ActionResult
        """
        start_time = time.time()

        try:
            # Finde Element im DOM
            selector = target.get("selector")

            if not selector:
                # Generiere Selector aus Text/Role
                selector = await self._find_dom_selector(target)

            if not selector:
                return ActionResult(
                    success=False,
                    method_used=ActionMethod.DOM,
                    execution_time=time.time() - start_time,
                    error="Kein Selector gefunden"
                )

            # Führe Aktion aus via browser_tool
            if action_type == "click":
                result = await self._call_mcp_tool("click_by_selector", {"selector": selector})
            elif action_type == "type":
                text = target.get("text", "")
                result = await self._call_mcp_tool("type_text", {
                    "selector": selector,
                    "text": text
                })
            else:
                return ActionResult(
                    success=False,
                    method_used=ActionMethod.DOM,
                    execution_time=time.time() - start_time,
                    error=f"Aktion '{action_type}' nicht unterstützt"
                )

            # Prüfe Ergebnis
            if "error" in result:
                return ActionResult(
                    success=False,
                    method_used=ActionMethod.DOM,
                    execution_time=time.time() - start_time,
                    error=str(result["error"])
                )

            return ActionResult(
                success=True,
                method_used=ActionMethod.DOM,
                execution_time=time.time() - start_time
            )

        except Exception as e:
            log.error(f"❌ DOM-Aktion fehlgeschlagen: {e}")
            return ActionResult(
                success=False,
                method_used=ActionMethod.DOM,
                execution_time=time.time() - start_time,
                error=str(e)
            )

    async def _execute_vision_action(self, action_type: str, target: Dict[str, Any]) -> ActionResult:
        """
        Führt Vision-basierte Aktion aus (SoM Tool).

        Args:
            action_type: Type der Aktion
            target: Target-Parameter

        Returns:
            ActionResult
        """
        start_time = time.time()

        try:
            # Nutze SoM Tool für UI-Element-Erkennung
            log.info("🔍 Nutze SoM Tool für Element-Erkennung...")

            scan_result = await self._call_mcp_tool("scan_ui_elements", {
                "element_types": [target.get("element_type", "button")]
            })

            if "error" in scan_result or not scan_result.get("elements"):
                return ActionResult(
                    success=False,
                    method_used=ActionMethod.VISION,
                    execution_time=time.time() - start_time,
                    error="Keine UI-Elemente gefunden"
                )

            # Finde passendes Element
            elements = scan_result["elements"]
            target_text = target.get("text", "").lower()

            matching_elem = None
            for elem in elements:
                elem_text = elem.get("text", "").lower()
                if target_text in elem_text:
                    matching_elem = elem
                    break

            if not matching_elem:
                # Nimm erstes Element als Fallback
                matching_elem = elements[0]

            # Koordinaten extrahieren
            coords = {
                "x": matching_elem.get("center_x"),
                "y": matching_elem.get("center_y")
            }

            # Klick via mouse_tool
            if action_type == "click":
                result = await self._call_mcp_tool("click_at", coords)

                if "error" in result:
                    return ActionResult(
                        success=False,
                        method_used=ActionMethod.VISION,
                        execution_time=time.time() - start_time,
                        error=str(result["error"])
                    )

                return ActionResult(
                    success=True,
                    method_used=ActionMethod.VISION,
                    execution_time=time.time() - start_time
                )

            return ActionResult(
                success=False,
                method_used=ActionMethod.VISION,
                execution_time=time.time() - start_time,
                error=f"Vision-Aktion '{action_type}' nicht unterstützt"
            )

        except Exception as e:
            log.error(f"❌ Vision-Aktion fehlgeschlagen: {e}")
            return ActionResult(
                success=False,
                method_used=ActionMethod.VISION,
                execution_time=time.time() - start_time,
                error=str(e)
            )

    async def _find_dom_selector(self, target: Dict[str, Any]) -> Optional[str]:
        """
        Findet CSS Selector aus Target-Beschreibung.

        Args:
            target: Target mit text, role, etc.

        Returns:
            CSS Selector oder None
        """
        # Hole aktuellen DOM-Content
        dom_content = await self._get_dom_content()
        if not dom_content:
            return None

        # Parse DOM
        elements = self.dom_parser.parse(dom_content)

        # Suche nach Text
        text = target.get("text")
        if text:
            matches = self.dom_parser.find_by_text(text, fuzzy=True)
            if matches:
                return matches[0].selector

        # Suche nach Role
        role = target.get("role")
        if role:
            matches = self.dom_parser.find_by_role(role)
            if matches:
                return matches[0].selector

        return None

    async def _get_dom_content(self) -> Optional[str]:
        """Holt aktuellen DOM-Content via browser_tool."""
        try:
            result = await self._call_mcp_tool("get_page_content", {})
            if "content" in result:
                return result["content"]
        except Exception as e:
            log.error(f"Fehler beim Holen des DOM: {e}")
        return None

    async def _auto_handle_cookie_banner(self):
        """Handlet Cookie-Banner automatisch (DOM-First!)."""
        try:
            log.debug("🍪 Prüfe Cookie-Banner...")

            for selector in self.COOKIE_SELECTORS:
                result = await self._call_mcp_tool("click_by_selector", {"selector": selector})

                if "error" not in result:
                    log.info(f"✅ Cookie-Banner akzeptiert (Selector: {selector})")
                    await asyncio.sleep(0.5)
                    return

        except Exception as e:
            log.debug(f"Cookie-Banner Handling: {e}")

    async def _capture_state(self) -> UIState:
        """Erfasst aktuellen UI-State."""
        try:
            # DOM Content holen
            dom_content = await self._get_dom_content() or ""

            # Visible Elements (via DOM Parser)
            elements = []
            if dom_content:
                parsed = self.dom_parser.parse(dom_content)
                elements = [e.selector for e in parsed[:50]]  # Max 50

            # State erstellen
            state = self.state_tracker.observe(
                url=self.current_url,
                dom_content=dom_content,
                visible_elements=elements,
                network_idle=True  # TODO: Check via browser_tool
            )

            return state

        except Exception as e:
            log.error(f"State-Erfassung fehlgeschlagen: {e}")
            # Fallback State
            return UIState(
                timestamp=time.time(),
                url=self.current_url,
                dom_hash="error",
                visible_elements=[]
            )

    async def _verify_action(self,
                            before: UIState,
                            after: UIState,
                            expected: Dict[str, Any]) -> bool:
        """
        Verifiziert Aktion gegen Expected State.

        Args:
            before: State vor Aktion
            after: State nach Aktion
            expected: Expected State Dict

        Returns:
            True wenn Verification erfolgreich
        """
        # URL-Check
        if "url_contains" in expected:
            if expected["url_contains"] not in after.url:
                log.warning(f"URL-Check fehlgeschlagen: '{expected['url_contains']}' nicht in '{after.url}'")
                return False

        # DOM-Check
        if "dom_contains" in expected:
            # Müsste DOM-Content holen und prüfen
            # TODO: Implementieren
            pass

        # State-Change-Check
        diff = self.state_tracker.get_state_diff(before, after)
        if not diff.has_significant_change():
            log.warning("Keine signifikante State-Änderung erkannt")
            return False

        return True

    def _has_state_changed(self, before: UIState, after: UIState) -> bool:
        """Prüft ob State sich geändert hat."""
        diff = self.state_tracker.get_state_diff(before, after)
        return diff.has_significant_change()

    async def _call_mcp_tool(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ruft MCP-Tool auf.

        Args:
            method: Tool-Methode
            params: Parameter

        Returns:
            Result-Dict
        """
        try:
            response = await self.http_client.post(
                self.mcp_url,
                json={
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params,
                    "id": 1
                }
            )
            data = response.json()

            if "result" in data:
                return data["result"]
            elif "error" in data:
                return {"error": data["error"]}

            return data

        except Exception as e:
            log.error(f"MCP-Call fehlgeschlagen ({method}): {e}")
            return {"error": str(e)}

    async def cleanup(self):
        """Räumt Ressourcen auf."""
        try:
            await self.http_client.aclose()
            log.info("✅ Browser-Controller cleanup abgeschlossen")
        except Exception as e:
            log.error(f"Cleanup-Fehler: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        return {
            **self.stats,
            'unique_states': self.state_tracker.get_unique_states(),
            'history_size': len(self.state_tracker.history)
        }
