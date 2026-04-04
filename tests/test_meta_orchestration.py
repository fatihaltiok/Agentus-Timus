from __future__ import annotations

from orchestration.meta_orchestration import (
    build_meta_feedback_targets,
    classify_meta_task,
    extract_meta_dialog_state,
    extract_effective_meta_query,
    extract_meta_context_anchor,
    get_agent_capability_map,
)
from agent.agents.meta import MetaAgent


def test_agent_capability_map_exposes_meta_visual_and_research_profiles():
    capability_map = get_agent_capability_map()

    assert capability_map["meta"]["agent"] == "meta"
    assert "workflow_orchestration" in capability_map["meta"]["capabilities"]
    assert "goal" in capability_map["meta"]["handoff_fields"]
    assert "browser_navigation" in capability_map["visual"]["capabilities"]
    assert "content_extraction" in capability_map["research"]["capabilities"]


def test_classify_meta_task_keeps_simple_booking_navigation_direct():
    result = classify_meta_task("Starte den Browser und gehe auf booking.com", action_count=1)

    assert result["task_type"] == "ui_navigation"
    assert result["site_kind"] == "booking"
    assert result["recommended_entry_agent"] == "visual"
    assert result["recommended_agent_chain"] == ["visual"]
    assert result["needs_structured_handoff"] is False


def test_classify_meta_task_recommends_visual_and_research_for_youtube_extraction():
    result = classify_meta_task(
        "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        action_count=3,
    )

    assert result["task_type"] == "youtube_content_extraction"
    assert result["site_kind"] == "youtube"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "visual", "research", "document"]
    assert result["needs_structured_handoff"] is True
    assert result["recommended_recipe_id"] == "youtube_content_extraction"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == [
        "visual_access",
        "research_synthesis",
        "document_output",
    ]
    assert [item["recipe_id"] for item in result["alternative_recipes"]] == [
        "youtube_search_then_visual",
        "youtube_research_only",
    ]
    assert result["recipe_recoveries"][0]["failed_stage_id"] == "visual_access"
    assert result["recipe_recoveries"][0]["recovery_stage_id"] == "research_context_recovery"
    assert result["recipe_recoveries"][0]["terminal"] is False
    assert result["goal_spec"]["output_mode"] == "report"
    assert result["adaptive_plan"]["recommended_chain"] == ["meta", "visual", "research", "document"]


def test_classify_meta_task_routes_casual_youtube_discovery_to_meta_executor():
    result = classify_meta_task(
        "Schau mal was es auf YouTube so gibt zu KI-Agenten",
        action_count=0,
    )

    assert result["task_type"] == "youtube_light_research"
    assert result["site_kind"] == "youtube"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "executor"]
    assert result["recommended_recipe_id"] == "youtube_light_research"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == ["youtube_search_scan"]
    assert result["alternative_recipes"] == []


def test_classify_meta_task_routes_direct_youtube_fact_check_to_research_recipe():
    result = classify_meta_task(
        "https://youtu.be/j4jBGHv9Eow?is=7eXEJB7wHGDk0F_f schau mal ob da etwas wahres dran ist",
        action_count=0,
    )

    assert result["task_type"] == "youtube_content_extraction"
    assert result["site_kind"] == "youtube"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "research"]
    assert result["recommended_recipe_id"] == "youtube_research_only"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == ["research_discovery", "document_output"]
    assert [item["recipe_id"] for item in result["alternative_recipes"]] == [
        "youtube_content_extraction",
        "youtube_search_then_visual",
    ]


def test_classify_meta_task_routes_local_nearby_queries_to_meta_executor():
    result = classify_meta_task(
        "Was ist hier in meiner Nähe gerade offen?",
        action_count=0,
    )

    assert result["task_type"] == "location_local_search"
    assert result["site_kind"] == "maps"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "executor"]
    assert result["recommended_recipe_id"] == "location_local_search"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == ["location_context_scan"]


def test_classify_meta_task_routes_local_action_plus_place_queries_to_meta_executor():
    result = classify_meta_task(
        "Wo bekomme ich gerade Kaffee?",
        action_count=0,
    )

    assert result["task_type"] == "location_local_search"
    assert result["site_kind"] == "maps"
    assert result["recommended_agent_chain"] == ["meta", "executor"]


