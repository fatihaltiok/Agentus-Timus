from types import SimpleNamespace

from orchestration.preference_instruction_memory import (
    _preference_memory_key,
    capture_preference_memory,
    derive_captured_preference,
    select_stored_preference_memory,
    select_stored_preference_memory_with_summary,
)


class _FakePersistent:
    def __init__(self, items=None):
        self._items = list(items or [])

    def get_memory_items(self, category):
        if category == "preference_memory":
            return list(self._items)
        return []


class _FakeMemoryManager:
    def __init__(self, items=None):
        self.persistent = _FakePersistent(items)
        self.stored = []

    def store_with_embedding(self, item):
        self.stored.append(item)
        return True


def test_derive_captured_preference_distinguishes_global_topic_and_session():
    global_pref = derive_captured_preference(
        effective_query="antworte kurz und praezise",
        session_id="canvas_pref",
        updated_state={},
        dominant_turn_type="preference_update",
        response_mode="acknowledge_and_store",
    )
    topic_pref = derive_captured_preference(
        effective_query="bei news bitte zuerst agenturquellen",
        session_id="canvas_pref",
        updated_state={"active_topic": "weltlage"},
        dominant_turn_type="preference_update",
        response_mode="acknowledge_and_store",
    )
    session_pref = derive_captured_preference(
        effective_query="fuer diesen vergleich nur deutschland betrachten",
        session_id="canvas_pref",
        updated_state={"active_topic": "zug vs auto"},
        dominant_turn_type="behavior_instruction",
        response_mode="acknowledge_and_store",
    )

    assert global_pref and global_pref.scope == "global"
    assert global_pref.stability < 0.85
    assert topic_pref and topic_pref.scope == "topic"
    assert topic_pref.topic_anchor == "news"
    assert session_pref and session_pref.scope == "session"


def test_capture_preference_memory_increments_evidence_count():
    baseline = derive_captured_preference(
        effective_query="bei news bitte zuerst agenturquellen",
        session_id="canvas_pref",
        updated_state={"active_topic": "news"},
        dominant_turn_type="preference_update",
        response_mode="acknowledge_and_store",
    )
    assert baseline is not None
    existing = SimpleNamespace(
        key=_preference_memory_key(baseline),
        value={
            "scope": "topic",
            "instruction": "bei news bitte zuerst agenturquellen",
            "normalized_instruction": "bei news bitte zuerst agenturquellen",
            "topic_anchor": "news",
            "session_id": "canvas_pref",
            "evidence_count": 1,
            "stability": 0.82,
        },
    )
    manager = _FakeMemoryManager([existing])

    # Ensure the generated key matches the existing fake key by using the same stable inputs.
    captured = capture_preference_memory(
        effective_query="bei news bitte zuerst agenturquellen",
        session_id="canvas_pref",
        updated_state={"active_topic": "news"},
        dominant_turn_type="preference_update",
        response_mode="acknowledge_and_store",
        memory_manager=manager,
        updated_at="2026-04-07T15:00:00Z",
    )

    assert captured
    assert captured["scope"] == "topic"
    assert captured["evidence_count"] == 2
    assert manager.stored
    stored_value = manager.stored[0].value
    assert stored_value["scope"] == "topic"
    assert stored_value["instruction"] == "bei news bitte zuerst agenturquellen"
    assert stored_value["evidence_count"] == 2


def test_select_stored_preference_memory_filters_by_scope_and_stability():
    items = [
        SimpleNamespace(
            key="global::1",
            value={
                "scope": "global",
                "instruction": "antworte kurz und praezise",
                "topic_anchor": "",
                "session_id": "canvas_x",
                "stability": 0.9,
                "evidence_count": 1,
            },
        ),
        SimpleNamespace(
            key="topic::1",
            value={
                "scope": "topic",
                "instruction": "bei news bitte zuerst agenturquellen",
                "topic_anchor": "news",
                "session_id": "canvas_x",
                "stability": 0.82,
                "evidence_count": 1,
            },
        ),
        SimpleNamespace(
            key="session::1",
            value={
                "scope": "session",
                "instruction": "fuer diesen vergleich nur deutschland betrachten",
                "topic_anchor": "",
                "session_id": "canvas_pref",
                "stability": 0.68,
                "evidence_count": 1,
            },
        ),
        SimpleNamespace(
            key="global::weak",
            value={
                "scope": "global",
                "instruction": "sei nett",
                "topic_anchor": "",
                "session_id": "canvas_x",
                "stability": 0.4,
                "evidence_count": 1,
            },
        ),
    ]
    manager = _FakeMemoryManager(items)

    selected = select_stored_preference_memory(
        effective_query="so aber mit live-news",
        conversation_state={
            "session_id": "canvas_pref",
            "active_topic": "news",
            "active_goal": "aktuelle news",
        },
        turn_type="followup",
        memory_manager=manager,
        limit=3,
    )

    assert any(item.startswith("stored_preference:topic[news]") for item in selected)
    assert any(item.startswith("stored_preference:global") for item in selected)
    assert any(item.startswith("stored_preference:session") for item in selected)
    assert all("sei nett" not in item for item in selected)


