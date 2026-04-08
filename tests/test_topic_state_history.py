from orchestration.topic_state_history import (
    parse_historical_topic_recall_hint,
    select_historical_topic_memory,
    update_topic_history,
)


def test_parse_historical_topic_recall_hint_supports_eben():
    hint = parse_historical_topic_recall_hint("kannst du dich an unser gespraech von eben erinnern")

    assert hint.requested is True
    assert hint.time_label == "recent_moment"


def test_parse_historical_topic_recall_hint_does_not_trigger_on_plain_recent_time_reference():
    hint = parse_historical_topic_recall_hint("ich habe dir eben einen link gegeben, hol mehr infos dazu")

    assert hint.requested is False


def test_parse_historical_topic_recall_hint_supports_month_and_year_ranges():
    six_months = parse_historical_topic_recall_hint("was hatten wir vor 6 monaten dazu besprochen")
    one_year = parse_historical_topic_recall_hint("weisst du noch was wir vor einem jahr dazu besprochen hatten")
    eighteen_months = parse_historical_topic_recall_hint("weisst du noch was wir vor 18 monaten zu timus besprochen hatten")
    three_years = parse_historical_topic_recall_hint("weisst du noch was wir vor 3 jahren zur agentenarchitektur besprochen hatten")

    assert six_months.requested is True
    assert six_months.time_label == "specific_month_range"
    assert six_months.min_age_days >= 150.0
    assert one_year.requested is True
    assert one_year.time_label == "year_scale"
    assert one_year.min_age_days >= 300.0
    assert eighteen_months.requested is True
    assert eighteen_months.time_label == "specific_month_range"
    assert eighteen_months.min_age_days >= 400.0
    assert three_years.requested is True
    assert three_years.time_label == "year_scale"
    assert three_years.min_age_days >= 800.0


def test_update_topic_history_and_select_historical_topic_for_yesterday():
    history = update_topic_history(
        [],
        session_id="canvas_hist",
        previous_state=None,
        updated_state={
            "active_topic": "Mars und kuenstliche Strukturen",
            "active_goal": "Einordnung der Mars-Pyramiden-These",
            "open_loop": "weitere wissenschaftliche Quellen suchen",
            "next_expected_step": "weitere wissenschaftliche Quellen suchen",
            "topic_confidence": 0.82,
            "turn_type_hint": "followup",
        },
        topic_transition={},
        updated_at="2026-04-07T11:00:00Z",
    )

    selected, summary = select_historical_topic_memory(
        history,
        session_id="canvas_hist",
        query="greif das thema von gestern nochmal auf",
        now="2026-04-08T09:00:00Z",
    )

    assert selected
    assert summary["time_label"] == "yesterday"
    assert "Mars und kuenstliche Strukturen" in selected[0]


def test_select_historical_topic_memory_can_recall_year_scale_topic():
    history = [
        {
            "topic": "Langzeitplan fuer Timus und seine Agentenarchitektur",
            "goal": "Roadmap fuer Phase D und E sauber ziehen",
            "open_loop": "",
            "next_expected_step": "",
            "status": "closed",
            "first_seen_at": "2025-03-20T10:00:00Z",
            "last_seen_at": "2025-04-01T10:00:00Z",
            "closed_at": "2025-04-01T10:00:00Z",
            "topic_confidence": 0.9,
            "turn_type_hint": "new_task",
        }
    ]

    selected, summary = select_historical_topic_memory(
        history,
        session_id="canvas_hist_year",
        query="weisst du noch was wir vor einem jahr ueber die agentenarchitektur besprochen hatten",
        now="2026-04-08T10:00:00Z",
    )

    assert selected
    assert summary["time_label"] == "year_scale"
    assert "agentenarchitektur" in selected[0].lower()


def test_select_historical_topic_memory_can_recall_multi_year_topic():
    history = [
        {
            "topic": "Langzeitgedaechtnis und Archivregeln",
            "goal": "mehrjaehrige Themen sauber wiederfinden",
            "open_loop": "",
            "next_expected_step": "",
            "status": "closed",
            "first_seen_at": "2022-03-20T10:00:00Z",
            "last_seen_at": "2023-04-01T10:00:00Z",
            "closed_at": "2023-04-01T10:00:00Z",
            "topic_confidence": 0.91,
            "turn_type_hint": "new_task",
        }
    ]

    selected, summary = select_historical_topic_memory(
        history,
        session_id="canvas_hist_multi_year",
        query="weisst du noch was wir vor 3 jahren ueber archivregeln besprochen hatten",
        now="2026-04-08T10:00:00Z",
    )

    assert selected
    assert summary["time_label"] == "year_scale"
    assert "archivregeln" in selected[0].lower()


def test_select_historical_topic_memory_prefers_newer_recent_match_for_recent_moment():
    history = [
        {
            "topic": "Thema alt",
            "goal": "A",
            "open_loop": "",
            "next_expected_step": "",
            "status": "historical",
            "first_seen_at": "2026-04-08T09:00:00Z",
            "last_seen_at": "2026-04-08T10:00:00Z",
            "closed_at": "",
            "topic_confidence": 0.9,
            "turn_type_hint": "followup",
        },
        {
            "topic": "Thema neu",
            "goal": "B",
            "open_loop": "",
            "next_expected_step": "",
            "status": "historical",
            "first_seen_at": "2026-04-08T11:00:00Z",
            "last_seen_at": "2026-04-08T11:50:00Z",
            "closed_at": "",
            "topic_confidence": 0.9,
            "turn_type_hint": "followup",
        },
    ]

    selected, _summary = select_historical_topic_memory(
        history,
        session_id="canvas_recent_order",
        query="weisst du noch was wir eben besprochen hatten",
        now="2026-04-08T12:00:00Z",
        limit=1,
    )

    assert selected
    assert "Thema neu" in selected[0]


def test_select_historical_topic_memory_supports_generic_previous_session_recall_without_topic_terms():
    history = [
        {
            "topic": "Archivregeln bei Timus",
            "goal": "Archivierung planen",
            "open_loop": "",
            "next_expected_step": "",
            "status": "closed",
            "first_seen_at": "2026-04-01T10:00:00Z",
            "last_seen_at": "2026-04-02T10:00:00Z",
            "closed_at": "2026-04-02T10:00:00Z",
            "topic_confidence": 0.91,
            "turn_type_hint": "followup",
        }
    ]

    selected, summary = select_historical_topic_memory(
        history,
        session_id="canvas_previous_session",
        query="weisst du noch was wir letztes mal besprochen hatten",
        now="2026-04-08T10:00:00Z",
        limit=1,
    )

    assert selected
    assert summary["time_label"] == "previous_session"
    assert "Archivregeln bei Timus" in selected[0]
