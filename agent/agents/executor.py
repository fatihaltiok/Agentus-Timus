"""ExecutorAgent - Schnelle einfache Tasks."""

from __future__ import annotations

import re
from typing import Any

from agent.base_agent import BaseAgent
from agent.prompts import EXECUTOR_PROMPT_TEMPLATE
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff
from orchestration.approval_auth_contract import (
    derive_user_action_blocker_reason,
    normalize_phase_d_workflow_payload,
)
from orchestration.specialist_context import (
    assess_specialist_context_alignment,
    extract_specialist_context_from_handoff_data,
    format_specialist_signal_response,
    render_specialist_context_block,
)
from orchestration.specialist_step_package import (
    extract_specialist_step_package_from_handoff_data,
    render_specialist_step_package_block,
)
from utils.location_local_intent import analyze_location_local_intent, analyze_location_route_intent
from utils.location_route import build_google_maps_directions_url, normalize_route_travel_mode

_SMALLTALK_PATTERNS = (
    r"^\s*(?:hey|hi|hallo|servus|moin|guten\s+tag|guten\s+morgen|guten\s+abend)(?:\s+timus)?[\s,!\.?]*$",
    r"^\s*(?:timus[\s,!\.?]*)?(?:wie geht'?s|was geht|na)[\s,!\.?]*$",
    r"^\s*(?:hey|hi|hallo|servus|moin)(?:\s+timus)?[\s,!\.?]+(?:wie geht'?s|was geht|na)[\s,!\.?]*$",
)

_SELF_STATUS_PATTERNS = (
    r"\bwas hast du (fuer|für) probleme\b",
    r"\bwelche probleme hast du\b",
    r"\bwas ist los\b",
    r"\bwo hakt es\b",
    r"\bwelche probleme gibt es\b",
    r"\bsag du es mir\b",
)

_SELF_REMEDIATION_PATTERNS = (
    r"\bwas kannst du dagegen tun\b",
    r"\bund was kannst du dagegen tun\b",
    r"\bwas tust du dagegen\b",
    r"\bwie behebst du das\b",
    r"\bwie willst du das beheben\b",
    r"\bund was jetzt\b",
    r"\bwas machst du jetzt dagegen\b",
)

_SELF_PRIORITY_PATTERNS = (
    r"\bwas davon machst du zuerst\b",
    r"\bwomit faengst du an\b",
    r"\bwomit fängst du an\b",
    r"\bwas zuerst\b",
    r"\bwelchen schritt zuerst\b",
    r"\bwie priorisierst du das\b",
    r"\bwas machst du als erstes\b",
)

_SELF_RECALL_PATTERNS = (
    r"\bwie war nochmal\b",
    r"\bwas war nochmal\b",
    r"\berinner\b",
    r"\bwie hattest du\b",
    r"\bwas hattest du\b",
    r"\bnochmal erklaer\b",
    r"\bnochmal erklär\b",
)

_CAPABILITY_LEARNING_PATTERNS = (
    r"\bk[oö]nntest du dir das beibringen\b",
    r"\bk[oö]nntest du das lernen\b",
    r"\bwie k[oö]nntest du das lernen\b",
    r"\bwie k[oö]nntest du dir das beibringen\b",
    r"\bwas br[aä]uchtest du daf[uü]r\b",
    r"\bwas m[uü]sstest du daf[uü]r haben\b",
    r"\bwie w[uü]rde das gehen\b",
    r"\bkannst du dir das aneignen\b",
)

_YOUTUBE_GENERIC_PATTERNS = (
    r"^hey\s+timus[, ]*",
    r"^herr\s+thimus[, ]*",
    r"^herr\s+timus[, ]*",
    r"^timus[, ]*",
    r"\bauf youtube\b",
    r"\bbei youtube\b",
    r"\bin youtube\b",
    r"\byoutube\s+rein\b",
    r"\bmal\b",
    r"\bkurz\b",
    r"\brein\b",
    r"\bso\b",
    r"\bgibt'?s\b",
    r"\bgibt es\b",
    r"\bwas gibt'?s neues\b",
    r"\bwas gibt es neues\b",
    r"\bwas es so\b",
    r"\bschau mal\b",
    r"\bzeig mir\b",
    r"\bfinde mir\b",
    r"\bfuer mich\b",
    r"\bfür mich\b",
    r"\bbitte\b",
    r"\bnur dinge die\b",
    r"\bnur videos die\b",
    r"\bnur inhalte die\b",
    r"\bgeben kann\b",
    r"\binteressant(?:es|e)?\b",
    r"\brelavant(?:e)?\s+sind\b",
    r"\brelevant(?:e)?\s+sind\b",
    r"\bauch\s+englisch(?:[- ]?sprachige?)?\b",
    r"\benglisch[- ]?sprachige?\b",
    r"\bauf englisch\b",
)

_YOUTUBE_DIRECT_URL_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\S*|youtu\.be/\S+)", re.IGNORECASE)

_YOUTUBE_FACT_CHECK_HINTS = (
    "ob da etwas wahres dran ist",
    "ob da was wahres dran ist",
    "wahres dran",
    "ob das stimmt",
    "stimmt das",
    "stimmt es",
    "faktencheck",
    "fact check",
    "behauptung",
    "behauptet",
    "gerücht",
    "geruecht",
)

_YOUTUBE_EDGE_FILLER_TOKENS = {
    "was",
    "es",
    "die",
    "das",
    "der",
    "den",
    "dem",
    "ein",
    "eine",
    "einer",
    "neues",
    "neu",
    "aktuelles",
    "aktuell",
    "gibt",
    "gibts",
    "gibt's",
    "videos",
    "video",
    "kurz",
    "rein",
    "nur",
    "mich",
    "mir",
    "dinge",
    "inhalte",
    "beitraege",
    "beiträge",
    "relavant",
    "relevant",
    "sprachige",
}

_YOUTUBE_DE_TO_EN_TERMS: dict[str, str] = {
    "ki": "AI",
    "künstliche intelligenz": "artificial intelligence",
    "agenten": "agents",
    "agent": "agent",
    "entwicklungen": "developments",
    "entwicklung": "development",
    "neuigkeiten": "news",
    "nachrichten": "news",
    "modelle": "models",
    "modell": "model",
    "sprachmodell": "language model",
    "sprachmodelle": "language models",
    "selbstlernend": "self-learning",
    "autonomie": "autonomy",
}


_YOUTUBE_EN_FILLER_TOKENS = {
    "schau", "was", "es", "gibt", "neues", "neu", "neue", "aktuell",
    "aktuelles", "bereich", "zum", "thema", "selbst", "und",
    "die", "der", "das", "auch", "im", "in", "an", "auf",
    "mit", "von", "für", "fuer", "zu",
}

_SIMPLE_LOOKUP_HARD_RESEARCH_MARKERS = (
    "tiefenrecherche",
    "tiefen recherche",
    "tiefe recherche",
    "deep research",
    "quellen",
    "studie",
    "studien",
    "paper",
    "papers",
    "bericht",
    "pdf",
    "docx",
    "analysiere",
    "maximal viel",
    "extrahiere",
)

_SIMPLE_LOOKUP_WEATHER_MARKERS = ("wetter", "temperatur", "regen", "sonne", "wind")
_SIMPLE_LOOKUP_NEWS_MARKERS = ("news", "nachrichten", "neuigkeiten", "was gibt es neues", "was gibts neues", "neues aus")
_SIMPLE_LOOKUP_SCIENCE_MARKERS = ("wissenschaft", "forschung", "studie", "studien", "science")
_SIMPLE_LOOKUP_PRICING_MARKERS = ("preis", "preise", "pricing", "kosten", "vergleich", "tabelle", "tokenpreise", "modellpreise")
_SIMPLE_LOOKUP_PERSON_MARKERS = ("wer ist", "wie heißt", "wie heisst", "ceo", "präsident", "praesident", "vorstand", "gründer", "gruender")
_SIMPLE_LOOKUP_CINEMA_MARKERS = ("kino", "kinoprogramm", "film", "filme", "filmstarts")
_SIMPLE_LOOKUP_LOCAL_PLACE_QUERY_MAP: dict[str, str] = {
    "café": "Cafes",
    "cafés": "Cafes",
    "cafe": "Cafes",
    "cafes": "Cafes",
    "kaffee": "Cafes",
    "restaurant": "Restaurants",
    "restaurants": "Restaurants",
    "bar": "Bars",
    "bars": "Bars",
    "apotheke": "Apotheken",
    "apotheken": "Apotheken",
    "supermarkt": "Supermaerkte",
    "supermärkte": "Supermaerkte",
    "supermaerkte": "Supermaerkte",
    "bäckerei": "Baeckereien",
    "baeckerei": "Baeckereien",
    "bäckereien": "Baeckereien",
    "baeckereien": "Baeckereien",
}
_SIMPLE_LOOKUP_FRESHNESS_MARKERS = ("aktuell", "aktuelle", "aktuellen", "heute", "jetzt", "live", "neueste", "latest", "current", "gerade")
_LOOKUP_EXTRACTION_FOLLOWUP_PATTERNS = (
    r"\bhol(?:e)?\b.*\bheraus\b",
    r"\bzieh(?:e)?\b.*\bheraus\b",
    r"\blist(?:e)?\b.*\baus\b",
    r"\bextrah(?:ier|iere)\b",
    r"\bfass\b.*\bzusammen\b",
    r"\bmach(?:e)?\b.*\btabelle\b",
    r"\btabell(?:e|arisch)\b",
)
_LOOKUP_PRICE_SIGNAL_PATTERNS = (
    r"\$ ?\d",
    r"\b(?:input|output|cached)[ -]?(?:preis|price|token)s?\b",
    r"\b\d+(?:[.,]\d+)?\s*(?:usd|eur|euro)\b",
    r"/\s*1m\b",
    r"/\s*1k\b",
)
_LOOKUP_MODEL_SIGNAL_PATTERNS = (
    r"\bgpt[- ]?\d",
    r"\bclaude\b",
    r"\bgemini\b",
    r"\bdeepseek\b",
    r"\bglm[- ]?\d",
    r"\bqwen\b",
    r"\bgrok\b",
    r"\bkimi\b",
    r"\bminimax\b",
    r"\bo[34](?:-mini)?\b",
)
_LOOKUP_ARTIFACT_FORMAT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("xlsx", r"\b(?:xlsx|excel)\b"),
    ("csv", r"\bcsv\b"),
    ("txt", r"\b(?:txt|textdatei|text datei|plaintext|rohtext)\b"),
)
_LOOKUP_PRICING_OUTPUT_NOISE_PATTERNS = (
    r"\berstelle(?:\s+mir)?\b",
    r"\bmach(?:e)?(?:\s+mir)?\b",
    r"\bzeige(?:\s+mir)?\b",
    r"\bliste(?:\s+mir)?\b",
    r"\bsuche(?:\s+da)?\b",
    r"\bhol(?:e)?\b",
    r"\bzieh(?:e)?\b",
    r"\baus\b",
    r"\bheraus\b",
    r"\btxt\b",
    r"\bdatei\b",
    r"\btextdatei\b",
    r"\btabelle\b",
    r"\bliste\b",
)

_LLM_PRICING_MARKERS = (
    "llm",
    "llms",
    "api",
    "token",
    "tokens",
    "input",
    "output",
    "cached",
    "sprachmodell",
    "sprachmodelle",
    "ki-modell",
    "ki-modelle",
    "ki modell",
    "ki modelle",
    "language model",
    "language models",
    "foundation model",
    "foundation models",
    "openai",
    "anthropic",
    "claude",
    "gpt",
    "gemini",
    "deepseek",
    "qwen",
    "grok",
    "kimi",
    "glm",
    "mistral",
    "openrouter",
)
_LOOKUP_PRICE_VALUE_MARKERS = (
    "preis-leistung",
    "preis leistung",
    "fuer sein geld",
    "für sein geld",
    "am meisten fuer sein geld",
    "am meisten für sein geld",
    "besser fuer sein geld",
    "besser für sein geld",
)
_PRICING_PROVIDER_HINTS: dict[str, tuple[str, ...]] = {
    "OpenAI": ("openai", "gpt", "chatgpt", "o3", "o4"),
    "Anthropic": ("anthropic", "claude"),
    "Google": ("google", "gemini"),
    "DeepSeek": ("deepseek",),
    "Qwen": ("qwen", "alibaba"),
    "Zhipu GLM": ("zhipu", "glm"),
    "Kimi": ("kimi", "moonshot"),
    "MiniMax": ("minimax",),
    "Baidu ERNIE": ("baidu", "ernie"),
}
_CHINESE_PRICING_PROVIDERS = ("DeepSeek", "Qwen", "Zhipu GLM", "Kimi", "MiniMax", "Baidu ERNIE")


def _youtube_translate_query(query: str) -> str:
    """Einfache DE→EN Übersetzung für KI-Kernbegriffe + Bereinigung verbliebener Filler."""
    result = query.lower()
    for de, en in sorted(_YOUTUBE_DE_TO_EN_TERMS.items(), key=lambda x: -len(x[0])):
        result = re.sub(r"\b" + re.escape(de) + r"\b", en, result, flags=re.IGNORECASE)
    # Verbliebene deutsche Filler-Tokens entfernen die nicht übersetzt wurden
    tokens = result.split()
    cleaned = [t for t in tokens if t not in _YOUTUBE_EN_FILLER_TOKENS]
    # Edge-Filler an Wortgrenzen trimmen
    while cleaned and cleaned[0] in _YOUTUBE_EN_FILLER_TOKENS:
        cleaned.pop(0)
    while cleaned and cleaned[-1] in _YOUTUBE_EN_FILLER_TOKENS:
        cleaned.pop()
    return " ".join(cleaned).strip()


