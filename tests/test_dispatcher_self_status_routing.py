import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def test_quick_intent_routes_self_status_to_meta():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("Was hast du fuer Probleme?") == "meta"
    assert main_dispatcher.quick_intent_check("sag du es mir") == "meta"
    assert main_dispatcher.quick_intent_check("und was kannst du dagegen tun") == "meta"
    assert main_dispatcher.quick_intent_check("und was davon machst du zuerst") == "meta"
    assert main_dispatcher.quick_intent_check("Hast du etwas zu korrigieren oder fixen?") == "meta"


def test_quick_intent_routes_colloquial_self_reflection_to_meta():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("ok was stoert dich wie kann ich dir helfen") == "meta"
    assert main_dispatcher.quick_intent_check("bist du anpassungsfaehig") == "meta"
    assert main_dispatcher.quick_intent_check("bist du ein funktionierendes ki system ?") == "meta"


def test_dispatcher_extracts_core_query_from_colloquial_shells():
    import main_dispatcher

    assert main_dispatcher._extract_dispatcher_core_query("hey timus was denkst du wird es morgen regnen") == (
        "wird es morgen regnen"
    )
    assert main_dispatcher._extract_dispatcher_core_query("kannst du mir sagen wie spaet es ist") == (
        "wie spaet es ist"
    )


def test_quick_intent_routes_trivial_colloquial_lookups_to_executor():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("was denkst du wird es morgen regnen") == "executor"
    assert main_dispatcher.quick_intent_check("kannst du mir sagen wie spaet es ist") == "executor"
    assert main_dispatcher.quick_intent_check("weisst du wann heute sonnenuntergang ist") == "executor"
    assert main_dispatcher.quick_intent_check("hi timus wie spaet ist es") == "executor"


def test_quick_intent_routes_greeting_prefixed_substantive_questions_to_meta():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("hi timus wie stehts um die aktuelle weltlage") == "meta"


def test_quick_intent_keeps_colloquial_nontrivial_strategy_question_out_of_executor():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("was meinst du wie koennte ich mein unternehmen skalieren") is None


def test_quick_intent_routes_open_advice_dialogue_to_meta():
    import main_dispatcher

    query = "koennte ich bei siemens anfangen zu arbeiten was denkst du"
    assert main_dispatcher.quick_intent_check(query) == "meta"


def test_quick_intent_routes_personal_strategy_dialogue_to_meta_instead_of_reasoning():
    import main_dispatcher

    query = (
        "ich arbeite bei norma germany bin einrichter an montage automaten "
        "und verstehe software architektur, will aber in 12 monaten raus "
        "und habe kein finanzielles polster"
    )
    assert main_dispatcher.quick_intent_check(query) == "meta"


def test_quick_intent_keeps_real_technical_architecture_review_on_reasoning():
    import main_dispatcher

    query = "Welche Software-Architektur passt fuer diese Python-API mit Postgres, Worker und zwei Services?"
    assert main_dispatcher.quick_intent_check(query) == "reasoning"


def test_quick_intent_routes_meta_feedback_and_reference_followups_to_meta():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("anscheinend verstehst du mich nicht") == "meta"
    assert main_dispatcher.quick_intent_check("du sollst nicht halluzinieren") == "meta"
    assert main_dispatcher.quick_intent_check("was machst du da das ist doch falsch") == "meta"
    assert main_dispatcher.quick_intent_check("dann uebernimm die empfehlung 2") == "meta"
    assert main_dispatcher.quick_intent_check("koenntest du damit arbeiten") == "meta"
    assert main_dispatcher.quick_intent_check("kannst du sie reparieren") == "meta"
    assert main_dispatcher.quick_intent_check("was ist passiert") == "meta"
    assert main_dispatcher.quick_intent_check("was gab es noch") == "meta"
    assert main_dispatcher.quick_intent_check("ok bin drin") == "meta"


def test_quick_intent_routes_conversational_clarification_turns_to_meta():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("muss ich mir noch ueberlegen") == "meta"
    assert main_dispatcher.quick_intent_check("ich bin mir noch nicht sicher") == "meta"
    assert main_dispatcher.quick_intent_check("wie meinst du das") == "meta"


def test_quick_intent_routes_blackboard_queries_directly_to_meta():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("was gibts auf dem blackboard") == "meta"
    assert main_dispatcher.quick_intent_check("zeige mir die working memory uebersicht") == "meta"


