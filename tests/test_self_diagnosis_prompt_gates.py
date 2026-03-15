from agent.prompts import (
    EXECUTOR_PROMPT_TEMPLATE,
    META_SYSTEM_PROMPT,
    REASONING_PROMPT_TEMPLATE,
)


def test_meta_prompt_requires_multi_source_provider_evidence():
    assert "agent/providers.py" in META_SYSTEM_PROMPT
    assert "main_dispatcher.py" in META_SYSTEM_PROMPT
    assert "IMMER mindestens 2 Quellen" in META_SYSTEM_PROMPT
    assert "EINZELNE ZEILEN ODER NUR EINE DATEI SIND NICHT AUSREICHEND." in META_SYSTEM_PROMPT


def test_executor_prompt_requires_multi_source_provider_evidence():
    assert "agent/providers.py" in EXECUTOR_PROMPT_TEMPLATE
    assert "main_dispatcher.py" in EXECUTOR_PROMPT_TEMPLATE
    assert "mindestens 2 Quellen" in EXECUTOR_PROMPT_TEMPLATE


def test_reasoning_prompt_has_self_diagnosis_gate():
    assert "SELBST-DIAGNOSE-GATE" in REASONING_PROMPT_TEMPLATE
    assert "[BELEGT" in REASONING_PROMPT_TEMPLATE
    assert "agent/providers.py" in REASONING_PROMPT_TEMPLATE
    assert "main_dispatcher.py" in REASONING_PROMPT_TEMPLATE
    assert "Keine freien Provider-Tabellen aus Vermutung" in REASONING_PROMPT_TEMPLATE