def test_classify_meta_task_marks_mixed_preference_and_wealth_prompt_for_semantic_review():
    result = classify_meta_task(
        "soll ich kaffee oder tee trinken was meinst du und was und wie koenntest du mich reich machen",
        action_count=0,
    )

    assert result["semantic_review_recommended"] is True
    assert "mixed_personal_preference_and_wealth_strategy" in result["semantic_ambiguity_hints"]
    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["reason"] == "semantic_multi_intent_dialogue_review"


def test_classify_meta_task_marks_business_strategy_cafe_prompt_for_semantic_review():
    result = classify_meta_task(
        "ich moechte ein cafe eroeffnen welches land ist am besten geeignet",
        action_count=0,
    )

    assert result["semantic_review_recommended"] is True
    assert "business_strategy_vs_local_lookup" in result["semantic_ambiguity_hints"]
    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["reason"] == "semantic_business_strategy_review"


def test_classify_meta_task_marks_user_reported_location_update_for_semantic_review():
    result = classify_meta_task(
        "ich habe meinen handy standort aktualisiert du musst das registrieren",
        action_count=0,
    )

    assert result["semantic_review_recommended"] is True
    assert "user_reported_location_state_update" in result["semantic_ambiguity_hints"]
    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["reason"] == "semantic_state_update_review"


def test_classify_meta_task_routes_simple_live_science_lookup_to_meta_executor():
    result = classify_meta_task(
        "Was gibt es Neues aus der Wissenschaft?",
        action_count=0,
    )

    assert result["task_type"] == "simple_live_lookup"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "executor"]
    assert result["recommended_recipe_id"] == "simple_live_lookup"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == ["live_lookup_scan"]


def test_classify_meta_task_routes_lookup_plus_txt_export_to_executor_and_document():
    result = classify_meta_task(
        "Speichere mir aktuelle LLM-Preise als txt Datei",
        action_count=0,
    )

    assert result["task_type"] == "simple_live_lookup_document"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "executor", "document"]
    assert result["recommended_recipe_id"] == "simple_live_lookup_document"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == [
        "live_lookup_scan",
        "document_output",
    ]
    assert result["goal_spec"]["artifact_format"] == "txt"
    assert result["capability_graph"]["goal_gaps"] == []
    assert result["adaptive_plan"]["recommended_recipe_hint"] == "simple_live_lookup_document"


def test_classify_meta_task_routes_lookup_plus_table_request_to_executor_and_document():
    result = classify_meta_task(
        "Erstelle mir eine Liste mit den aktuellen Preisen der besten LLMs und zeige mir dann die Tabelle",
        action_count=0,
    )

    assert result["task_type"] == "simple_live_lookup_document"
    assert result["recommended_agent_chain"] == ["meta", "executor", "document"]
    assert result["recommended_recipe_id"] == "simple_live_lookup_document"
    assert result["goal_spec"]["output_mode"] == "table"
    assert result["adaptive_plan"]["recommended_chain"] == ["meta", "executor", "document"]


def test_classify_meta_task_exposes_learned_chain_stats_when_available(monkeypatch):
    class _FakeAdaptivePlanMemory:
        def get_goal_chain_stats(self, goal_signature: str):
            assert goal_signature
            return [
                {
                    "chain": ["meta", "executor", "document"],
                    "evidence_count": 3,
                    "success_count": 3,
                    "failure_count": 0,
                    "success_rate": 1.0,
                    "runtime_gap_rate": 0.0,
                    "avg_duration_ms": 1100,
                    "learned_confidence": 1.0,
                    "learned_bias": 0.18,
                    "last_seen_at": "2026-03-27T12:00:00",
                }
            ]

    monkeypatch.setattr(
        "orchestration.meta_orchestration.get_adaptive_plan_memory",
        lambda: _FakeAdaptivePlanMemory(),
    )

    result = classify_meta_task(
        "Erstelle mir eine Liste mit den aktuellen Preisen der besten LLMs und zeige mir dann die Tabelle",
        action_count=0,
    )

    assert result["learned_chain_stats"][0]["chain"] == ["meta", "executor", "document"]
    assert result["adaptive_plan"]["candidate_chains"][0]["learned_bias"] >= 0.0


