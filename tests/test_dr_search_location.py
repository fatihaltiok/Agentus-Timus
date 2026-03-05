# tests/test_dr_search_location.py
"""
Tests für Suchlocation & Query-Expansion (M2 — RC4).

Prüft: Language-Detection, Location-Mapping, Query-Expansion.
Kein Netzwerk.
"""

import pytest
from tools.deep_research.tool import (
    _detect_language,
    _detect_domain,
    _LANG_LOCATION_MAP,
    TECH_KEYWORDS,
)


class TestDetectLanguage:
    def test_english_query(self):
        assert _detect_language("self-monitoring AI agents") == "en"

    def test_english_technical(self):
        assert _detect_language("transformer architecture deep learning benchmark") == "en"

    def test_german_query_with_many_umlauts(self):
        # String mit genug Umlauten damit ASCII-Ratio < 80%
        # "Über üben öfter ärger übergröße" → viele Umlaute
        text = "ü" * 5 + " normale worte"  # >20% non-ASCII
        assert _detect_language(text) == "de"

    def test_german_with_high_umlaut_density(self):
        # Genug Nicht-ASCII damit Ratio < 80%
        # 5 Umlaute in 20-Zeichen-String: 25% non-ASCII → de
        text = "üöäÜÖ worte"  # 5 non-ASCII von 11 → 54% ASCII → de
        assert _detect_language(text) == "de"

    def test_empty_query_fallback(self):
        assert _detect_language("") == "de"

    def test_mostly_ascii_is_english(self):
        # Nur ASCII → englisch
        result = _detect_language("state of the art language model training")
        assert result == "en"

    def test_high_non_ascii_is_german(self):
        # >20% Umlaute → de
        # "üüüüü test" — 5 Umlaute von 10 Zeichen = 50% ASCII
        result = _detect_language("üüüüü test")
        assert result == "de"


class TestLanguageLocationMapping:
    def test_english_maps_to_us(self):
        assert _LANG_LOCATION_MAP["en"] == 2840  # USA

    def test_german_maps_to_germany(self):
        assert _LANG_LOCATION_MAP["de"] == 2276  # Deutschland

    def test_french_maps_to_france(self):
        assert _LANG_LOCATION_MAP["fr"] == 2250

    def test_spanish_maps_to_spain(self):
        assert _LANG_LOCATION_MAP["es"] == 2724

    def test_map_has_four_languages(self):
        assert len(_LANG_LOCATION_MAP) >= 4


class TestDetectDomain:
    def test_ai_query_is_tech(self):
        assert _detect_domain("self-monitoring AI agents") == "tech"

    def test_llm_query_is_tech(self):
        assert _detect_domain("LLM fine-tuning performance") == "tech"

    def test_transformer_is_tech(self):
        assert _detect_domain("transformer architecture attention mechanism") == "tech"

    def test_generic_query_is_default(self):
        assert _detect_domain("Wettervorhersage Methoden") == "default"

    def test_politics_is_default(self):
        assert _detect_domain("Bundestagswahl Ergebnisse") == "default"

    def test_case_insensitive(self):
        assert _detect_domain("AI Agents Architecture") == "tech"

    def test_neural_keyword(self):
        assert _detect_domain("neural network training") == "tech"


class TestTechKeywords:
    def test_tech_keywords_not_empty(self):
        assert len(TECH_KEYWORDS) >= 10

    def test_ai_in_keywords(self):
        assert "ai" in TECH_KEYWORDS

    def test_transformer_in_keywords(self):
        assert "transformer" in TECH_KEYWORDS

    def test_agent_in_keywords(self):
        assert "agent" in TECH_KEYWORDS
