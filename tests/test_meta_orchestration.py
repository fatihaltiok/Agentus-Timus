from __future__ import annotations

import sys
from types import SimpleNamespace

from orchestration.meta_orchestration import (
    build_meta_feedback_targets,
    classify_meta_task,
    extract_meta_dialog_state,
    extract_effective_meta_query,
    extract_meta_context_anchor,
    get_agent_capability_map,
    looks_like_meta_clarification_turn,
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


def test_meta_clarification_turn_helper_recognizes_short_ambiguous_dialogue():
    assert looks_like_meta_clarification_turn("muss ich mir noch überlegen") is True
    assert looks_like_meta_clarification_turn("ich bin mir noch nicht sicher") is True
    assert looks_like_meta_clarification_turn("wie meinst du das") is True
    assert looks_like_meta_clarification_turn("prüfe bitte den systemstatus und die logs") is False


def test_classify_meta_task_routes_conversational_clarification_turn_to_meta():
    result = classify_meta_task(
        "muss ich mir noch überlegen",
        action_count=0,
    )

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["reason"] == "semantic_clarification_turn"
    assert "conversational_clarification_needed" in result["semantic_ambiguity_hints"]


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
    assert result["response_mode"] == "execute"
    assert result["meta_policy_decision"]["override_applied"] is False


def test_classify_meta_task_uses_state_summary_policy_for_status_question():
    result = classify_meta_task(
        "wo stehen wir gerade",
        action_count=0,
        conversation_state={
            "session_id": "canvas_d06_summary",
            "active_topic": "D0.6 Meta-Policy",
            "active_goal": "Antwortmodus sauber vom Turn-Typ trennen",
            "open_loop": "Naechsten Runtime-Slice und Tests fertigziehen",
            "next_expected_step": "Policy-Events und Handoff final verdrahten",
        },
    )

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["response_mode"] == "summarize_state"
    assert result["reason"] == "meta_policy:state_summary_request"
    assert result["meta_policy_decision"]["override_applied"] is True
    assert result["meta_policy_decision"]["should_summarize_state"] is True


def test_classify_meta_task_uses_direct_recommendation_policy_for_next_step_question():
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

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["response_mode"] == "summarize_state"
    assert result["reason"] == "meta_policy:next_step_summary_request"
    assert result["meta_policy_decision"]["override_applied"] is True
    assert result["meta_policy_decision"]["answer_shape"] == "direct_recommendation"
    assert result["meta_clarity_contract"]["request_kind"] == "direct_recommendation"
    assert result["meta_clarity_contract"]["direct_answer_required"] is True
    assert result["meta_clarity_contract"]["answer_obligation"] == "answer_now_with_single_recommendation"
    assert result["meta_clarity_contract"]["completion_condition"] == "next_recommended_block_or_step_named"


def test_classify_meta_task_uses_historical_topic_recall_policy_for_time_anchored_memory_queries():
    result = classify_meta_task(
        "weisst du noch was wir vor 6 monaten ueber die agentenarchitektur besprochen hatten",
        action_count=0,
        topic_history=[
            {
                "topic": "Agentenarchitektur und Meta-Koordination",
                "goal": "saubere Rollen fuer Meta, Executor und Research",
                "open_loop": "",
                "next_expected_step": "",
                "status": "closed",
                "first_seen_at": "2025-09-20T10:00:00Z",
                "last_seen_at": "2025-10-05T10:00:00Z",
                "closed_at": "2025-10-05T10:00:00Z",
                "topic_confidence": 0.88,
                "turn_type_hint": "new_task",
            }
        ],
    )

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["response_mode"] == "summarize_state"
    assert result["reason"] == "meta_policy:historical_topic_recall"
    assert result["meta_policy_decision"]["answer_shape"] == "historical_topic_state"
    assert result["meta_policy_decision"]["should_delegate"] is False
    assert "historical_topic_memory" in result["meta_context_slot_types"]


def test_classify_meta_task_falls_back_to_recent_user_turn_for_recent_historical_recall():
    result = classify_meta_task(
        "weisst du noch was wir eben ueber archivregeln besprochen hatten",
        action_count=0,
        recent_user_turns=["Lass uns ueber Langzeitgedaechtnis und Archivregeln bei Timus sprechen."],
    )

    assert result["recommended_agent_chain"] == ["meta"]
    assert result["reason"] == "meta_policy:historical_topic_recall"
    assert result["dominant_turn_type"] == "followup"
    assert result["response_mode"] == "summarize_state"
    assert "historical_topic_memory" in result["meta_context_slot_types"]
    assert result["historical_topic_selection"]["fallback_applied"] is True
    assert result["historical_topic_selection"]["fallback_source"] == "recent_user_turn"


def test_classify_meta_task_can_fall_back_to_recent_assistant_turn_for_what_you_said():
    result = classify_meta_task(
        "was hast du eben gesagt",
        action_count=0,
        recent_assistant_turns=["Ich habe dir gerade drei Optionen fuer die Archivregeln genannt."],
    )

    assert result["reason"] == "meta_policy:historical_topic_recall"
    assert result["dominant_turn_type"] == "followup"
    assert result["response_mode"] == "summarize_state"
    assert "historical_topic_memory" in result["meta_context_slot_types"]
    assert result["historical_topic_selection"]["fallback_applied"] is True
    assert result["historical_topic_selection"]["fallback_source"] == "recent_assistant_turn"


def test_classify_meta_task_does_not_misclassify_plain_recent_time_reference_as_historical_recall():
    result = classify_meta_task(
        "ich habe dir eben einen link gegeben, hol mehr infos dazu",
        action_count=0,
    )

    assert result["reason"] != "meta_policy:historical_topic_recall"
    assert result["response_mode"] != "summarize_state"
    assert result["meta_policy_decision"]["policy_reason"] != "historical_topic_recall"


def test_classify_meta_task_uses_self_model_status_policy_for_capability_question():
    result = classify_meta_task(
        "ist das geplant oder kannst du das jetzt schon",
        action_count=0,
    )

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["response_mode"] == "summarize_state"
    assert result["reason"] == "meta_policy:self_model_status_request"
    assert result["meta_policy_decision"]["override_applied"] is True
    assert result["meta_policy_decision"]["self_model_bound_applied"] is True
    assert result["meta_policy_decision"]["answer_shape"] == "self_model_status"


def test_classify_meta_task_clarifies_low_confidence_action_followup_before_execution():
    result = classify_meta_task(
        "# FOLLOW-UP CONTEXT\n"
        "last_agent: meta\n"
        "session_id: canvas_d06_clarify\n"
        "last_assistant: Soll ich mit dem ersten Schritt anfangen?\n"
        "recent_assistant_replies: Soll ich mit dem ersten Schritt anfangen?\n"
        "\n"
        "# CURRENT USER QUERY\n"
        "ok fang an und such aktuelle live-news",
        action_count=0,
    )

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["response_mode"] == "clarify_before_execute"
    assert result["reason"].startswith("meta_policy:")
    assert result["meta_policy_decision"]["override_applied"] is True
    assert result["meta_policy_decision"]["should_delegate"] is False


def test_classify_meta_task_routes_future_behavior_alignment_turn_to_meta_review():
    result = classify_meta_task(
        "dann mach das in zukunft so dass du auf echtzeit agenturmeldungen zugreifst bei news und aktuellem geschehen",
        action_count=0,
    )

    assert result["task_type"] == "single_lane"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["reason"] == "semantic_preference_alignment"
    assert "behavior_preference_alignment" in result["semantic_ambiguity_hints"]
    assert result["dominant_turn_type"] == "behavior_instruction"
    assert result["response_mode"] == "acknowledge_and_store"
    assert result["state_effects"]["update_preferences"] is True


def test_classify_meta_task_routes_followup_capsule_behavior_alignment_to_meta_review():
    result = classify_meta_task(
        "# FOLLOW-UP CONTEXT\n"
        "last_agent: meta\n"
        "session_id: canvas_test\n"
        "last_user: wie stehts um die aktuelle weltlage\n"
        "last_assistant: Ehrliches Ergebnis: Die Recherche hat keine belastbaren Live-News gefunden.\n"
        "recent_assistant_replies: Ehrliches Ergebnis: Die Recherche hat keine belastbaren Live-News gefunden.\n"
        "\n"
        "# CURRENT USER QUERY\n"
        "dann mach das in zukunft so dass du auf echtzeit agenturmeldungen zugreifst bei news und aktuellem geschehen",
        action_count=0,
    )

    assert result["task_type"] == "single_lane"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["recommended_recipe_id"] is None
    assert result["reason"] == "semantic_preference_alignment"
    assert "behavior_preference_alignment" in result["semantic_ambiguity_hints"]
    assert result["turn_understanding"]["dominant_turn_type"] == "behavior_instruction"
    assert result["turn_understanding"]["route_bias"] == "meta_only"


def test_classify_meta_task_routes_correction_turn_to_meta_only():
    result = classify_meta_task(
        "# FOLLOW-UP CONTEXT\n"
        "last_agent: meta\n"
        "session_id: canvas_test\n"
        "last_user: wie stehts um die weltlage\n"
        "pending_followup_prompt: Soll ich aktuelle News oder eine tiefere Analyse priorisieren?\n"
        "\n"
        "# CURRENT USER QUERY\n"
        "nein, ich meinte aktuelle news und nicht wieder lokale nearby treffer",
        action_count=0,
    )

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["dominant_turn_type"] == "correction"
    assert result["response_mode"] == "correct_previous_path"
    assert result["reason"] == "turn_understanding:correction"


def test_meta_recipe_stage_delegation_uses_source_aware_handoff_for_x_lookup():
    handoff = {
        "task_type": "simple_live_lookup",
        "recommended_recipe_id": "simple_live_lookup",
        "site_kind": "",
    }
    stage = {
        "agent": "executor",
        "stage_id": "live_lookup_scan",
        "goal": "Fuehre eine kompakte aktuelle Live-Recherche aus.",
        "expected_output": "quick_summary, top_results, source_urls",
    }

    task = MetaAgent._build_recipe_stage_delegation_task(
        handoff=handoff,
        stage=stage,
        original_user_task="hey timus was gibts denn so auf x an neuigkeiten über ki",
        previous_stage_result=None,
        stage_history=[],
    )

    assert "- task_type: single_lane" in task
    assert "- source_hint: x" in task
    assert "preferred_tools: search_web, fetch_social_media, fetch_page_with_js" in task
    assert "search_news_as_primary_step" in task
    assert "X/Twitter" in task
    assert "frage den Nutzer explizit nach Login-Zugang" in task


def test_meta_recipe_stage_delegation_uses_source_aware_handoff_for_github_lookup():
    handoff = {
        "task_type": "simple_live_lookup",
        "recommended_recipe_id": "simple_live_lookup",
        "site_kind": "",
    }
    stage = {
        "agent": "executor",
        "stage_id": "live_lookup_scan",
        "goal": "Fuehre eine kompakte aktuelle Live-Recherche aus.",
        "expected_output": "quick_summary, top_results, source_urls",
    }

    task = MetaAgent._build_recipe_stage_delegation_task(
        handoff=handoff,
        stage=stage,
        original_user_task="was gibt es auf github neues zu KI agenten",
        previous_stage_result=None,
        stage_history=[],
    )

    assert "- task_type: single_lane" in task
    assert "- source_hint: github" in task
    assert "preferred_tools: search_web, fetch_url" in task
    assert "fetch_social_media" not in task
    assert "GitHub" in task


def test_meta_recipe_stage_delegation_keeps_structured_lookup_for_generic_science_query():
    handoff = {
        "task_type": "simple_live_lookup",
        "recommended_recipe_id": "simple_live_lookup",
        "site_kind": "",
        "goal_spec": {"uses_location": False},
    }
    stage = {
        "agent": "executor",
        "stage_id": "live_lookup_scan",
        "goal": "Fuehre eine kompakte aktuelle Live-Recherche aus.",
        "expected_output": "quick_summary, top_results, source_urls",
    }

    task = MetaAgent._build_recipe_stage_delegation_task(
        handoff=handoff,
        stage=stage,
        original_user_task="Was gibt es Neues aus der Wissenschaft?",
        previous_stage_result=None,
        stage_history=[],
    )

    assert "- task_type: simple_live_lookup" in task
    assert "fallback_tools: search_news, fetch_url" in task
    assert "search_google_maps_places" not in task
    assert "get_current_location_context" not in task
    assert "source_hint:" not in task


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
    assert result["dominant_turn_type"] == "followup"
    assert result["response_mode"] == "resume_open_loop"


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


def test_classify_meta_task_applies_context_anchor_for_deferred_decision_followup():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_geh1xquj "
        "last_user: könntest du dir selbst eine telefonfunktion einrichten um mit mir zu telefonieren "
        "pending_followup_prompt: Was willst du? "
        "# CURRENT USER QUERY muss ich mir noch überlegen"
    )

    result = classify_meta_task(query, action_count=0)

    assert result["recommended_agent_chain"] == ["meta"]
    assert result["context_anchor_applied"] is True
    assert result["reason"] == "semantic_clarification_turn"
    assert "telefonfunktion" in (result["active_topic"] or "").lower()
    assert "was willst du" not in (result["open_goal"] or "").lower()
    assert "telefonfunktion" in (result["open_goal"] or "").lower()


