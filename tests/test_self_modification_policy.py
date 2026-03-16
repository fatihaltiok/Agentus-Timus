import pytest

from orchestration.self_modification_policy import evaluate_self_modification_policy


def test_policy_allows_prompt_policy_zone():
    decision = evaluate_self_modification_policy("agent/prompts.py")
    assert decision.allowed is True
    assert decision.zone_id == "prompt_policy"
    assert decision.effective_change_type == "prompt_policy"
    assert "tests/test_meta_handoff.py" in decision.required_test_targets


def test_policy_blocks_agent_runtime_files_even_if_editor_whitelist_allows_them():
    decision = evaluate_self_modification_policy("agent/agents/meta.py")
    assert decision.allowed is False
    assert "gesperrten" in decision.reason


def test_policy_blocks_unlisted_low_risk_zone():
    decision = evaluate_self_modification_policy("tools/demo.py")
    assert decision.allowed is False
    assert "keiner freigegebenen" in decision.reason


def test_policy_allows_deep_research_reporting_zone():
    decision = evaluate_self_modification_policy(
        "tools/deep_research/tool.py",
        change_type="report_quality_guardrails",
    )
    assert decision.allowed is True
    assert decision.zone_id == "deep_research_reporting"
    assert "tests/test_deep_research_pdf_requirements.py" in decision.required_test_targets


def test_policy_rejects_wrong_change_type_for_docs():
    decision = evaluate_self_modification_policy("docs/report.md", change_type="orchestration_policy")
    assert decision.allowed is False
    assert "nicht erlaubt" in decision.reason
