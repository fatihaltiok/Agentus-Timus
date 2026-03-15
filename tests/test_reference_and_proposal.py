"""
Tests für P2 (Referenz-Fortsetzung) und P4 (Self-Proposal-Resolution):
- _is_reference_continuation  (mcp_server.py)
- _is_affirmation              (mcp_server.py)
- _extract_proposal_metadata   (mcp_server.py)
- ExecutorAgent._recover_resolved_proposal
- _youtube_translate_query EN-Filler-Bereinigung
"""
import re
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


# ── Reine Konstanten / Funktionen aus mcp_server.py direkt testen ─────────────
# (ohne schwere FastAPI-Imports — wir extrahieren nur was wir brauchen)

_REFERENCE_CONTINUATION_PATTERNS = (
    r"\bdamit\b",
    r"\bdas gleiche\b",
    r"\bdie gleiche\b",
    r"\bdieselbe\b",
    r"\bdas selbe\b",
    r"\bgenau das\b",
    r"\bgenau das gleiche\b",
    r"\bselbiges\b",
)

_AFFIRMATION_PATTERNS = (
    r"^\s*ja\s*[.!]?\s*$",
    r"^\s*ok\s*[.!]?\s*$",
    r"^\s*okay\s*[.!]?\s*$",
    r"\bja\s+mach\s+das\b",
    r"\bja\s+mach\s+mal\b",
    r"\bja\s+schau\s+(mal\s+)?danach\b",
    r"\bschau\s+mal\s+danach\b",
    r"\bklingt\s+gut\b",
    r"\bgerne\s*[.!]?\s*$",
    r"\bsicher\s*[.!]?\s*$",
    r"\bjep\s*[.!]?\s*$",
    r"\byep\s*[.!]?\s*$",
    r"^\s*mach\s+das\s*[.!]?\s*$",
    r"^\s*mach\s+mal\s*[.!]?\s*$",
    r"\blos\s+geht.?s\b",
    r"\bauf\s+jeden\s+fall\b",
)

_PROPOSAL_TRIGGER_PATTERNS = (
    r"\bsoll\s+ich\b",
    r"\bich\s+kann\b",
    r"\bich\s+k[oö]nnte\b",
    r"\bwillst\s+du\b",
    r"\bmagst\s+du\b",
    r"\bmöchtest\s+du\b",
    r"\bmoechtest\s+du\b",
)

_PROPOSAL_TRAILING_VERBS = re.compile(
    r"\s+(?:suchen|starten|machen|ausführen|ausfuehren|recherchieren|ansehen|anschauen|schauen)\s*$",
    re.IGNORECASE,
)


