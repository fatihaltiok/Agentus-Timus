from __future__ import annotations

import sqlite3

import pytest

from orchestration.session_reflection import SessionReflectionLoop


@pytest.mark.asyncio
async def test_get_improvement_suggestions_merges_reflection_and_self_improvement(tmp_path, monkeypatch):
    db_path = tmp_path / "timus_memory.db"
    loop = SessionReflectionLoop(db_path=db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """INSERT INTO improvement_suggestions
               (pattern, occurrences, suggestion, applied, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("pattern-x", 3, "reflection fix", 0, "2026-03-18T10:00:00"),
        )
        conn.commit()

    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: type(
            "_Engine",
            (),
            {
                "get_suggestions": staticmethod(
                    lambda applied=False: [
                        {
                            "id": 7,
                            "type": "routing",
                            "target": "research",
                            "finding": "Routing zu research schwach",
                            "suggestion": "route härten",
                            "confidence": 0.7,
                            "severity": "medium",
                            "applied": False,
                            "created_at": "2026-03-18T11:00:00",
                        }
                    ]
                )
            },
        )(),
    )

    suggestions = await loop.get_improvement_suggestions()

    assert len(suggestions) == 2
    assert {item["source"] for item in suggestions} == {
        "session_reflection",
        "self_improvement_engine",
    }
    assert any(item["id"] == "m12:7" for item in suggestions)
    reflection_item = next(item for item in suggestions if item["source"] == "session_reflection")
    assert reflection_item["candidate_id"] == "m8:1"
    assert reflection_item["raw_category"] == "reflection_pattern"
    assert reflection_item["category"] == "reflection_pattern"
    assert reflection_item["occurrence_count"] == 3
    assert reflection_item["severity"] == "medium"
    assert reflection_item["status"] == "open"

    m12_item = next(item for item in suggestions if item["source"] == "self_improvement_engine")
    assert m12_item["candidate_id"] == "m12:7"
    assert m12_item["category"] == "routing"
    assert m12_item["problem"] == "Routing zu research schwach"
    assert m12_item["proposed_action"] == "route härten"
    assert m12_item["status"] == "open"


@pytest.mark.asyncio
async def test_get_improvement_suggestions_dedupes_cross_source_candidates(tmp_path, monkeypatch):
    db_path = tmp_path / "timus_memory.db"
    loop = SessionReflectionLoop(db_path=db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """INSERT INTO improvement_suggestions
               (pattern, occurrences, suggestion, applied, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("Routing zu research ist schwach", 3, "Routing haerten", 0, "2026-03-18T10:00:00"),
        )
        conn.commit()

    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: type(
            "_Engine",
            (),
            {
                "get_suggestions": staticmethod(
                    lambda applied=False: [
                        {
                            "id": 7,
                            "type": "routing",
                            "target": "research",
                            "finding": "Routing zu research ist schwach",
                            "suggestion": "Routing haerten",
                            "confidence": 0.8,
                            "severity": "high",
                            "applied": False,
                            "created_at": "2026-03-18T11:00:00",
                        }
                    ]
                )
            },
        )(),
    )

    suggestions = await loop.get_improvement_suggestions()

    assert len(suggestions) == 1
    candidate = suggestions[0]
    assert candidate["source_count"] == 2
    assert candidate["merged_sources"] == ["self_improvement_engine", "session_reflection"]
    assert candidate["category"] == "routing"
    assert candidate["signal_class"] == "structural_issue"


@pytest.mark.asyncio
async def test_get_improvement_suggestions_includes_runtime_incident_candidates(tmp_path, monkeypatch):
    db_path = tmp_path / "timus_memory.db"
    loop = SessionReflectionLoop(db_path=db_path)

    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: type("_Engine", (), {"get_suggestions": staticmethod(lambda applied=False: [])})(),
    )
    monkeypatch.setattr(
        "orchestration.task_queue.get_queue",
        lambda: type(
            "_Queue",
            (),
            {
                "list_self_healing_incidents": staticmethod(
                    lambda statuses=None, limit=20: [
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
                    ]
                )
            },
        )(),
    )

    suggestions = await loop.get_improvement_suggestions()

    assert len(suggestions) == 1
    candidate = suggestions[0]
    assert candidate["source"] == "self_healing_incident"
    assert candidate["category"] == "runtime"
    assert candidate["candidate_id"] == "incident:m3_mcp_health_unavailable"
    assert candidate["priority_score"] > 0.0


@pytest.mark.asyncio
async def test_get_improvement_suggestions_includes_observation_candidates(tmp_path, monkeypatch):
    db_path = tmp_path / "timus_memory.db"
    loop = SessionReflectionLoop(db_path=db_path)

    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: type("_Engine", (), {"get_suggestions": staticmethod(lambda applied=False: [])})(),
    )
    monkeypatch.setattr(
        "orchestration.task_queue.get_queue",
        lambda: type(
            "_Queue",
            (),
            {"list_self_healing_incidents": staticmethod(lambda statuses=None, limit=20: [])},
        )(),
    )
    monkeypatch.setattr(
        loop,
        "_get_recent_observation_events",
        lambda limit=120: [
            {
                "id": "evt-1",
                "observed_at": "2026-04-11T12:00:00",
                "event_type": "context_misread_suspected",
                "payload": {
                    "dominant_turn_type": "followup",
                    "risk_reasons": ["topic_leak", "weak_followup_anchor"],
                },
            }
        ],
    )

    suggestions = await loop.get_improvement_suggestions()

    assert len(suggestions) == 1
    candidate = suggestions[0]
    assert candidate["source"] == "autonomy_observation"
    assert candidate["category"] == "context"
    assert candidate["candidate_id"] == "obs:evt-1"
    assert candidate["priority_score"] > 0.0
