"""Research Contract v2 fuer evidenzbasierte Recherche.

Diese Strukturen bilden die allgemeine Research-Engine fuer alle Recherchearten:
- Frage / Profil
- Quellenklassifikation
- Claim -> Evidence -> Verdict
- offene Unsicherheiten

Die Logik in diesem Modul ist bewusst moeglichst rein und deterministisch,
damit sie mit Hypothesis, CrossHair und Lean abgesichert werden kann.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


class ResearchProfile(str, Enum):
    FACT_CHECK = "fact_check"
    NEWS = "news"
    SCIENTIFIC = "scientific"
    VENDOR_COMPARISON = "vendor_comparison"
    MARKET_INTELLIGENCE = "market_intelligence"
    POLICY_REGULATION = "policy_regulation"
    COMPETITIVE_LANDSCAPE = "competitive_landscape"


class SourceType(str, Enum):
    OFFICIAL = "official"
    PAPER = "paper"
    BENCHMARK = "benchmark"
    REGULATOR = "regulator"
    FILING = "filing"
    REPOSITORY = "repository"
    PRESS = "press"
    ANALYSIS = "analysis"
    VENDOR = "vendor"
    YOUTUBE = "youtube"
    FORUM = "forum"
    SOCIAL = "social"
    UNKNOWN = "unknown"


class SourceTier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class BiasRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class TimeSensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ClaimVerdict(str, Enum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    MIXED_EVIDENCE = "mixed_evidence"
    VENDOR_CLAIM_ONLY = "vendor_claim_only"
    CONTESTED = "contested"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceStance(str, Enum):
    SUPPORTS = "supports"
    WEAKENS = "weakens"
    NEUTRAL = "neutral"
    CONTRADICTS = "contradicts"


@dataclass
class ResearchQuestion:
    question_id: str
    text: str
    profile: ResearchProfile
    subquestions: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SourceRecord:
    source_id: str
    url: str
    title: str
    source_type: SourceType
    tier: SourceTier
    bias_risk: BiasRisk = BiasRisk.UNKNOWN
    time_sensitivity: TimeSensitivity = TimeSensitivity.MEDIUM
    is_primary: bool = False
    is_official: bool = False
    has_transcript: bool = False
    has_methodology: bool = False
    published_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceRecord:
    evidence_id: str
    claim_id: str
    source_id: str
    stance: EvidenceStance
    excerpt: str = ""
    timestamp: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimRecord:
    claim_id: str
    question_id: str
    domain: str
    subject: str
    claim_text: str
    claim_type: str = "descriptive"
    time_scope: str = ""
    verdict: ClaimVerdict = ClaimVerdict.INSUFFICIENT_EVIDENCE
    confidence: float = 0.0
    supports: List[str] = field(default_factory=list)
    contradicts: List[str] = field(default_factory=list)
    notes: str = ""
    unknowns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["verdict"] = self.verdict.value
        return data


@dataclass
class ResearchContract:
    question: ResearchQuestion
    claims: List[ClaimRecord] = field(default_factory=list)
    sources: List[SourceRecord] = field(default_factory=list)
    evidences: List[EvidenceRecord] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    summary: str = ""
    confidence_overall: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question.to_dict(),
            "claims": [claim.to_dict() for claim in self.claims],
            "sources": [source.to_dict() for source in self.sources],
            "evidences": [evidence.to_dict() for evidence in self.evidences],
            "open_questions": list(self.open_questions),
            "summary": self.summary,
            "confidence_overall": self.confidence_overall,
        }


@dataclass(frozen=True)
class ResearchProfilePolicy:
    min_high_quality_independent_for_confirmed: int
    require_primary_for_confirmed: bool = False
    require_authoritative_for_confirmed: bool = False
    require_benchmark_or_methodology_for_confirmed: bool = False
    allow_youtube_for_confirmed: bool = True


_VENDOR_DOMAINS = (
    "openai.com",
    "anthropic.com",
    "deepseek.com",
    "qwen.ai",
    "qwenlm.github.io",
    "minimax.io",
    "z.ai",
    "moonshot.cn",
)


def choose_research_profile(query: str, metadata: Optional[Dict[str, Any]] = None) -> ResearchProfile:
    text = f"{query} {(metadata or {}).get('hint', '')}".lower()
    if any(token in text for token in (
        "gesetz", "gesetze", "verordnung", "regulation", "policy",
        "court", "behörde", "behoerde", "regulierung", "compliance", "gericht",
    )):
        return ResearchProfile.POLICY_REGULATION
    if any(token in text for token in ("paper", "studie", "arxiv", "wissenschaft", "scientific")):
        return ResearchProfile.SCIENTIFIC
    if any(token in text for token in ("breaking", "news", "heute", "latest", "aktuell")):
        return ResearchProfile.NEWS
    if any(token in text for token in ("benchmark", "vergleich", "versus", "vs", "vendor", "modellvergleich")):
        return ResearchProfile.VENDOR_COMPARISON
    if any(token in text for token in ("markt", "market", "adoption", "pricing", "share")):
        return ResearchProfile.MARKET_INTELLIGENCE
    if any(token in text for token in ("competitor", "wettbewerb", "landscape")):
        return ResearchProfile.COMPETITIVE_LANDSCAPE
    return ResearchProfile.FACT_CHECK


def infer_source_type(url: str, declared_type: str = "", metadata: Optional[Dict[str, Any]] = None) -> SourceType:
    declared = (declared_type or "").strip().lower()
    if declared == "youtube":
        return SourceType.YOUTUBE
    if declared == "arxiv":
        return SourceType.PAPER
    if declared == "github":
        return SourceType.REPOSITORY
    if declared == "huggingface":
        return SourceType.REPOSITORY
    if declared == "edison":
        return SourceType.ANALYSIS

    domain = urlparse(url).netloc.lower()
    meta = metadata or {}
    if "youtube.com" in domain or "youtu.be" in domain:
        return SourceType.YOUTUBE
    if "arxiv.org" in domain:
        return SourceType.PAPER
    if "github.com" in domain or "huggingface.co" in domain:
        return SourceType.REPOSITORY
    if domain.endswith(".gov") or domain.endswith(".eu"):
        return SourceType.REGULATOR
    if any(vendor_domain in domain for vendor_domain in _VENDOR_DOMAINS):
        return SourceType.VENDOR
    if bool(meta.get("is_official")):
        return SourceType.OFFICIAL
    if domain.endswith(".edu"):
        return SourceType.PAPER
    return SourceType.UNKNOWN


def classify_source_tier(
    source_type: SourceType,
    *,
    is_official: bool = False,
    has_transcript: bool = False,
    has_methodology: bool = False,
) -> SourceTier:
    if source_type in {SourceType.OFFICIAL, SourceType.REGULATOR, SourceType.FILING}:
        return SourceTier.A
    if source_type in {SourceType.PAPER, SourceType.BENCHMARK, SourceType.REPOSITORY}:
        return SourceTier.A if has_methodology else SourceTier.B
    if source_type == SourceType.YOUTUBE:
        if is_official and has_transcript:
            return SourceTier.A
        if has_transcript:
            return SourceTier.B
        return SourceTier.D
    if source_type in {SourceType.PRESS, SourceType.ANALYSIS}:
        return SourceTier.B if has_methodology else SourceTier.C
    if source_type == SourceType.VENDOR:
        return SourceTier.A if is_official else SourceTier.C
    if source_type in {SourceType.FORUM, SourceType.SOCIAL, SourceType.UNKNOWN}:
        return SourceTier.D
    return SourceTier.C


def build_source_record_from_legacy(
    source_id: str,
    url: str,
    title: str,
    declared_type: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> SourceRecord:
    meta = metadata or {}
    source_type = infer_source_type(url, declared_type=declared_type, metadata=meta)
    is_official = bool(meta.get("is_official")) or source_type in {SourceType.OFFICIAL, SourceType.REGULATOR}
    has_transcript = bool(meta.get("has_transcript"))
    has_methodology = bool(meta.get("has_methodology")) or source_type in {
        SourceType.PAPER, SourceType.BENCHMARK, SourceType.REPOSITORY,
    }
    tier = classify_source_tier(
        source_type,
        is_official=is_official,
        has_transcript=has_transcript,
        has_methodology=has_methodology,
    )
    return SourceRecord(
        source_id=source_id,
        url=url,
        title=title,
        source_type=source_type,
        tier=tier,
        bias_risk=BiasRisk(meta.get("bias_risk", BiasRisk.UNKNOWN.value)),
        time_sensitivity=TimeSensitivity(meta.get("time_sensitivity", TimeSensitivity.MEDIUM.value)),
        is_primary=bool(meta.get("is_primary")) or source_type in {SourceType.OFFICIAL, SourceType.PAPER, SourceType.BENCHMARK, SourceType.REGULATOR},
        is_official=is_official,
        has_transcript=has_transcript,
        has_methodology=has_methodology,
        published_at=str(meta.get("published_at") or ""),
        metadata=dict(meta),
    )


def infer_domain_from_text(text: str, source_type: SourceType = SourceType.UNKNOWN) -> str:
    combined = f"{text} {source_type.value}".lower()
    if any(token in combined for token in ("code", "coding", "swe", "programming", "repo")):
        return "coding"
    if any(token in combined for token in ("image", "vision", "bild", "visual")):
        return "image"
    if any(token in combined for token in ("video", "multimodal", "vl", "omni")):
        return "video"
    if any(token in combined for token in ("agent", "tool", "computer use", "workflow")):
        return "agentic"
    if any(token in combined for token in ("benchmark", "reasoning", "math", "text")):
        return "text"
    if any(token in combined for token in ("markt", "market", "share", "adoption", "pricing")):
        return "market"
    if any(token in combined for token in ("gesetz", "regulation", "policy", "compliance")):
        return "policy"
    return "general"


def is_youtube_hard_evidence(source: SourceRecord) -> bool:
    if source.source_type != SourceType.YOUTUBE:
        return False
    return source.has_transcript and (source.is_official or source.tier in {SourceTier.A, SourceTier.B})


def get_research_profile_policy(profile: ResearchProfile) -> ResearchProfilePolicy:
    if profile == ResearchProfile.FACT_CHECK:
        return ResearchProfilePolicy(min_high_quality_independent_for_confirmed=2)
    if profile == ResearchProfile.NEWS:
        return ResearchProfilePolicy(
            min_high_quality_independent_for_confirmed=2,
            allow_youtube_for_confirmed=False,
        )
    if profile == ResearchProfile.SCIENTIFIC:
        return ResearchProfilePolicy(
            min_high_quality_independent_for_confirmed=2,
            require_primary_for_confirmed=True,
            require_benchmark_or_methodology_for_confirmed=True,
        )
    if profile == ResearchProfile.VENDOR_COMPARISON:
        return ResearchProfilePolicy(
            min_high_quality_independent_for_confirmed=2,
            require_benchmark_or_methodology_for_confirmed=True,
        )
    if profile == ResearchProfile.MARKET_INTELLIGENCE:
        return ResearchProfilePolicy(min_high_quality_independent_for_confirmed=2)
    if profile == ResearchProfile.POLICY_REGULATION:
        return ResearchProfilePolicy(
            min_high_quality_independent_for_confirmed=1,
            require_primary_for_confirmed=True,
            require_authoritative_for_confirmed=True,
            allow_youtube_for_confirmed=False,
        )
    if profile == ResearchProfile.COMPETITIVE_LANDSCAPE:
        return ResearchProfilePolicy(min_high_quality_independent_for_confirmed=2)
    return ResearchProfilePolicy(min_high_quality_independent_for_confirmed=2)


def compute_claim_verdict(
    profile: ResearchProfile,
    evidence_records: List[EvidenceRecord],
    source_records: List[SourceRecord],
) -> ClaimVerdict:
    policy = get_research_profile_policy(profile)
    source_by_id = {source.source_id: source for source in source_records}
    supporting = [ev for ev in evidence_records if ev.stance == EvidenceStance.SUPPORTS]
    contradicting = [ev for ev in evidence_records if ev.stance == EvidenceStance.CONTRADICTS]

    if not supporting and not contradicting:
        return ClaimVerdict.INSUFFICIENT_EVIDENCE
    if supporting and contradicting:
        return ClaimVerdict.CONTESTED
    if contradicting and not supporting:
        return ClaimVerdict.MIXED_EVIDENCE

    supporting_sources = [source_by_id.get(ev.source_id) for ev in supporting]
    supporting_sources = [src for src in supporting_sources if src is not None]
    if not supporting_sources:
        return ClaimVerdict.INSUFFICIENT_EVIDENCE

    independent_support = [
        src for src in supporting_sources
        if src.source_type != SourceType.VENDOR
    ]
    vendor_support = [
        src for src in supporting_sources
        if src.source_type == SourceType.VENDOR
    ]

    if vendor_support and not independent_support:
        return ClaimVerdict.VENDOR_CLAIM_ONLY

    high_quality_independent = [
        src for src in independent_support if src.tier in {SourceTier.A, SourceTier.B}
    ]
    effective_high_quality = list(high_quality_independent)
    if not policy.allow_youtube_for_confirmed:
        effective_high_quality = [
            src for src in effective_high_quality
            if src.source_type != SourceType.YOUTUBE
        ]

    has_primary_support = any(
        src.is_primary or src.source_type in {SourceType.PAPER, SourceType.BENCHMARK, SourceType.REPOSITORY, SourceType.REGULATOR, SourceType.FILING}
        for src in independent_support
    )
    has_authoritative_support = any(
        src.is_official or src.source_type in {SourceType.OFFICIAL, SourceType.REGULATOR, SourceType.FILING}
        for src in independent_support
    )
    has_methodological_support = any(
        src.has_methodology or src.source_type in {SourceType.BENCHMARK, SourceType.PAPER, SourceType.REPOSITORY}
        for src in independent_support
    )

    meets_confirmed = len(effective_high_quality) >= policy.min_high_quality_independent_for_confirmed
    if policy.require_primary_for_confirmed:
        meets_confirmed = meets_confirmed and has_primary_support
    if policy.require_authoritative_for_confirmed:
        meets_confirmed = meets_confirmed and has_authoritative_support
    if policy.require_benchmark_or_methodology_for_confirmed:
        meets_confirmed = meets_confirmed and has_methodological_support

    if meets_confirmed:
        return ClaimVerdict.CONFIRMED

    if high_quality_independent or vendor_support:
        return ClaimVerdict.LIKELY
    return ClaimVerdict.INSUFFICIENT_EVIDENCE


def summarize_claims(claims: List[ClaimRecord]) -> Dict[str, int]:
    summary = {
        "total": len(claims),
        ClaimVerdict.CONFIRMED.value: 0,
        ClaimVerdict.LIKELY.value: 0,
        ClaimVerdict.MIXED_EVIDENCE.value: 0,
        ClaimVerdict.VENDOR_CLAIM_ONLY.value: 0,
        ClaimVerdict.CONTESTED.value: 0,
        ClaimVerdict.INSUFFICIENT_EVIDENCE.value: 0,
    }
    for claim in claims:
        summary[claim.verdict.value] = summary.get(claim.verdict.value, 0) + 1
    return summary


def sort_claims_for_report(claims: List[ClaimRecord]) -> List[ClaimRecord]:
    priority = {
        ClaimVerdict.CONFIRMED: 5,
        ClaimVerdict.LIKELY: 4,
        ClaimVerdict.MIXED_EVIDENCE: 3,
        ClaimVerdict.CONTESTED: 3,
        ClaimVerdict.VENDOR_CLAIM_ONLY: 2,
        ClaimVerdict.INSUFFICIENT_EVIDENCE: 1,
    }
    return sorted(
        claims,
        key=lambda claim: (
            -priority.get(claim.verdict, 0),
            -max(0.0, min(1.0, float(claim.confidence))),
            claim.domain,
            claim.claim_text,
        ),
    )


def build_domain_scorecards(claims: List[ClaimRecord]) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for claim in claims:
        bucket = buckets.setdefault(
            claim.domain or "general",
            {
                "domain": claim.domain or "general",
                "total": 0,
                "confirmed": 0,
                "likely": 0,
                "mixed": 0,
                "vendor_only": 0,
                "insufficient": 0,
                "avg_confidence": 0.0,
                "_confidence_sum": 0.0,
            },
        )
        bucket["total"] += 1
        bucket["_confidence_sum"] += max(0.0, min(1.0, float(claim.confidence)))
        if claim.verdict == ClaimVerdict.CONFIRMED:
            bucket["confirmed"] += 1
        elif claim.verdict == ClaimVerdict.LIKELY:
            bucket["likely"] += 1
        elif claim.verdict in {ClaimVerdict.MIXED_EVIDENCE, ClaimVerdict.CONTESTED}:
            bucket["mixed"] += 1
        elif claim.verdict == ClaimVerdict.VENDOR_CLAIM_ONLY:
            bucket["vendor_only"] += 1
        else:
            bucket["insufficient"] += 1

    scorecards: List[Dict[str, Any]] = []
    for bucket in buckets.values():
        total = max(1, int(bucket["total"]))
        bucket["avg_confidence"] = round(float(bucket["_confidence_sum"]) / total, 2)
        bucket.pop("_confidence_sum", None)
        scorecards.append(bucket)

    return sorted(scorecards, key=lambda item: (-int(item["total"]), str(item["domain"])))


def aggregate_overall_confidence(claims: List[ClaimRecord]) -> float:
    if not claims:
        return 0.0
    total = 0.0
    for claim in claims:
        total += max(0.0, min(1.0, float(claim.confidence)))
    return round(total / len(claims), 4)


def initial_research_contract(question_text: str, metadata: Optional[Dict[str, Any]] = None) -> ResearchContract:
    profile = choose_research_profile(question_text, metadata=metadata)
    question = ResearchQuestion(
        question_id="rq-1",
        text=question_text,
        profile=profile,
    )
    return ResearchContract(question=question)
