# Communication Contract Completion Report

Date: 2026-03-07

## Scope

This report summarizes the completed hardening work for the Timus communication contract across:

- sequential delegation
- parallel delegation
- tool result normalization
- core-path consumers
- fallback reduction and observability

## Outcome

The productive core path now follows one consistent priority rule:

`artifacts -> metadata -> regex/text fallback`

This rule is implemented in code, covered by tests, and reflected in agent prompts.

## Completed Milestones

### M0: Baseline and Delegation Blackboard Fix

Completed:

- documented the core-path baseline
- fixed the delegation blackboard write contract
- propagated effective `session_id`
- added Lean, Hypothesis, CrossHair, and regression coverage

Primary files:

- `agent/agent_registry.py`
- `tests/test_auto_blackboard_write.py`
- `tests/test_delegation_hardening.py`
- `tests/test_agent_registry_blackboard_contracts.py`
- `lean/CiSpecs.lean`

### M1: AgentResult v2 and Artifact Priority

Completed:

- introduced `artifacts` into `AgentResult`
- enforced fallback policy in delegation handling
- persisted `artifacts` and `metadata` into blackboard payloads
- updated prompts and result aggregation

Primary files:

- `agent/agent_registry.py`
- `agent/result_aggregator.py`
- `agent/prompts.py`
- `tests/test_agent_result.py`
- `tests/test_agent_result_artifacts.py`
- `tests/test_artifact_fallback_contracts.py`

### M1.2 / M1.3: Tool Producers

Completed for core producers:

- `save_results`
- `email_tool`
- `creative_tool`
- `document_creator`
- `deep_research`

These tools now emit typed `artifacts` while retaining backward-compatible fields.

Primary files:

- `tools/save_results/tool.py`
- `tools/email_tool/tool.py`
- `tools/creative_tool/tool.py`
- `tools/document_creator/tool.py`
- `tools/deep_research/tool.py`

### M2: Parallel Delegation Convergence

Completed:

- `delegate_parallel()` now returns worker entries aligned with `AgentResult`
- each worker carries `quality`, `metadata`, `artifacts`, and `blackboard_key`
- `ResultAggregator` and prompt guidance were updated atomically
- parallel results are now first-class structured outputs

Primary files:

- `agent/agent_registry.py`
- `agent/result_aggregator.py`
- `agent/prompts.py`
- `tests/test_m3_delegate_parallel.py`
- `tests/test_m4_result_aggregator.py`
- `tests/test_m5_parallel_delegation_integration.py`
- `tests/test_parallel_result_contracts.py`

### M3: Central Tool Envelope

Completed:

- added central dict-result normalization in `tool_registry_v2`
- JSON-RPC bridge now normalizes dict tool outputs
- direct tool consumers in `BaseAgent` and dynamic agents now consume normalized results
- explicit `normalize=True` support added for direct registry execution

Primary files:

- `tools/tool_registry_v2.py`
- `agent/base_agent.py`
- `agent/dynamic_tool_mixin.py`
- `agent/dynamic_tool_agent.py`
- `tests/test_tool_registry_envelope.py`
- `tests/test_base_agent_tool_envelope.py`

### M4: Fallback Reduction and Closure

Completed:

- metadata and wrapper fallbacks now emit warnings
- core consumers were moved off direct `saved_as` / `filepath` primary reads
- `CreativeAgent`, `ImageCollector`, and `report_generator` now prefer `artifacts`
- prompt guidance now treats metadata as exception fallback, not normal flow
- regex remains only as an isolated emergency path in delegation result recovery

Primary files:

- `agent/agents/creative.py`
- `tools/deep_research/image_collector.py`
- `tools/report_generator/tool.py`
- `agent/prompts.py`
- `tests/test_m4_fallback_cleanup.py`

## Deliberately Retained Fallbacks

These remain intentionally:

- regex fallback in `agent/agent_registry.py` for unstructured delegated outputs
- metadata fallback for backward compatibility with older tool and agent outputs
- wrapper artifact inference in `tools/tool_registry_v2.py` for dict tools not yet emitting native `artifacts`

These are no longer silent. They now produce warnings and are no longer the preferred path.

## Validation Summary

Validated during rollout with:

- targeted regression tests
- Hypothesis property tests
- CrossHair contract checks
- Lean invariants in `lean/CiSpecs.lean`

Final closure gate passed with:

- productive core-path tests
- fallback policy tests
- prompt regression tests
- parallel delegation contract tests

## Final State

For the Timus core flow:

`FastAPI/MCP -> Tool Registry -> Agent -> Delegation -> Meta-Agent`

the communication contract is now structured, observable, and materially less dependent on fragile text parsing.

## Recommended Future Work

Optional future cleanup:

1. remove the final regex emergency path once telemetry shows it is unused
2. expand native `artifacts` emission across lower-priority tools
3. add explicit runtime metrics for fallback frequency by tool and agent
