# Communication Contract Baseline M0

Date: 2026-03-07
Scope: core path only

## Core path shape today

### 1. Sequential delegation

Producer:

- [tools/delegation_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/delegation_tool/tool.py)
- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)

Observed output shape:

- dict with `status`, `agent`
- success path adds `result`, `quality`, `blackboard_key`, `metadata`
- error path adds `error`, `quality`, `blackboard_key`
- `metadata` is partially derived from regex over `result`

Risk:

- `result` is still largely free text
- `metadata` extraction is symptom handling

### 2. Parallel delegation

Producer:

- [tools/delegation_tool/parallel_delegation_tool.py](/home/fatih-ubuntu/dev/timus/tools/delegation_tool/parallel_delegation_tool.py)
- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)

Observed output shape:

- top-level dict with `trace_id`, counters, `results`, `summary`
- each entry in `results` is a dict, not a first-class `AgentResult`
- Meta consumption currently depends on textual reading and formatting

Risk:

- structured enough for transport, not structured enough for orchestration

### 3. Blackboard write in delegation path

Producer:

- [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py)

Observed issue:

- `_auto_write_to_blackboard()` is a tail-end patch on delegation
- it does not live at the end of every tool path
- current implementation mismatches the real blackboard write signature

Risk:

- structured delegation data is not reliably persisted into shared short-term memory

## Top core producers and consumers

### Producers to prioritize

Simple, low-risk validation targets:

- [tools/save_results/tool.py](/home/fatih-ubuntu/dev/timus/tools/save_results/tool.py)
- [tools/email_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/email_tool/tool.py)

High-impact producers after validation:

- [tools/deep_research/tool.py](/home/fatih-ubuntu/dev/timus/tools/deep_research/tool.py)
- [tools/creative_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/creative_tool/tool.py)
- [tools/document_creator/tool.py](/home/fatih-ubuntu/dev/timus/tools/document_creator/tool.py)

### Current formatting/consumption points

- [agent/result_aggregator.py](/home/fatih-ubuntu/dev/timus/agent/result_aggregator.py)
- [agent/agents/meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [agent/prompts.py](/home/fatih-ubuntu/dev/timus/agent/prompts.py)

## Mandatory policy from M1 onward

Consumers must resolve artifact-like information in this order:

1. `artifacts`
2. `metadata`
3. regex fallback with WARNING log

No new consumer may be introduced with regex-first behavior.
