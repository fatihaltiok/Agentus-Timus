"""Self-selected tool and agent strategies for lightweight orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class TaskProfile:
    intent: str
    desired_depth: str
    effort_level: str
    risk_level: str
    browser_need: str
    latency_expectation: str
    cost_sensitivity: str
    output_mode: str
    error_recovery_bias: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolAffordance:
    name: str
    kind: str
    cost: str
    latency: str
    reliability: str
    good_for: Tuple[str, ...]
    avoid_when: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["good_for"] = list(self.good_for)
        payload["avoid_when"] = list(self.avoid_when)
        return payload


@dataclass(frozen=True)
class SelectedStrategy:
    strategy_id: str
    strategy_mode: str
    primary_recipe_id: str
    fallback_recipe_id: str
    preferred_tools: Tuple[str, ...]
    fallback_tools: Tuple[str, ...]
    avoid_tools: Tuple[str, ...]
    error_strategy: str
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key in ("preferred_tools", "fallback_tools", "avoid_tools"):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True)
class StrategyErrorSignal:
    error_class: str
    cause_hint: str
    suggested_reaction: str
    prefer_non_browser_fallback: bool = False
    prefer_recipe_id: str = ""
    degrade_ok: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_AFFORDANCE_CATALOG: Dict[str, ToolAffordance] = {
    "executor": ToolAffordance(
        name="executor",
        kind="agent",
        cost="low",
        latency="low",
        reliability="high",
        good_for=("casual_lookup", "quick_summaries", "light_search"),
        avoid_when=("deep_artifact_generation", "multi_step_ui"),
    ),
    "visual": ToolAffordance(
        name="visual",
        kind="agent",
        cost="medium",
        latency="medium",
        reliability="medium",
        good_for=("ui_navigation", "interactive_sites", "state_capture"),
        avoid_when=("casual_lookup", "search_only_tasks"),
    ),
    "research": ToolAffordance(
        name="research",
        kind="agent",
        cost="medium",
        latency="medium",
        reliability="high",
        good_for=("content_extraction", "source_comparison", "transcript_analysis"),
        avoid_when=("very_light_lookup",),
    ),
    "system": ToolAffordance(
        name="system",
        kind="agent",
        cost="low",
        latency="medium",
        reliability="high",
        good_for=("diagnostics", "health_analysis", "log_triage"),
        avoid_when=("browser_tasks",),
    ),
    "shell": ToolAffordance(
        name="shell",
        kind="agent",
        cost="medium",
        latency="medium",
        reliability="medium",
        good_for=("controlled_runtime_probe", "service_actions"),
        avoid_when=("casual_lookup", "high_risk_without_confirmation"),
    ),
    "document": ToolAffordance(
        name="document",
        kind="agent",
        cost="medium",
        latency="medium",
        reliability="high",
        good_for=("artifact_generation", "report_exports"),
        avoid_when=("quick_summary_only",),
    ),
    "search_youtube": ToolAffordance(
        name="search_youtube",
        kind="tool",
        cost="low",
        latency="low",
        reliability="high",
        good_for=("youtube_discovery", "lightweight_scan", "top_results"),
        avoid_when=("full_transcript_extraction",),
    ),
    "get_youtube_video_info": ToolAffordance(
        name="get_youtube_video_info",
        kind="tool",
        cost="low",
        latency="low",
        reliability="high",
        good_for=("video_metadata", "related_videos", "comments_context"),
        avoid_when=("generic_web_search",),
    ),
    "get_youtube_subtitles": ToolAffordance(
        name="get_youtube_subtitles",
        kind="tool",
        cost="low",
        latency="low",
        reliability="medium",
        good_for=("transcript_extraction", "chapter_signals", "content_synthesis"),
        avoid_when=("videos_without_captions",),
    ),
    "search_web": ToolAffordance(
        name="search_web",
        kind="tool",
        cost="low",
        latency="low",
        reliability="medium",
        good_for=("fallback_discovery", "cross_source_search"),
        avoid_when=("direct_ui_state_needed",),
    ),
    "search_news": ToolAffordance(
        name="search_news",
        kind="tool",
        cost="low",
        latency="low",
        reliability="medium",
        good_for=("news_lookup", "current_updates", "headline_scan"),
        avoid_when=("deep_source_verification",),
    ),
    "get_current_location_context": ToolAffordance(
        name="get_current_location_context",
        kind="tool",
        cost="low",
        latency="low",
        reliability="high",
        good_for=("location_context", "where_am_i", "nearby_search_setup"),
        avoid_when=("non_location_tasks",),
    ),
    "search_google_maps_places": ToolAffordance(
        name="search_google_maps_places",
        kind="tool",
        cost="low",
        latency="low",
        reliability="high",
        good_for=("nearby_places", "local_lookup", "maps_search"),
        avoid_when=("global_web_search",),
    ),
    "get_google_maps_place": ToolAffordance(
        name="get_google_maps_place",
        kind="tool",
        cost="low",
        latency="low",
        reliability="medium",
        good_for=("place_details", "opening_hours", "contact_lookup"),
        avoid_when=("broad_discovery_without_place",),
    ),
    "get_google_maps_route": ToolAffordance(
        name="get_google_maps_route",
        kind="tool",
        cost="low",
        latency="low",
        reliability="high",
        good_for=("route_planning", "eta_lookup", "navigation_setup"),
        avoid_when=("non_location_tasks",),
    ),
    "start_deep_research": ToolAffordance(
        name="start_deep_research",
        kind="tool",
        cost="high",
        latency="high",
        reliability="medium",
        good_for=("evidence_heavy_reports", "artifact_focused_research"),
        avoid_when=("casual_lookup", "quick_scan", "soft_latency_budget"),
    ),
    "open_url": ToolAffordance(
        name="open_url",
        kind="tool",
        cost="low",
        latency="low",
        reliability="high",
        good_for=("direct_navigation", "non_interactive_fetch"),
        avoid_when=("forms_and_login",),
    ),
    "fetch_url": ToolAffordance(
        name="fetch_url",
        kind="tool",
        cost="low",
        latency="low",
        reliability="high",
        good_for=("page_fetch", "source_excerpt", "quick_verification"),
        avoid_when=("interactive_login",),
    ),
    "run_command": ToolAffordance(
        name="run_command",
        kind="tool",
        cost="medium",
        latency="medium",
        reliability="medium",
        good_for=("runtime_probe", "controlled_system_checks"),
        avoid_when=("casual_lookup", "unsafe_runtime_actions"),
    ),
}


def build_task_profile(query: str, classification: Dict[str, Any]) -> Dict[str, Any]:
    normalized = str(query or "").strip().lower()
    task_type = str(classification.get("task_type") or "").strip().lower()
    chain = [str(agent).strip().lower() for agent in (classification.get("recommended_agent_chain") or [])]
    needs_document = "document" in chain

    if task_type == "youtube_light_research":
        profile = TaskProfile(
            intent="casual_lookup",
            desired_depth="light",
            effort_level="light",
            risk_level="low",
            browser_need="avoid_if_possible",
            latency_expectation="fast",
            cost_sensitivity="high",
            output_mode="quick_summary",
            error_recovery_bias="switch_tool_then_degrade",
        )
    elif task_type == "simple_live_lookup":
        profile = TaskProfile(
            intent="live_lookup",
            desired_depth="light",
            effort_level="light",
            risk_level="low",
            browser_need="avoid_if_possible",
            latency_expectation="fast",
            cost_sensitivity="high",
            output_mode="quick_summary",
            error_recovery_bias="switch_tool_then_degrade",
        )
    elif task_type == "youtube_content_extraction":
        profile = TaskProfile(
            intent="content_extraction",
            desired_depth="deep",
            effort_level="medium",
            risk_level="medium",
            browser_need="prefer_direct_source",
            latency_expectation="balanced",
            cost_sensitivity="medium",
            output_mode="artifact" if needs_document else "detailed_summary",
            error_recovery_bias="recover_then_continue",
        )
    elif task_type == "web_content_extraction":
        profile = TaskProfile(
            intent="content_extraction",
            desired_depth="medium",
            effort_level="medium",
            risk_level="medium",
            browser_need="prefer_when_source_specific",
            latency_expectation="balanced",
            cost_sensitivity="medium",
            output_mode="summary",
            error_recovery_bias="switch_tool_then_continue",
        )
    elif task_type == "knowledge_research":
        profile = TaskProfile(
            intent="source_research",
            desired_depth="deep" if any(token in normalized for token in ("quellen", "fakten", "news", "studie", "paper")) else "medium",
            effort_level="medium",
            risk_level="low",
            browser_need="avoid_if_possible",
            latency_expectation="balanced",
            cost_sensitivity="medium",
            output_mode="detailed_summary",
            error_recovery_bias="switch_tool_then_continue",
        )
    elif task_type == "multi_stage_web_task":
        profile = TaskProfile(
            intent="interactive_navigation",
            desired_depth="task_completion",
            effort_level="medium",
            risk_level="medium",
            browser_need="required",
            latency_expectation="balanced",
            cost_sensitivity="low",
            output_mode="verified_state",
            error_recovery_bias="inspect_then_retry",
        )
    elif task_type == "system_diagnosis":
        profile = TaskProfile(
            intent="system_diagnosis",
            desired_depth="medium",
            effort_level="medium",
            risk_level="high" if any(token in normalized for token in ("restart", "systemctl", "sudo")) else "medium",
            browser_need="none",
            latency_expectation="balanced",
            cost_sensitivity="medium",
            output_mode="incident_summary",
            error_recovery_bias="observe_then_escalate",
        )
    elif task_type == "location_local_search":
        profile = TaskProfile(
            intent="local_lookup",
            desired_depth="light",
            effort_level="light",
            risk_level="low",
            browser_need="none",
            latency_expectation="fast",
            cost_sensitivity="high",
            output_mode="location_summary",
            error_recovery_bias="switch_tool_then_degrade",
        )
    elif task_type == "location_route":
        profile = TaskProfile(
            intent="route_planning",
            desired_depth="light",
            effort_level="light",
            risk_level="low",
            browser_need="none",
            latency_expectation="fast",
            cost_sensitivity="high",
            output_mode="route_summary",
            error_recovery_bias="switch_tool_then_degrade",
        )
    else:
        profile = TaskProfile(
            intent="general_task",
            desired_depth="medium",
            effort_level="light",
            risk_level="low",
            browser_need="none",
            latency_expectation="balanced",
            cost_sensitivity="medium",
            output_mode="answer",
            error_recovery_bias="degrade_cleanly",
        )

    return profile.to_dict()


def select_tool_affordances(classification: Dict[str, Any], task_profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    task_type = str(classification.get("task_type") or "").strip().lower()
    names: List[str]
    if task_type == "simple_live_lookup":
        names = [
            "executor",
            "search_web",
            "search_news",
            "fetch_url",
            "get_current_location_context",
            "search_google_maps_places",
            "get_google_maps_place",
        ]
    elif task_type == "youtube_light_research":
        names = ["executor", "search_youtube", "search_web", "start_deep_research"]
    elif task_type == "youtube_content_extraction":
        names = [
            "visual",
            "research",
            "document",
            "search_youtube",
            "get_youtube_video_info",
            "get_youtube_subtitles",
            "start_deep_research",
        ]
    elif task_type == "web_content_extraction":
        names = ["visual", "research", "open_url", "search_web"]
    elif task_type == "knowledge_research":
        names = ["research", "search_web", "start_deep_research"]
    elif task_type == "system_diagnosis":
        names = ["system", "shell", "run_command"]
    elif task_type == "location_local_search":
        names = [
            "executor",
            "get_current_location_context",
            "search_google_maps_places",
            "get_google_maps_place",
            "search_web",
        ]
    elif task_type == "location_route":
        names = [
            "executor",
            "get_current_location_context",
            "get_google_maps_route",
            "search_web",
        ]
    elif task_type == "multi_stage_web_task":
        names = ["visual", "open_url", "search_web"]
    else:
        names = ["executor", "research", "search_web"]

    if str(task_profile.get("output_mode") or "") == "artifact" and "document" not in names:
        names.append("document")

    return [_AFFORDANCE_CATALOG[name].to_dict() for name in names if name in _AFFORDANCE_CATALOG]


def select_strategy(
    query: str,
    classification: Dict[str, Any],
    task_profile: Dict[str, Any],
    tool_affordances: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized = str(query or "").strip().lower()
    task_type = str(classification.get("task_type") or "").strip().lower()
    recommended_recipe_id = str(classification.get("recommended_recipe_id") or "").strip()

    if task_type == "simple_live_lookup":
        strategy = SelectedStrategy(
            strategy_id="executor_live_lookup",
            strategy_mode="lightweight_first",
            primary_recipe_id=recommended_recipe_id or "simple_live_lookup",
            fallback_recipe_id="",
            preferred_tools=(
                "get_current_location_context",
                "search_google_maps_places",
                "get_google_maps_place",
                "search_news",
                "search_web",
                "fetch_url",
            ),
            fallback_tools=("search_web",),
            avoid_tools=("start_deep_research", "visual"),
            error_strategy="switch_tool_then_degrade",
            rationale="Aktuelle Alltagsrecherchen zuerst ueber den executor mit direkter Search-/Maps-Toolchain beantworten.",
        )
    elif task_type == "youtube_light_research":
        strategy = SelectedStrategy(
            strategy_id="youtube_lightweight_scan",
            strategy_mode="lightweight_first",
            primary_recipe_id=recommended_recipe_id or "youtube_light_research",
            fallback_recipe_id="",
            preferred_tools=("search_youtube", "executor"),
            fallback_tools=("search_web",),
            avoid_tools=("start_deep_research",),
            error_strategy="switch_tool_then_degrade",
            rationale="Lockere YouTube-Anfrage zuerst mit leichtem Suchpfad beantworten.",
        )
    elif task_type == "youtube_content_extraction":
        fallback_recipe_id = "youtube_search_then_visual" if any(
            token in normalized for token in ("suche", "finde", "relevante video", "erstes video")
        ) else "youtube_research_only"
        strategy = SelectedStrategy(
            strategy_id="layered_youtube_extraction",
            strategy_mode="layered_extraction",
            primary_recipe_id=recommended_recipe_id or "youtube_content_extraction",
            fallback_recipe_id=fallback_recipe_id,
            preferred_tools=("get_youtube_video_info", "get_youtube_subtitles", "search_youtube"),
            fallback_tools=("search_web", "start_deep_research"),
            avoid_tools=(),
            error_strategy="recover_then_continue",
            rationale="Video-Inhalt erst direkt und strukturiert extrahieren, erst spaeter auf teurere Pfade gehen.",
        )
    elif task_type == "web_content_extraction":
        strategy = SelectedStrategy(
            strategy_id="web_source_then_summarize",
            strategy_mode="source_first",
            primary_recipe_id=recommended_recipe_id or "web_visual_research_summary",
            fallback_recipe_id="web_research_only",
            preferred_tools=("open_url", "search_web", "research"),
            fallback_tools=("search_web",),
            avoid_tools=("start_deep_research",),
            error_strategy="switch_tool_then_continue",
            rationale="Web-Inhalt zuerst direkt lesen oder erreichen, dann verdichten.",
        )
    elif task_type == "knowledge_research":
        strategy = SelectedStrategy(
            strategy_id="knowledge_research_orchestration",
            strategy_mode="source_first",
            primary_recipe_id=recommended_recipe_id or "knowledge_research",
            fallback_recipe_id="",
            preferred_tools=("research", "search_web"),
            fallback_tools=("start_deep_research",),
            avoid_tools=("visual",),
            error_strategy="switch_tool_then_continue",
            rationale="Externe Fakten- und Quellenfragen zuerst ueber den Research-Pfad mit leichter Web-Suche beantworten.",
        )
    elif task_type == "system_diagnosis":
        strategy = SelectedStrategy(
            strategy_id="observe_before_action",
            strategy_mode="diagnose_first",
            primary_recipe_id=recommended_recipe_id or "system_diagnosis",
            fallback_recipe_id="system_shell_probe_first",
            preferred_tools=("system", "run_command"),
            fallback_tools=("shell",),
            avoid_tools=(),
            error_strategy="observe_then_escalate",
            rationale="Systemfehler zuerst beobachten und nur dann in Shell-Probes kippen, wenn Diagnose stockt.",
        )
    elif task_type == "location_local_search":
        strategy = SelectedStrategy(
            strategy_id="location_context_then_maps",
            strategy_mode="lightweight_first",
            primary_recipe_id=recommended_recipe_id or "location_local_search",
            fallback_recipe_id="",
            preferred_tools=("get_current_location_context", "search_google_maps_places", "get_google_maps_place"),
            fallback_tools=("search_web",),
            avoid_tools=("start_deep_research",),
            error_strategy="switch_tool_then_degrade",
            rationale="Lokale Anfragen zuerst aus aktuellem Geraetestandort und leichter Maps-Suche beantworten.",
        )
    elif task_type == "location_route":
        strategy = SelectedStrategy(
            strategy_id="location_context_then_route",
            strategy_mode="lightweight_first",
            primary_recipe_id=recommended_recipe_id or "location_route",
            fallback_recipe_id="",
            preferred_tools=("get_current_location_context", "get_google_maps_route"),
            fallback_tools=("search_web",),
            avoid_tools=("start_deep_research",),
            error_strategy="switch_tool_then_degrade",
            rationale="Routenanfragen zuerst direkt aus aktuellem Geraetestandort und echter Directions-Berechnung beantworten.",
        )
    elif task_type == "multi_stage_web_task":
        strategy = SelectedStrategy(
            strategy_id="interactive_visual_flow",
            strategy_mode="stateful_navigation",
            primary_recipe_id=recommended_recipe_id,
            fallback_recipe_id="",
            preferred_tools=("visual", "open_url"),
            fallback_tools=("search_web",),
            avoid_tools=("start_deep_research",),
            error_strategy="inspect_then_retry",
            rationale="Interaktive Web-Aufgaben brauchen verifizierte UI-Zustaende statt schwerer Recherche.",
        )
    else:
        strategy = SelectedStrategy(
            strategy_id="general_lightweight_answer",
            strategy_mode="lightweight_first",
            primary_recipe_id=recommended_recipe_id,
            fallback_recipe_id="",
            preferred_tools=("executor", "search_web"),
            fallback_tools=("research",),
            avoid_tools=("start_deep_research",),
            error_strategy=str(task_profile.get("error_recovery_bias") or "degrade_cleanly"),
            rationale="Allgemeine Aufgaben zuerst mit leichtem Pfad beantworten.",
        )

    return strategy.to_dict()


def classify_strategy_error(
    *,
    handoff: Dict[str, Any],
    failed_stage: Dict[str, Any],
) -> Dict[str, Any]:
    error_text = str(failed_stage.get("error") or "").strip().lower()
    failed_agent = str(failed_stage.get("agent") or "").strip().lower()
    task_type = str(handoff.get("task_type") or "").strip().lower()
    site_kind = str(handoff.get("site_kind") or "").strip().lower()
    strategy = dict(handoff.get("selected_strategy") or {})
    fallback_recipe_id = str(strategy.get("fallback_recipe_id") or "").strip()

    if any(token in error_text for token in ("status=11", "segv", "core dumped", "service unavailable", "backend down")):
        signal = StrategyErrorSignal(
            error_class="backend_runtime_failure",
            cause_hint="Backend- oder nativer Laufzeitfehler auf einem schweren Pfad.",
            suggested_reaction="avoid_heavy_path_and_switch",
            prefer_non_browser_fallback=True,
            prefer_recipe_id=fallback_recipe_id,
            degrade_ok=False,
        )
    elif any(token in error_text for token in ("failed to fetch", "timeout", "connection", "429", "tempor", "net::")):
        signal = StrategyErrorSignal(
            error_class="transport_failure",
            cause_hint="Transport- oder Netzfehler beim aktuellen Pfad.",
            suggested_reaction="switch_tool_then_retry",
            prefer_non_browser_fallback=failed_agent == "visual",
            prefer_recipe_id=fallback_recipe_id,
            degrade_ok=True,
        )
    elif failed_agent == "visual" or any(
        token in error_text
        for token in ("konnte nicht verifiziert", "nicht geladen", "selector", "login-maske", "videoseite")
    ):
        signal = StrategyErrorSignal(
            error_class="browser_runtime_failure",
            cause_hint="UI- oder Browserzustand war nicht robust erreichbar.",
            suggested_reaction="switch_to_non_browser_fallback",
            prefer_non_browser_fallback=True,
            prefer_recipe_id=fallback_recipe_id,
            degrade_ok=task_type in {"youtube_content_extraction", "web_content_extraction"},
        )
    elif any(token in error_text for token in ("untertitel", "transcript", "caption", "captions", "no transcript")):
        signal = StrategyErrorSignal(
            error_class="missing_transcript",
            cause_hint="Das Video lieferte keinen nutzbaren Transcript-/Caption-Pfad.",
            suggested_reaction="use_metadata_and_context_fallback",
            prefer_non_browser_fallback=False,
            prefer_recipe_id="youtube_research_only" if site_kind == "youtube" else fallback_recipe_id,
            degrade_ok=True,
        )
    elif any(token in error_text for token in ("pdf", "anhang", "attachment", "artifact")):
        signal = StrategyErrorSignal(
            error_class="artifact_generation_failure",
            cause_hint="Die Artefakterzeugung ist fehlgeschlagen, nicht die inhaltliche Recherche.",
            suggested_reaction="preserve_content_and_degrade_artifact",
            prefer_non_browser_fallback=False,
            prefer_recipe_id="",
            degrade_ok=True,
        )
    elif any(token in error_text for token in ("leer", "unvollständig", "unvollstaendig", "zu wenig belastbare quellen")):
        signal = StrategyErrorSignal(
            error_class="weak_result_signal",
            cause_hint="Der aktuelle Pfad lieferte zu schwache oder unvollständige Evidenz.",
            suggested_reaction="switch_strategy_or_validate",
            prefer_non_browser_fallback=False,
            prefer_recipe_id=fallback_recipe_id,
            degrade_ok=True,
        )
    elif any(token in error_text for token in ("kein aktueller mobil-standort", "runtime-standort", "permission denied", "missing_query")):
        signal = StrategyErrorSignal(
            error_class="missing_device_location",
            cause_hint="Es fehlt ein aktueller oder nutzbarer Handy-Standort fuer lokale Suche.",
            suggested_reaction="degrade_or_request_location_refresh",
            prefer_non_browser_fallback=True,
            prefer_recipe_id="",
            degrade_ok=True,
        )
    else:
        signal = StrategyErrorSignal(
            error_class="unknown_failure",
            cause_hint="Unklassifizierter Fehler im aktuellen Pfad.",
            suggested_reaction=str(strategy.get("error_strategy") or "degrade_cleanly"),
            prefer_non_browser_fallback=False,
            prefer_recipe_id=fallback_recipe_id,
            degrade_ok=True,
        )

    return signal.to_dict()
