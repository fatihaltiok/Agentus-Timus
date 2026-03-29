from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


_MAX_ITEMS = 8
_MAX_TEXT = 240
_MAX_PATH = 320
_MAX_FUNC = 160
_EVIDENCE_RANKS = {
    "verified": 4,
    "corroborated": 3,
    "observed": 2,
    "hypothesis": 1,
    "unverified": 0,
}


def normalize_evidence_level(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"verified", "belegt", "confirmed"}:
        return "verified"
    if text in {"corroborated", "cross_checked", "cross-checked", "supported"}:
        return "corroborated"
    if text in {"observed", "inspected", "runtime_observed"}:
        return "observed"
    if text in {"hypothesis", "plausible", "likely"}:
        return "hypothesis"
    return "unverified"


def _clamp_unit(value: Any) -> float:
    try:
        parsed = float(value)
    except Exception:
        return 0.0
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def _normalize_text_list(values: Iterable[Any], *, max_items: int = _MAX_ITEMS, max_len: int = _MAX_TEXT) -> Tuple[str, ...]:
    normalized: List[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        safe = text[:max_len]
        if safe not in normalized:
            normalized.append(safe)
        if len(normalized) >= max_items:
            break
    return tuple(normalized)


def _normalize_function_names(values: Iterable[Any]) -> Tuple[str, ...]:
    normalized: List[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        safe = "".join(ch for ch in text[:_MAX_FUNC] if ch.isalnum() or ch in {"_", ".", ":"})
        if not safe:
            continue
        if safe not in normalized:
            normalized.append(safe)
        if len(normalized) >= _MAX_ITEMS:
            break
    return tuple(normalized)


def _normalize_paths(values: Iterable[Any], *, existing_paths: Iterable[str] | None = None) -> Tuple[str, ...]:
    allowed = {
        str(Path(path).resolve())
        for path in (existing_paths or [])
        if str(path or "").strip()
    }
    normalized: List[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        candidate = str(Path(text).resolve()) if text.startswith("/") else text[:_MAX_PATH]
        is_allowed = candidate in allowed if allowed else (candidate.startswith("/") and Path(candidate).exists())
        if not is_allowed:
            continue
        if candidate not in normalized:
            normalized.append(candidate[:_MAX_PATH])
        if len(normalized) >= _MAX_ITEMS:
            break
    return tuple(normalized)


@dataclass(frozen=True)
class DiagnosisRecord:
    source_agent: str
    claim: str
    evidence_level: str
    evidence_refs: Tuple[str, ...]
    confidence: float
    actionability: float
    verified_paths: Tuple[str, ...]
    verified_functions: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


@dataclass(frozen=True)
class DiagnosisResolution:
    lead_diagnosis: DiagnosisRecord | None
    supporting_diagnoses: Tuple[DiagnosisRecord, ...]
    rejected_diagnoses: Tuple[DiagnosisRecord, ...]
    suppressed_claims: Tuple[str, ...]
    conflict_detected: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_diagnosis": None if self.lead_diagnosis is None else self.lead_diagnosis.to_dict(),
            "supporting_diagnoses": [item.to_dict() for item in self.supporting_diagnoses],
            "rejected_diagnoses": [item.to_dict() for item in self.rejected_diagnoses],
            "suppressed_claims": list(self.suppressed_claims),
            "conflict_detected": self.conflict_detected,
        }


@dataclass(frozen=True)
class DeveloperTaskBrief:
    lead_diagnosis: str
    evidence_level: str
    verified_paths: Tuple[str, ...]
    verified_functions: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    supporting_diagnoses: Tuple[str, ...]
    suppressed_claims: Tuple[str, ...]
    constraints: Tuple[str, ...]
    conflict_detected: bool

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


def normalize_diagnosis_record(
    payload: Dict[str, Any] | DiagnosisRecord,
    *,
    existing_paths: Iterable[str] | None = None,
) -> DiagnosisRecord:
    if isinstance(payload, DiagnosisRecord):
        return DiagnosisRecord(
            source_agent=str(payload.source_agent or "").strip().lower() or "unknown",
            claim=str(payload.claim or "").strip()[:_MAX_TEXT],
            evidence_level=normalize_evidence_level(payload.evidence_level),
            evidence_refs=_normalize_text_list(payload.evidence_refs),
            confidence=_clamp_unit(payload.confidence),
            actionability=_clamp_unit(payload.actionability),
            verified_paths=_normalize_paths(payload.verified_paths, existing_paths=existing_paths),
            verified_functions=_normalize_function_names(payload.verified_functions),
        )

    safe = dict(payload or {})
    return DiagnosisRecord(
        source_agent=str(safe.get("source_agent") or "unknown").strip().lower()[:40] or "unknown",
        claim=str(safe.get("claim") or "").strip()[:_MAX_TEXT],
        evidence_level=normalize_evidence_level(safe.get("evidence_level")),
        evidence_refs=_normalize_text_list(safe.get("evidence_refs") or []),
        confidence=_clamp_unit(safe.get("confidence")),
        actionability=_clamp_unit(safe.get("actionability")),
        verified_paths=_normalize_paths(safe.get("verified_paths") or [], existing_paths=existing_paths),
        verified_functions=_normalize_function_names(safe.get("verified_functions") or []),
    )


def build_diagnosis_records(
    raw_records: Sequence[Dict[str, Any] | DiagnosisRecord] | None,
    *,
    existing_paths: Iterable[str] | None = None,
) -> Tuple[DiagnosisRecord, ...]:
    records: List[DiagnosisRecord] = []
    for item in list(raw_records or [])[:16]:
        normalized = normalize_diagnosis_record(item, existing_paths=existing_paths)
        if not normalized.claim:
            continue
        records.append(normalized)
    return tuple(records)


def _evidence_rank(level: str) -> int:
    return int(_EVIDENCE_RANKS.get(normalize_evidence_level(level), 0))


def _record_score(record: DiagnosisRecord, *, index: int = 0) -> Tuple[float, ...]:
    return (
        float(_evidence_rank(record.evidence_level)),
        1.0 if (record.verified_paths or record.verified_functions) else 0.0,
        min(len(record.evidence_refs), _MAX_ITEMS) / 10.0,
        record.actionability,
        record.confidence,
        -float(index),
    )


def select_lead_diagnosis(records: Sequence[DiagnosisRecord]) -> DiagnosisResolution:
    if not records:
        return DiagnosisResolution(
            lead_diagnosis=None,
            supporting_diagnoses=(),
            rejected_diagnoses=(),
            suppressed_claims=(),
            conflict_detected=False,
        )

    ranked = sorted(
        enumerate(records),
        key=lambda item: _record_score(item[1], index=item[0]),
        reverse=True,
    )
    lead = ranked[0][1]
    supporting: List[DiagnosisRecord] = []
    rejected: List[DiagnosisRecord] = []
    suppressed: List[str] = []
    lead_rank = _evidence_rank(lead.evidence_level)

    for _, candidate in ranked[1:]:
        candidate_rank = _evidence_rank(candidate.evidence_level)
        useful = bool(
            candidate_rank > 0
            or candidate.evidence_refs
            or candidate.verified_paths
            or candidate.verified_functions
            or candidate.confidence >= 0.55
        )
        if useful and candidate_rank >= max(1, lead_rank - 2):
            supporting.append(candidate)
        else:
            rejected.append(candidate)
            if candidate.claim:
                suppressed.append(candidate.claim)

    conflict_detected = len(supporting) > 0 and len(
        {
            item.source_agent
            for item in (lead, *supporting)
            if str(item.source_agent or "").strip()
        }
    ) > 1
    return DiagnosisResolution(
        lead_diagnosis=lead,
        supporting_diagnoses=tuple(supporting[:4]),
        rejected_diagnoses=tuple(rejected[:8]),
        suppressed_claims=tuple(suppressed[:8]),
        conflict_detected=conflict_detected,
    )


def compile_developer_task_brief(resolution: DiagnosisResolution) -> DeveloperTaskBrief:
    lead = resolution.lead_diagnosis
    if lead is None:
        return DeveloperTaskBrief(
            lead_diagnosis="",
            evidence_level="unverified",
            verified_paths=(),
            verified_functions=(),
            evidence_refs=(),
            supporting_diagnoses=(),
            suppressed_claims=resolution.suppressed_claims,
            constraints=(
                "nur_verifizierte_dateien_und_funktionen_verwenden",
                "unverifizierte_claims_nicht_als_belegt_behandeln",
            ),
            conflict_detected=False,
        )

    verified_paths = _normalize_paths(
        [*lead.verified_paths, *(path for item in resolution.supporting_diagnoses for path in item.verified_paths)],
        existing_paths=[*lead.verified_paths, *(path for item in resolution.supporting_diagnoses for path in item.verified_paths)],
    )
    verified_functions = _normalize_function_names(
        [*lead.verified_functions, *(name for item in resolution.supporting_diagnoses for name in item.verified_functions)]
    )
    evidence_refs = _normalize_text_list(
        [*lead.evidence_refs, *(ref for item in resolution.supporting_diagnoses for ref in item.evidence_refs)]
    )
    supporting_claims = tuple(item.claim for item in resolution.supporting_diagnoses if item.claim)[:4]

    return DeveloperTaskBrief(
        lead_diagnosis=lead.claim,
        evidence_level=lead.evidence_level,
        verified_paths=verified_paths,
        verified_functions=verified_functions,
        evidence_refs=evidence_refs,
        supporting_diagnoses=supporting_claims,
        suppressed_claims=resolution.suppressed_claims,
        constraints=(
            "nur_verifizierte_dateien_und_funktionen_verwenden",
            "unverifizierte_claims_nicht_als_belegt_behandeln",
        ),
        conflict_detected=bool(resolution.conflict_detected),
    )