def _is_reference_continuation(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized or len(normalized.split()) > 12:
        return False
    return any(re.search(p, normalized) for p in _REFERENCE_CONTINUATION_PATTERNS)


def _is_affirmation(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized or len(normalized.split()) > 8:
        return False
    return any(re.search(p, normalized) for p in _AFFIRMATION_PATTERNS)


def _clean_proposal_query(text: str) -> str:
    return _PROPOSAL_TRAILING_VERBS.sub("", text.strip()).strip(" ,.!?")


def _extract_proposal_metadata(text: str) -> dict | None:
    source = str(text or "").strip()
    if not source:
        return None
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", source) if s.strip()]
    tail = sentences[-3:] if len(sentences) >= 3 else sentences
    for sentence in reversed(tail):
        normalized = sentence.lower()
        if not any(re.search(p, normalized) for p in _PROPOSAL_TRIGGER_PATTERNS):
            continue
        yt_match = re.search(
            r"youtube(?:[- ]?videos?)?(?:\s+zu\s+|\s+über\s+|\s+ueber\s+)([^?.!,]+)",
            normalized,
        )
        if not yt_match:
            yt_match_rev = re.search(r"([^?.!,]+?)\s+(?:auf|in|bei)\s+youtube", normalized)
            if yt_match_rev:
                raw = yt_match_rev.group(1)
                raw = re.sub(
                    r"^.*?(?:soll ich|ich kann|ich könnte|ich koennte|willst du)"
                    r"(?:\s+\w+){0,4}\s+nach\s+", "", raw, flags=re.IGNORECASE,
                ).strip()
                if raw and len(raw) >= 3:
                    return {
                        "kind": "youtube_search", "target": "youtube",
                        "suggested_query": _clean_proposal_query(raw)[:200],
                        "raw_sentence": sentence[:300],
                    }
        if yt_match:
            return {
                "kind": "youtube_search", "target": "youtube",
                "suggested_query": _clean_proposal_query(yt_match.group(1))[:200],
                "raw_sentence": sentence[:300],
            }
        web_match = re.search(r"(?:nach\s+|zu\s+|über\s+|ueber\s+)([^?.!,]{4,})", normalized)
        if web_match:
            suggested = _clean_proposal_query(web_match.group(1))
            if suggested and len(suggested) >= 3:
                return {
                    "kind": "web_search", "target": "web",
                    "suggested_query": suggested[:200],
                    "raw_sentence": sentence[:300],
                }
        content_match = re.search(
            r"(?:soll ich|ich kann|ich könnte|ich koennte|willst du|magst du|möchtest du|moechtest du)"
            r"(?:\s+\w+){0,5}\s+(.+?)(?:\s*\?.*)?$",
            normalized,
        )
        if content_match:
            suggested = _clean_proposal_query(content_match.group(1))
            if suggested and len(suggested) >= 4:
                return {
                    "kind": "generic_action", "target": "executor",
                    "suggested_query": suggested[:200],
                    "raw_sentence": sentence[:300],
                }
    return None


# ── P2: Referenz-Fortsetzung ──────────────────────────────────────────────────

class TestIsReferenceContinuation:
    def test_damit(self):
        assert _is_reference_continuation("mach damit eine youtube suche") is True

    def test_das_gleiche(self):
        assert _is_reference_continuation("das gleiche bitte") is True

    def test_dieselbe(self):
        assert _is_reference_continuation("dieselbe suche nochmal") is True

    def test_genau_das(self):
        assert _is_reference_continuation("genau das mach nochmal") is True

    def test_no_ref_ki(self):
        assert _is_reference_continuation("was ist ki") is False

    def test_no_ref_long(self):
        assert _is_reference_continuation(
            "damit meine ich eigentlich etwas ganz anderes als das was du sagst hier"
        ) is False

    def test_empty(self):
        assert _is_reference_continuation("") is False


# ── P4: Affirmations-Erkennung ────────────────────────────────────────────────

class TestIsAffirmation:
    def test_ja(self):
        assert _is_affirmation("ja") is True

    def test_ok(self):
        assert _is_affirmation("ok") is True

    def test_ja_mach_das(self):
        assert _is_affirmation("ja mach das") is True

    def test_schau_mal_danach(self):
        assert _is_affirmation("schau mal danach") is True

    def test_ja_schau_mal_danach(self):
        assert _is_affirmation("ja schau mal danach") is True

    def test_klingt_gut(self):
        assert _is_affirmation("klingt gut") is True

    def test_gerne(self):
        assert _is_affirmation("gerne") is True

    def test_auf_jeden_fall(self):
        assert _is_affirmation("auf jeden fall") is True

    def test_negation_not_affirm(self):
        assert _is_affirmation("nein danke") is False

    def test_question_not_affirm(self):
        assert _is_affirmation("was ist ki") is False

    def test_long_not_affirm(self):
        assert _is_affirmation("ja das wäre interessant aber ich bin nicht sicher") is False

    def test_empty(self):
        assert _is_affirmation("") is False


# ── P4: Proposal Extraction ───────────────────────────────────────────────────

class TestExtractProposalMetadata:
    def test_youtube_zu(self):
        reply = (
            "Hier sind die Ergebnisse. "
            "Soll ich auch nach aktuellen YouTube-Videos zu KI Agenten suchen?"
        )
        p = _extract_proposal_metadata(reply)
        assert p is not None
        assert p["kind"] == "youtube_search"
        assert "ki agenten" in p["suggested_query"]
        assert not p["suggested_query"].endswith("suchen")

    def test_youtube_auf(self):
        reply = (
            "Ich könnte auch nach neuen KI-Entwicklungen auf YouTube suchen. "
            "Willst du das?"
        )
        p = _extract_proposal_metadata(reply)
        assert p is not None
        assert p["kind"] == "youtube_search"

    def test_generic_action(self):
        reply = "Das waren die News. Soll ich das direkt ausführen?"
        p = _extract_proposal_metadata(reply)
        assert p is not None
        assert p["kind"] in {"generic_action", "web_search"}

    def test_no_proposal_statement(self):
        reply = "Ich habe gerade keine passenden Videos gefunden."
        p = _extract_proposal_metadata(reply)
        assert p is None

    def test_no_proposal_fact(self):
        reply = "KI Agenten sind autonome Softwaresysteme die eigenständig handeln."
        p = _extract_proposal_metadata(reply)
        assert p is None

    def test_raw_sentence_stored(self):
        reply = "Soll ich nach YouTube-Videos zu Machine Learning suchen?"
        p = _extract_proposal_metadata(reply)
        assert p is not None
        assert "raw_sentence" in p
        assert len(p["raw_sentence"]) > 0

    def test_empty_text(self):
        assert _extract_proposal_metadata("") is None


# ── P4: Executor RESOLVED_PROPOSAL ───────────────────────────────────────────

class TestRecoverResolvedProposal:
    _task = (
        "# RESOLVED_PROPOSAL\n"
        "kind: youtube_search\n"
        "suggested_query: KI Agenten neue Entwicklungen\n"
        "raw_proposal: Soll ich nach YouTube-Videos zu KI Agenten suchen?\n"
        "\n"
        "# CURRENT USER QUERY\n"
        "ja schau mal danach"
    )

    def test_kind_parsed(self):
        from agent.agents.executor import ExecutorAgent
        p = ExecutorAgent._recover_resolved_proposal(self._task)
        assert p is not None
        assert p["kind"] == "youtube_search"

    def test_query_parsed(self):
        from agent.agents.executor import ExecutorAgent
        p = ExecutorAgent._recover_resolved_proposal(self._task)
        assert p["suggested_query"] == "KI Agenten neue Entwicklungen"

    def test_no_proposal_returns_none(self):
        from agent.agents.executor import ExecutorAgent
        assert ExecutorAgent._recover_resolved_proposal("was ist ki?") is None

    def test_empty_returns_none(self):
        from agent.agents.executor import ExecutorAgent
        assert ExecutorAgent._recover_resolved_proposal("") is None

    def test_incomplete_no_query_returns_none(self):
        from agent.agents.executor import ExecutorAgent
        task = "# RESOLVED_PROPOSAL\nkind: youtube_search\n"
        assert ExecutorAgent._recover_resolved_proposal(task) is None


# ── EN-Query Übersetzung: kein DE-Filler im Output ────────────────────────────

class TestYoutubeTranslateQuery:
    def test_ki_to_ai(self):
        from agent.agents.executor import _youtube_translate_query
        result = _youtube_translate_query("ki agenten")
        assert "AI" in result or "ai" in result.lower()

    def test_no_german_filler_in_output(self):
        from agent.agents.executor import _youtube_translate_query
        q = "ki agenten und ki selbst neue entwicklungen im bereich ki"
        result = _youtube_translate_query(q)
        for german_word in ["und", "selbst", "neue", "bereich", "im"]:
            assert german_word not in result.lower(), (
                f"Deutsches Filler-Wort '{german_word}' noch im EN-Query: {repr(result)}"
            )

    def test_english_preserved(self):
        from agent.agents.executor import _youtube_translate_query
        assert _youtube_translate_query("python machine learning") == "python machine learning"

    def test_empty(self):
        from agent.agents.executor import _youtube_translate_query
        assert _youtube_translate_query("") == ""
