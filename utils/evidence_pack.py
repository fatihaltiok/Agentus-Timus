# utils/evidence_pack.py
"""
Evidence Pack Schema — einheitliches Format fuer Behauptung → Quelle.
Wird von fact_corroborator und decision_verifier genutzt.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime


@dataclass
class EvidenceItem:
    """Ein einzelner Beleg fuer oder gegen eine Behauptung."""
    claim: str
    source_url: str
    snippet: str
    confidence: float  # 0.0 - 1.0
    stance: str = "supports"  # "supports", "contradicts", "neutral"
    source_title: str = ""
    retrieved_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidencePack:
    """Sammlung von Belegen fuer einen Task/eine Antwort."""
    items: List[EvidenceItem] = field(default_factory=list)
    overall_confidence: float = 0.0
    task_id: str = ""

    def add(self, item: EvidenceItem):
        self.items.append(item)
        self._recalculate_confidence()

    def _recalculate_confidence(self):
        if self.items:
            self.overall_confidence = sum(i.confidence for i in self.items) / len(self.items)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "overall_confidence": round(self.overall_confidence, 3),
            "evidence_count": len(self.items),
            "items": [i.to_dict() for i in self.items],
        }

    @classmethod
    def from_fact_verification(cls, fv_result: dict) -> "EvidencePack":
        """Factory: Konvertiert FactVerificationResult-Dict zu EvidencePack."""
        pack = cls()
        fact_text = fv_result.get("fact", "")

        for src in fv_result.get("supporting_sources", []):
            source_info = src.get("source", {})
            pack.add(EvidenceItem(
                claim=fact_text,
                source_url=source_info.get("url", ""),
                snippet=src.get("evidence_quote", src.get("snippet", ""))[:500],
                confidence=src.get("confidence", 0.5),
                stance="supports",
                source_title=source_info.get("title", ""),
            ))

        for src in fv_result.get("contradicting_sources", []):
            source_info = src.get("source", {})
            pack.add(EvidenceItem(
                claim=fact_text,
                source_url=source_info.get("url", ""),
                snippet=src.get("evidence_quote", src.get("snippet", ""))[:500],
                confidence=src.get("confidence", 0.5),
                stance="contradicts",
                source_title=source_info.get("title", ""),
            ))

        return pack
