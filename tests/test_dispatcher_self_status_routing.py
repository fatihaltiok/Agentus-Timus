import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def test_quick_intent_routes_self_status_to_executor():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("Was hast du fuer Probleme?") == "executor"
    assert main_dispatcher.quick_intent_check("sag du es mir") == "executor"
    assert main_dispatcher.quick_intent_check("und was kannst du dagegen tun") == "executor"
    assert main_dispatcher.quick_intent_check("und was davon machst du zuerst") == "executor"
    assert main_dispatcher.quick_intent_check("Hast du etwas zu korrigieren oder fixen?") == "executor"


def test_quick_intent_routes_colloquial_self_reflection_to_executor():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("ok was stoert dich wie kann ich dir helfen") == "executor"
    assert main_dispatcher.quick_intent_check("bist du anpassungsfaehig") == "executor"
    assert main_dispatcher.quick_intent_check("bist du ein funktionierendes ki system ?") == "executor"


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


def test_quick_intent_keeps_colloquial_nontrivial_strategy_question_out_of_executor():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("was meinst du wie koennte ich mein unternehmen skalieren") is None


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
    assert main_dispatcher.quick_intent_check("was machst du da das ist doch falsch") == "meta"
    assert main_dispatcher.quick_intent_check("dann uebernimm die empfehlung 2") == "meta"
    assert main_dispatcher.quick_intent_check("koenntest du damit arbeiten") == "meta"
    assert main_dispatcher.quick_intent_check("kannst du sie reparieren") == "meta"


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