def test_classify_meta_task_keeps_source_bound_research_out_of_simple_live_lookup():
    result = classify_meta_task(
        "Recherchiere aktuelle Entwicklungen zu KI-Agenten mit Quellen und Studien",
        action_count=0,
    )

    assert result["task_type"] == "knowledge_research"
    assert result["recommended_entry_agent"] == "research"


def test_classify_meta_task_routes_route_queries_to_meta_executor():
    result = classify_meta_task(
        "Erstelle mir eine Route zur Zeil in Frankfurt",
        action_count=0,
    )

    assert result["task_type"] == "location_route"
    assert result["site_kind"] == "maps"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "executor"]
    assert result["recommended_recipe_id"] == "location_route"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == ["location_route_plan"]


def test_classify_meta_task_routes_broad_research_requests_via_meta():
    result = classify_meta_task(
        "Recherchiere KI-Agenten fuer Unternehmen",
        action_count=1,
    )

    assert result["task_type"] == "knowledge_research"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "research"]
    assert result["recommended_recipe_id"] == "knowledge_research"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == ["research_discovery"]


def test_classify_meta_task_routes_legal_claim_check_direct_to_research():
    result = classify_meta_task(
        "das ist falsch ich will wissen ob es wirklich Bestrebungen gibt das wenn man ausreisen moechte sie Deutschland eine Genehmigung braucht",
        action_count=0,
    )

    assert result["task_type"] == "knowledge_research"
    assert result["recommended_entry_agent"] == "research"
    assert result["recommended_agent_chain"] == ["research"]
    assert result["recommended_recipe_id"] == "knowledge_research"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == ["research_discovery"]


def test_classify_meta_task_keeps_explicit_source_research_direct():
    result = classify_meta_task(
        "Recherchiere aktuelle Entwicklungen zu KI-Agenten mit Quellen und Studien",
        action_count=1,
    )

    assert result["task_type"] == "knowledge_research"
    assert result["recommended_entry_agent"] == "research"
    assert result["recommended_agent_chain"] == ["research"]
    assert result["recommended_recipe_id"] == "knowledge_research"


def test_classify_meta_task_exposes_booking_recipe_for_multistage_workflow():
    result = classify_meta_task(
        "Öffne booking.com, gib Berlin ein, wähle Daten und starte die Suche",
        action_count=4,
    )

    assert result["task_type"] == "multi_stage_web_task"
    assert result["site_kind"] == "booking"
    assert result["recommended_recipe_id"] == "booking_search"
    assert [stage["agent"] for stage in result["recipe_stages"]] == ["visual", "visual"]


def test_classify_meta_task_exposes_generic_web_recipe_for_x_summary():
    result = classify_meta_task(
        "Öffne x.com, lies den Thread zu KI-Agenten und fasse die wichtigsten Punkte zusammen",
        action_count=3,
    )

    assert result["task_type"] == "web_content_extraction"
    assert result["site_kind"] == "x"
    assert result["recommended_recipe_id"] == "web_visual_research_summary"
    assert result["alternative_recipes"][0]["recipe_id"] == "web_research_only"
    assert result["recipe_recoveries"][0]["recovery_stage_id"] == "research_context_recovery"


def test_classify_meta_task_exposes_system_diagnosis_recipe():
    result = classify_meta_task(
        "Prüfe die Logs, analysiere den Systemstatus und starte den Service wenn nötig neu",
        action_count=3,
    )

    assert result["task_type"] == "system_diagnosis"
    assert result["recommended_recipe_id"] == "system_diagnosis"
    assert result["recipe_stages"][0]["agent"] == "system"
    assert result["alternative_recipes"][0]["recipe_id"] == "system_shell_probe_first"


