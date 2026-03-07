"""CrossHair-Contracts + Hypothesis für Timeout-Auswahl-Logik.

Modelliert die Invariante aus agent/agent_registry.py:
  RESEARCH_TIMEOUT default="600" (sequential + parallel)

CrossHair-Contracts beschreiben die pure Timeout-Auswahl-Funktion,
die äquivalent zur Logik in delegate() und run_single() ist.

Lean 4 Bezug (CiSpecs.lean):
  Th.9  research_timeout_sufficient:  600 ∈ [300, 900]
  Th.10 research_timeout_gt_delegation: 600 > 120
  Th.11 parallel_research_timeout_eq_sequential: t_seq=600 = t_par=600
"""
from __future__ import annotations

import os
from typing import Optional

import deal
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Pure Funktion — isoliert testbar, modelliert agent_registry.py Logik
# ---------------------------------------------------------------------------

@deal.pre(lambda _: _.research_env >= 1, message="RESEARCH_TIMEOUT muss > 0 sein")
@deal.pre(lambda _: _.delegation_env >= 1, message="DELEGATION_TIMEOUT muss > 0 sein")
@deal.post(lambda r: r > 0, message="Timeout muss positiv sein")
@deal.post(lambda r: r >= 1, message="Timeout-Mindestwert 1s")
def select_sequential_timeout(
    agent_name: str,
    research_env: float = 600.0,
    delegation_env: float = 120.0,
) -> float:
    """Wählt sequenziellen Timeout (entspricht delegate() in agent_registry.py)."""
    if agent_name == "research":
        return research_env
    return delegation_env


@deal.pre(lambda _: _.research_env >= 1, message="RESEARCH_TIMEOUT muss > 0 sein")
@deal.pre(lambda _: _.delegation_env >= 1, message="DELEGATION_TIMEOUT muss > 0 sein")
@deal.pre(lambda _: _.task_override is None or _.task_override > 0,
          message="Expliziter Task-Timeout muss positiv sein wenn gesetzt")
@deal.post(lambda r: r > 0, message="Timeout muss positiv sein")
def select_parallel_timeout(
    agent_name: str,
    task_override: Optional[float] = None,
    research_env: float = 600.0,
    delegation_env: float = 120.0,
) -> float:
    """Wählt parallelen Timeout (entspricht run_single() in agent_registry.py)."""
    default = research_env if agent_name == "research" else delegation_env
    return task_override if task_override is not None else default


# ---------------------------------------------------------------------------
# CrossHair-kompatible Unit-Tests (laufen auch ohne crosshair CLI)
# ---------------------------------------------------------------------------

class TestCrossHairContracts:

    def test_sequential_research_default_is_600(self):
        """Lean Th.9 + Th.10: research bekommt 600s (sequential)."""
        result = select_sequential_timeout("research")
        assert result == pytest.approx(600.0)
        assert 300 <= result <= 900  # Lean Th.9
        assert result > 120.0        # Lean Th.10

    def test_sequential_other_agent_default_is_120(self):
        """Andere Agenten bekommen 120s (sequential)."""
        for agent in ("meta", "executor", "document", "shell"):
            result = select_sequential_timeout(agent)
            assert result == pytest.approx(120.0), f"{agent} sollte 120s haben"

    def test_parallel_research_default_is_600(self):
        """Lean Th.11: parallel research == sequential research == 600s."""
        seq = select_sequential_timeout("research")
        par = select_parallel_timeout("research")
        assert seq == pytest.approx(par), "Lean Th.11: parallel == sequential"
        assert par == pytest.approx(600.0)

    def test_parallel_task_override_respected(self):
        """Expliziter task timeout überschreibt den Default."""
        result = select_parallel_timeout("research", task_override=300.0)
        assert result == pytest.approx(300.0)

    def test_parallel_other_agent_default_is_120(self):
        """Nicht-Research bekommt 120s im parallel-Modus."""
        result = select_parallel_timeout("document")
        assert result == pytest.approx(120.0)

    def test_research_timeout_env_override(self):
        """RESEARCH_TIMEOUT=60 überschreibt Default (ENV-Simulation)."""
        result = select_sequential_timeout("research", research_env=60.0)
        assert result == pytest.approx(60.0)

    def test_contract_pre_condition_positive_timeout(self):
        """deal.pre: research_env muss > 0 sein."""
        with pytest.raises(deal.PreContractError):
            select_sequential_timeout("research", research_env=0.0)

    def test_contract_pre_parallel_task_override_must_be_positive(self):
        """deal.pre: expliziter Task-Override muss > 0 sein."""
        with pytest.raises(deal.PreContractError):
            select_parallel_timeout("research", task_override=-1.0)


# ---------------------------------------------------------------------------
# Hypothesis Property Tests
# ---------------------------------------------------------------------------

@given(
    research_env=st.floats(min_value=1.0, max_value=3600.0),
    delegation_env=st.floats(min_value=1.0, max_value=600.0),
)
@settings(max_examples=200)
def test_hypothesis_research_always_gets_more_or_equal_time(research_env, delegation_env):
    """Property: RESEARCH_TIMEOUT ≥ DELEGATION_TIMEOUT (wenn research_env ≥ delegation_env)."""
    assume(research_env >= delegation_env)
    seq_research = select_sequential_timeout("research", research_env=research_env, delegation_env=delegation_env)
    seq_other = select_sequential_timeout("meta", research_env=research_env, delegation_env=delegation_env)
    assert seq_research >= seq_other


@given(research_env=st.floats(min_value=1.0, max_value=3600.0))
@settings(max_examples=200)
def test_hypothesis_parallel_eq_sequential_for_research(research_env):
    """Lean Th.11: parallel == sequential für research bei allen gültigen env-Werten."""
    seq = select_sequential_timeout("research", research_env=research_env)
    par = select_parallel_timeout("research", task_override=None, research_env=research_env)
    assert seq == pytest.approx(par), f"Lean Th.11 verletzt: seq={seq} ≠ par={par}"


@given(
    agent=st.sampled_from(["meta", "executor", "document", "shell", "communication"]),
    delegation_env=st.floats(min_value=1.0, max_value=600.0),
)
@settings(max_examples=200)
def test_hypothesis_non_research_always_gets_delegation_timeout(agent, delegation_env):
    """Nicht-Research-Agenten bekommen immer delegation_env (nicht research_env)."""
    result = select_sequential_timeout(agent, research_env=999.0, delegation_env=delegation_env)
    assert result == pytest.approx(delegation_env), (
        f"{agent} sollte delegation_env={delegation_env} bekommen, nicht research_env"
    )


@given(
    task_override=st.floats(min_value=1.0, max_value=7200.0),
    research_env=st.floats(min_value=1.0, max_value=3600.0),
)
@settings(max_examples=200)
def test_hypothesis_task_override_always_wins(task_override, research_env):
    """Expliziter Task-Timeout überschreibt immer den Default."""
    result = select_parallel_timeout("research", task_override=task_override, research_env=research_env)
    assert result == pytest.approx(task_override), (
        f"Task-Override {task_override} sollte Default {research_env} überschreiben"
    )


@given(research_env=st.floats(min_value=300.0, max_value=900.0))
@settings(max_examples=100)
def test_hypothesis_lean_th9_research_timeout_sufficient(research_env):
    """Lean Th.9: research_timeout ∈ [300, 900] ist ausreichend für Deep Research."""
    result = select_sequential_timeout("research", research_env=research_env)
    assert 300.0 <= result <= 900.0, f"Lean Th.9: {result} ∉ [300, 900]"
