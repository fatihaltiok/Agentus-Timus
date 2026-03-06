# Contributing to Timus

Thank you for your interest in Timus. This document explains how to set up a development environment, add new tools or agents, and submit contributions.

---

## Development Setup

### Prerequisites

- Python 3.11
- A `.env` file (copy `.env.example` and fill in your API keys)
- At minimum: `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` + `OPENROUTER_API_KEY`

### Quick Start

```bash
git clone https://github.com/fatihaltiok/Agentus-Timus.git
cd Agentus-Timus
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit with your keys
python server/mcp_server.py
```

Canvas runs at `http://localhost:5000`.

---

## Project Structure

```
agent/
  base_agent.py          # BaseAgent (ReAct loop, tool calls, LLM dispatch)
  agents/                # 13 specialized agents (meta, research, visual, ...)
  providers.py           # ModelProvider enum + client factory

tools/                   # 80+ MCP tools (one directory per tool)
  deep_research/         # Deep Research v7.0 pipeline
  file_system_tool/      # File operations
  search_tool/           # DataForSEO web + YouTube search

orchestration/           # Autonomy layers M1–M16
  goal_queue_manager.py  # M11: hierarchical goals
  feedback_engine.py     # M16: learning from feedback
  email_autonomy_engine.py # M14: autonomous email

memory/                  # Memory system
  soul_engine.py         # Soul Engine: 5 personality axes
  agent_blackboard.py    # M9: shared agent memory (TTL-based)
  qdrant_provider.py     # Qdrant drop-in for ChromaDB

server/
  mcp_server.py          # FastAPI + JSON-RPC + Canvas UI + SSE

tests/                   # pytest test suite (300+ tests)
lean/
  CiSpecs.lean           # 49 Lean 4 theorems (formal invariant proofs)
```

---

## Adding a New Tool

1. Create `tools/<tool_name>/tool.py` using the `@tool` decorator:

```python
from tools.tool_registry_v2 import tool, ToolParameter

@tool(
    name="my_tool",
    description="What this tool does",
    parameters=[
        ToolParameter("input", "string", "Description", required=True),
    ],
    capabilities=["web"],   # which agents can use this tool
    category="utility",
)
async def my_tool(input: str) -> dict:
    return {"result": input}
```

2. Create `tools/<tool_name>/__init__.py` (empty is fine).
3. Register in `server/mcp_server.py` under `TOOL_MODULES`.
4. Add tests in `tests/test_<tool_name>.py`.

---

## Adding a New Agent

1. Create `agent/agents/<name>.py` inheriting from `BaseAgent`:

```python
from agent.base_agent import BaseAgent
from agent.prompts import YOUR_PROMPT

class MyAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(YOUR_PROMPT, tools_description_string, max_iterations=10, agent_type="my_agent")
```

2. Register in `agent/agent_registry.py` → `AGENT_FACTORIES`.
3. Add the agent type to `AGENT_CAPABILITY_MAP` in `tools/tool_registry_v2.py`.
4. Add a system prompt in `agent/prompts.py`.

---

## Adding a Lean Theorem

Formal invariants live in `lean/CiSpecs.lean`. Add theorems using `omega`:

```lean
-- Short description — source: path/to/file.py:line
theorem my_invariant (v : Int) : 0 ≤ max 0 (min 100 v) := by omega
```

Run `lean lean/CiSpecs.lean` to verify (requires Lean 4 + Std).

---

## Code Style

- Python 3.11, type hints where practical
- `async def` for all tool handlers and agent methods
- Imports at module top; no star imports
- Keep methods under ~50 lines; extract helpers for longer logic
- All new features need at least one `pytest` test

---

## Commit Message Format

```
<type>(<scope>): <summary>

<body — optional>

Co-Authored-By: Your Name <email@example.com>
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`

Examples:
```
feat(research): add source deduplication + ranking
fix(qdrant): use env var for vector size
test(m14): whitelist guard property-based tests
```

---

## Running Tests

```bash
pytest tests/ -q                               # all tests
pytest tests/test_hypothesis_formal.py -v      # property-based (Lean-mapped)
pytest tests/test_m16_feedback_engine.py -v    # specific module
```

Pre-commit hook runs `lean lean/CiSpecs.lean` + Mathlib specs automatically.

---

## Pull Request Guidelines

- One logical change per PR
- Include tests (unit or property-based) for new code
- Update `.env.example` if you add new environment variables
- Update `README.md` if you add a user-visible feature
- Lean theorems required for numeric invariants (clamp, bounds, thresholds)

---

## Questions?

Open an issue on GitHub or reach out via the repository's discussion board.