def test_classify_meta_task_routes_topic_referential_followup_to_meta_without_capsule_wrapper():
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

    assert result["dominant_turn_type"] == "followup"
    assert result["recommended_agent_chain"] == ["meta", "research"]
    assert result["reason"] == "frame:migration_work"
    assert "kanada" in (result["active_topic"] or "").lower()


def test_classify_meta_task_builds_meta_context_bundle_with_state_priority_and_suppression():
    query = (
        "# FOLLOW-UP CONTEXT "
        "last_agent: meta session_id: canvas_d03 "
        "last_assistant: Dein letzter bekannter Standort war in Offenbach am Main. "
        "pending_followup_prompt: Soll ich Reuters und AP kuenftig priorisieren? "
        "# CURRENT USER QUERY dann mach das in zukunft so dass du fuer news agenturmeldungen priorisierst"
    )

    result = classify_meta_task(
        query,
        action_count=0,
        conversation_state={
            "active_topic": "Weltlage und News-Qualitaet",
            "active_goal": "Echtzeit-Agenturmeldungen priorisieren",
            "open_loop": "Reuters und AP priorisieren",
            "next_expected_step": "Praeferenz bestaetigen",
            "turn_type_hint": "behavior_instruction",
            "preferences": ["Reuters zuerst", "AP zuerst"],
            "recent_corrections": ["Nicht auf Standort abdriften"],
            "topic_confidence": 0.72,
        },
        recent_user_turns=["wie stehts um die aktuelle weltlage"],
        recent_assistant_turns=["Dein letzter bekannter Standort war in Offenbach am Main."],
        session_summary="Wir sprachen ueber bessere News-Quellen fuer aktuelle Weltlage.",
        semantic_recall_hits=[
            {
                "role": "assistant",
                "agent": "meta",
                "text": "Du wolltest bei News belastbare Agenturquellen statt langsamer Analysen.",
            }
        ],
    )

    bundle = result["meta_context_bundle"]
    slot_types = [slot["slot"] for slot in bundle["context_slots"]]

    assert result["reason"] == "semantic_preference_alignment"
    assert result["active_topic"] == "Weltlage und News-Qualitaet"
    assert result["open_goal"] == "Echtzeit-Agenturmeldungen priorisieren"
    assert bundle["active_topic"] == "Weltlage und News-Qualitaet"
    assert bundle["open_loop"] == "Praeferenz bestaetigen"
    assert result["meta_clarity_contract"]["request_kind"] == "acknowledgment"
    assert slot_types[:2] == ["current_query", "conversation_state"]
    assert "recent_user_turn" in slot_types
    assert "preference_memory" in slot_types
    assert "open_loop" not in slot_types
    assert any(
        item["reason"] == "location_context_without_current_evidence"
        for item in bundle["suppressed_context"]
    )