def test_select_stored_preference_memory_ignores_weak_global_until_repeated():
    manager = _FakeMemoryManager(
        [
            SimpleNamespace(
                key="global::style",
                value={
                    "scope": "global",
                    "instruction": "antworte kurz und praezise",
                    "topic_anchor": "",
                    "session_id": "canvas_pref",
                    "stability": 0.78,
                    "explicit_global": False,
                    "preference_family": "response_style",
                    "evidence_count": 1,
                    "updated_at": "2026-04-07T15:00:00Z",
                },
            )
        ]
    )

    selection = select_stored_preference_memory_with_summary(
        effective_query="wie ist der stand",
        conversation_state={"session_id": "canvas_pref"},
        turn_type="followup",
        memory_manager=manager,
        limit=2,
    )

    assert selection.selected == ()
    assert selection.ignored_low_stability
    assert selection.ignored_low_stability[0]["reason"] == "global_requires_repeat_or_explicit"


def test_select_stored_preference_memory_filters_cross_domain_goal_leak_on_followup():
    manager = _FakeMemoryManager(
        [
            SimpleNamespace(
                key="global::twilio_goal",
                value={
                    "scope": "global",
                    "instruction": "dass du mir ueber twillo und api Zugang mit mir telefonieren sollst",
                    "topic_anchor": "",
                    "session_id": "canvas_pref",
                    "stability": 0.96,
                    "explicit_global": True,
                    "preference_family": "instruction:twilio01",
                    "evidence_count": 3,
                    "updated_at": "2026-04-20T08:59:21Z",
                },
            ),
            SimpleNamespace(
                key="global::style",
                value={
                    "scope": "global",
                    "instruction": "antworte kurz und praezise",
                    "topic_anchor": "",
                    "session_id": "canvas_pref",
                    "stability": 0.9,
                    "explicit_global": True,
                    "preference_family": "response_style",
                    "evidence_count": 2,
                    "updated_at": "2026-04-20T08:59:21Z",
                },
            ),
        ]
    )

    selection = select_stored_preference_memory_with_summary(
        effective_query="Informationen ueber Kanada wie kann ich dort arbeiten",
        conversation_state={
            "session_id": "canvas_pref",
            "active_topic": "Kanada",
            "active_goal": "in Kanada Fuss fassen",
        },
        turn_type="followup",
        memory_manager=manager,
        limit=2,
    )

    assert any("antworte kurz und praezise" in item for item in selection.selected)
    assert all("twillo" not in item.lower() for item in selection.selected)
    assert any(item["reason"] == "preference_domain_mismatch" for item in selection.ignored_low_stability)


def test_select_stored_preference_memory_resolves_conflict_by_narrower_scope():
    manager = _FakeMemoryManager(
        [
            SimpleNamespace(
                key="global::style",
                value={
                    "scope": "global",
                    "instruction": "antworte kurz und praezise",
                    "topic_anchor": "",
                    "session_id": "canvas_pref",
                    "stability": 0.95,
                    "explicit_global": True,
                    "preference_family": "response_style",
                    "evidence_count": 2,
                    "updated_at": "2026-04-07T15:00:00Z",
                },
            ),
            SimpleNamespace(
                key="session::style",
                value={
                    "scope": "session",
                    "instruction": "fuer diesen chat antworte ausfuehrlich",
                    "topic_anchor": "",
                    "session_id": "canvas_pref",
                    "stability": 0.7,
                    "explicit_global": False,
                    "preference_family": "response_style",
                    "evidence_count": 1,
                    "updated_at": "2026-04-07T15:05:00Z",
                },
            ),
        ]
    )

    selection = select_stored_preference_memory_with_summary(
        effective_query="erklaere mir das",
        conversation_state={"session_id": "canvas_pref"},
        turn_type="followup",
        memory_manager=manager,
        limit=2,
    )

    assert selection.selected
    assert selection.selected[0].startswith("stored_preference:session")
    assert selection.conflicts_resolved
    assert selection.conflicts_resolved[0]["reason"] == "narrower_scope_wins"