def test_extract_effective_meta_query_prefers_current_user_query_from_followup_context():
    query = (
        "# FOLLOW-UP CONTEXT\n"
        "last_agent: meta\n"
        "last_assistant: System stabil - kein aktiver Incident festgestellt.\n"
        "semantic_recall: assistant:meta => Status: Das Chunking läuft im Hintergrund\n"
        "\n"
        "# CURRENT USER QUERY\n"
        "hey timus ist das chunking fertig"
    )

    assert extract_effective_meta_query(query) == "hey timus ist das chunking fertig"


def test_extract_effective_meta_query_handles_single_line_serialized_followup_context():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_nruf7dni "
        "last_user: ich arbeite seit 2010 als industriemechaniker "
        'last_assistant: Die meisten KI-Leute kennen Maschinen nur aus YouTube-Videos. '
        "# CURRENT USER QUERY und wie kannst du mir dabei behilflich sein"
    )

    assert extract_effective_meta_query(query) == "und wie kannst du mir dabei behilflich sein"


def test_extract_meta_context_anchor_prefers_last_user_from_followup_context():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_nruf7dni "
        "last_user: ich arbeite seit 2010 als industriemechaniker und will in die ki selbststaendigkeit "
        "last_assistant: System stabil. "
        "# CURRENT USER QUERY und wie kannst du mir dabei behilflich sein"
    )

    assert extract_meta_context_anchor(query) == (
        "ich arbeite seit 2010 als industriemechaniker und will in die ki selbststaendigkeit"
    )


def test_extract_meta_dialog_state_keeps_active_topic_and_constraints_for_compact_followup():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_nruf7dni "
        "last_user: ich arbeite seit 2010 als industriemechaniker in der industrie und will mich in richtung ki selbststaendig machen "
        "pending_followup_prompt: entwickle mit mir einen realistischen plan fuer den einstieg in ki-consulting "
        "# CURRENT USER QUERY KI-Consulting, KI-Tools 2 stunden budget 0"
    )

    state = extract_meta_dialog_state(query)

    assert "industriemechaniker" in (state["active_topic"] or "")
    assert "ki-consulting" in (state["open_goal"] or "").lower()
    assert "2 stunden" in state["constraints"]
    assert "budget 0" in state["constraints"]
    assert state["compressed_followup_parsed"] is True
    assert state["active_topic_reused"] is True


def test_classify_meta_task_does_not_route_chunking_followup_to_system_diagnosis():
    query = (
        "# FOLLOW-UP CONTEXT\n"
        "last_agent: meta\n"
        "last_assistant: System stabil - kein aktiver Incident festgestellt.\n"
        "semantic_recall: assistant:meta => Status: Das Chunking läuft im Hintergrund\n"
        "\n"
        "# CURRENT USER QUERY\n"
        "hey timus ist das chunking fertig"
    )

    result = classify_meta_task(query, action_count=0)

    assert result["task_type"] != "system_diagnosis"
    assert result["recommended_recipe_id"] != "system_diagnosis"


def test_classify_meta_task_ignores_old_assistant_text_in_single_line_followup_capsule():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_nruf7dni "
        "last_user: ich arbeite seit 2010 als industriemechaniker "
        "last_assistant: System stabil. Die meisten KI-Leute kennen Maschinen nur aus YouTube-Videos. "
        "# CURRENT USER QUERY und wie kannst du mir dabei behilflich sein"
    )

    result = classify_meta_task(query, action_count=0)

    assert result["site_kind"] is None
    assert result["task_type"] != "system_diagnosis"
    assert result["recommended_recipe_id"] != "system_diagnosis"


def test_classify_meta_task_keeps_context_dependent_career_followup_on_meta():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_nruf7dni "
        "last_user: ich arbeite seit 2010 als industriemechaniker in der industrie und will mich in richtung ki selbststaendig machen "
        "last_assistant: Die meisten KI-Leute kennen Maschinen nur aus YouTube-Videos. "
        "# CURRENT USER QUERY und wie kannst du mir dabei behilflich sein"
    )

    result = classify_meta_task(query, action_count=0)

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["context_anchor_applied"] is True
    assert result["reason"] == "context_anchored_followup"
    assert result["site_kind"] is None


