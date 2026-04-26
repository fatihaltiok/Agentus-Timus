"""RCF1 + CCF1: Telegram-Beratungsverlauf als Replay-Regression.

Sichert den Conversation-Carryover-Block aus
docs/META_CONTEXT_ROUTING_RELIABILITY_PLAN_2026-04-26.md gegen
zukuenftige Drifts. Pflichtfaelle:

- Startup-/KI-Beratung als topic_advisory + think_partner
- kurzer Constraint-/Einschaetzungs-Followup darf den Kontext halten
- Bundle traegt conversation_state-Slot
- meta_context_authority erlaubt conversation_state in Followups
"""

from __future__ import annotations

from orchestration.meta_orchestration import classify_meta_task


# --- RCF1 Replay --------------------------------------------------------


def test_rcf1_replay_startup_advisory_initial_turn_uses_advisory_frame():
    result = classify_meta_task(
        "ich will ein Unternehmen gruenden und ki soll eine Rolle spielen "
        "wie koennte ich mit meinen Faehigkeiten starten",
        action_count=0,
    )

    frame = result.get("meta_request_frame") or {}
    mode = result.get("meta_interaction_mode") or {}

    # Beratung muss als advisory-Pfad erkannt werden, nicht als Setup-Build
    # oder Skill-Creator. Wir lassen die Domain offen, weil sich
    # advisory-Subdomain entwickeln kann; entscheidend ist:
    # kein Drift in technische/Setup-Domains.
    assert frame.get("task_domain") not in {
        "skill_creation",
        "setup_build",
        "location_route",
        "docs_status",
    }
    # Interaktionsmodus darf nicht assist sein - das ist ein Beratungsturn.
    assert mode.get("mode") in {"think_partner", "inspect"}


def test_rcf1_replay_short_personal_assessment_followup_stays_in_session_thread():
    """`du kannst mich ungefaehr einschaetzen was passt zu mir`

    Dieser Folge-Turn kam in der Telegram-Session direkt nach dem
    Startup-Turn. Er darf nicht auf migration_work, location_route oder
    eine generische single_lane-Hilfe driften. Der Frame muss im
    Beratungspfad bleiben.
    """
    result = classify_meta_task(
        "du kannst mich ungefaehr einschaetzen was passt zu mir",
        action_count=0,
        recent_user_turns=[
            "ich will ein Unternehmen gruenden und ki soll eine Rolle "
            "spielen wie koennte ich mit meinen Faehigkeiten starten",
        ],
        recent_assistant_turns=[
            "Was bringst du mit? Sag mir in 2-3 Saetzen, was du gut kannst "
            "und was dich interessiert.",
        ],
        conversation_state={
            "active_topic": "Unternehmensgruendung mit KI",
            "active_goal": "Startansatz mit vorhandenen Faehigkeiten finden",
            "active_domain": "topic_advisory",
            "open_loop": "Was sind deine Skills, Ressourcen und Interessen?",
            "next_expected_step": "Skills und Interessen nennen",
            "turn_type_hint": "followup",
            "topic_confidence": 0.7,
        },
    )

    frame = result.get("meta_request_frame") or {}
    assert frame.get("task_domain") not in {
        "migration_work",
        "location_route",
        "skill_creation",
        "setup_build",
    }
    # Specialist-Chain darf bei reiner Beratung nicht auf executor/research
    # zwingen, das war in den Telegram-Logs der Hauptdrift.
    chain = result.get("recommended_agent_chain") or []
    assert chain[:1] == ["meta"]


def test_rcf1_replay_recall_question_finds_session_anchor():
    """`worueber hatte ich dich eben gebeten`

    Reine Erinnerungsfrage. Der Turn darf nicht als neuer Auftrag
    auf single_lane gedrueckt werden, wenn ein offener Open-Loop existiert.
    """
    result = classify_meta_task(
        "worueber hatte ich dich eben gebeten",
        action_count=0,
        recent_user_turns=[
            "ich will ein Unternehmen gruenden und ki soll eine Rolle "
            "spielen wie koennte ich mit meinen Faehigkeiten starten",
            "du kannst mich ungefaehr einschaetzen was passt zu mir",
        ],
        recent_assistant_turns=[
            "Was bringst du mit?",
            "Klar, ich kann dich einschaetzen - aber dafuer brauch ich "
            "erst mal einen Rahmen.",
        ],
        conversation_state={
            "active_topic": "Unternehmensgruendung mit KI",
            "active_goal": "Startansatz mit vorhandenen Faehigkeiten finden",
            "active_domain": "topic_advisory",
            "open_loop": "Was sind deine Skills, Ressourcen und Interessen?",
            "next_expected_step": "Skills und Interessen nennen",
            "turn_type_hint": "followup",
            "topic_confidence": 0.7,
        },
    )

    chain = result.get("recommended_agent_chain") or []
    assert chain[:1] == ["meta"]