def test_classify_meta_task_normalizes_semantic_recall_into_bundle_slot():
    result = classify_meta_task(
        "wie war nochmal dein plan fuer visual",
        action_count=0,
        semantic_recall_hits=[
            {
                "role": "assistant",
                "agent": "executor",
                "text": "Frueher habe ich den Visual-Pfad bereits als Hauptproblem markiert.",
            }
        ],
    )

    bundle = result["meta_context_bundle"]
    semantic_slots = [slot for slot in bundle["context_slots"] if slot["slot"] == "semantic_recall"]

    assert semantic_slots
    assert "assistant:executor => Frueher habe ich den Visual-Pfad" in semantic_slots[0]["content"]


def test_classify_meta_task_loads_topic_and_preference_memory_from_memory_system(monkeypatch):
    def _get_memory_items(category):
        if category == "preference_memory":
            return [
                SimpleNamespace(
                    key="topic::news::agency",
                    value={
                        "scope": "topic",
                        "instruction": "bei news bitte zuerst agenturquellen",
                        "topic_anchor": "news",
                        "session_id": "default",
                        "stability": 0.91,
                        "evidence_count": 2,
                    },
                ),
                SimpleNamespace(
                    key="global::weak",
                    value={
                        "scope": "global",
                        "instruction": "sei nett",
                        "topic_anchor": "",
                        "session_id": "default",
                        "stability": 0.4,
                        "evidence_count": 1,
                    },
                ),
            ]
        if category == "user_profile":
            return [
                SimpleNamespace(key="preference", value="Fakten und Quellen zuerst"),
                SimpleNamespace(key="preference", value="Ich trinke gerne Tee"),
            ]
        return []

    fake_memory_manager = SimpleNamespace(
        find_related_memories=lambda query, n_results=6: [
            {
                "content": "Reuters meldete neue Entwicklungen zur Weltlage und zu KI-Politik.",
                "category": "news_archive",
                "relevance": 0.91,
            },
            {
                "content": "Ich trinke gerne Tee.",
                "category": "user_profile",
                "relevance": 0.99,
            },
        ],
        get_behavior_hooks=lambda: [
            "Wichtige Aussagen mit Quellen belegen.",
            "Antworten kurz und präzise.",
        ],
        get_self_model_prompt=lambda: "Präferenzen: Wichtige Aussagen mit Quellen belegen.\nZiele: Belastbare News zuerst.",
        persistent=SimpleNamespace(get_memory_items=_get_memory_items),
    )
    monkeypatch.setitem(
        sys.modules,
        "memory.memory_system",
        SimpleNamespace(memory_manager=fake_memory_manager),
    )

    result = classify_meta_task(
        "dann mach das in zukunft so dass du fuer aktuelle news agenturmeldungen und belastbare quellen priorisierst",
        action_count=0,
    )

    bundle = result["meta_context_bundle"]
    topic_slots = [slot for slot in bundle["context_slots"] if slot["slot"] == "topic_memory"]
    preference_slots = [slot for slot in bundle["context_slots"] if slot["slot"] == "preference_memory"]

    assert result["meta_clarity_contract"]["request_kind"] == "acknowledgment"
    assert topic_slots == []
    assert preference_slots
    assert any(slot["content"].startswith("stored_preference:topic[news]") for slot in preference_slots)
    assert any(
        any(token in slot["content"].lower() for token in ("quellen", "news zuerst", "fakten"))
        for slot in preference_slots
    )
    assert all("tee" not in slot["content"].lower() for slot in preference_slots)


