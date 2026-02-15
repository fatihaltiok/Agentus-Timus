"""
DOM Parser für Browser Controller.

Parst DOM und Accessibility-Tree für präzise Element-Auswahl.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from bs4 import BeautifulSoup, Tag

log = logging.getLogger("dom_parser")


@dataclass
class DOMElement:
    """Repräsentiert ein DOM-Element."""

    tag: str
    id: Optional[str] = None
    classes: List[str] = None
    text: str = ""
    aria_label: Optional[str] = None
    role: Optional[str] = None
    placeholder: Optional[str] = None
    selector: str = ""
    xpath: str = ""
    is_interactive: bool = False
    is_visible: bool = True

    def __post_init__(self):
        if self.classes is None:
            self.classes = []

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'tag': self.tag,
            'id': self.id,
            'classes': self.classes,
            'text': self.text[:50],
            'aria_label': self.aria_label,
            'role': self.role,
            'placeholder': self.placeholder,
            'selector': self.selector,
            'is_interactive': self.is_interactive
        }


class DOMParser:
    """
    Parst DOM für Element-Auswahl.

    Features:
    - Interactive Elements finden (button, input, a, etc.)
    - ARIA-Labels extrahieren
    - CSS Selectors generieren
    - Fuzzy Text-Matching
    """

    INTERACTIVE_TAGS = [
        'button', 'input', 'a', 'select', 'textarea',
        'option', 'label', 'summary', 'details'
    ]

    INTERACTIVE_ROLES = [
        'button', 'link', 'textbox', 'searchbox', 'combobox',
        'checkbox', 'radio', 'menuitem', 'tab', 'switch'
    ]

    def __init__(self):
        self.soup: Optional[BeautifulSoup] = None
        self.elements: List[DOMElement] = []

    def parse(self, html: str) -> List[DOMElement]:
        """
        Parst HTML und extrahiert interaktive Elemente.

        Args:
            html: HTML Content

        Returns:
            Liste von DOMElement Objekten
        """
        self.soup = BeautifulSoup(html, 'html.parser')
        self.elements = []

        # Finde alle interaktiven Elemente
        for tag in self.soup.find_all(True):
            if self._is_interactive(tag):
                element = self._tag_to_element(tag)
                self.elements.append(element)

        log.debug(f"DOM parsed: {len(self.elements)} interactive elements found")
        return self.elements

    def _is_interactive(self, tag: Tag) -> bool:
        """Prüft ob Tag interaktiv ist."""
        # Nach Tag-Name
        if tag.name in self.INTERACTIVE_TAGS:
            return True

        # Nach ARIA-Role
        role = tag.get('role')
        if role in self.INTERACTIVE_ROLES:
            return True

        # Nach Klick-Handlern
        if tag.get('onclick') or tag.get('ng-click'):
            return True

        return False

    def _tag_to_element(self, tag: Tag) -> DOMElement:
        """Konvertiert BS4 Tag zu DOMElement."""
        # Basis-Infos
        tag_name = tag.name
        elem_id = tag.get('id')
        classes = tag.get('class', [])
        text = tag.get_text(strip=True)

        # ARIA-Attributes
        aria_label = tag.get('aria-label')
        role = tag.get('role')
        placeholder = tag.get('placeholder')

        # Selector generieren
        selector = self._generate_selector(tag, elem_id, classes)

        return DOMElement(
            tag=tag_name,
            id=elem_id,
            classes=classes if isinstance(classes, list) else [classes],
            text=text,
            aria_label=aria_label,
            role=role,
            placeholder=placeholder,
            selector=selector,
            is_interactive=True,
            is_visible=True  # TODO: Check computed styles
        )

    def _generate_selector(self, tag: Tag, elem_id: Optional[str], classes: List[str]) -> str:
        """Generiert CSS Selector für Tag."""
        # ID hat höchste Priorität
        if elem_id:
            return f"#{elem_id}"

        # Dann Classes
        if classes and len(classes) > 0:
            class_str = '.'.join(classes) if isinstance(classes, list) else classes
            return f"{tag.name}.{class_str}"

        # Fallback: Tag-Name
        return tag.name

    def find_by_text(self, text: str, fuzzy: bool = True) -> List[DOMElement]:
        """
        Findet Elemente nach Text-Content.

        Args:
            text: Suchtext
            fuzzy: Fuzzy Matching (case-insensitive, partial match)

        Returns:
            Liste passender DOMElements
        """
        matches = []
        search_text = text.lower() if fuzzy else text

        for elem in self.elements:
            # Text Content
            elem_text = elem.text.lower() if fuzzy else elem.text
            if search_text in elem_text:
                matches.append(elem)
                continue

            # ARIA-Label
            if elem.aria_label:
                aria_text = elem.aria_label.lower() if fuzzy else elem.aria_label
                if search_text in aria_text:
                    matches.append(elem)
                    continue

            # Placeholder
            if elem.placeholder:
                ph_text = elem.placeholder.lower() if fuzzy else elem.placeholder
                if search_text in ph_text:
                    matches.append(elem)
                    continue

        log.debug(f"find_by_text('{text}'): {len(matches)} matches")
        return matches

    def find_by_role(self, role: str) -> List[DOMElement]:
        """Findet Elemente nach ARIA-Role."""
        return [e for e in self.elements if e.role == role]

    def find_by_tag(self, tag: str) -> List[DOMElement]:
        """Findet Elemente nach Tag-Name."""
        return [e for e in self.elements if e.tag == tag]

    def find_by_selector(self, selector: str) -> Optional[DOMElement]:
        """Findet Element nach CSS Selector."""
        for elem in self.elements:
            if elem.selector == selector:
                return elem
        return None

    def get_all_interactive(self) -> List[DOMElement]:
        """Gibt alle interaktiven Elemente zurück."""
        return self.elements

    def describe_element(self, elem: DOMElement) -> str:
        """Erstellt menschenlesbare Beschreibung eines Elements."""
        parts = [elem.tag]

        if elem.id:
            parts.append(f"id='{elem.id}'")

        if elem.aria_label:
            parts.append(f"label='{elem.aria_label}'")
        elif elem.text:
            parts.append(f"text='{elem.text[:30]}'")
        elif elem.placeholder:
            parts.append(f"placeholder='{elem.placeholder}'")

        return f"<{' '.join(parts)}>"
