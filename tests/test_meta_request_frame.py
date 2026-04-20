from orchestration.meta_orchestration import classify_meta_task
from orchestration.meta_request_frame import build_meta_request_frame


def test_build_meta_request_frame_recognizes_docs_status_direct_answer():
    frame = build_meta_request_frame(
        effective_query="lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
        dominant_turn_type="new_task",
        response_mode="summarize_state",
        answer_shape="direct_recommendation",
        task_type="single_lane",
        active_topic="Phase F Abschluss",
        open_goal="Naechsten Hauptblock festlegen",
        next_step="Mehrschritt-Planungsblock starten",
        recommended_agent_chain=("meta",),
        active_plan={},
    )

    assert frame.frame_kind == "direct_answer"
    assert frame.task_domain == "docs_status"
    assert frame.execution_mode == "answer_directly"
    assert "skill_creation" in frame.forbidden_memory_domains
    assert frame.delegation_budget == 0


def test_build_meta_request_frame_recognizes_migration_work_from_stateful_followup():
    frame = build_meta_request_frame(
        effective_query="koennte ich da fuss fassen",
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
        answer_shape="resume_action",
        task_type="single_lane",
        active_topic="Auswanderung nach Kanada",
        open_goal="Pruefen ob du in Kanada ein neues Leben aufbauen kannst",
        next_step="Visa- und Arbeitsmarktchancen einschaetzen",
        recommended_agent_chain=("meta", "research"),
        active_plan={},
    )

    assert frame.frame_kind == "stateful_followup"
    assert frame.task_domain == "migration_work"
    assert frame.execution_mode == "plan_and_delegate"
    assert "telephony_setup" in frame.forbidden_memory_domains
    assert "topic_memory" in frame.allowed_context_slots


def test_build_meta_request_frame_recognizes_setup_build_for_twilio_and_inworld():
    frame = build_meta_request_frame(
        effective_query="richte fuer mich eine anruffunktion ueber twilio mit der stimme von inworld ein",
        dominant_turn_type="new_task",
        response_mode="execute",
        answer_shape="action_first",
        task_type="single_lane",
        active_topic="",
        open_goal="",
        next_step="",
        recommended_agent_chain=("meta", "executor"),
        active_plan={},
    )

    assert frame.frame_kind == "new_task"
    assert frame.task_domain == "setup_build"
    assert frame.execution_mode == "plan_and_delegate"


def test_classify_meta_task_exposes_meta_request_frame_for_docs_status():
    result = classify_meta_task(
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
        action_count=2,
        conversation_state={
            "session_id": "canvas_phase_f_closeout",
            "active_topic": "Phase F Abschluss",
            "active_goal": "Naechsten Hauptblock festlegen",
            "open_loop": "Nachfolger von Phase F bestimmen",
            "next_expected_step": "Mehrschritt-Planungsblock starten",
        },
    )

    frame = result["meta_request_frame"]

    assert frame["frame_kind"] == "direct_answer"
    assert frame["task_domain"] == "docs_status"
    assert frame["execution_mode"] == "answer_directly"
    assert frame["delegation_budget"] == 0


def test_classify_meta_task_exposes_meta_request_frame_for_canada_followup():
    result = classify_meta_task(
        "Informationen ueber Kanada wie kann ich dort arbeiten",
        action_count=0,
        conversation_state={
            "session_id": "tg_demo",
            "active_topic": "Kanada",
            "active_goal": "Möglichkeiten in Kanada Fuß zu fassen",
            "open_loop": "",
            "next_expected_step": "",
            "turn_type_hint": "followup",
            "topic_confidence": 0.81,
        },
        recent_user_turns=["suche mir Möglichkeiten in Kanada Fuß zu fassen"],
        recent_assistant_turns=["Kontext geladen. 07:31 Uhr, 0 offene Tasks, Routinen laufen.\n\nWas brauchst du?"],
    )

    frame = result["meta_request_frame"]

    assert frame["frame_kind"] == "stateful_followup"
    assert frame["task_domain"] == "migration_work"
    assert frame["execution_mode"] == "plan_and_delegate"
    assert "skill_creation" in frame["forbidden_memory_domains"]