def test_classify_meta_task_filters_irrelevant_location_and_voice_memory_from_meta_bundle(monkeypatch):
    def _get_memory_items(category):
        if category == "preference_memory":
            return [
                SimpleNamespace(
                    key="topic::voice::twilio",
                    value={
                        "scope": "topic",
                        "instruction": "Bei Telefonie immer zuerst Twilio und Inworld pruefen.",
                        "topic_anchor": "telefonie twilio inworld",
                        "session_id": "default",
                        "stability": 0.94,
                        "evidence_count": 3,
                    },
                )
            ]
        return []

    fake_memory_manager = SimpleNamespace(
        find_related_memories=lambda query, n_results=6: [
            {
                "content": "Dein letzter bekannter Standort war in Offenbach am Main in der Naehe des Marktplatzes.",
                "category": "location_memory",
                "relevance": 0.99,
            },
            {
                "content": "Phase F Runtime-Board und CHANGELOG wurden zuletzt fuer Betriebsvertraege erweitert.",
                "category": "project_notes",
                "relevance": 0.82,
            },
        ],
        get_behavior_hooks=lambda: [
            "Bei Telefonie immer zuerst Twilio und Inworld pruefen.",
        ],
        get_self_model_prompt=lambda: "Praeferenzen: Bei Telefonie immer zuerst Twilio und Inworld pruefen.",
        persistent=SimpleNamespace(get_memory_items=_get_memory_items),
    )
    monkeypatch.setitem(
        sys.modules,
        "memory.memory_system",
        SimpleNamespace(memory_manager=fake_memory_manager),
    )

    result = classify_meta_task(
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
        action_count=2,
        recent_assistant_turns=["Dein letzter bekannter Standort war in Offenbach am Main."],
    )

    bundle = result["meta_context_bundle"]
    rendered_context = " || ".join(slot["content"] for slot in bundle["context_slots"])
    topic_slots = [slot for slot in bundle["context_slots"] if slot["slot"] == "topic_memory"]
    slot_types = [slot["slot"] for slot in bundle["context_slots"]]
    clarity = result["meta_clarity_contract"]

    assert "offenbach" not in rendered_context.lower()
    assert "twilio" not in rendered_context.lower()
    assert topic_slots == []
    assert clarity["request_kind"] == "direct_recommendation"
    assert "topic_memory" in clarity["forbidden_context_slots"]
    assert "preference_memory" not in slot_types
    assert "semantic_recall" not in slot_types
    assert any(
        item["reason"] == "location_context_without_current_evidence"
        for item in bundle["suppressed_context"]
    )


