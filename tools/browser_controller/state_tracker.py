"""
UI State Tracker für Browser Controller.

Verfolgt UI-Zustand über Aktionen hinweg:
- URL Changes
- DOM Changes
- Visible Elements
- Modal/Cookie-Banner Detection
- Loop Detection
"""

import time
import logging
from typing import List, Optional, Set, Dict, Any
from dataclasses import dataclass, field
from PIL import Image
from utils.stable_hash import stable_hex_digest, stable_text_digest

log = logging.getLogger("state_tracker")


@dataclass
class UIState:
    """Repräsentiert einen UI-Zustand."""

    timestamp: float
    url: str
    dom_hash: str
    visible_elements: List[str] = field(default_factory=list)
    modals_present: bool = False
    cookie_banner: bool = False
    network_idle: bool = True
    screenshot_hash: Optional[str] = None

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'timestamp': self.timestamp,
            'url': self.url,
            'dom_hash': self.dom_hash,
            'visible_elements_count': len(self.visible_elements),
            'modals_present': self.modals_present,
            'cookie_banner': self.cookie_banner,
            'network_idle': self.network_idle
        }


@dataclass
class StateDiff:
    """Unterschied zwischen zwei UI-Zuständen."""

    url_changed: bool
    dom_changed: bool
    new_elements: Set[str]
    removed_elements: Set[str]
    modal_appeared: bool
    modal_disappeared: bool
    cookie_banner_appeared: bool

    def has_significant_change(self) -> bool:
        """Prüft ob signifikante Änderung stattfand."""
        return (
            self.url_changed or
            self.dom_changed or
            len(self.new_elements) > 0 or
            len(self.removed_elements) > 0 or
            self.modal_appeared or
            self.cookie_banner_appeared
        )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'url_changed': self.url_changed,
            'dom_changed': self.dom_changed,
            'new_elements': len(self.new_elements),
            'removed_elements': len(self.removed_elements),
            'modal_appeared': self.modal_appeared,
            'modal_disappeared': self.modal_disappeared,
            'cookie_banner_appeared': self.cookie_banner_appeared,
            'has_significant_change': self.has_significant_change()
        }


class UIStateTracker:
    """
    Verfolgt UI-Zustand über Browser-Aktionen hinweg.

    Features:
    - State History
    - Loop Detection (3x gleicher State = Loop)
    - Diff Calculation
    - Cookie Banner Detection
    - Modal Detection
    """

    def __init__(self, max_history: int = 20):
        self.history: List[UIState] = []
        self.current_state: Optional[UIState] = None
        self.max_history = max_history

    def observe(self,
                url: str,
                dom_content: str,
                visible_elements: List[str],
                modals_present: bool = False,
                cookie_banner: bool = False,
                network_idle: bool = True,
                screenshot: Optional[Image.Image] = None) -> UIState:
        """
        Beobachtet aktuellen UI-Zustand.

        Args:
            url: Aktuelle URL
            dom_content: DOM HTML Content
            visible_elements: Liste sichtbarer Element-IDs/Selectors
            modals_present: Sind Modals/Dialoge offen?
            cookie_banner: Ist Cookie-Banner sichtbar?
            network_idle: Sind alle Network-Requests abgeschlossen?
            screenshot: Optional Screenshot für Hash

        Returns:
            UIState Objekt
        """
        # DOM Hash berechnen
        dom_hash = stable_text_digest(dom_content, hex_chars=16)

        # Screenshot Hash (optional)
        screenshot_hash = None
        if screenshot:
            screenshot_hash = stable_hex_digest(screenshot.tobytes(), hex_chars=16)

        # State erstellen
        state = UIState(
            timestamp=time.time(),
            url=url,
            dom_hash=dom_hash,
            visible_elements=visible_elements,
            modals_present=modals_present,
            cookie_banner=cookie_banner,
            network_idle=network_idle,
            screenshot_hash=screenshot_hash
        )

        # History aktualisieren
        self.history.append(state)
        if len(self.history) > self.max_history:
            self.history.pop(0)

        self.current_state = state

        log.debug(f"State observed: URL={url[:50]}, DOM={dom_hash}, Elements={len(visible_elements)}")

        return state

    def get_state_diff(self, before: UIState, after: UIState) -> StateDiff:
        """
        Berechnet Unterschied zwischen zwei Zuständen.

        Args:
            before: Zustand vor Aktion
            after: Zustand nach Aktion

        Returns:
            StateDiff mit allen Änderungen
        """
        before_elements = set(before.visible_elements)
        after_elements = set(after.visible_elements)

        return StateDiff(
            url_changed=before.url != after.url,
            dom_changed=before.dom_hash != after.dom_hash,
            new_elements=after_elements - before_elements,
            removed_elements=before_elements - after_elements,
            modal_appeared=not before.modals_present and after.modals_present,
            modal_disappeared=before.modals_present and not after.modals_present,
            cookie_banner_appeared=not before.cookie_banner and after.cookie_banner
        )

    def detect_loop(self, window: int = 3) -> bool:
        """
        Erkennt ob Agent in Loop festhängt.

        Args:
            window: Anzahl letzter States zu prüfen

        Returns:
            True wenn Loop erkannt (3x gleicher DOM-Hash)
        """
        if len(self.history) < window:
            return False

        recent_states = self.history[-window:]
        dom_hashes = [s.dom_hash for s in recent_states]

        # Alle gleich = Loop
        if len(set(dom_hashes)) == 1:
            log.warning(f"🔄 LOOP ERKANNT! {window}x identischer DOM-Hash: {dom_hashes[0]}")
            return True

        return False

    def get_unique_states(self) -> int:
        """Gibt Anzahl unique States in History zurück."""
        return len(set(s.dom_hash for s in self.history))

    def get_last_state(self) -> Optional[UIState]:
        """Gibt letzten State zurück."""
        return self.current_state

    def get_history(self, limit: int = 10) -> List[UIState]:
        """Gibt letzte N States zurück."""
        return self.history[-limit:]

    def clear_history(self):
        """Löscht History (für neuen Task)."""
        self.history.clear()
        self.current_state = None
        log.info("State History gelöscht")
