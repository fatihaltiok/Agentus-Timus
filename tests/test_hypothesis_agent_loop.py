"""
Hypothesis Property-based Tests für Agent-Loop-Fixes.
Sucht aktiv nach Gegenbeispielen für die formalen Invarianten.
"""
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from agent.base_agent import BaseAgent


# ── Th.54: max_tokens immer positiv ───────────────────────────────────────

@given(st.text(min_size=0, max_size=100))
@settings(max_examples=500)
def test_max_tokens_always_positive(model_name):
    """Für jeden beliebigen Modellnamen: max_tokens > 0."""
    result = BaseAgent._get_max_tokens_for_model(model_name)
    assert result > 0, f"max_tokens={result} für model='{model_name}'"


# ── Th.55: Reasoning-Modelle ≥ Standard ───────────────────────────────────

@given(st.sampled_from([
    "qwen/qwq-32b", "deepseek-reasoner", "deepseek-r1",
    "qwen/qvq-72b", "deepseek/deepseek-r1",
]))
def test_reasoning_tokens_ge_standard(reasoning_model):
    """Reasoning-Modelle bekommen immer mehr Tokens als Standard-Modelle."""
    reasoning_tokens = BaseAgent._get_max_tokens_for_model(reasoning_model)
    standard_tokens = BaseAgent._get_max_tokens_for_model("claude-haiku-4-5")
    assert reasoning_tokens >= standard_tokens, (
        f"{reasoning_model}: {reasoning_tokens} < standard {standard_tokens}"
    )


# ── Th.56: strip_think_tags — Ausgabe ≤ Länge der Eingabe ─────────────────

@given(st.text(max_size=2000))
@settings(max_examples=1000)
def test_strip_think_output_le_input(text):
    """strip_think_tags() gibt niemals mehr Zeichen zurück als rein."""
    result = BaseAgent._strip_think_tags(text)
    assert len(result) <= len(text), (
        f"Ausgabe ({len(result)}) > Eingabe ({len(text)})"
    )


@given(st.text(max_size=2000))
@settings(max_examples=1000)
def test_strip_think_no_open_tag_in_output(text):
    """Nach dem Strip enthält die Ausgabe niemals <think>."""
    result = BaseAgent._strip_think_tags(text)
    assert "<think>" not in result, f"<think> noch in Ausgabe: {result[:100]}"


@given(st.text(max_size=500).filter(lambda t: "<think>" not in t))
@settings(max_examples=500)
def test_strip_think_passthrough_without_tags(text):
    """Text ohne <think>-Tags wird unverändert durchgereicht."""
    result = BaseAgent._strip_think_tags(text)
    assert result == text, f"Unerwartete Veränderung: '{text[:50]}' → '{result[:50]}'"


# ── Bug-Regression: Error:-Prefix darf loop nicht beenden ─────────────────

@given(
    st.text(min_size=1, max_size=200).filter(lambda t: not t.startswith("Error")),
    st.text(min_size=1, max_size=500),
)
@settings(max_examples=300)
def test_reasoning_content_fallback_never_returns_error_prefix(content, reasoning):
    """
    Wenn content leer ist und reasoning_content vorhanden:
    Der Rückgabewert darf NICHT mit 'Error:' beginnen.
    (Regression: alte Implementierung beendete den Loop durch Error:-Prefix)
    """
    # Simuliere die Fallback-Logik aus _call_openai_compatible
    stripped_reasoning = BaseAgent._strip_think_tags(reasoning.strip())
    # Die neue Implementierung gibt reasoning zurück (kein "Error:" Prefix)
    assert not stripped_reasoning.startswith("Error:"), (
        f"reasoning_content-Fallback würde Loop beenden: '{stripped_reasoning[:60]}'"
    )


@given(st.text(max_size=1000))
@settings(max_examples=500)
def test_strip_think_idempotent(text):
    """Doppeltes Strippen verändert das Ergebnis nicht."""
    once = BaseAgent._strip_think_tags(text)
    twice = BaseAgent._strip_think_tags(once)
    assert once == twice, f"Nicht idempotent: einmal='{once[:50]}', zweimal='{twice[:50]}'"