def test_classify_meta_task_applies_clarity_filter_for_direct_recommendation_bundle(monkeypatch):
    fake_memory_manager = SimpleNamespace(
        find_related_memories=lambda query, n_results=6: [
            {
                "content": "Dein letzter bekannter Standort war in Offenbach am Main in der Naehe des Marktplatzes.",
                "category": "location_memory",
                "relevance": 0.99,
            },
            {
                "content": "Phase F ist im Kern abgeschlossen; als naechstes folgt die allgemeine Mehrschritt-Planung.",
                "category": "project_notes",
                "relevance": 0.83,
            },
        ],
        get_behavior_hooks=lambda: ["Bei Telefonie zuerst Twilio pruefen."],
        get_self_model_prompt=lambda: "Praeferenzen: Bei Telefonie zuerst Twilio pruefen.",
        persistent=SimpleNamespace(get_memory_items=lambda category: []),
    )
    monkeypatch.setitem(
        sys.modules,
        "memory.memory_system",
        SimpleNamespace(memory_manager=fake_memory_manager),
    )

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
        recent_assistant_turns=["Dein letzter bekannter Standort war in Offenbach am Main."],
    )

    bundle = result["meta_context_bundle"]
    slot_types = [slot["slot"] for slot in bundle["context_slots"]]
    clarity = result["meta_clarity_contract"]

    assert clarity["request_kind"] == "direct_recommendation"
    assert clarity["direct_answer_required"] is True
    assert clarity["allowed_working_memory_sections"] == ["KURZZEITKONTEXT"]
    assert "topic_memory" not in slot_types
    assert "preference_memory" not in slot_types
    assert "historical_topic_memory" not in slot_types
    assert any(
        item["reason"] == "clarity_contract_filtered_context"
        for item in bundle["suppressed_context"]
    )


