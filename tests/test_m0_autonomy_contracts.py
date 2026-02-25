"""M0 Contracts: Architektur-Invarianten fuer Autonomie-Ausbau (kompatibel)."""

from __future__ import annotations

import ast
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _find_function(tree: ast.AST, name: str, async_only: bool = False) -> ast.AST | None:
    for node in ast.walk(tree):
        if async_only and isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
        if not async_only and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_m0_docs_exist() -> None:
    required = [
        "docs/autonomy/M0_P1_ARCHITEKTURVERTRAG.md",
        "docs/autonomy/M0_P2_TESTMATRIX_GATES.md",
        "docs/autonomy/M0_P3_FEATURE_FLAGS.md",
    ]
    missing = [path for path in required if not (PROJECT_ROOT / path).exists()]
    assert not missing, f"Missing M0 docs: {missing}"


def test_env_example_contains_autonomy_flags_with_safe_defaults() -> None:
    env_text = _read(".env.example")
    expected = {
        "AUTONOMY_GOALS_ENABLED": "false",
        "AUTONOMY_PLANNING_ENABLED": "false",
        "AUTONOMY_REPLANNING_ENABLED": "false",
        "AUTONOMY_SELF_HEALING_ENABLED": "false",
        "AUTONOMY_POLICY_GATES_STRICT": "false",
        "AUTONOMY_AUDIT_DECISIONS_ENABLED": "false",
        "AUTONOMY_CANARY_PERCENT": "0",
        "AUTONOMY_COMPAT_MODE": "true",
    }
    for key, value in expected.items():
        pattern = rf"(?m)^\s*{re.escape(key)}\s*=\s*{re.escape(value)}\s*(?:#.*)?$"
        assert re.search(pattern, env_text), f"Missing or invalid default for {key}"


def test_main_dispatcher_contract_signatures() -> None:
    source = _read("main_dispatcher.py")
    tree = ast.parse(source)

    get_agent_decision = _find_function(tree, "get_agent_decision", async_only=True)
    assert isinstance(get_agent_decision, ast.AsyncFunctionDef)
    assert [arg.arg for arg in get_agent_decision.args.args] == ["user_query"]

    run_agent = _find_function(tree, "run_agent", async_only=True)
    assert isinstance(run_agent, ast.AsyncFunctionDef)
    arg_names = [arg.arg for arg in run_agent.args.args]
    assert arg_names[:3] == ["agent_name", "query", "tools_description"]
    assert "session_id" in arg_names


def test_agent_registry_contract_points_exist() -> None:
    source = _read("agent/agent_registry.py")
    tree = ast.parse(source)

    delegate = _find_function(tree, "delegate", async_only=True)
    assert isinstance(delegate, ast.AsyncFunctionDef)

    delegate_parallel = _find_function(tree, "delegate_parallel", async_only=True)
    assert isinstance(delegate_parallel, ast.AsyncFunctionDef)

    register_all_agents = _find_function(tree, "register_all_agents")
    assert isinstance(register_all_agents, ast.FunctionDef)


def test_mcp_jsonrpc_endpoint_contract_exists() -> None:
    source = _read("server/mcp_server.py")
    assert '@app.post("/", summary="JSON-RPC Endpoint")' in source
    assert "async def handle_jsonrpc(request: Request):" in source
