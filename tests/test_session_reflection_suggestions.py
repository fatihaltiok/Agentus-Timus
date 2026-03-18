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