def test_classify_meta_task_keeps_canada_context_for_context_dependent_footing_query(monkeypatch):
    fake_memory_manager = SimpleNamespace(
        find_related_memories=lambda query, n_results=6: [
            {
                "content": "Du wolltest pruefen, ob du in Kanada ein neues Leben aufbauen und beruflich Fuss fassen kannst.",
                "category": "goal_memory",
                "relevance": 0.88,
            },
            {
                "content": "Dein letzter bekannter Standort war in Offenbach am Main.",
                "category": "location_memory",
                "relevance": 0.98,
            },
        ],
        get_behavior_hooks=lambda: [],
        get_self_model_prompt=lambda: "",
        persistent=SimpleNamespace(get_memory_items=lambda category: []),
    )
    monkeypatch.setitem(
        sys.modules,
        "memory.memory_system",
        SimpleNamespace(memory_manager=fake_memory_manager),
    )

    result = classify_meta_task(
        "koennte ich da fuss fassen",
        action_count=0,
        conversation_state={
            "session_id": "canvas_canada_context",
            "active_topic": "Auswanderung nach Kanada",
            "active_goal": "Pruefen ob du in Kanada ein neues Leben aufbauen kannst",
            "open_loop": "Einwanderungs- und Jobchancen bewerten",
            "next_expected_step": "Visa- und Arbeitsmarktchancen einschaetzen",
            "turn_type_hint": "followup",
        },
        recent_user_turns=[
            "Ich ueberlege, ob ich nach Kanada auswandern und dort beruflich Fuss fassen kann."
        ],
    )

    bundle = result["meta_context_bundle"]
    rendered_context = " || ".join(slot["content"] for slot in bundle["context_slots"])
    topic_slots = [slot for slot in bundle["context_slots"] if slot["slot"] == "topic_memory"]

    assert "kanada" in (result["active_topic"] or "").lower()
    assert topic_slots
    assert "kanada" in topic_slots[0]["content"].lower()
    assert "offenbach" not in rendered_context.lower()


