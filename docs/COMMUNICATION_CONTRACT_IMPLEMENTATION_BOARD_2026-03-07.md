# Communication Contract Implementation Board

Date: 2026-03-07
Status: active
Owner: Timus core runtime

## Goal

Harden the communication contract in the core path:

`MCP -> Registry -> Agent -> Delegation -> Meta-Agent`

without forcing a full refactor of 80+ tools.

## Guardrails

- No `next_actions` field for now.
- Tools return data, not orchestration decisions.
- Central wrapping in the registry/wrapper layer, not tool-by-tool first.
- Fallback policy from M1 onward is mandatory:

  `artifacts -> metadata -> regex fallback + WARNING`

- `delegate_parallel()` type change and Meta-agent consumption must ship atomically.
- Every phase ends with Lean 4, Hypothesis, CrossHair plus example-based verification.

## Milestone 0

### Goal

Characterize the current core-path contract before changing it, then fix the
delegation blackboard write bug without guesswork.

### Phase 0.2

Scope:

- Characterize top-10 core tools only.
- Characterize all delegation inputs and outputs.
- Identify all current `metadata` and regex-dependent consumers.
- Capture baseline return shapes for `delegate()` and `delegate_parallel()`.
- Document current blackboard usage in the delegation path.

Files:

- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- [agent/result_aggregator.py](/home/fatih-ubuntu/dev/timus/agent/result_aggregator.py)
- [tools/delegation_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/delegation_tool/tool.py)
- [tools/delegation_tool/parallel_delegation_tool.py](/home/fatih-ubuntu/dev/timus/tools/delegation_tool/parallel_delegation_tool.py)
- [memory/agent_blackboard.py](/home/fatih-ubuntu/dev/timus/memory/agent_blackboard.py)
- [tests/test_auto_blackboard_write.py](/home/fatih-ubuntu/dev/timus/tests/test_auto_blackboard_write.py)
- [tests/test_delegation_hardening.py](/home/fatih-ubuntu/dev/timus/tests/test_delegation_hardening.py)
- [tests/test_m4_result_aggregator.py](/home/fatih-ubuntu/dev/timus/tests/test_m4_result_aggregator.py)
- [tests/test_m5_parallel_delegation_integration.py](/home/fatih-ubuntu/dev/timus/tests/test_m5_parallel_delegation_integration.py)

Stop criteria:

- Core-path baseline documented.
- Top-10 core tools characterized.
- Delegation path fully reproducible in tests.
- No expansion into long-tail tools.

### Phase 0.1

Scope:

- Fix `_auto_write_to_blackboard()` to match the real blackboard API.
- Persist a stable `topic`.
- Pass `session_id` through the delegation path.
- Keep current TTL and status semantics unchanged.

Files:

- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- [memory/agent_blackboard.py](/home/fatih-ubuntu/dev/timus/memory/agent_blackboard.py)
- [tests/test_auto_blackboard_write.py](/home/fatih-ubuntu/dev/timus/tests/test_auto_blackboard_write.py)

Stop criteria:

- Blackboard writes work for `success`, `partial`, `error`.
- No signature mismatch remains.
- Existing delegation paths stay green.

### Gate 0

Lean 4:

- delegation status remains in `{success, partial, error}`
- blackboard write uses a complete contract
- `blackboard_key` behavior is well-defined

Hypothesis:

- random delegation results do not create inconsistent blackboard writes
- empty or unusual result payloads do not crash the helper

CrossHair plus examples:

- contracts for `_auto_write_to_blackboard()`
- status normalization helpers
- examples for `research`, `creative`, `document`

## Milestone 1

### Goal

Introduce `AgentResult.artifacts` and make typed artifact transport the primary
mechanism, while keeping backward compatibility.

### Phase 1.1

Scope:

- Extend `AgentResult` with `artifacts: List[Dict]`.
- Make `artifacts` default to `[]`.
- Add defensive deserialization for older objects without `artifacts`.
- Enforce the fallback policy:

  `artifacts -> metadata -> regex fallback + WARNING`

- Forbid new regex-first consumers.

Files:

- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- [agent/result_aggregator.py](/home/fatih-ubuntu/dev/timus/agent/result_aggregator.py)
- consumer files in `agent/agents/`
- blackboard read/write helpers if required

Stop criteria:

- `AgentResult` serializes/deserializes with and without `artifacts`.
- Old data does not break new readers.
- Fallback order is encoded in code and tests.

### Phase 1.2

Scope:

- Validate the mechanism first on simpler structured producers:
  - `save_results`
  - `email_tool`

Files:

- [tools/save_results/tool.py](/home/fatih-ubuntu/dev/timus/tools/save_results/tool.py)
- [tools/email_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/email_tool/tool.py)
- related consumers and tests