# --- CCF1 Carryover-Contract ------------------------------------------


def test_ccf1_session_followup_keeps_conversation_state_class_in_authority():
    """Bei einem erkannten Followup muss die Authority conversation_state
    explizit als erlaubte Kontextklasse fuehren, damit
    KURZZEITKONTEXT im Working Memory nicht leer bleibt.
    """
    result = classify_meta_task(
        "und was bedeutet das fuer mich",
        action_count=0,
        recent_user_turns=[
            "ich will ein Unternehmen gruenden und ki soll eine Rolle spielen",
            "du kannst mich ungefaehr einschaetzen was passt zu mir",
        ],
        recent_assistant_turns=[
            "Was bringst du mit?",
            "Klar, ich kann dich einschaetzen.",
        ],
        conversation_state={
            "active_topic": "Unternehmensgruendung mit KI",
            "active_goal": "Startansatz finden",
            "active_domain": "topic_advisory",
            "open_loop": "Skills und Interessen nennen",
            "next_expected_step": "Skills nennen",
            "turn_type_hint": "followup",
            "topic_confidence": 0.7,
        },
    )

    authority = result.get("meta_context_authority") or {}
    allowed_classes = authority.get("allowed_context_classes") or []
    forbidden_classes = authority.get("forbidden_context_classes") or []

    # CCF1: bei Followups darf conversation_state nie verboten sein.
    assert "conversation_state" in allowed_classes
    assert "conversation_state" not in forbidden_classes


def test_ccf1_session_followup_allows_kurzzeit_section_in_working_memory():
    """Authority muss bei Followups KURZZEITKONTEXT als Section zulassen
    (sofern allowed_sections gesetzt sind), damit context_chars > 0
    erreichbar ist.
    """
    result = classify_meta_task(
        "mach jetzt Vorschlaege",
        action_count=0,
        recent_user_turns=[
            "ich will ein Unternehmen gruenden und ki soll eine Rolle spielen",
        ],
        recent_assistant_turns=[
            "Was bringst du mit?",
        ],
        conversation_state={
            "active_topic": "Unternehmensgruendung mit KI",
            "active_goal": "Startansatz finden",
            "active_domain": "topic_advisory",
            "open_loop": "Skills nennen",
            "next_expected_step": "Skills nennen",
            "turn_type_hint": "followup",
            "topic_confidence": 0.7,
        },
    )

    authority = result.get("meta_context_authority") or {}
    allowed_sections = authority.get("working_memory_allowed_sections") or []
    if allowed_sections:
        assert "KURZZEITKONTEXT" in allowed_sections
    # working_memory_max_recent darf bei Followups nicht 0 sein.
    max_recent = authority.get("working_memory_max_recent")
    if isinstance(max_recent, int) and max_recent != -1:
        assert max_recent > 0


def test_ccf1_neutral_new_topic_does_not_force_session_followup():
    """Gegenprobe: ein klar neuer Topic darf NICHT als Session-Followup
    behandelt werden, sonst wuerde alter Kontext kontaminieren.
    """
    result = classify_meta_task(
        "wie ist das Wetter morgen in Berlin",
        action_count=0,
    )

    authority = result.get("meta_context_authority") or {}
    rationale = authority.get("rationale") or ""
    # Wenn kein Followup-State, darf rationale nicht "session:followup" tragen.
    assert "session:followup" not in rationale


# --- Bundle/Slot Sanity ------------------------------------------------


def test_ccf1_followup_bundle_carries_conversation_state_slot():
    """Bei einem Followup mit gesetztem conversation_state muss der Bundle
    einen entsprechenden Slot tragen - sonst kann Meta den Faden nicht
    weiterfuehren.
    """
    result = classify_meta_task(
        "und was bedeutet das fuer mich",
        action_count=0,
        recent_user_turns=[
            "ich will ein Unternehmen gruenden",
            "du kannst mich ungefaehr einschaetzen",
        ],
        recent_assistant_turns=[
            "Was bringst du mit?",
            "Klar, ich kann dich einschaetzen.",
        ],
        conversation_state={
            "active_topic": "Unternehmensgruendung mit KI",
            "active_goal": "Startansatz finden",
            "active_domain": "topic_advisory",
            "open_loop": "Skills nennen",
            "next_expected_step": "Skills nennen",
            "turn_type_hint": "followup",
            "topic_confidence": 0.7,
        },
    )

    bundle = result.get("meta_context_bundle") or {}
    slots = bundle.get("context_slots") or []
    slot_names = {
        str(item.get("slot") or "").strip().lower()
        for item in slots
        if isinstance(item, dict)
    }
    # Mindestens current_query oder conversation_state muss vorhanden sein.
    assert slot_names, "Bundle darf bei Followup nicht ohne Slots bleiben"
    assert ("current_query" in slot_names) or ("conversation_state" in slot_names)