def test_classify_meta_task_suppresses_topic_mismatched_assistant_context():
    result = classify_meta_task(
        "# FOLLOW-UP CONTEXT "
        "last_assistant: Systemstatus gruen. MCP Health 200 OK. "
        "recent_user_queries: wie stehts um die aktuelle weltlage || nein ich meinte aktuelle news "
        "# CURRENT USER QUERY nein ich meinte aktuelle news",
        action_count=0,
        recent_user_turns=["wie stehts um die aktuelle weltlage", "nein ich meinte aktuelle news"],
        recent_assistant_turns=["Systemstatus gruen. MCP Health 200 OK."],
    )

    suppressed = result["meta_context_bundle"]["suppressed_context"]

    assert any(item["reason"] == "topic_mismatch_with_current_query" for item in suppressed)


def test_classify_meta_task_filters_preference_memory_for_docs_status_frame(monkeypatch):
    fake_memory_manager = SimpleNamespace(
        persistent=SimpleNamespace(
            get_memory_items=lambda category: [
                SimpleNamespace(
                    value={
                        "scope": "global",
                        "instruction": "Nutze fuer Twilio und Inworld immer denselben Setup-Pfad.",
                        "topic_anchor": "Twilio Inworld Setup",
                        "session_id": "sess_pref",
                        "stability": 0.95,
                        "evidence_count": 3,
                        "explicit_global": True,
                        "preference_family": "topic:twilio",
                        "updated_at": "2026-04-20T10:00:00+00:00",
                    }
                )
            ]
        ),
        get_behavior_hooks=lambda: [],
        get_self_model_prompt=lambda: "Der Nutzer lebt in Offenbach und interessiert sich fuer Setup-Themen.",
    )
    monkeypatch.setitem(
        sys.modules,
        "memory.memory_system",
        SimpleNamespace(memory_manager=fake_memory_manager),
    )

    result = classify_meta_task(
        "lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht",
        action_count=0,
    )

    assert result["meta_request_frame"]["task_domain"] == "docs_status"
    assert result["preference_memory_selection"]["selected"] == []
    context_slots = result["meta_context_bundle"]["context_slots"]
    assert all(slot["slot"] != "preference_memory" for slot in context_slots)
    assert result["specialist_context_seed"]["user_preferences"] == []


def test_classify_meta_task_marks_topic_shift_for_new_unrelated_task():
    result = classify_meta_task(
        "lass uns jetzt ueber browser automation reden",
        action_count=0,
        conversation_state={
            "session_id": "canvas_d04",
            "active_topic": "aktuelle Weltlage und News-Qualitaet",
            "active_goal": "Live-News besser einschaetzen",
            "open_loop": "Reuters zuerst pruefen",
        },
    )

    assert result["topic_shift_detected"] is True
    transition = result["topic_state_transition"]
    assert transition["previous_topic"] == "aktuelle Weltlage und News-Qualitaet"
    assert "browser automation" in transition["next_topic"].lower()
    assert result["meta_context_bundle"]["open_loop"] == ""


