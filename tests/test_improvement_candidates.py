from __future__ import annotations

from orchestration.improvement_candidates import (
    consolidate_improvement_candidates,
    normalize_autonomy_observation_candidate,
    normalize_self_improvement_candidate,
    normalize_self_healing_incident_candidate,
    normalize_session_reflection_candidate,
    sort_improvement_candidates,
)


def test_normalize_self_improvement_candidate_returns_phase_e_shape():
    candidate = normalize_self_improvement_candidate(
        {
            "id": 7,
            "type": "routing",
            "target": "research",
            "finding": "Routing zu research ist schwach.",
            "suggestion": "Routing haerten.",
            "confidence": 0.72,
            "severity": "high",
            "evidence_level": "measured",
            "evidence_basis": "runtime_analytics",
            "applied": False,
            "created_at": "2026-04-11T09:00:00",
        }
    )

    assert candidate["candidate_id"] == "m12:7"
    assert candidate["source"] == "self_improvement_engine"
    assert candidate["category"] == "routing"
    assert candidate["target"] == "research"
    assert candidate["problem"] == "Routing zu research ist schwach."
    assert candidate["proposed_action"] == "Routing haerten."
    assert candidate["severity"] == "high"
    assert candidate["confidence"] == 0.72
    assert candidate["status"] == "open"
    assert candidate["occurrence_count"] == 1


def test_normalize_session_reflection_candidate_derives_priority_from_occurrences():
    candidate = normalize_session_reflection_candidate(
        {
            "id": 3,
            "pattern": "Antworten verlieren Follow-up-Kontext",
            "occurrences": 6,
            "suggestion": "Follow-up-Bindung pruefen.",
            "applied": False,
            "created_at": "2026-04-11T09:00:00",
        }
    )

    assert candidate["candidate_id"] == "m8:3"
    assert candidate["source"] == "session_reflection"
    assert candidate["raw_category"] == "reflection_pattern"
    assert candidate["category"] == "context"
    assert candidate["severity"] == "high"
    assert candidate["confidence"] == 0.93
    assert candidate["occurrence_count"] == 6
    assert candidate["status"] == "open"


def test_sort_improvement_candidates_prefers_severity_then_confidence_then_occurrences():
    sorted_candidates = sort_improvement_candidates(
        [
            {
                "candidate_id": "c-low",
                "severity": "low",
                "confidence": 0.99,
                "occurrence_count": 10,
                "created_at": "2026-04-11T09:00:00",
            },
            {
                "candidate_id": "c-high",
                "severity": "high",
                "confidence": 0.3,
                "occurrence_count": 1,
                "created_at": "2026-04-11T08:00:00",
            },
            {
                "candidate_id": "c-high-better",
                "severity": "high",
                "confidence": 0.8,
                "occurrence_count": 2,
                "created_at": "2026-04-11T10:00:00",
            },
        ]
    )

    assert [item["candidate_id"] for item in sorted_candidates] == [
        "c-high-better",
        "c-high",
        "c-low",
    ]


def test_consolidate_improvement_candidates_dedupes_cross_source_and_prioritizes():
    consolidated = consolidate_improvement_candidates(
        [
            normalize_session_reflection_candidate(
                {
                    "id": 1,
                    "pattern": "Routing zu research ist schwach",
                    "occurrences": 3,
                    "suggestion": "Routing haerten",
                    "created_at": "2026-04-11T09:00:00",
                }
            ),
            normalize_self_improvement_candidate(
                {
                    "id": 7,
                    "type": "routing",
                    "target": "research",
                    "finding": "Routing zu research ist schwach",
                    "suggestion": "Routing haerten",
                    "confidence": 0.8,
                    "severity": "high",
                    "created_at": "2026-04-11T10:00:00",
                }
            ),
        ]
    )

    assert len(consolidated) == 1
    candidate = consolidated[0]
    assert candidate["category"] == "routing"
    assert candidate["source_count"] == 2
    assert candidate["merged_sources"] == [
        "self_improvement_engine",
        "session_reflection",
    ]
    assert candidate["occurrence_count"] == 4
    assert candidate["signal_class"] == "structural_issue"
    assert candidate["priority_score"] > 1.0
    assert "multi_source" in candidate["priority_reasons"]


def test_normalize_self_healing_incident_candidate_maps_runtime_incident():
    candidate = normalize_self_healing_incident_candidate(
        {
            "incident_key": "m3_mcp_health_unavailable",
            "component": "mcp",
            "signal": "health_unavailable",
            "severity": "high",
            "status": "open",
            "title": "MCP Health Endpoint nicht erreichbar",
            "details": {"failure_streak": 4},
            "recovery_action": "MCP Dienst und Health-Check pruefen.",
            "last_seen_at": "2026-04-11T11:00:00",
        }
    )

    assert candidate["candidate_id"] == "incident:m3_mcp_health_unavailable"
    assert candidate["source"] == "self_healing_incident"
    assert candidate["category"] == "runtime"
    assert candidate["target"] == "mcp:health_unavailable"
    assert candidate["problem"] == "MCP Health Endpoint nicht erreichbar"
    assert candidate["proposed_action"] == "MCP Dienst und Health-Check pruefen."
    assert candidate["occurrence_count"] == 4
    assert candidate["evidence_level"] == "incident"
    assert candidate["status"] == "open"


def test_normalize_autonomy_observation_candidate_maps_context_misread_event():
    candidate = normalize_autonomy_observation_candidate(
        {
            "id": "evt-1",
            "observed_at": "2026-04-11T12:00:00",
            "event_type": "context_misread_suspected",
            "payload": {
                "dominant_turn_type": "followup",
                "risk_reasons": ["topic_leak", "weak_followup_anchor"],
            },
        }
    )

    assert candidate is not None
    assert candidate["candidate_id"] == "obs:evt-1"
    assert candidate["source"] == "autonomy_observation"
    assert candidate["category"] == "context"
    assert candidate["target"] == "followup"
    assert "Kontext-Fehlgriff vermutet" in candidate["problem"]
    assert candidate["evidence_level"] == "observation"
    assert candidate["status"] == "open"