def _detect_youtube_language_preference(text: str) -> list[str]:
    """Erkennt ob der Nutzer explizit englische Inhalte möchte."""
    normalized = str(text or "").lower()
    wants_english = any(m in normalized for m in (
        "englisch", "englischsprachig", "english", "auf englisch", "in english",
    ))
    if wants_english:
        return ["de", "en"]
    return ["de"]


class ExecutorAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(EXECUTOR_PROMPT_TEMPLATE, tools_description_string, 30, "executor")

    def _build_executor_handoff_context(self, handoff: DelegationHandoff | None) -> str:
        if not handoff:
            return ""

        lines: list[str] = ["# STRUKTURIERTER EXECUTOR-HANDOFF"]
        if handoff.expected_output:
            lines.append(f"Erwarteter Output: {handoff.expected_output}")
        if handoff.success_signal:
            lines.append(f"Erfolgssignal: {handoff.success_signal}")
        if handoff.constraints:
            lines.append("Constraints: " + " | ".join(handoff.constraints))

        specialist_context_payload = extract_specialist_context_from_handoff_data(handoff.handoff_data)
        specialist_context = render_specialist_context_block(
            specialist_context_payload,
            alignment=assess_specialist_context_alignment(
                current_task=handoff.handoff_data.get("original_user_task") or handoff.goal,
                payload=specialist_context_payload,
            ),
        )
        if specialist_context:
            lines.append(specialist_context)
        specialist_step_package = render_specialist_step_package_block(
            extract_specialist_step_package_from_handoff_data(handoff.handoff_data)
        )
        if specialist_step_package:
            lines.append(specialist_step_package)

        for key, label in (
            ("task_type", "Task-Typ"),
            ("recipe_id", "Rezept"),
            ("stage_id", "Stage"),
            ("site_kind", "Seitenklasse"),
            ("strategy_id", "Strategie"),
            ("strategy_mode", "Strategiemodus"),
            ("error_strategy", "Fehlerstrategie"),
            ("preferred_search_tool", "Bevorzugtes Suchtool"),
            ("preferred_tools", "Bevorzugte Tools"),
            ("fallback_tools", "Fallback-Tools"),
            ("avoid_tools", "Zu vermeidende Tools"),
            ("search_mode", "Suchmodus"),
            ("max_results", "Max Ergebnisse"),
            ("avoid_deep_research", "Deep-Research vermeiden"),
            ("workspace_root", "Workspace-Root"),
            ("project_root", "Projekt-Root"),
            ("previous_stage_result", "Vorheriges Stage-Ergebnis"),
            ("previous_blackboard_key", "Blackboard-Key"),
        ):
            value = handoff.handoff_data.get(key)
            if value:
                lines.append(f"{label}: {value}")
        return "\n".join(lines)

    def _notify_delegation_progress(self, stage: str, **payload: Any) -> None:
        callback = getattr(self, "_delegation_progress_callback", None)
        if not callable(callback):
            return
        try:
            callback(stage=stage, payload=payload)
            return
        except TypeError:
            pass
        try:
            callback(stage, payload)
            return
        except TypeError:
            pass
        try:
            callback(stage)
        except Exception:
            return

    def _emit_user_action_blocker(self, payload: Any, *, stage: str = "user_action_required") -> None:
        if not isinstance(payload, dict):
            return
        normalized_payload = normalize_phase_d_workflow_payload(payload)
        if not normalized_payload and not (payload.get("auth_required") or payload.get("user_action_required")):
            return
        effective_payload = normalized_payload or dict(payload)
        blocker_reason = derive_user_action_blocker_reason(effective_payload)
        self._notify_delegation_progress(
            stage,
            kind="blocker",
            blocker_reason=blocker_reason,
            message=str(effective_payload.get("error") or effective_payload.get("message") or "Nutzeraktion erforderlich.").strip(),
            user_action_required=str(effective_payload.get("user_action_required") or "").strip(),
            platform=str(effective_payload.get("platform") or "").strip(),
            service=str(effective_payload.get("service") or "").strip(),
            url=str(effective_payload.get("url") or "").strip(),
            tool_status=str(effective_payload.get("status") or "").strip(),
            workflow_id=str(effective_payload.get("workflow_id") or "").strip(),
            workflow_kind=str(effective_payload.get("workflow_kind") or "").strip(),
            workflow_reason=str(effective_payload.get("reason") or "").strip(),
            approval_scope=str(effective_payload.get("approval_scope") or "").strip(),
            resume_hint=str(effective_payload.get("resume_hint") or "").strip(),
            challenge_type=str(effective_payload.get("challenge_type") or "").strip(),
            auth_required=bool(effective_payload.get("auth_required")),
            approval_required=bool(effective_payload.get("approval_required")),
            awaiting_user=bool(effective_payload.get("awaiting_user")),
            challenge_required=bool(effective_payload.get("challenge_required")),
        )

    @staticmethod
    def _recover_user_query(task_text: str) -> str:
        text = str(task_text or "").strip()
        if not text:
            return ""
        original_user_match = re.search(
            r"^\s*-\s*original_user_task:\s*(.+?)(?=^\s*-\s*[a-z_]+:|\n\s*#\s*task\b|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )
        if original_user_match:
            recovered = original_user_match.group(1).strip()
            if recovered:
                text = recovered
        current_query_match = re.search(
            r"#\s*current user query\s*(.+)$",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if current_query_match:
            recovered = current_query_match.group(1).strip()
            if recovered:
                return recovered
        match = re.search(r"nutzeranfrage:\s*(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            recovered = match.group(1).strip()
            if recovered:
                text = recovered
        text = re.sub(
            (
                r"^\s*#\s*live location context\b.*?"
                r"(?:use this location only for nearby, routing, navigation, or explicit place-context tasks\.?\s*|(?=\n\s*\n)|\Z)"
            ),
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()
        if text:
            return text
        lowered = text.lower()
        if lowered.startswith("antworte ausschliesslich auf deutsch") or lowered.startswith(
            "antworte ausschließlich auf deutsch"
        ):
            return ""
        return text

    @staticmethod
    def _is_simple_live_lookup_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_HARD_RESEARCH_MARKERS):
            return False
        if analyze_location_route_intent(normalized).is_route_request:
            return False
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_WEATHER_MARKERS):
            return True
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_PRICING_MARKERS):
            return True
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_PERSON_MARKERS):
            return True
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_CINEMA_MARKERS):
            return True
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_LOCAL_PLACE_QUERY_MAP):
            return True
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_NEWS_MARKERS):
            return True
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_SCIENCE_MARKERS):
            return True
        lookup_markers = (
            "preis",
            "preise",
            "pricing",
            "news",
            "nachrichten",
            "wetter",
            "film",
            "kino",
            "modell",
            "modelle",
        )
        return any(marker in normalized for marker in _SIMPLE_LOOKUP_FRESHNESS_MARKERS) and any(
            marker in normalized for marker in lookup_markers
        )

    @classmethod
    def _infer_simple_live_lookup_category(cls, task: str, *, context_seed: str = "") -> str:
        normalized = str(task or "").strip().lower()
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_WEATHER_MARKERS):
            return "weather"
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_LOCAL_PLACE_QUERY_MAP):
            return "local_places"
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_CINEMA_MARKERS):
            return "cinema"
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_SCIENCE_MARKERS):
            return "science_news"
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_NEWS_MARKERS):
            return "news"
        if cls._is_llm_pricing_query(normalized, context_seed=context_seed):
            return "pricing"
        if any(marker in normalized for marker in _SIMPLE_LOOKUP_PERSON_MARKERS):
            return "person_lookup"
        return "web_lookup"

    @staticmethod
    def _truncate_text(text: Any, limit: int = 280) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: max(0, limit - 3)].rstrip() + "..."

    @classmethod
    def _infer_simple_live_lookup_local_query(cls, user_task: str) -> str:
        normalized = str(user_task or "").strip().lower()
        for marker, canonical in _SIMPLE_LOOKUP_LOCAL_PLACE_QUERY_MAP.items():
            if marker in normalized:
                return canonical
        return ""

    @staticmethod
    def _task_mentions_explicit_place(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        return any(
            marker in normalized
            for marker in (
                " in ",
                " bei ",
                " um ",
                " nahe ",
                " nähe ",
                " naehe ",
                " frankfurt",
                "offenbach",
                "berlin",
                "münchen",
                "muenchen",
                "hamburg",
                "köln",
                "koeln",
            )
        )

    @staticmethod
    def _is_lookup_result_extraction_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 18:
            return False
        return any(re.search(pattern, normalized) for pattern in _LOOKUP_EXTRACTION_FOLLOWUP_PATTERNS)

    @staticmethod
    def _extract_urls_from_context(task_text: str, *, limit: int = 4) -> list[str]:
        text = str(task_text or "")
        if not text:
            return []
        matches = re.findall(r"https?://[^\s|]+", text, flags=re.IGNORECASE)
        urls: list[str] = []
        seen: set[str] = set()
        for raw in matches:
            cleaned = str(raw).strip().rstrip(".,);]>\"'")
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            urls.append(cleaned)
            if len(urls) >= limit:
                break
        return urls

    @staticmethod
    def _contextual_lookup_seed(topic_recall: list[str], recent_assistant_replies: list[str]) -> str:
        candidates = [*topic_recall, *recent_assistant_replies]
        for item in candidates:
            cleaned = re.sub(r"https?://\S+", " ", str(item or ""))
            cleaned = re.sub(r"\b(?:assistant|user|executor|meta)\s*:\s*", " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" |-")
            if len(cleaned) >= 20:
                return cleaned[:180]
        return ""

    @classmethod
    def _infer_lookup_artifact_format(cls, task: str) -> str:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return ""
        for format_name, pattern in _LOOKUP_ARTIFACT_FORMAT_PATTERNS:
            if re.search(pattern, normalized):
                return format_name
        return ""

    @classmethod
    def _strip_lookup_output_request_terms(cls, task: str) -> str:
        cleaned = str(task or "").strip().lower()
        for pattern in _LOOKUP_PRICING_OUTPUT_NOISE_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bund\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\banschlie(?:ss|ß)end\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
        return cleaned

    @classmethod
    def _infer_pricing_provider_focus(cls, task: str, *, context_seed: str = "") -> list[str]:
        normalized = f"{task or ''} {context_seed or ''}".lower()
        providers: list[str] = []
        seen: set[str] = set()
        if any(marker in normalized for marker in ("chines", "china", "chinesisch", "chinesichen")):
            for provider in _CHINESE_PRICING_PROVIDERS:
                providers.append(provider)
                seen.add(provider)
        for provider, aliases in _PRICING_PROVIDER_HINTS.items():
            if any(alias in normalized for alias in aliases) and provider not in seen:
                providers.append(provider)
                seen.add(provider)
        return providers

    @classmethod
    def _is_llm_pricing_query(cls, task: str, *, context_seed: str = "") -> bool:
        normalized = f"{task or ''} {context_seed or ''}".lower()
        if not any(marker in normalized for marker in _SIMPLE_LOOKUP_PRICING_MARKERS):
            return False
        if any(marker in normalized for marker in _LLM_PRICING_MARKERS):
            return True
        return any(re.search(pattern, normalized) for pattern in _LOOKUP_MODEL_SIGNAL_PATTERNS)

    @classmethod
    def _extract_pricing_lines_from_text(cls, text: str) -> list[str]:
        raw_text = str(text or "")
        if not raw_text:
            return []
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines()]
        lines = [line for line in lines if line]
        extracted: list[str] = []
        seen: set[str] = set()
        for line in lines:
            lower = line.lower()
            has_price_signal = any(re.search(pattern, lower) for pattern in _LOOKUP_PRICE_SIGNAL_PATTERNS)
            has_model_signal = any(re.search(pattern, lower) for pattern in _LOOKUP_MODEL_SIGNAL_PATTERNS)
            is_table_like = "|" in line and ("modell" in lower or has_price_signal or has_model_signal)
            if not ((has_price_signal and has_model_signal) or is_table_like):
                continue
            cleaned = line.strip()
            if len(cleaned) > 220:
                cleaned = cleaned[:220].rstrip() + "..."
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            extracted.append(cleaned)
            if len(extracted) >= 10:
                break
        return extracted

    @classmethod
    def _filter_pricing_lines_for_provider_focus(
        cls,
        lines: list[str],
        provider_focus: list[str],
    ) -> list[str]:
        if not provider_focus:
            return list(lines)
        allowed_patterns: list[str] = []
        for provider in provider_focus:
            aliases = _PRICING_PROVIDER_HINTS.get(provider, ())
            allowed_patterns.extend(alias for alias in aliases if alias)
        filtered: list[str] = []
        for line in lines:
            lower = line.lower()
            if any(alias in lower for alias in allowed_patterns):
                filtered.append(line)
        return filtered or list(lines)

    @classmethod
    def _infer_pricing_provider_from_text(cls, text: str) -> str:
        lowered = str(text or "").lower()
        for provider, aliases in _PRICING_PROVIDER_HINTS.items():
            if any(alias in lowered for alias in aliases):
                return provider
        return ""

    @staticmethod
    def _extract_price_value(text: str) -> float | None:
        raw = str(text or "")
        match = re.search(r"(\d+(?:[.,]\d+)?)", raw)
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    @classmethod
    def _parse_pricing_rows(cls, lines: list[str]) -> list[dict[str, str]]:
        parsed: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_line in lines:
            cleaned = re.sub(r"\s+", " ", str(raw_line or "")).strip().strip("|")
            if not cleaned:
                continue
            columns = [col.strip() for col in cleaned.split("|") if col.strip()]
            if len(columns) < 2:
                continue
            model = columns[0]
            lowered_columns = [col.lower() for col in columns]
            if model.lower() in {"modell", "model", "anbieter"}:
                continue
            input_value = ""
            output_value = ""
            cached_value = ""
            for index, column in enumerate(columns[1:], start=1):
                lowered = lowered_columns[index]
                if "cached" in lowered or "cache" in lowered:
                    cached_value = column
                elif "output" in lowered or "ausgabe" in lowered:
                    output_value = column
                elif "input" in lowered or "eingabe" in lowered:
                    input_value = column
            if not input_value and len(columns) >= 2:
                input_value = columns[1]
            if not output_value and len(columns) >= 3:
                output_value = columns[2]
            if not cached_value and len(columns) >= 4:
                cached_value = columns[3]
            if not (input_value or output_value or cached_value):
                continue
            provider = cls._infer_pricing_provider_from_text(f"{model} {cleaned}")
            key = f"{provider}|{model}|{input_value}|{output_value}|{cached_value}".casefold()
            if key in seen:
                continue
            seen.add(key)
            parsed.append(
                {
                    "provider": provider or "Unbekannt",
                    "model": model,
                    "input": input_value,
                    "output": output_value,
                    "cached": cached_value,
                    "raw": cleaned,
                }
            )
        return parsed

    @classmethod
    def _render_pricing_table(cls, rows: list[dict[str, str]]) -> str:
        if not rows:
            return ""
        lines = [
            "| Anbieter | Modell | Input | Output | Cached |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows[:10]:
            lines.append(
                "| {provider} | {model} | {input} | {output} | {cached} |".format(
                    provider=row.get("provider") or "-",
                    model=row.get("model") or "-",
                    input=row.get("input") or "-",
                    output=row.get("output") or "-",
                    cached=row.get("cached") or "-",
                )
            )
        return "\n".join(lines)

    @classmethod
    def _render_pricing_plaintext_table(cls, rows: list[dict[str, str]]) -> str:
        if not rows:
            return ""
        lines = ["Anbieter | Modell | Input | Output | Cached"]
        for row in rows[:10]:
            lines.append(
                " | ".join(
                    [
                        row.get("provider") or "-",
                        row.get("model") or "-",
                        row.get("input") or "-",
                        row.get("output") or "-",
                        row.get("cached") or "-",
                    ]
                )
            )
        return "\n".join(lines)

    @classmethod
    def _render_pricing_value_note(cls, user_task: str, rows: list[dict[str, str]]) -> str:
        normalized = str(user_task or "").lower()
        if not any(marker in normalized for marker in _LOOKUP_PRICE_VALUE_MARKERS):
            return ""
        cheapest_input = min(
            (row for row in rows if cls._extract_price_value(row.get("input")) is not None),
            key=lambda row: cls._extract_price_value(row.get("input")) or 0.0,
            default=None,
        )
        cheapest_output = min(
            (row for row in rows if cls._extract_price_value(row.get("output")) is not None),
            key=lambda row: cls._extract_price_value(row.get("output")) or 0.0,
            default=None,
        )
        notes: list[str] = []
        if cheapest_input:
            notes.append(
                f"Beim Input wirkt {cheapest_input.get('provider')} / {cheapest_input.get('model')} aktuell am guenstigsten."
            )
        if cheapest_output:
            notes.append(
                f"Beim Output wirkt {cheapest_output.get('provider')} / {cheapest_output.get('model')} aktuell am guenstigsten."
            )
        if notes:
            notes.append(
                "Das ist nur ein Preisvergleich. Fuer einen echten Preis-Leistungs-Sieger brauche ich zusaetzlich aktuelle Benchmarkdaten."
            )
        return " ".join(notes)

    async def _maybe_create_lookup_artifact(
        self,
        *,
        artifact_format: str,
        user_task: str,
        rows: list[dict[str, str]],
        source_title: str,
        source_url: str,
        value_note: str,
    ) -> str:
        if not artifact_format or not rows:
            return ""
        title = "LLM_Preise_Vergleich"
        if artifact_format == "txt":
            content = self._render_pricing_plaintext_table(rows)
            if source_title or source_url:
                source_parts = [part for part in (source_title, source_url) if part]
                content += "\n\nQuelle: " + " | ".join(source_parts)
            if value_note:
                content += "\n\n" + value_note
            result = await self._call_tool("create_txt", {"title": title, "content": content})
        elif artifact_format == "csv":
            result = await self._call_tool(
                "create_csv",
                {
                    "title": title,
                    "headers": ["Anbieter", "Modell", "Input", "Output", "Cached"],
                    "rows": [
                        [
                            row.get("provider") or "-",
                            row.get("model") or "-",
                            row.get("input") or "-",
                            row.get("output") or "-",
                            row.get("cached") or "-",
                        ]
                        for row in rows[:10]
                    ],
                },
            )
        elif artifact_format == "xlsx":
            result = await self._call_tool(
                "create_xlsx",
                {
                    "title": title,
                    "headers": ["Anbieter", "Modell", "Input", "Output", "Cached"],
                    "rows": [
                        [
                            row.get("provider") or "-",
                            row.get("model") or "-",
                            row.get("input") or "-",
                            row.get("output") or "-",
                            row.get("cached") or "-",
                        ]
                        for row in rows[:10]
                    ],
                },
            )
        else:
            return ""
        payload = self._tool_payload(result)
        if (
            (isinstance(result, dict) and result.get("error"))
            or str(payload.get("status") or "").strip().lower() == "error"
        ):
            return ""
        path = str(payload.get("path") or payload.get("filepath") or "").strip()
        filename = str(payload.get("filename") or "").strip()
        location = path or filename
        if not location:
            return ""
        response_lines = [f"Ich habe die {artifact_format.upper()}-Datei mit den aktuellen LLM-Preisen erstellt: {location}"]
        response_lines.append("")
        response_lines.append(self._render_pricing_table(rows))
        if value_note:
            response_lines.append("")
            response_lines.append(value_note)
        return "\n".join(response_lines)

    async def _finalize_pricing_lookup(
        self,
        *,
        user_task: str,
        source_title: str,
        source_url: str,
        source_text: str,
        context_seed: str = "",
        allow_artifact_creation: bool = True,
    ) -> str:
        extracted_lines = self._extract_pricing_lines_from_text(source_text)
        provider_focus = self._infer_pricing_provider_focus(user_task, context_seed=context_seed)
        focused_lines = self._filter_pricing_lines_for_provider_focus(extracted_lines, provider_focus)
        rows = self._parse_pricing_rows(focused_lines)
        if not rows:
            return ""
        value_note = self._render_pricing_value_note(user_task, rows)
        if allow_artifact_creation:
            artifact_format = self._infer_lookup_artifact_format(user_task)
            artifact_response = await self._maybe_create_lookup_artifact(
                artifact_format=artifact_format,
                user_task=user_task,
                rows=rows,
                source_title=source_title,
                source_url=source_url,
                value_note=value_note,
            )
            if artifact_response:
                return artifact_response
        lines = ["Ich habe aus der zuletzt geprueften Quelle diese Preis-Tabelle herausgezogen:"]
        if source_title or source_url:
            lines.append("Quelle: " + " | ".join(part for part in (source_title, source_url) if part))
        lines.append("")
        lines.append(self._render_pricing_table(rows))
        if value_note:
            lines.append("")
            lines.append(value_note)
        return "\n".join(lines)

    @classmethod
    def _format_pricing_source_response(
        cls,
        *,
        source_title: str,
        source_url: str,
        extracted_lines: list[str],
    ) -> str:
        lines = ["Ich habe aus der zuletzt geprueften Quelle diese Preisangaben herausgezogen:"]
        if source_title or source_url:
            source_parts = [part for part in (source_title, source_url) if part]
            lines.append("Quelle: " + " | ".join(source_parts))
        for line in extracted_lines[:8]:
            lines.append(f"- {line}")
        return "\n".join(lines)

    @classmethod
    def _build_simple_live_lookup_query(
        cls,
        *,
        user_task: str,
        category: str,
        location_label: str = "",
        context_seed: str = "",
    ) -> str:
        base_query = str(user_task or "").strip()
        if not base_query:
            return ""
        if cls._is_lookup_result_extraction_query(base_query) and context_seed:
            if category == "pricing":
                return f"aktuelle llm preise input output token vergleich {context_seed[:140]}"
            return f"{base_query} {context_seed[:140]}".strip()
        if category == "weather":
            if location_label and not cls._task_mentions_explicit_place(base_query):
                return f"Wetter heute {location_label}"
            return base_query
        if category == "pricing":
            cleaned = cls._strip_lookup_output_request_terms(base_query)
            provider_focus = cls._infer_pricing_provider_focus(cleaned, context_seed=context_seed)
            query_terms = ["aktuelle", "llm", "api", "preise", "input", "output", "token"]
            if provider_focus:
                query_terms.extend(provider_focus)
            elif cleaned:
                query_terms.append(cleaned)
            elif context_seed:
                query_terms.append(context_seed[:120])
            deduped: list[str] = []
            seen: set[str] = set()
            for term in query_terms:
                normalized = re.sub(r"\s+", " ", str(term or "")).strip()
                if not normalized:
                    continue
                key = normalized.casefold()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(normalized)
            return " ".join(deduped).strip()
        if category == "cinema":
            if location_label and not cls._task_mentions_explicit_place(base_query):
                return f"Kinoprogramm heute {location_label}"
            return base_query
        if category == "science_news" and "wissenschaft" not in base_query.lower():
            return f"Wissenschaft News aktuell {base_query}"
        return base_query

    @classmethod
    def _format_simple_lookup_results(
        cls,
        *,
        intro: str,
        results: list[dict[str, Any]],
        fetched_payload: dict[str, Any] | None = None,
    ) -> str:
        if not results:
            return intro

        lines = [intro, "Top-Treffer:"]
        for item in results[:5]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            parts = [title]
            snippet = cls._truncate_text(item.get("snippet") or item.get("description") or "", limit=160)
            if snippet:
                parts.append(snippet)
            domain = str(item.get("domain") or "").strip()
            if domain:
                parts.append(domain)
            url = str(item.get("url") or "").strip()
            if url:
                parts.append(url)
            lines.append("- " + " | ".join(parts))

        if isinstance(fetched_payload, dict) and str(fetched_payload.get("status") or "success").lower() == "success":
            source_title = str(fetched_payload.get("title") or "").strip()
            source_url = str(fetched_payload.get("url") or "").strip()
            excerpt = cls._truncate_text(fetched_payload.get("content") or fetched_payload.get("markdown") or "", limit=320)
            if source_title or excerpt:
                lines.append("")
                lines.append("Direkt gepruefte Quelle:")
                checked_parts = [part for part in (source_title, source_url) if part]
                if checked_parts:
                    lines.append("- " + " | ".join(checked_parts))
                if excerpt:
                    lines.append(cls._truncate_text(excerpt, limit=320))
        return "\n".join(lines)

    @staticmethod
    def _recover_semantic_recall(task_text: str) -> list[str]:
        text = str(task_text or "")
        match = re.search(
            r"semantic_recall:\s*(.+?)(?:\n#\s*current user query|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return []
        raw = match.group(1).strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split("||") if part.strip()]

    @staticmethod
    def _recover_recent_assistant_replies(task_text: str) -> list[str]:
        text = str(task_text or "")
        match = re.search(
            r"recent_assistant_replies:\s*(.+?)(?:\n[#a-z_]+:|\n#\s*current user query|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return []
        raw = match.group(1).strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split("||") if part.strip()]

    @staticmethod
    def _recover_session_summary(task_text: str) -> str:
        text = str(task_text or "")
        match = re.search(
            r"session_summary:\s*(.+?)(?:\n[a-z_]+:|\n#\s*current user query|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        return match.group(1).strip()

    @staticmethod
    def _recover_topic_recall(task_text: str) -> list[str]:
        text = str(task_text or "")
        match = re.search(
            r"topic_recall:\s*(.+?)(?:\n[#a-z_]+:|\n#\s*current user query|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return []
        raw = match.group(1).strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split("||") if part.strip()]

    @staticmethod
    def _recover_followup_session_id(task_text: str) -> str:
        text = str(task_text or "")
        match = re.search(r"session_id:\s*([^\n]+)", text, flags=re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip()

    @staticmethod
    def _tool_payload(result: dict[str, Any] | Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        payload = result.get("data")
        return payload if isinstance(payload, dict) else result

    @staticmethod
    def _tool_list_payload(result: dict[str, Any] | list[Any] | Any) -> list[dict[str, Any]]:
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if not isinstance(result, dict):
            return []
        payload = result.get("data")
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            return [item for item in payload["results"] if isinstance(item, dict)]
        if isinstance(result.get("results"), list):
            return [item for item in result["results"] if isinstance(item, dict)]
        return []

    @staticmethod
    def _record_conversation_recall(
        *,
        session_id: str,
        query: str,
        source: str,
        semantic_recall: list[str],
        recent_assistant_replies: list[str],
        session_summary: str,
    ) -> None:
        try:
            from orchestration.self_improvement_engine import (
                ConversationRecallRecord,
                get_improvement_engine,
            )

            top_agent = ""
            top_role = ""
            top_distance = 0.0
            if semantic_recall:
                header = str(semantic_recall[0]).split("=>", 1)[0].strip()
                if ":" in header:
                    top_role, top_agent = [part.strip() for part in header.split(":", 1)]
                else:
                    top_role = header
            get_improvement_engine().record_conversation_recall(
                ConversationRecallRecord(
                    session_id=session_id,
                    query=query,
                    source=source,
                    semantic_candidates=len(semantic_recall),
                    recent_reply_candidates=len(recent_assistant_replies),
                    used_summary=bool(session_summary),
                    top_agent=top_agent,
                    top_role=top_role,
                    top_distance=top_distance,
                )
            )
        except Exception:
            return

    @staticmethod
    def _format_distance(distance_meters: Any) -> str:
        try:
            value = float(distance_meters)
        except (TypeError, ValueError):
            return ""
        if value >= 1000:
            return f"{value / 1000:.1f} km"
        return f"{int(round(value))} m"

    @staticmethod
    def _format_rating(place: dict[str, Any]) -> str:
        rating = place.get("rating")
        reviews = place.get("reviews")
        if isinstance(rating, (int, float)) and rating > 0:
            if isinstance(reviews, int) and reviews > 0:
                return f"{rating:.1f} ({reviews} Reviews)"
            return f"{rating:.1f}"
        return ""

    @classmethod
    def _location_summary(cls, location: dict[str, Any]) -> str:
        display_name = str(location.get("display_name") or "").strip()
        locality = str(location.get("locality") or "").strip()
        admin_area = str(location.get("admin_area") or "").strip()
        country_name = str(location.get("country_name") or "").strip()

        if display_name:
            return display_name

        parts = [part for part in (locality, admin_area, country_name) if part]
        return ", ".join(parts)

    @staticmethod
    def _normalize_location_presence_status(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"live", "recent", "stale", "unknown"}:
            return normalized
        return "unknown"

    @classmethod
    def _infer_location_nearby_query(cls, user_task: str) -> str:
        intent = analyze_location_local_intent(user_task)
        if intent.is_location_only:
            return ""
        return intent.maps_query

    @staticmethod
    def _infer_location_route(user_task: str) -> tuple[str, str]:
        intent = analyze_location_route_intent(user_task)
        return intent.destination_query, normalize_route_travel_mode(intent.travel_mode)

    @staticmethod
    def _location_coordinates(location: dict[str, Any]) -> tuple[float | None, float | None]:
        try:
            latitude = float(location.get("latitude"))
        except (TypeError, ValueError):
            latitude = None
        try:
            longitude = float(location.get("longitude"))
        except (TypeError, ValueError):
            longitude = None
        return latitude, longitude

    @classmethod
    def _recover_live_location_context(cls, task_text: str) -> dict[str, Any] | None:
        text = str(task_text or "")
        match = re.search(
            r"# LIVE LOCATION CONTEXT\s*(.+?)(?:\n\s*\n|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None

        parsed: dict[str, Any] = {}
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.lower().startswith("use this location only"):
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            parsed[key.strip().lower()] = value.strip()

        if not parsed:
            return None

        recovered: dict[str, Any] = {
            "display_name": str(parsed.get("display_name") or "").strip(),
            "locality": str(parsed.get("locality") or "").strip(),
            "admin_area": str(parsed.get("admin_area") or "").strip(),
            "country_name": str(parsed.get("country_name") or "").strip(),
            "captured_at": str(parsed.get("captured_at") or "").strip(),
            "received_at": str(parsed.get("received_at") or "").strip(),
            "maps_url": str(parsed.get("maps_url") or "").strip(),
            "presence_status": cls._normalize_location_presence_status(parsed.get("presence_status") or "unknown"),
            "usable_for_context": str(parsed.get("usable_for_context") or "").strip().lower() == "true",
        }

        latitude = cls._as_float(parsed.get("latitude"))
        longitude = cls._as_float(parsed.get("longitude"))
        if latitude is None or longitude is None:
            maps_url = recovered["maps_url"]
            coords_match = re.search(r"query=([-0-9.]+),([-0-9.]+)", maps_url)
            if coords_match:
                latitude = cls._as_float(coords_match.group(1))
                longitude = cls._as_float(coords_match.group(2))
        if latitude is not None:
            recovered["latitude"] = latitude
        if longitude is not None:
            recovered["longitude"] = longitude
        return recovered

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _resolve_effective_location(
        cls,
        *,
        location_payload: dict[str, Any],
        task_text: str,
    ) -> tuple[bool, dict[str, Any] | None, str]:
        has_location = bool(location_payload.get("has_location"))
        location = location_payload.get("location")
        if has_location and isinstance(location, dict):
            return True, location, cls._normalize_location_presence_status(
                location_payload.get("presence_status") or location.get("presence_status") or "live"
            )

        recovered = cls._recover_live_location_context(task_text)
        if isinstance(recovered, dict):
            return True, recovered, cls._normalize_location_presence_status(recovered.get("presence_status") or "unknown")
        return False, None, "unknown"

    @staticmethod
    def _activate_route_snapshot(route_payload: dict[str, Any]) -> None:
        try:
            from server import mcp_server as mcp_server_module
            from utils.location_route import prepare_route_snapshot

            setter = getattr(mcp_server_module, "_set_route_snapshot", None)
            if callable(setter):
                setter(prepare_route_snapshot(route_payload))
        except Exception:
            return

    @staticmethod
    def _is_smalltalk_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 12:
            return False
        return any(re.search(pattern, normalized) for pattern in _SMALLTALK_PATTERNS)

    @staticmethod
    def _smalltalk_response(task: str) -> str:
        normalized = str(task or "").strip().lower()
        if "wie geht" in normalized:
            return (
                "Lauft. Die Systeme stehen gerade wieder, und ich bin einsatzbereit. "
                "Wenn du etwas Konkretes willst, sag es direkt."
            )
        if "was geht" in normalized or "was gibt" in normalized:
            return (
                "Gerade nichts Magisches. Ich bin da, die Systeme laufen, und du kannst mir direkt Arbeit geben."
            )
        return "Ich bin da. Sag direkt, was du brauchst."

    @staticmethod
    def _is_self_status_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 16:
            return False
        return any(re.search(pattern, normalized) for pattern in _SELF_STATUS_PATTERNS)

    @staticmethod
    def _is_self_remediation_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 20:
            return False
        return any(re.search(pattern, normalized) for pattern in _SELF_REMEDIATION_PATTERNS)

    @staticmethod
    def _is_self_priority_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 20:
            return False
        return any(re.search(pattern, normalized) for pattern in _SELF_PRIORITY_PATTERNS)

    @staticmethod
    def _is_self_recall_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 24:
            return False
        return any(re.search(pattern, normalized) for pattern in _SELF_RECALL_PATTERNS)

    @staticmethod
    def _is_topic_followup_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 24:
            return False
        if any(re.search(pattern, normalized) for pattern in _SELF_RECALL_PATTERNS):
            return True
        if "nochmal" in normalized and "mit " in normalized:
            return True
        if ("erklaer" in normalized or "erklär" in normalized) and "mit " in normalized:
            return True
        return False

    @staticmethod
    def _is_capability_learning_query(task: str) -> bool:
        normalized = str(task or "").strip().lower()
        if not normalized:
            return False
        if len(normalized.split()) > 20:
            return False
        return any(re.search(pattern, normalized) for pattern in _CAPABILITY_LEARNING_PATTERNS)

    @classmethod
    def _format_ops_self_status(cls, ops: dict[str, Any]) -> str:
        state = str(ops.get("state") or "unknown").strip().lower()
        critical = int(ops.get("critical_alerts") or 0)
        warnings = int(ops.get("warnings") or 0)
        failing_services = int(ops.get("failing_services") or 0)
        unhealthy_providers = int(ops.get("unhealthy_providers") or 0)
        alerts = ops.get("alerts") or []
        if not isinstance(alerts, list):
            alerts = []

        if state in {"ok", "healthy", "green"} and critical == 0 and warnings == 0:
            return (
                "Gerade nichts Kritisches. MCP und Dispatcher laufen, und ich sehe im Ops-Bild aktuell keine akute Stoerung."
            )

        lines = [
            "Gerade sehe ich diese Baustellen bei mir:",
            f"- Zustand: {state or 'unknown'}",
            f"- Kritische Alerts: {critical}",
            f"- Warnungen: {warnings}",
        ]
        if failing_services:
            lines.append(f"- Problematische Services: {failing_services}")
        if unhealthy_providers:
            lines.append(f"- Wackelige Provider: {unhealthy_providers}")
        for alert in alerts[:3]:
            if not isinstance(alert, dict):
                continue
            message = str(alert.get("message") or "").strip()
            severity = str(alert.get("severity") or "warn").strip()
            if message:
                lines.append(f"- {severity}: {message}")
        return "\n".join(lines)

    @classmethod
    def _format_ops_remediation(cls, ops: dict[str, Any]) -> str:
        alerts = ops.get("alerts") or []
        if not isinstance(alerts, list):
            alerts = []
        messages = [
            str(alert.get("message") or "").strip().lower()
            for alert in alerts
            if isinstance(alert, dict) and str(alert.get("message") or "").strip()
        ]

        actions: list[str] = []
        if any("routing visual" in message for message in messages):
            actions.append(
                "Visual strenger nur fuer echte UI-Aufgaben verwenden und lockere Text-/Statusfragen davor abfangen."
            )
        if any("routing research" in message for message in messages):
            actions.append(
                "Leichte Recherchefaelle im executor halten und Research erst bei echter Tiefe oder Quellenpflicht zuschalten."
            )
        if int(ops.get("failing_services") or 0) > 0:
            actions.append(
                "Die betroffenen Services gezielt beobachten, Health-Checks schaerfer auswerten und Absturzpfade isolieren."
            )
        if int(ops.get("unhealthy_providers") or 0) > 0:
            actions.append(
                "Instabile Modellpfade auf stabilere Provider umlegen und Fallbacks frueher aktivieren."
            )
        if not actions:
            actions.append("Die aktuellen Warnungen weiter beobachten und die auffaelligen Routing-Pfade gezielt haerten.")

        lines = ["Dagegen kann ich im Moment konkret Folgendes tun:"]
        for action in actions[:4]:
            lines.append(f"- {action}")
        return "\n".join(lines)

    @classmethod
    def _format_ops_priority(cls, ops: dict[str, Any]) -> str:
        alerts = ops.get("alerts") or []
        if not isinstance(alerts, list):
            alerts = []
        messages = [
            str(alert.get("message") or "").strip().lower()
            for alert in alerts
            if isinstance(alert, dict) and str(alert.get("message") or "").strip()
        ]

        first_step = "Zuerst die auffaelligste Warnung isolieren und dann den naechsten Engpass nachziehen."
        reason = "Das reduziert das akute Risiko am schnellsten."

        if any("routing visual" in message for message in messages):
            first_step = (
                "Zuerst den Visual-Pfad haerten und vage Folgefragen strikt aus dem Screen-/UI-Pfad heraushalten."
            )
            reason = "Der Visual-Routing-Fehler ist aktuell der kritischste und fuehrt direkt in Absturzpfade."
        elif any("routing research" in message for message in messages):
            first_step = (
                "Zuerst leichte Recherchefaelle aus Deep-Research herausziehen und im executor deterministisch beantworten."
            )
            reason = "Damit sinken Last, Latenz und Fehlrouting gleichzeitig."
        elif int(ops.get("failing_services") or 0) > 0:
            first_step = "Zuerst die betroffenen Services stabilisieren und Health-Checks enger auswerten."
            reason = "Wenn Services wackeln, bringt Optimierung auf höherer Ebene wenig."
        elif int(ops.get("unhealthy_providers") or 0) > 0:
            first_step = "Zuerst den instabilsten Modellpfad auf einen robusteren Provider umlegen."
            reason = "Ein instabiler Provider zieht sonst weitere Fehlerketten nach sich."

        return "\n".join(
            [
                "Als Erstes wuerde ich das hier angehen:",
                f"- {first_step}",
                f"- Warum zuerst: {reason}",
            ]
        )

    @classmethod
    def _format_semantic_recall_response(
        cls,
        user_task: str,
        recall_lines: list[str],
        session_summary: str = "",
    ) -> str:
        if not recall_lines and not session_summary:
            return ""

        primary = recall_lines[0] if recall_lines else session_summary[:240]
        if "visual" in str(user_task or "").lower():
            return "\n".join(
                [
                    "Daran erinnere ich mich aus dem bisherigen Verlauf:",
                    f"- {primary}",
                    "- Das ist weiter mein relevanter Bezugspunkt fuer den Visual-Pfad.",
                ]
            )
        return "\n".join(
            [
                "Daran erinnere ich mich aus dem bisherigen Verlauf:",
                f"- {primary}",
            ]
        )

    @staticmethod
    def _infer_topic_focus_label(user_task: str) -> str:
        normalized = str(user_task or "").strip().lower()
        match = re.search(
            r"\bmit\s+(?:dem|der|den|des|die|das)?\s*([a-zA-Z0-9äöüÄÖÜß_-]+)",
            normalized,
        )
        if match:
            token = match.group(1).strip(" -_")
            if token:
                return token
        return ""

    @classmethod
    def _format_topic_recall_response(cls, user_task: str, topic_lines: list[str]) -> str:
        if not topic_lines:
            return ""

        primary = str(topic_lines[0]).strip()
        if not primary:
            return ""

        normalized = str(user_task or "").strip().lower()
        focus = cls._infer_topic_focus_label(user_task)

        if "erklaer" in normalized or "erklär" in normalized:
            if focus:
                return f"Klar. Mit {focus} meinte ich: {primary}"
            return f"Klar. Damit meinte ich: {primary}"

        if focus:
            return f"Mit {focus} war gemeint: {primary}"

        return f"Damit war gemeint: {primary}"

    @classmethod
    def _format_capability_learning_response(
        cls,
        user_task: str,
        recall_lines: list[str],
        session_summary: str = "",
    ) -> str:
        basis = " ".join(str(line or "").strip() for line in recall_lines if str(line or "").strip())
        if not basis and session_summary:
            basis = str(session_summary or "").strip()
        lowered = basis.lower()

        requirements: list[str] = []
        if any(token in lowered for token in ("lieferplattform", "lieferservice", "pizza", "bestellen")):
            requirements.append("eine echte Integration zu Lieferplattformen oder einen freigegebenen Browser-Bestellworkflow")
        if "zugang" in lowered:
            requirements.append("autorisierten Zugriff auf die benoetigten Bestellplattformen")
        if "zahlungsdaten" in lowered or "zahlung" in lowered:
            requirements.append("eine sichere Zahlungsfreigabe oder hinterlegte Zahlungsdaten")
        if "lieferadresse" in lowered or ("adresse" in lowered and "mail" not in lowered):
            requirements.append("eine bestaetigte Lieferadresse")

        deduped: list[str] = []
        seen: set[str] = set()
        for item in requirements:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        if not deduped:
            deduped = [
                "die passende externe Integration oder API",
                "die dafuer noetigen Freigaben und Nutzerdaten",
                "einen kontrollierten Ausfuehrungsweg fuer echte Bestellungen",
            ]

        lines = [
            "Ja, theoretisch schon, aber nicht einfach spontan aus mir selbst heraus.",
            "Dafuer bräuchte ich mindestens:",
        ]
        for item in deduped[:4]:
            lines.append(f"- {item}")
        lines.append(
            "Kurz: Ich koennte so eine Faehigkeit nur ueber neue Integrationen, Freigaben und einen sicheren Bestellpfad bekommen, nicht durch blosses 'Selbstlernen' im laufenden Chat."
        )
        return "\n".join(lines)

    @staticmethod
    def _infer_youtube_search_query(user_task: str) -> str:
        normalized = str(user_task or "").strip().lower()
        if not normalized:
            return "trending deutschland"
        if normalized.startswith("antworte ausschliesslich auf deutsch") or normalized.startswith(
            "antworte ausschließlich auf deutsch"
        ):
            return "trending deutschland"
        normalized = re.sub(
            r"^antworte\s+.*?nutzeranfrage:\s*",
            "",
            normalized,
            flags=re.IGNORECASE | re.DOTALL,
        )
        normalized = re.sub(r"^nutzeranfrage:\s*", "", normalized, flags=re.IGNORECASE)

        query = _YOUTUBE_DIRECT_URL_RE.sub(" ", normalized)
        for pattern in _YOUTUBE_GENERIC_PATTERNS:
            query = re.sub(pattern, " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+", " ", query).strip(" ,.!?:;")

        # Separator-Extraktion: Inhalt nach typischen Einleitungsphrasen
        for separator in (" zu ", " ueber ", " über ", " fuer ", " für ", " sind ", " über das thema ", " zum thema "):
            padded = f" {query} "
            if separator in padded:
                tail = query.split(separator.strip(), 1)[1].strip(" ,.!?:;")
                # Tail nur nehmen wenn er mehr Inhalt hat als das was davor war
                if tail and len(tail.split()) >= 2:
                    query = tail
                    break

        # Zweite Bereinigungsrunde nach Separator-Split
        for pattern in _YOUTUBE_GENERIC_PATTERNS:
            query = re.sub(pattern, " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+", " ", query).strip(" ,.!?:;")

        tokens = [token for token in query.split() if token]
        while tokens and tokens[0] in _YOUTUBE_EDGE_FILLER_TOKENS:
            tokens.pop(0)
        while tokens and tokens[-1] in _YOUTUBE_EDGE_FILLER_TOKENS:
            tokens.pop()
        query = " ".join(tokens).strip()

        if not query or len(query) < 3:
            return "trending deutschland"
        if query in {"youtube", "neu", "neues", "aktuell", "aktuelle videos"}:
            return "trending deutschland"
        return query

    @staticmethod
    def _is_direct_youtube_fact_check_request(user_task: str) -> bool:
        normalized = str(user_task or "").strip().lower()
        if not normalized:
            return False
        return bool(_YOUTUBE_DIRECT_URL_RE.search(normalized)) and any(
            hint in normalized for hint in _YOUTUBE_FACT_CHECK_HINTS
        )

    @classmethod
    def _format_views(cls, views: Any) -> str:
        try:
            value = int(views)
        except (TypeError, ValueError):
            return ""
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f} Mio. Aufrufe"
        if value >= 1_000:
            return f"{value / 1_000:.1f} Tsd. Aufrufe"
        return f"{value} Aufrufe"

    @classmethod
    def _format_youtube_light_response(
        cls,
        *,
        user_task: str,
        search_query: str,
        results: list[dict[str, Any]],
    ) -> str:
        if not results:
            return (
                f"Ich habe auf YouTube gerade keine brauchbaren Treffer fuer '{search_query}' gefunden. "
                "Wenn du willst, nenne mir ein konkretes Thema oder einen Kanal."
            )

        generic_request = search_query == "trending deutschland"
        if generic_request:
            lines = ["Auf YouTube fallen gerade diese aktuellen Treffer auf:"]
        else:
            lines = [f"Auf YouTube habe ich zu '{search_query}' gerade diese Treffer gefunden:"]

        for item in results[:5]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            parts = [title]
            channel_name = str(item.get("channel_name") or "").strip()
            if channel_name:
                parts.append(channel_name)
            views = cls._format_views(item.get("views_count"))
            if views:
                parts.append(views)
            url = str(item.get("url") or "").strip()
            if url:
                parts.append(url)
            lines.append("- " + " | ".join(parts))

        if generic_request and any(token in str(user_task or "").lower() for token in ("neu", "neues", "aktuell")):
            lines.append("Wenn du willst, filtere ich das direkt weiter nach Thema, Kanal oder nur deutschsprachigen Videos.")
        return "\n".join(lines)

    @classmethod
    def _format_location_response(
        cls,
        *,
        user_task: str,
        location: dict[str, Any],
        maps_results: list[dict[str, Any]],
        maps_query: str,
    ) -> str:
        location_summary = cls._location_summary(location)
        if not location_summary:
            location_summary = "deinem aktuellen Mobil-Standort"
        presence_status = cls._normalize_location_presence_status(
            location.get("presence_status") or location.get("status")
        )
        if presence_status == "recent":
            lines = [f"Dein letzter frischer Standort war bei {location_summary}."]
        else:
            lines = [f"Du bist gerade bei {location_summary}."]

        if not maps_query:
            maps_url = str(location.get("maps_url") or "").strip()
            if maps_url:
                lines.append(f"Google Maps: {maps_url}")
            return " ".join(lines)

        if not maps_results:
            lines.append(
                f"Ich habe auf Google Maps gerade keine klaren Treffer fuer '{maps_query}' in deiner unmittelbaren Naehe gefunden."
            )
            return " ".join(lines)

        lines.append(f"In deiner Naehe habe ich fuer '{maps_query}' diese Treffer gefunden:")
        for place in maps_results[:5]:
            title = str(place.get("title") or "").strip()
            if not title:
                continue
            parts = [title]
            distance = cls._format_distance(place.get("distance_meters"))
            if distance:
                parts.append(distance)
            hours = str(place.get("hours_summary") or "").strip()
            if hours:
                parts.append(hours)
            rating = cls._format_rating(place)
            if rating:
                parts.append(f"Rating {rating}")
            address = str(place.get("address") or "").strip()
            if address:
                parts.append(address)
            lines.append("- " + " | ".join(parts))

        if "offen" in str(user_task or "").lower():
            lines.append("Oeffnungszeiten sind, sofern vorhanden, direkt aus Google Maps uebernommen.")
        return "\n".join(lines)

    @classmethod
    def _format_stale_location_response(cls, location: dict[str, Any]) -> str:
        location_summary = cls._location_summary(location)
        if not location_summary:
            location_summary = "deinem letzten bekannten Standort"
        maps_url = str(location.get("maps_url") or "").strip()
        lines = [
            f"Dein letzter bekannter Standort war bei {location_summary}, aber dieser Standort ist gerade nicht frisch genug fuer verlaessliche Nearby-Antworten.",
            "Aktualisiere den Standort kurz in der App, dann kann ich Orte in deiner unmittelbaren Naehe wieder sauber einordnen.",
        ]
        if maps_url:
            lines.append(f"Letzte Kartenposition: {maps_url}")
        return " ".join(lines)

    @classmethod
    def _format_route_response(
        cls,
        *,
        route: dict[str, Any],
    ) -> str:
        destination_label = str(route.get("destination_label") or route.get("destination_query") or "dem Ziel").strip()
        start_address = str(route.get("start_address") or "").strip()
        end_address = str(route.get("end_address") or destination_label).strip()
        distance_text = str(route.get("distance_text") or "").strip()
        duration_text = str(route.get("duration_text") or "").strip()
        travel_mode = normalize_route_travel_mode(route.get("travel_mode"))
        route_url = str(route.get("route_url") or route.get("maps_url") or "").strip()
        steps = route.get("steps")
        if not isinstance(steps, list):
            steps = []

        mode_labels = {
            "driving": "Auto",
            "walking": "Zu Fuss",
            "bicycling": "Fahrrad",
            "transit": "OePNV",
        }
        lines = [f"Route nach {destination_label} ist erstellt."]
        detail_parts = [part for part in (duration_text, distance_text) if part]
        if detail_parts:
            lines.append(f"{mode_labels.get(travel_mode, 'Route')}: " + " | ".join(detail_parts))
        if start_address:
            lines.append(f"Von: {start_address}")
        if end_address:
            lines.append(f"Nach: {end_address}")
        if route_url:
            lines.append(f"Google Maps: {route_url}")

        step_lines: list[str] = []
        for step in steps[:3]:
            if not isinstance(step, dict):
                continue
            instruction = str(step.get("instruction") or "").strip()
            if not instruction:
                continue
            parts = [instruction]
            step_distance = str(step.get("distance_text") or "").strip()
            step_duration = str(step.get("duration_text") or "").strip()
            if step_distance:
                parts.append(step_distance)
            if step_duration:
                parts.append(step_duration)
            step_lines.append("- " + " | ".join(parts))
        if step_lines:
            lines.append("Naechste Schritte:")
            lines.extend(step_lines)
        return "\n".join(lines)

    @classmethod
    def _format_route_error_response(
        cls,
        *,
        location: dict[str, Any],
        destination_query: str,
        travel_mode: str,
        error: str,
    ) -> str:
        latitude, longitude = cls._location_coordinates(location)
        route_url = ""
        if latitude is not None and longitude is not None and destination_query:
            route_url = build_google_maps_directions_url(
                origin_latitude=latitude,
                origin_longitude=longitude,
                destination_query=destination_query,
                travel_mode=travel_mode,
            )

        lines = [
            f"Ich konnte gerade keine aktive Route nach {destination_query or 'dem Ziel'} erzeugen: {error}",
        ]
        if route_url:
            lines.append(f"Direkter Google-Maps-Link: {route_url}")
        return " ".join(lines)

    async def _run_location_local_search(
        self,
        handoff: DelegationHandoff,
        task_text: str = "",
    ) -> str:
        self._notify_delegation_progress("location_local_search_start")
        source_task = (
            handoff.handoff_data.get("original_user_task")
            or handoff.handoff_data.get("query")
            or handoff.goal
            or ""
        )
        user_task = self._recover_user_query(source_task)
        if not analyze_location_local_intent(user_task).is_location_relevant and task_text:
            recovered_from_task = self._recover_user_query(task_text)
            if analyze_location_local_intent(recovered_from_task).is_location_relevant:
                user_task = recovered_from_task
        self._notify_delegation_progress("location_context_lookup")
        location_result = await self._call_tool("get_current_location_context", {})
        if isinstance(location_result, dict) and location_result.get("error"):
            return f"Ich konnte den aktuellen Standort nicht laden: {location_result['error']}"

        location_payload = self._tool_payload(location_result)
        has_location, location, presence_status = self._resolve_effective_location(
            location_payload=location_payload,
            task_text=task_text or source_task,
        )
        if not has_location or not isinstance(location, dict):
            return (
                "Ich habe aktuell keinen synchronisierten Handy-Standort. "
                "Oeffne in der App Home > Standort und aktualisiere ihn, dann kann ich lokale Orte ueber Google Maps finden."
            )
        usable_for_context = bool(location.get("usable_for_context", True))
        if presence_status not in {"live", "recent"} or not usable_for_context:
            return self._format_stale_location_response(location)

        maps_query = self._infer_location_nearby_query(user_task)
        canonical_maps_query = self._infer_simple_live_lookup_local_query(user_task)
        if canonical_maps_query and (
            not maps_query
            or maps_query.strip().lower() in {
                canonical_maps_query.strip().lower(),
                canonical_maps_query.strip().lower().rstrip("s"),
            }
        ):
            maps_query = canonical_maps_query
        if not maps_query:
            return self._format_location_response(
                user_task=user_task,
                location=location,
                maps_results=[],
                maps_query="",
            )

        latitude, longitude = self._location_coordinates(location)
        maps_params: dict[str, Any] = {"query": maps_query, "max_results": 5, "language_code": "de"}
        if latitude is not None and longitude is not None:
            maps_params["latitude"] = latitude
            maps_params["longitude"] = longitude
        self._notify_delegation_progress("maps_places_lookup", query=maps_query)
        maps_result = await self._call_tool("search_google_maps_places", maps_params)
        if isinstance(maps_result, dict) and maps_result.get("error"):
            return (
                self._format_location_response(
                    user_task=user_task,
                    location=location,
                    maps_results=[],
                    maps_query="",
                )
                + f" Die Google-Maps-Suche ist gerade fehlgeschlagen: {maps_result['error']}"
            )

        maps_payload = self._tool_payload(maps_result)
        maps_results = maps_payload.get("results")
        if not isinstance(maps_results, list):
            maps_results = []
        return self._format_location_response(
            user_task=user_task,
            location=location,
            maps_results=maps_results,
            maps_query=maps_query,
        )

    async def _run_location_route(
        self,
        handoff: DelegationHandoff,
        task_text: str = "",
    ) -> str:
        self._notify_delegation_progress("location_route_start")
        source_task = (
            handoff.handoff_data.get("original_user_task")
            or handoff.handoff_data.get("query")
            or handoff.goal
            or ""
        )
        user_task = self._recover_user_query(source_task)
        if not analyze_location_route_intent(user_task).is_route_request and task_text:
            recovered_from_task = self._recover_user_query(task_text)
            if analyze_location_route_intent(recovered_from_task).is_route_request:
                user_task = recovered_from_task
        destination_query = str(handoff.handoff_data.get("destination_query") or "").strip()
        travel_mode = normalize_route_travel_mode(str(handoff.handoff_data.get("travel_mode") or "driving"))
        if not destination_query:
            inferred_destination, inferred_mode = self._infer_location_route(user_task)
            destination_query = inferred_destination
            travel_mode = inferred_mode or travel_mode
        if not destination_query:
            return (
                "Ich habe die Route erkannt, aber noch kein klares Ziel extrahiert. "
                "Nenne mir das Ziel bitte direkt, zum Beispiel: 'Route zur Zeil in Frankfurt'."
            )

        self._notify_delegation_progress("location_context_lookup")
        location_result = await self._call_tool("get_current_location_context", {})
        if isinstance(location_result, dict) and location_result.get("error"):
            return f"Ich konnte den aktuellen Standort nicht laden: {location_result['error']}"

        location_payload = self._tool_payload(location_result)
        has_location, location, presence_status = self._resolve_effective_location(
            location_payload=location_payload,
            task_text=task_text or source_task,
        )
        if not has_location or not isinstance(location, dict):
            return (
                "Ich habe aktuell keinen synchronisierten Handy-Standort. "
                "Oeffne in der App Home > Standort und aktualisiere ihn, dann kann ich eine Route berechnen."
            )
        usable_for_context = bool(location.get("usable_for_context", True))
        if presence_status not in {"live", "recent"} or not usable_for_context:
            return self._format_stale_location_response(location)

        latitude, longitude = self._location_coordinates(location)
        route_params: dict[str, Any] = {
            "destination_query": destination_query,
            "travel_mode": travel_mode,
            "language_code": "de",
        }
        if latitude is not None and longitude is not None:
            route_params["latitude"] = latitude
            route_params["longitude"] = longitude
        self._notify_delegation_progress("maps_route_lookup", destination=destination_query)
        route_result = await self._call_tool(
            "get_google_maps_route",
            route_params,
        )
        if isinstance(route_result, dict) and route_result.get("error"):
            return self._format_route_error_response(
                location=location,
                destination_query=destination_query,
                travel_mode=travel_mode,
                error=str(route_result["error"]),
            )

        route_payload = self._tool_payload(route_result)
        if not isinstance(route_payload, dict) or not str(route_payload.get("route_url") or "").strip():
            return self._format_route_error_response(
                location=location,
                destination_query=destination_query,
                travel_mode=travel_mode,
                error="Die Directions-Antwort war unvollstaendig.",
            )
        self._activate_route_snapshot(route_payload)
        return self._format_route_response(route=route_payload)

    async def _run_youtube_light_research(self, handoff: DelegationHandoff) -> str:
        self._notify_delegation_progress("youtube_light_lookup_start")
        raw_task = (
            handoff.handoff_data.get("original_user_task")
            or handoff.handoff_data.get("query")
            or handoff.goal
            or ""
        )
        user_task = self._recover_user_query(raw_task)
        if self._is_direct_youtube_fact_check_request(user_task):
            return (
                "Das sieht nach einem konkreten YouTube-Video-Faktencheck aus, nicht nach einer allgemeinen "
                "YouTube-Suche. Dafuer brauche ich den Analyse-/Research-Pfad auf genau dieses Video statt "
                "einer Trefferliste."
            )
        preferred_search_tool = str(handoff.handoff_data.get("preferred_search_tool") or "search_youtube").strip()
        max_results = handoff.handoff_data.get("max_results") or 5
        try:
            max_results_int = max(1, min(int(max_results), 10))
        except (TypeError, ValueError):
            max_results_int = 5
        search_mode = str(handoff.handoff_data.get("search_mode") or "live").strip() or "live"
        search_query = self._infer_youtube_search_query(user_task)
        lang_prefs = _detect_youtube_language_preference(user_task)

        # P2: Referenz-Fortsetzung — kurze Query + topic_recall im vollen Task-Text
        # Beispiel: "mach damit eine youtube suche" → user_task ist kurz, kein verwertbares Thema
        if search_query == "trending deutschland" or len(search_query.split()) <= 2:
            topic_recall = self._recover_topic_recall(raw_task)
            if topic_recall:
                # Ersten Recall-Eintrag als Query-Basis nehmen
                recall_text = topic_recall[0]
                recall_query = self._infer_youtube_search_query(recall_text)
                if recall_query and recall_query != "trending deutschland":
                    search_query = recall_query
                    lang_prefs = _detect_youtube_language_preference(recall_text)

        seen_ids: set[str] = set()
        combined_results: list[dict] = []

        async def _fetch(query: str, lang: str) -> list[dict]:
            self._notify_delegation_progress("youtube_search_lookup", query=query, language=lang)
            res = await self._call_tool(
                preferred_search_tool,
                {
                    "query": query,
                    "max_results": max_results_int,
                    "language_code": lang,
                    "mode": search_mode,
                },
            )
            if isinstance(res, dict) and res.get("error"):
                return []
            return self._tool_list_payload(res)

        def _dedup_add(items: list[dict]) -> None:
            for item in items:
                vid = str(item.get("video_id") or "").strip()
                if vid:
                    if vid not in seen_ids:
                        seen_ids.add(vid)
                        combined_results.append(item)
                else:
                    # Kein video_id (z.B. Mock-Daten) → anhand Titel deduplizieren
                    title_key = str(item.get("title") or "").strip().lower()
                    if title_key and title_key not in seen_ids:
                        seen_ids.add(title_key)
                        combined_results.append(item)
                    elif not title_key:
                        combined_results.append(item)

        # DE-Suche immer
        _dedup_add(await _fetch(search_query, "de"))

        # EN-Suche wenn Nutzer englische Inhalte wollte
        if "en" in lang_prefs:
            en_query = _youtube_translate_query(search_query)
            if en_query and en_query != search_query:
                _dedup_add(await _fetch(en_query, "en"))

        if not combined_results:
            return (
                f"Die YouTube-Suche ist gerade fehlgeschlagen oder lieferte keine Treffer fuer '{search_query}'. "
                "Wenn du willst, versuche ich es gleich mit einer praeziseren Suchanfrage nochmal."
            )

        return self._format_youtube_light_response(
            user_task=user_task,
            search_query=search_query,
            results=combined_results,
        )

    @staticmethod
    def _infer_setup_build_focus_terms(user_task: str) -> list[str]:
        lowered = str(user_task or "").strip().lower()
        if not lowered:
            return []
        preferred_terms: list[str] = []
        term_groups = (
            ("twilio", ("twilio",)),
            ("inworld", ("inworld",)),
            ("voice", ("voice", "stimme", "tts")),
            ("call", ("call", "anruf", "phone", "telefon", "telephony")),
        )
        for canonical, variants in term_groups:
            if any(item in lowered for item in variants):
                preferred_terms.append(canonical)
        if preferred_terms:
            return preferred_terms

        stopwords = {
            "richte",
            "ein",
            "fuer",
            "mich",
            "eine",
            "funktion",
            "kannst",
            "sollst",
            "schau",
            "nach",
            "ob",
            "schon",
            "gibt",
            "vorbereitungen",
            "mir",
            "dann",
            "dich",
            "ueber",
            "hilfreich",
            "seite",
        }
        tokens = [
            token
            for token in re.findall(r"[a-zA-Z][\w.-]{4,}", lowered)
            if token not in stopwords
        ]
        seen: set[str] = set()
        result: list[str] = []
        for token in tokens:
            if token in seen:
                continue
            seen.add(token)
            result.append(token)
            if len(result) >= 4:
                break
        return result

    @staticmethod
    def _is_setup_build_noise_path(path: str) -> bool:
        lowered = str(path or "").strip().lower()
        if not lowered:
            return True
        filename = lowered.rsplit("/", 1)[-1]
        if filename in {".gitignore", ".qdrant-initialized"}:
            return True
        if filename.endswith((".bak", ".backup", ".orig", ".rej", ".tmp")):
            return True
        if filename.startswith(".env.") and any(
            suffix in filename for suffix in (".example", ".sample", ".template", ".backup", ".bak", ".orig")
        ):
            return True
        noisy_fragments = (
            "/docs/autonomy/",
            "/data/",
            "/.git/",
            "/.hypothesis/",
            "/__pycache__/",
            "/.venv/",
            "/venv/",
            "/logs/",
            "/results/",
            ".env.example",
            "phase_f_plan",
            "changelog_dev",
            "zwischenprojekt_allgemeine_mehrschritt_planung",
        )
        return any(fragment in lowered for fragment in noisy_fragments)

    @classmethod
    def _setup_build_path_priority(cls, path: str) -> int:
        lowered = str(path or "").strip().lower()
        if not lowered:
            return 99
        filename = lowered.rsplit("/", 1)[-1]
        if cls._is_setup_build_noise_path(lowered):
            return 99
        if filename == ".env":
            return 0
        if any(segment in lowered for segment in ("/tools/", "/skills/", "/server/", "/agent/", "/scripts/", "/config/")):
            return 1
        if any(segment in lowered for segment in ("/docs/", "/tests/")) or filename in {"conftest.py", "roadmap.md", "readme.md"}:
            return 5
        return 3

    @staticmethod
    def _is_setup_build_sensitive_path(path: str) -> bool:
        filename = str(path or "").strip().rsplit("/", 1)[-1].lower()
        return filename.startswith(".env")

    @classmethod
    def _sanitize_setup_build_match_line(cls, file_path: str, line: str) -> str:
        text = str(line or "").strip()
        if not text:
            return ""
        if not cls._is_setup_build_sensitive_path(file_path):
            return text

        env_match = re.match(r"^([A-Z0-9_]+)\s*=\s*(.+)$", text)
        if env_match:
            key = str(env_match.group(1) or "").strip()
            if key:
                return f"{key}=<configured>"
        return "<sensitive env entry present>"

    async def _collect_setup_build_probe_findings(
        self,
        handoff: DelegationHandoff,
        task_text: str = "",
    ) -> dict[str, Any]:
        handoff_data = handoff.handoff_data if handoff else {}
        source_task = (
            handoff_data.get("original_user_task")
            or handoff_data.get("query")
            or handoff.goal
            or task_text
            or ""
        )
        user_task = self._recover_user_query(source_task)
        project_root = str(
            handoff_data.get("project_root")
            or handoff_data.get("workspace_root")
            or "."
        ).strip() or "."
        focus_terms = self._infer_setup_build_focus_terms(user_task)
        search_terms = list(focus_terms)
        if "twilio" in focus_terms:
            search_terms.append("TWILIO_")
        if "inworld" in focus_terms:
            search_terms.append("INWORLD_")
        if "voice" in focus_terms or "call" in focus_terms:
            search_terms.append("voice_")

        hits_by_file: dict[str, list[str]] = {}
        for term in search_terms[:6]:
            self._notify_delegation_progress("setup_build_repo_search", term=term)
            result = await self._call_tool(
                "search_in_files",
                {
                    "path": project_root,
                    "text": term,
                    "file_pattern": "*",
                    "limit": 20,
                },
            )
            payload = self._tool_payload(result)
            if str(payload.get("status") or "").strip().lower() != "success":
                continue
            for entry in payload.get("results") or []:
                if not isinstance(entry, dict):
                    continue
                file_path = str(entry.get("file") or "").strip()
                if not file_path or self._is_setup_build_noise_path(file_path):
                    continue
                matches = entry.get("matches") or []
                match_lines = [
                    self._sanitize_setup_build_match_line(
                        file_path,
                        str(item.get("content") or "").strip(),
                    )
                    for item in matches
                    if isinstance(item, dict) and str(item.get("content") or "").strip()
                ]
                bucket = hits_by_file.setdefault(file_path, [])
                for line in match_lines[:3]:
                    if line and line not in bucket:
                        bucket.append(line)

        prioritized_files = sorted(
            hits_by_file.keys(),
            key=lambda item: (
                self._setup_build_path_priority(item),
                item,
            ),
        )
        strongest_priority = min((self._setup_build_path_priority(item) for item in prioritized_files), default=99)
        max_allowed_priority = strongest_priority
        if strongest_priority <= 1:
            max_allowed_priority = 1
        relevant_files = [
            item
            for item in prioritized_files
            if self._setup_build_path_priority(item) <= max_allowed_priority
        ][:6]
        if not relevant_files:
            relevant_files = prioritized_files[:6]

        read_snippets: dict[str, str] = {}
        for file_path in relevant_files[:4]:
            if self._is_setup_build_sensitive_path(file_path):
                continue
            self._notify_delegation_progress("setup_build_read_file", path=file_path)
            read_result = await self._call_tool("read_file", {"path": file_path})
            read_payload = self._tool_payload(read_result)
            if str(read_payload.get("status") or "").strip().lower() != "success":
                continue
            content = str(read_payload.get("content") or "")
            if content:
                read_snippets[file_path] = content[:1800]

        combined_text = "\n".join(read_snippets.values())
        lowered_text = combined_text.lower()
        twilio_present = (
            "twilio" in lowered_text
            or any("twilio" in path.lower() for path in relevant_files)
            or any("TWILIO_" in line for lines in hits_by_file.values() for line in lines)
        )
        inworld_present = (
            "inworld" in lowered_text
            or any("inworld" in path.lower() for path in relevant_files)
            or any("INWORLD_" in line for lines in hits_by_file.values() for line in lines)
        )
        voice_present = (
            "voice_" in lowered_text
            or "tts" in lowered_text
            or any("voice" in path.lower() for path in relevant_files)
        )
        twilio_env_present = (
            "twilio_" in lowered_text
            or any("TWILIO_" in line for lines in hits_by_file.values() for line in lines)
        )
        inworld_env_present = (
            "inworld_" in lowered_text
            or any("INWORLD_" in line for lines in hits_by_file.values() for line in lines)
        )
        twilio_call_logic_present = any(
            marker in lowered_text
            for marker in ("client.calls", "calls.create", "twiml", "voice_response")
        ) or any("test_call.py" in path.lower() for path in relevant_files)

        return {
            "user_task": user_task,
            "project_root": project_root,
            "hits_by_file": hits_by_file,
            "relevant_files": relevant_files,
            "read_snippets": read_snippets,
            "twilio_present": twilio_present,
            "inworld_present": inworld_present,
            "voice_present": voice_present,
            "twilio_env_present": twilio_env_present,
            "inworld_env_present": inworld_env_present,
            "twilio_call_logic_present": twilio_call_logic_present,
        }

    @staticmethod
    def _derive_setup_build_first_execution_step(findings: dict[str, Any]) -> tuple[str, str]:
        twilio_present = bool(findings.get("twilio_present"))
        inworld_present = bool(findings.get("inworld_present"))
        voice_present = bool(findings.get("voice_present"))
        twilio_env_present = bool(findings.get("twilio_env_present"))
        inworld_env_present = bool(findings.get("inworld_env_present"))
        twilio_call_logic_present = bool(findings.get("twilio_call_logic_present"))

        if not twilio_present and not inworld_present and not voice_present:
            return (
                "Lege zuerst den minimalen Integrationspfad fest und verankere die benoetigten "
                "Twilio- und Inworld-Bausteine im Repo.",
                "Im Repo ist derzeit kaum belastbare Vorarbeit fuer diese Integration sichtbar.",
            )
        if not twilio_env_present:
            return (
                "Ergaenze oder validiere zuerst die benoetigten `TWILIO_*`-Konfigurationen, "
                "bevor du einen Outbound-Call-Flow aufbaust.",
                "Die benoetigten `TWILIO_*`-Eintraege sind im geprueften Stand noch nicht belastbar sichtbar.",
            )
        if not inworld_env_present:
            return (
                "Ergaenze oder validiere zuerst den `INWORLD_API_KEY`, bevor du die Sprachausgabe "
                "in den Call-Flow verdrahtest.",
                "Die benoetigte Inworld-Konfiguration ist im geprueften Stand noch nicht belastbar sichtbar.",
            )
        if twilio_present and inworld_present and not twilio_call_logic_present:
            return (
                "Baue als ersten Umsetzungsschritt einen ausgehenden Twilio-Call-Flow, der die "
                "vorhandenen Twilio-Credentials mit dem bestehenden Inworld-TTS-Pfad zusammenfuehrt.",
                "",
            )
        if twilio_call_logic_present and inworld_present:
            return (
                "Pruefe als ersten Umsetzungsschritt, wie die bestehende Twilio-Call-Logik den "
                "Inworld-TTS-Pfad wirklich nutzt, und schliesse danach die letzte Voice-Bridge.",
                "",
            )
        if twilio_present and not inworld_present:
            return (
                "Ergaenze als ersten Umsetzungsschritt die Inworld-TTS-Anbindung im bestehenden "
                "Twilio-Kontext.",
                "",
            )
        if inworld_present and not twilio_present:
            return (
                "Ergaenze als ersten Umsetzungsschritt einen belastbaren Twilio-Voice-Outbound-Pfad "
                "zu den vorhandenen Inworld-Bausteinen.",
                "",
            )
        return (
            "Fuehre als ersten Umsetzungsschritt die vorhandenen Setup-Bausteine in einen "
            "klaren End-to-End-Pfad mit echten Runtime-Blockern zusammen.",
            "",
        )

    @staticmethod
    def _render_setup_build_probe_report(findings: dict[str, Any]) -> str:
        hits_by_file = findings.get("hits_by_file") or {}
        relevant_files = findings.get("relevant_files") or []
        if not hits_by_file:
            return (
                "Ich habe im Projekt keine klaren Vorbereitungen fuer diesen Setup-Auftrag gefunden. "
                "Es gibt aktuell keine belastbaren Repo-Hinweise auf die angefragte Integration."
            )

        twilio_present = bool(findings.get("twilio_present"))
        inworld_present = bool(findings.get("inworld_present"))
        voice_present = bool(findings.get("voice_present"))
        twilio_env_present = bool(findings.get("twilio_env_present"))
        inworld_env_present = bool(findings.get("inworld_env_present"))
        twilio_call_logic_present = bool(findings.get("twilio_call_logic_present"))

        lines = ["**Repo-Probe fuer vorhandene Vorbereitungen**", ""]
        lines.append("**Relevante Fundstellen:**")
        for file_path in relevant_files:
            lines.append(f"- {file_path}")
            for match_line in hits_by_file.get(file_path, [])[:2]:
                lines.append(f"  - {match_line}")
        lines.extend(
            [
                "",
                "**Verdichteter Stand:**",
                f"- Twilio-Bezug im Repo: {'ja' if twilio_present else 'nein'}",
                f"- Inworld-Bezug im Repo: {'ja' if inworld_present else 'nein'}",
                f"- Voice-/TTS-Bezug im Repo: {'ja' if voice_present else 'nein'}",
                f"- TWILIO_-Keys referenziert: {'ja' if twilio_env_present else 'nein'}",
                f"- INWORLD_-Keys referenziert: {'ja' if inworld_env_present else 'nein'}",
                f"- Outbound-Call-Logik fuer Twilio sichtbar: {'ja' if twilio_call_logic_present else 'nein'}",
                "",
                "**Einordnung:**",
            ]
        )
        if twilio_present or inworld_present or voice_present:
            lines.append(
                "- Es gibt bereits erkennbare Vorbereitungen im Repo. "
                "Die Basis ist also nicht null."
            )
        else:
            lines.append("- Im Repo ist derzeit kaum belastbare Vorarbeit fuer diese Integration sichtbar.")
        if not twilio_call_logic_present:
            lines.append(
                "- Eine klare Twilio-Outbound-Call-Implementierung ist in den geprueften Dateien noch nicht sichtbar."
            )
        if twilio_present and inworld_present:
            lines.append(
                "- Die naechste sinnvolle Arbeit ist, die vorhandenen Twilio- und Inworld-Bausteine "
                "in einen konkreten Call-Flow zusammenzufuehren."
            )

        return "\n".join(lines).strip()

    @classmethod
    def _render_setup_build_execution_report(cls, findings: dict[str, Any]) -> str:
        probe_report = cls._render_setup_build_probe_report(findings)
        first_step, blocker = cls._derive_setup_build_first_execution_step(findings)
        lines = [probe_report, "", "**Konkreter erster Umsetzungsschritt:**", f"- {first_step}"]
        if blocker:
            lines.extend(["", "**Blocker:**", f"- {blocker}"])
        lines.extend(
            [
                "",
                "**Ausfuehrungspfad:**",
                "- Noch keine freie Mehrfach-Delegation.",
                "- Keine generische Setup-Hilfe.",
                "- Zuerst den genannten ersten Umsetzungsschritt oder Blocker sauber schliessen.",
            ]
        )
        return "\n".join(lines).strip()

    async def _run_setup_build_probe(
        self,
        handoff: DelegationHandoff,
        task_text: str = "",
    ) -> str:
        self._notify_delegation_progress("setup_build_probe_start")
        findings = await self._collect_setup_build_probe_findings(handoff, task_text)
        return self._render_setup_build_probe_report(findings)

    async def _run_setup_build_execution(
        self,
        handoff: DelegationHandoff,
        task_text: str = "",
    ) -> str:
        self._notify_delegation_progress("setup_build_execution_start")
        findings = await self._collect_setup_build_probe_findings(handoff, task_text)
        return self._render_setup_build_execution_report(findings)

    async def _run_simple_live_lookup(
        self,
        handoff: DelegationHandoff | None,
        task_text: str = "",
    ) -> str:
        self._notify_delegation_progress("simple_live_lookup_start")
        handoff_task_type = str(handoff.handoff_data.get("task_type") or "").strip().lower() if handoff else ""
        allow_pricing_artifact_creation = handoff_task_type != "simple_live_lookup_document"
        source_task = (
            handoff.handoff_data.get("original_user_task")
            if handoff
            else ""
        ) or (
            handoff.handoff_data.get("query")
            if handoff
            else ""
        ) or (
            handoff.goal
            if handoff
            else ""
        ) or task_text
        user_task = self._recover_user_query(source_task)
        context_text = task_text or source_task
        topic_recall = self._recover_topic_recall(context_text)
        recent_assistant_replies = self._recover_recent_assistant_replies(context_text)
        extraction_followup = self._is_lookup_result_extraction_query(user_task)
        context_seed = self._contextual_lookup_seed(topic_recall, recent_assistant_replies)
        category = self._infer_simple_live_lookup_category(user_task, context_seed=context_seed)
        contextual_urls = self._extract_urls_from_context(context_text)

        if category == "local_places":
            synthetic_handoff = handoff or DelegationHandoff(
                goal=user_task,
                handoff_data={
                    "task_type": "location_local_search",
                    "original_user_task": user_task,
                    "query": user_task,
                },
            )
            return await self._run_location_local_search(synthetic_handoff, task_text or user_task)

        location_label = ""
        if category in {"weather", "cinema"}:
            self._notify_delegation_progress("location_context_lookup")
            location_result = await self._call_tool("get_current_location_context", {})
            if not (isinstance(location_result, dict) and location_result.get("error")):
                location_payload = self._tool_payload(location_result)
                has_location, location, presence_status = self._resolve_effective_location(
                    location_payload=location_payload,
                    task_text=task_text or source_task,
                )
                if (
                    has_location
                    and isinstance(location, dict)
                    and presence_status in {"live", "recent"}
                    and bool(location.get("usable_for_context", True))
                ):
                    location_label = self._location_summary(location)

        fetched_payload: dict[str, Any] | None = None
        if category == "pricing" and contextual_urls:
            primary_url = contextual_urls[0]
            self._notify_delegation_progress("fetch_contextual_source", url=primary_url)
            fetched = await self._call_tool(
                "fetch_url",
                {"url": primary_url, "max_content_length": 6000, "timeout": 15},
            )
            if not (isinstance(fetched, dict) and fetched.get("error")):
                fetched_payload = self._tool_payload(fetched)
                self._emit_user_action_blocker(fetched_payload, stage="fetch_contextual_source_blocked")
                pricing_response = await self._finalize_pricing_lookup(
                    user_task=user_task,
                    source_title=str(fetched_payload.get("title") or "").strip(),
                    source_url=str(fetched_payload.get("url") or primary_url).strip(),
                    source_text=str(fetched_payload.get("content") or fetched_payload.get("markdown") or ""),
                    context_seed=context_seed,
                    allow_artifact_creation=allow_pricing_artifact_creation,
                )
                if pricing_response:
                    return pricing_response
        elif extraction_followup and contextual_urls:
            primary_url = contextual_urls[0]
            self._notify_delegation_progress("fetch_contextual_source", url=primary_url)
            fetched = await self._call_tool(
                "fetch_url",
                {"url": primary_url, "max_content_length": 6000, "timeout": 15},
            )
            if not (isinstance(fetched, dict) and fetched.get("error")):
                fetched_payload = self._tool_payload(fetched)
                self._emit_user_action_blocker(fetched_payload, stage="fetch_contextual_source_blocked")

        search_query = self._build_simple_live_lookup_query(
            user_task=user_task,
            category=category,
            location_label=location_label,
            context_seed=context_seed,
        )
        if not search_query:
            return "Ich konnte aus der Anfrage noch keine brauchbare Live-Suchanfrage ableiten."

        if category in {"news", "science_news"}:
            self._notify_delegation_progress("news_lookup", query=search_query)
            search_result = await self._call_tool(
                "search_news",
                {"query": search_query, "max_results": 5, "language_code": "de"},
            )
        else:
            self._notify_delegation_progress("web_lookup", query=search_query)
            search_result = await self._call_tool(
                "search_web",
                {
                    "query": search_query,
                    "max_results": 5,
                    "language_code": "en" if category == "pricing" else "de",
                },
            )
        if isinstance(search_result, dict) and search_result.get("error"):
            return f"Die Live-Suche ist gerade fehlgeschlagen: {search_result['error']}"

        results = self._tool_list_payload(search_result)
        if results and not fetched_payload:
            top_url = str(results[0].get("url") or "").strip()
            if top_url:
                self._notify_delegation_progress("fetch_primary_source", url=top_url)
                fetched = await self._call_tool(
                    "fetch_url",
                    {
                        "url": top_url,
                        "max_content_length": 6000 if category == "pricing" else 1800,
                        "timeout": 15,
                    },
                )
                if not (isinstance(fetched, dict) and fetched.get("error")):
                    fetched_payload = self._tool_payload(fetched)
                    self._emit_user_action_blocker(fetched_payload, stage="fetch_primary_source_blocked")
                    if category == "pricing":
                        pricing_response = await self._finalize_pricing_lookup(
                            user_task=user_task,
                            source_title=str(fetched_payload.get("title") or "").strip(),
                            source_url=str(fetched_payload.get("url") or top_url).strip(),
                            source_text=str(fetched_payload.get("content") or fetched_payload.get("markdown") or ""),
                            context_seed=context_seed,
                            allow_artifact_creation=allow_pricing_artifact_creation,
                        )
                        if pricing_response:
                            return pricing_response

        intros = {
            "weather": f"Zum Wetter habe ich gerade diese aktuellen Treffer{' fuer ' + location_label if location_label else ''} gefunden:",
            "news": "Ich habe gerade diese aktuellen Treffer gefunden:",
            "science_news": "Aus der Wissenschaft fallen gerade diese aktuellen Treffer auf:",
            "pricing": "Zu den aktuellen Preisen habe ich gerade diese Treffer gefunden:",
            "person_lookup": "Zu der aktuellen Personen- oder Rollenfrage habe ich gerade diese Treffer gefunden:",
            "cinema": f"Zum aktuellen Kinoprogramm{' bei ' + location_label if location_label else ''} habe ich diese Treffer gefunden:",
            "web_lookup": "Ich habe gerade diese aktuellen Treffer gefunden:",
        }
        empty_messages = {
            "weather": "Ich habe zum Wetter gerade keine brauchbaren Live-Treffer gefunden.",
            "news": "Ich habe gerade keine brauchbaren News-Treffer gefunden.",
            "science_news": "Ich habe gerade keine brauchbaren Wissenschafts-Treffer gefunden.",
            "pricing": "Ich habe gerade keine brauchbaren Preis-Treffer gefunden.",
            "person_lookup": "Ich habe gerade keine brauchbaren aktuellen Personen-Treffer gefunden.",
            "cinema": "Ich habe gerade kein brauchbares Kinoprogramm gefunden.",
            "web_lookup": "Ich habe gerade keine brauchbaren Live-Treffer gefunden.",
        }
        return self._format_simple_lookup_results(
            intro=empty_messages.get(category, "Ich habe gerade keine brauchbaren Live-Treffer gefunden.")
            if not results
            else intros.get(category, "Ich habe gerade diese aktuellen Treffer gefunden:"),
            results=results,
            fetched_payload=fetched_payload,
        )

    async def _run_self_status_probe(self) -> str:
        ops_result = await self._call_tool("get_ops_observability", {"days": 7, "limit": 4})
        if isinstance(ops_result, dict) and ops_result.get("error"):
            return (
                f"Ich kann meinen aktuellen Ops-Zustand gerade nicht sauber lesen: {ops_result['error']}"
            )
        payload = self._tool_payload(ops_result)
        return self._format_ops_self_status(payload)

    async def _run_self_remediation_probe(self) -> str:
        ops_result = await self._call_tool("get_ops_observability", {"days": 7, "limit": 4})
        if isinstance(ops_result, dict) and ops_result.get("error"):
            return (
                f"Ich kann meine Gegenmassnahmen gerade nicht sauber ableiten: {ops_result['error']}"
            )
        payload = self._tool_payload(ops_result)
        return self._format_ops_remediation(payload)

    async def _run_self_priority_probe(self) -> str:
        ops_result = await self._call_tool("get_ops_observability", {"days": 7, "limit": 4})
        if isinstance(ops_result, dict) and ops_result.get("error"):
            return (
                f"Ich kann meine Priorisierung gerade nicht sauber ableiten: {ops_result['error']}"
            )
        payload = self._tool_payload(ops_result)
        return self._format_ops_priority(payload)

    @staticmethod
    def _recover_resolved_proposal(task_text: str) -> dict | None:
        """P4: Parst RESOLVED_PROPOSAL-Block aus dem Task-Text."""
        text = str(task_text or "")
        if "# RESOLVED_PROPOSAL" not in text:
            return None
        kind_match = re.search(r"^kind:\s*(\S+)", text, re.MULTILINE)
        query_match = re.search(r"^suggested_query:\s*(.+)$", text, re.MULTILINE)
        raw_match = re.search(r"^raw_proposal:\s*(.+)$", text, re.MULTILINE)
        if not kind_match or not query_match:
            return None
        return {
            "kind": kind_match.group(1).strip(),
            "suggested_query": query_match.group(1).strip(),
            "raw_proposal": raw_match.group(1).strip() if raw_match else "",
        }

    async def run(self, task: str) -> str:
        self._notify_delegation_progress("executor_run_started")
        handoff = parse_delegation_handoff(task)
        handoff_data = handoff.handoff_data if handoff else {}
        specialist_context_payload = (
            extract_specialist_context_from_handoff_data(handoff_data) if handoff else {}
        )
        alignment = assess_specialist_context_alignment(
            current_task=(
                handoff_data.get("original_user_task")
                or handoff_data.get("query")
                or (handoff.goal if handoff else task)
            ),
            payload=specialist_context_payload,
        )
        response_mode = str(specialist_context_payload.get("response_mode") or "").strip().lower()
        handoff_task_type = str(handoff_data.get("task_type") or "").strip().lower() if handoff else ""
        if handoff and response_mode == "summarize_state" and handoff_task_type in {
            "simple_live_lookup",
            "simple_live_lookup_document",
            "location_local_search",
            "location_route",
            "youtube_light_research",
        }:
            return format_specialist_signal_response(
                "needs_meta_reframe",
                reason="state_mode_conflicts_with_action_task",
                message=(
                    "Der Handoff verlangt einen Aktionspfad, der propagierte Meta-Modus erwartet aber eher "
                    "eine Zustandszusammenfassung oder Neubewertung statt direkter Ausfuehrung."
                ),
            )
        if handoff and alignment.get("alignment_state") == "needs_meta_reframe":
            return format_specialist_signal_response(
                "needs_meta_reframe",
                reason=str(alignment.get("reason") or ""),
                message=(
                    "Der aktuelle Handoff ist fuer diesen Executor-Lauf zu schwach oder falsch am laufenden "
                    "Gesprächsanker verankert. Meta sollte den Rahmen erst neu setzen."
                ),
            )
        plain_task = self._recover_user_query(task)
        semantic_recall = self._recover_semantic_recall(task)
        recent_assistant_replies = self._recover_recent_assistant_replies(task)
        topic_recall = self._recover_topic_recall(task)
        session_summary = self._recover_session_summary(task)
        followup_session_id = self._recover_followup_session_id(task)

        # P4: RESOLVED_PROPOSAL — Angebot direkt ausführen ohne LLM-Runde
        resolved_proposal = self._recover_resolved_proposal(task)
        if resolved_proposal:
            kind = resolved_proposal.get("kind", "generic_action")
            suggested_query = resolved_proposal.get("suggested_query", "")
            if kind == "youtube_search" and suggested_query:
                from agent.shared.delegation_handoff import DelegationHandoff
                synthetic_handoff = DelegationHandoff(
                    goal=suggested_query,
                    expected_output="YouTube-Videos zu dem angefragten Thema",
                    handoff_data={
                        "task_type": "youtube_light_research",
                        "query": suggested_query,
                        "original_user_task": suggested_query,
                        "search_mode": "live",
                        "max_results": 5,
                    },
                )
                return await self._run_youtube_light_research(synthetic_handoff)

        if handoff and handoff.handoff_data.get("task_type") == "location_local_search":
            return await self._run_location_local_search(handoff, task)
        if handoff and handoff.handoff_data.get("task_type") == "location_route":
            return await self._run_location_route(handoff, task)
        if handoff and handoff.handoff_data.get("task_type") == "youtube_light_research":
            return await self._run_youtube_light_research(handoff)
        if handoff and handoff.handoff_data.get("task_type") == "setup_build_probe":
            return await self._run_setup_build_probe(handoff, task)
        if handoff and handoff.handoff_data.get("task_type") == "setup_build_execution":
            return await self._run_setup_build_execution(handoff, task)
        if handoff and handoff.handoff_data.get("task_type") in {"simple_live_lookup", "simple_live_lookup_document"}:
            return await self._run_simple_live_lookup(handoff, task)
        if not handoff and self._is_simple_live_lookup_query(plain_task):
            return await self._run_simple_live_lookup(None, plain_task)
        if not handoff and self._is_self_status_query(plain_task):
            return await self._run_self_status_probe()
        if not handoff and self._is_self_remediation_query(plain_task):
            return await self._run_self_remediation_probe()
        if not handoff and self._is_self_priority_query(plain_task):
            return await self._run_self_priority_probe()
        if not handoff and self._is_self_recall_query(plain_task):
            recall_basis = semantic_recall or recent_assistant_replies
            recall_source = (
                "semantic"
                if semantic_recall
                else "recent_assistant"
                if recent_assistant_replies
                else "summary"
                if session_summary
                else "none"
            )
            self._record_conversation_recall(
                session_id=followup_session_id,
                query=plain_task,
                source=recall_source,
                semantic_recall=semantic_recall,
                recent_assistant_replies=recent_assistant_replies,
                session_summary=session_summary,
            )
            formatted_recall = self._format_semantic_recall_response(
                plain_task,
                recall_basis,
                session_summary=session_summary,
            )
            if formatted_recall:
                return formatted_recall
        if not handoff and self._is_capability_learning_query(plain_task):
            capability_basis = topic_recall or recent_assistant_replies or semantic_recall
            formatted_capability = self._format_capability_learning_response(
                plain_task,
                capability_basis,
                session_summary=session_summary,
            )
            if formatted_capability:
                return formatted_capability
        if not handoff and topic_recall and self._is_topic_followup_query(plain_task):
            self._record_conversation_recall(
                session_id=followup_session_id,
                query=plain_task,
                source="topic_recall",
                semantic_recall=[],
                recent_assistant_replies=topic_recall,
                session_summary=session_summary,
            )
            formatted_topic_recall = self._format_topic_recall_response(plain_task, topic_recall)
            if formatted_topic_recall:
                return formatted_topic_recall
        if not handoff and self._is_smalltalk_query(plain_task):
            return self._smalltalk_response(plain_task)
        effective_task = handoff.goal if handoff and handoff.goal else task
        handoff_context = self._build_executor_handoff_context(handoff)
        enriched_task = "\n\n".join(part for part in (effective_task, handoff_context) if part)
        self._notify_delegation_progress("executor_llm_fallback")
        return await super().run(enriched_task)