def test_classify_meta_task_resumes_open_loop_for_first_option_followup():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_d04_options "
        "last_user: soll ich fuer amsterdam lieber mit dem zug oder mit dem auto fahren "
        "pending_followup_prompt: Waehle eine der zwei Optionen und ich arbeite sie aus "
        "# CURRENT USER QUERY die erste option"
    )

    result = classify_meta_task(
        query,
        action_count=0,
        conversation_state={
            "session_id": "canvas_d04_options",
            "active_topic": "Amsterdam Reisevergleich",
            "active_goal": "Beste Reiseoption zwischen Zug und Auto finden",
            "open_loop": "Waehle eine der zwei Optionen und ich arbeite sie aus",
            "next_expected_step": "Waehle eine Option",
        },
    )

    assert result["dominant_turn_type"] == "handover_resume"
    assert result["response_mode"] == "resume_open_loop"
    assert result["topic_shift_detected"] is False
    assert result["topic_state_transition"]["open_loop_state"] == "resumed"


def test_classify_meta_task_keeps_topic_for_live_news_reframing_followup():
    query = (
        "# FOLLOW-UP CONTEXT last_agent: meta session_id: canvas_d04_news "
        "last_user: wie stehts um die aktuelle weltlage "
        "pending_followup_prompt: Soll ich fuer aktuelle Nachrichten Reuters und AP zuerst pruefen? "
        "# CURRENT USER QUERY so aber mit live-news"
    )

    result = classify_meta_task(
        query,
        action_count=0,
        conversation_state={
            "session_id": "canvas_d04_news",
            "active_topic": "aktuelle Weltlage und News-Qualitaet",
            "active_goal": "belastbare aktuelle Nachrichten",
            "open_loop": "Reuters und AP zuerst pruefen",
            "next_expected_step": "schnelle Live-Recherche mit Agenturquellen",
        },
    )

    assert result["dominant_turn_type"] == "followup"
    assert result["response_mode"] == "resume_open_loop"
    assert result["topic_shift_detected"] is False
    assert result["topic_state_transition"]["next_topic"] == "aktuelle Weltlage und News-Qualitaet"


def test_classify_meta_task_uses_active_plan_next_step_for_resume_followup():
    result = classify_meta_task(
        "und jetzt weiter",
        action_count=0,
        conversation_state={
            "session_id": "canvas_z3_plan",
            "active_topic": "YouTube-Analyse",
            "active_goal": "Videoinhalt sammeln",
            "open_loop": "YouTube-Seite oeffnen",
            "next_expected_step": "YouTube-Seite oeffnen",
            "active_plan": {
                "plan_id": "yt-plan-1",
                "plan_mode": "multi_step_execution",
                "goal": "Videoinhalt sammeln",
                "next_step_id": "research_synthesis",
                "next_step_title": "Quellen und Transcript verdichten",
                "next_step_agent": "research",
                "step_count": 3,
            },
        },
    )

    assert result["response_mode"] == "resume_open_loop"
    assert result["next_step"] == "Quellen und Transcript verdichten"
    assert result["task_decomposition"]["planning_needed"] is True
    assert result["meta_execution_plan"]["next_step_id"] == "research_synthesis"


def test_classify_meta_task_treats_short_contextual_reframe_as_followup_from_state():
    result = classify_meta_task(
        "so aber mit live-news",
        action_count=0,
        conversation_state={
            "session_id": "canvas_d04_reframe",
            "active_topic": "bei news bitte zuerst agenturquellen",
            "active_goal": "bei news bitte zuerst agenturquellen",
            "next_expected_step": "bei news bitte zuerst agenturquellen",
            "turn_type_hint": "preference_update",
        },
        recent_user_turns=["bei news bitte zuerst agenturquellen"],
    )

    assert result["dominant_turn_type"] == "followup"
    assert result["response_mode"] == "resume_open_loop"


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