def test_classify_meta_task_routes_compact_budget_followup_to_meta():
    result = classify_meta_task("KI-Consulting, KI-Tools 2 stunden budget 0", action_count=0)

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["compressed_followup_parsed"] is True
    assert result["reason"] == "compressed_advisory_followup"
    assert "2 stunden" in result["dialog_constraints"]
    assert "budget 0" in result["dialog_constraints"]


def test_classify_meta_task_reuses_brazil_topic_for_short_followup():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: executor session_id: canvas_am26swx3 "
        "last_user: was denkst du ueber brasilien wie koennte ich mich dort machen ich habe kontakte zu brasilien ich bin mit einer brasilianerin zusammen "
        "pending_followup_prompt: pruefe ob ich dort mit ki beeindrucken kann "
        "# CURRENT USER QUERY koennte ich dort mit ki oder mit dir sogar beeindrucken"
    )

    result = classify_meta_task(query, action_count=0)

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["active_topic_reused"] is True
    assert "brasilien" in (result["active_topic"] or "").lower()
    assert "ki" in (result["open_goal"] or "").lower()


def test_classify_meta_task_requires_current_location_evidence_despite_location_anchor():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_maps1 "
        "last_user: was ist hier in meiner naehe gerade offen "
        "pending_followup_prompt: schlage einen naechsten schritt vor "
        "# CURRENT USER QUERY und wie koennte ich mich dort vorstellen"
    )

    result = classify_meta_task(query, action_count=0)

    assert result["site_kind"] is None
    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]


def test_classify_meta_task_keeps_real_system_question_inside_followup_context():
    query = (
        "# FOLLOW-UP CONTEXT\n"
        "last_agent: meta\n"
        "last_assistant: Route nach Münster ist erstellt.\n"
        "\n"
        "# CURRENT USER QUERY\n"
        "prüfe bitte den systemstatus und die logs"
    )

    result = classify_meta_task(query, action_count=2)

    assert result["task_type"] == "system_diagnosis"
    assert result["recommended_recipe_id"] == "system_diagnosis"


def test_classify_meta_task_applies_context_anchor_for_ok_fang_an_followup():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: phaseb_live_replay_20260403 "
        "last_user: hey timus kannst du meinen googlekalender einsehen "
        "pending_followup_prompt: Hast du schon ein Google Cloud Projekt oder soll ich dich durch die Erstellung führen? "
        "# CURRENT USER QUERY ok fang an"
    )

    result = classify_meta_task(query, action_count=0)

    assert result["recommended_agent_chain"] == ["meta"]
    assert result["context_anchor_applied"] is True
    assert result["reason"] == "context_anchored_followup"
    assert "google cloud projekt" in (result["active_topic"] or "").lower()


def test_build_meta_feedback_targets_emits_task_recipe_and_chain_targets():
    result = classify_meta_task(
        "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        action_count=3,
    )

    targets = build_meta_feedback_targets(result)

    assert {"namespace": "meta_task_type", "key": "youtube_content_extraction"} in targets
    assert {"namespace": "meta_recipe", "key": "youtube_content_extraction"} in targets
    assert {
        "namespace": "meta_site_recipe",
        "key": "youtube::youtube_content_extraction",
    } in targets
    assert {
        "namespace": "meta_agent_chain",
        "key": "meta__visual__research__document",
    } in targets


def test_meta_prefers_strategy_selected_fallback_recipe_for_youtube_extraction():
    classification = classify_meta_task(
        "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        action_count=3,
    )
    handoff = {
        **classification,
        "selected_strategy": {
            "strategy_id": "layered_youtube_extraction",
            "primary_recipe_id": "youtube_research_only",
            "fallback_recipe_id": "youtube_search_then_visual",
        },
        "meta_self_state": {"runtime_constraints": {}, "active_tools": []},
        "alternative_recipe_scores": [],
        "meta_learning_posture": "neutral",
    }

    selected = MetaAgent._select_initial_recipe_payload(handoff)

    assert selected["recipe_id"] == "youtube_research_only"
    assert selected["switch_reason"] == "selected_strategy_primary"