Stop criteria:

- These producers emit stable artifacts.
- Consumers prefer artifacts correctly.
- Regex is not needed in these paths.

### Phase 1.3

Scope:

- Move high-impact producers to artifacts:
  - `deep_research`
  - `creative_tool`
  - `document_creator`
  - optionally `communication`

Files:

- [tools/deep_research/tool.py](/home/fatih-ubuntu/dev/timus/tools/deep_research/tool.py)
- [tools/creative_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/creative_tool/tool.py)
- [tools/document_creator/tool.py](/home/fatih-ubuntu/dev/timus/tools/document_creator/tool.py)
- related agent consumers

Stop criteria:

- High-impact producers emit artifacts.
- `_extract_metadata()` is fallback only.
- Regex usage is visible and declining in logs.

### Gate 1

Lean 4:

- `artifacts` is never `None`
- each `AgentResult` has a valid status
- artifact path invariants hold

Hypothesis:

- random `AgentResult` payloads stay robust
- partial artifact lists do not break consumers
- old objects without `artifacts` remain compatible

CrossHair plus examples:

- artifact normalization
- fallback chain
- examples for PDF, image, DOCX and attachment flows

## Milestone 2

### Goal

Make `delegate_parallel()` a first-class structured delegation path.

### Phase 2.1

Atomic scope:

- `delegate_parallel()` returns structured `AgentResult` objects per worker.
- `ResultAggregator` consumes the new format.
- Meta-agent prompt and consumption path update in the same change.
- No intermediate rollout where old prompt reads new result shapes.

Files:

- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)
- [agent/result_aggregator.py](/home/fatih-ubuntu/dev/timus/agent/result_aggregator.py)
- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [agent/prompts.py](/home/fatih-ubuntu/dev/timus/agent/prompts.py)
- delegation tests and parallel integration tests

Stop criteria:

- `delegate_parallel()` emits consistent structured results.
- Meta-agent can consume them without textual guesswork.
- No prompt/type skew exists.

### Gate 2

Lean 4:

- `success + partial + errors == total_tasks`
- every parallel result is a valid `AgentResult`
- artifacts survive fan-in

Hypothesis:

- mixed result sets keep aggregation stable
- ordering changes do not affect counters

CrossHair plus examples:

- aggregation contracts
- parallel timeout plus success examples
- Meta-agent consumption examples

## Milestone 3

### Goal

Introduce a central wrapper that normalizes tool outputs into a minimal
data-only envelope.

### Phase 3.1

Scope:

- Define the minimal tool envelope:

```python
{
  "status": "success|partial|error",
  "data": ...,
  "summary": "...",
  "artifacts": [],
  "metadata": {},
  "error": ""
}
```

- Define idempotence:
  if a value is already a dict with a valid `status` and expected top-level
  keys, the wrapper validates it but does not semantically repack it.

Stop criteria:

- Envelope defined.
- Idempotence defined.
- No ambiguity about "already normalized".

### Phase 3.2

Scope:

- Add wrapping in the registry layer, not in the HTTP handler first.
- Normalize `str`, `dict`, `None`.
- Promote known file fields into `artifacts`.

Files:

- [tools/tool_registry_v2.py](/home/fatih-ubuntu/dev/timus/tools/tool_registry_v2.py)
- tool tests around save/report/image/file outputs

Stop criteria:

- Wrapper is central and active.
- Core tools normalize correctly.
- Already normalized responses stay stable.

### Phase 3.3

Scope:

- Move core-path consumers onto the normalized envelope first:
  - `save_results`
  - `email_tool`
  - `deep_research`
  - `creative_tool`
  - `document_creator`

Stop criteria:

- Core consumers do not depend on raw special cases as their primary path.
- Regex and ad-hoc handling continue to decline.

### Gate 3

Lean 4:

- every normalized tool output has a valid status
- wrapper idempotence holds
- artifacts are preserved

Hypothesis:

- arbitrary raw tool returns normalize safely
- already normalized values remain semantically stable

CrossHair plus examples:

- wrapper normalization
- artifact extraction
- error normalization

## Milestone 4

### Goal

Reduce fallback paths and make structured transport the default in the core path.

### Phase 4.1

- Reduce regex fallback to exception mode
- emit WARNING logs for every fallback hit
- add telemetry to show remaining legacy hotspots

### Phase 4.2

- remove legacy text-first branches where artifacts are stable
- update docs and tests to the final contract

### Gate 4

- Lean 4 on final invariants
- Hypothesis on end-to-end contracts
- CrossHair on wrapper, delegation and aggregation helpers
- example-based end-to-end flows on main scenarios
