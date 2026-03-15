from __future__ import annotations

import deal

from agent.prompts import (
    EXECUTOR_PROMPT_TEMPLATE,
    META_SYSTEM_PROMPT,
    REASONING_PROMPT_TEMPLATE,
)


@deal.post(lambda r: r is True)
def _contract_meta_prompt_has_multisource_provider_gate() -> bool:
    return (
        "SELBST-DIAGNOSE-GATE" in META_SYSTEM_PROMPT
        and "agent/providers.py" in META_SYSTEM_PROMPT
        and "main_dispatcher.py" in META_SYSTEM_PROMPT
        and "IMMER mindestens 2 Quellen" in META_SYSTEM_PROMPT
    )


@deal.post(lambda r: r is True)
def _contract_executor_prompt_has_multisource_provider_gate() -> bool:
    return (
        "SELBST-DIAGNOSE-GATE" in EXECUTOR_PROMPT_TEMPLATE
        and "agent/providers.py" in EXECUTOR_PROMPT_TEMPLATE
        and "main_dispatcher.py" in EXECUTOR_PROMPT_TEMPLATE
        and "mindestens 2 Quellen" in EXECUTOR_PROMPT_TEMPLATE
    )


@deal.post(lambda r: r is True)
def _contract_reasoning_prompt_has_self_diagnosis_gate() -> bool:
    return (
        "SELBST-DIAGNOSE-GATE" in REASONING_PROMPT_TEMPLATE
        and "[BELEGT" in REASONING_PROMPT_TEMPLATE
        and "agent/providers.py" in REASONING_PROMPT_TEMPLATE
        and "main_dispatcher.py" in REASONING_PROMPT_TEMPLATE
    )


def test_contract_meta_prompt_has_multisource_provider_gate():
    assert _contract_meta_prompt_has_multisource_provider_gate() is True


def test_contract_executor_prompt_has_multisource_provider_gate():
    assert _contract_executor_prompt_has_multisource_provider_gate() is True


def test_contract_reasoning_prompt_has_self_diagnosis_gate():
    assert _contract_reasoning_prompt_has_self_diagnosis_gate() is True