def test_quick_intent_routes_google_calendar_access_queries_to_meta():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("hey timus kannst du meinen googlekalender einsehen") == "meta"
    assert main_dispatcher.quick_intent_check("hilf mir bei einer google calendar integration") == "meta"


def test_quick_intent_routes_direct_youtube_verification_to_meta():
    import main_dispatcher

    query = "überprüfe das mal ob es wahr ist was da erzählt wird https://youtu.be/niHG1OTfBrY"
    assert main_dispatcher.quick_intent_check(query) == "meta"


def test_quick_intent_prefers_current_user_query_inside_followup_capsule():
    import main_dispatcher

    augmented = """# FOLLOW-UP CONTEXT
last_agent: research
last_user: Recherchiere aktuelle LLM-Preise
last_assistant: Ich habe drei Optionen gefunden.
# CURRENT USER QUERY
dann uebernimm die empfehlung 2
"""

    assert main_dispatcher._extract_dispatcher_focus_query(augmented) == "dann uebernimm die empfehlung 2"
    assert main_dispatcher.quick_intent_check(augmented) == "meta"


def test_quick_intent_routes_deferred_followup_inside_capsule_to_meta():
    import main_dispatcher

    augmented = """# FOLLOW-UP CONTEXT
last_agent: meta
last_user: koenntest du dir selbst eine telefonfunktion einrichten um mit mir zu telefonieren
pending_followup_prompt: Was willst du?
# CURRENT USER QUERY
muss ich mir noch ueberlegen
"""

    assert main_dispatcher._extract_dispatcher_focus_query(augmented) == "muss ich mir noch ueberlegen"
    assert main_dispatcher.quick_intent_check(augmented) == "meta"


def test_quick_intent_does_not_route_generic_oder_to_reasoning():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("soll ich kaffee oder tee trinken") is None


def test_quick_intent_routes_location_only_queries_to_executor():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("Wo bin ich?") == "executor"
    assert main_dispatcher.quick_intent_check("Wo ist mein Standort gerade?") == "executor"


def test_quick_intent_routes_broad_research_via_meta_and_strict_research_direct():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("Recherchiere KI-Agenten fuer Unternehmen") == "meta"
    assert (
        main_dispatcher.quick_intent_check(
            "Recherchiere aktuelle Entwicklungen zu KI-Agenten mit Quellen und Studien"
        )
        == "research"
    )


def test_quick_intent_routes_research_plus_setup_to_meta():
    import main_dispatcher

    query = "Recherchiere eine passende Home Assistant Kamera und richte sie danach bei mir ein"
    assert main_dispatcher.quick_intent_check(query) == "meta"


def test_quick_intent_keeps_explicit_shell_execution_out_of_planning_meta():
    import main_dispatcher

    query = "pip install homeassistant und starte danach systemctl restart mosquitto"
    assert main_dispatcher.quick_intent_check(query) == "shell"


def test_quick_intent_routes_exact_direct_response_to_meta_not_shell():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("Antworte exakt nur mit CHAT_OK") == "meta"
    assert main_dispatcher.quick_intent_check("führe aus: antworte exakt nur mit KIMI_CHAT_OK") == "meta"
    assert main_dispatcher.quick_intent_check("führe aus: systemctl restart timus-mcp") == "shell"


def test_build_dispatcher_llm_query_enforces_token_only_contract():
    import main_dispatcher

    query = main_dispatcher._build_dispatcher_llm_query(
        "Bitte melde mich in Chrome bei grok.com an und nutze den Passwortmanager."
    )

    assert "Antworte ausschliesslich mit genau einem dieser Tokens" in query
    assert "visual_login" in query
    assert "visual_nemotron" in query


def test_prepare_direct_research_request_compacts_and_marks_preflight():
    import main_dispatcher

    raw_query = "Recherchiere aktuelle LLM-Preise mit Quellen. " * 500

    safe_query, packet, preflight = main_dispatcher._prepare_direct_research_request(raw_query)

    assert len(safe_query) < len(raw_query)
    assert packet["packet_type"] == "research_specialist_request"
    assert "start_deep_research" in list(packet.get("allowed_tools") or [])
    assert preflight["schema_version"] == 1
    assert preflight["metrics"]["original_request_chars"] == len(safe_query)
