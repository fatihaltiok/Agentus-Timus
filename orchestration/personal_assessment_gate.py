"""CCF4: Personal Assessment Gate.

Erkennt explizite Personalisierungsanfragen wie ``du kennst mich``,
``du kannst mich einschaetzen``, ``was passt zu mir``,
``mit meinen Faehigkeiten``. Bei solchen Queries darf
``preference_profile`` als bounded Evidenzklasse zugelassen werden,
sonst nicht.

Output:

    {
        "is_personal_assessment": bool,
        "trigger_phrase": str,
        "confidence": float,
    }

Wird vom meta_context_authority-Builder konsumiert, um
``preference_profile`` aus den verbotenen Klassen zu entfernen, wenn
der Trigger erkannt ist.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


_PERSONAL_ASSESSMENT_HINTS = (
    "du kennst mich",
    "du kannst mich einschaetzen",
    "du kannst mich einschätzen",
    "du kannst mich ungefaehr einschaetzen",
    "du kannst mich ungefähr einschätzen",
    "kannst du mich einschaetzen",
    "kannst du mich einschätzen",
    "schaetze mich ein",
    "schätze mich ein",
    "schaetz mich ein",
    "schätz mich ein",
    "was passt zu mir",
    "was wuerde zu mir passen",
    "was würde zu mir passen",
    "mit meinen faehigkeiten",
    "mit meinen fähigkeiten",
    "mit meinen skills",
    "auf basis meines profils",
    "anhand meines profils",
    "wenn du mein profil",
    "kennst du mein profil",
    "was weisst du ueber mich",
    "was weißt du über mich",
)

_NORMALIZATION_MAP = (
    ("ü", "ue"),
    ("ö", "oe"),
    ("ä", "ae"),
    ("ß", "ss"),
)


def _normalize(text: Any) -> str:
    lowered = str(text or "").lower().strip()
    for src, target in _NORMALIZATION_MAP:
        lowered = lowered.replace(src, target)
    return lowered


@dataclass(frozen=True)
class PersonalAssessmentGate:
    is_personal_assessment: bool
    trigger_phrase: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def detect_personal_assessment(query: str) -> PersonalAssessmentGate:
    normalized = _normalize(query)
    if not normalized:
        return PersonalAssessmentGate(
            is_personal_assessment=False,
            trigger_phrase="",
            confidence=0.0,
        )
    padded = f" {normalized} "
    for hint in _PERSONAL_ASSESSMENT_HINTS:
        normalized_hint = _normalize(hint)
        if normalized_hint in padded:
            return PersonalAssessmentGate(
                is_personal_assessment=True,
                trigger_phrase=normalized_hint.strip(),
                confidence=0.85,
            )
    return PersonalAssessmentGate(
        is_personal_assessment=False,
        trigger_phrase="",
        confidence=0.0,
    )
