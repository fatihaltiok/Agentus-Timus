# tests/test_safety_schema_hardening.py
"""
Tests für Phase 1: Safety- und Schema-Härtung.

Run:
    pytest tests/test_safety_schema_hardening.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestParameterValidation:
    """Tests für die Runtime-Parameter-Validierung."""

    def test_string_validation(self):
        from tools.tool_registry_v2 import (
            validate_parameter_value,
            ToolParameter,
            ValidationError,
        )

        param = ToolParameter(
            name="test", type="string", description="Test", required=True
        )

        result = validate_parameter_value(param, "hello")
        assert result == "hello"

        with pytest.raises(ValidationError):
            validate_parameter_value(param, 123)

    def test_integer_validation(self):
        from tools.tool_registry_v2 import (
            validate_parameter_value,
            ToolParameter,
            ValidationError,
        )

        param = ToolParameter(
            name="count", type="integer", description="Count", required=True
        )

        result = validate_parameter_value(param, 42)
        assert result == 42

        with pytest.raises(ValidationError):
            validate_parameter_value(param, "not a number")

        with pytest.raises(ValidationError):
            validate_parameter_value(param, 3.14)

    def test_boolean_validation(self):
        from tools.tool_registry_v2 import (
            validate_parameter_value,
            ToolParameter,
            ValidationError,
        )

        param = ToolParameter(
            name="flag", type="boolean", description="Flag", required=True
        )

        result = validate_parameter_value(param, True)
        assert result is True

        result = validate_parameter_value(param, False)
        assert result is False

        with pytest.raises(ValidationError):
            validate_parameter_value(param, "true")

    def test_array_validation(self):
        from tools.tool_registry_v2 import (
            validate_parameter_value,
            ToolParameter,
            ValidationError,
        )

        param = ToolParameter(
            name="items", type="array", description="Items", required=True
        )

        result = validate_parameter_value(param, [1, 2, 3])
        assert result == [1, 2, 3]

        with pytest.raises(ValidationError):
            validate_parameter_value(param, "not an array")

    def test_object_validation(self):
        from tools.tool_registry_v2 import (
            validate_parameter_value,
            ToolParameter,
            ValidationError,
        )

        param = ToolParameter(
            name="config", type="object", description="Config", required=True
        )

        result = validate_parameter_value(param, {"key": "value"})
        assert result == {"key": "value"}

        with pytest.raises(ValidationError):
            validate_parameter_value(param, "not an object")

    def test_enum_validation(self):
        from tools.tool_registry_v2 import (
            validate_parameter_value,
            ToolParameter,
            ValidationError,
        )

        param = ToolParameter(
            name="mode",
            type="string",
            description="Mode",
            required=True,
            enum=["fast", "slow", "balanced"],
        )

        result = validate_parameter_value(param, "fast")
        assert result == "fast"

        with pytest.raises(ValidationError):
            validate_parameter_value(param, "invalid")

    def test_required_parameter_missing(self):
        from tools.tool_registry_v2 import (
            validate_parameter_value,
            ToolParameter,
            ValidationError,
        )

        param = ToolParameter(
            name="required_param", type="string", description="Required", required=True
        )

        with pytest.raises(ValidationError):
            validate_parameter_value(param, None)

    def test_optional_parameter_default(self):
        from tools.tool_registry_v2 import validate_parameter_value, ToolParameter

        param = ToolParameter(
            name="optional_param",
            type="string",
            description="Optional",
            required=False,
            default="default_value",
        )

        result = validate_parameter_value(param, None)
        assert result == "default_value"

    def test_validate_tool_parameters(self):
        from tools.tool_registry_v2 import (
            validate_tool_parameters,
            ToolParameter,
            ValidationError,
        )

        params = [
            ToolParameter(
                name="query", type="string", description="Query", required=True
            ),
            ToolParameter(
                name="count",
                type="integer",
                description="Count",
                required=False,
                default=10,
            ),
        ]

        result = validate_tool_parameters("test_tool", params, {"query": "hello"})
        assert result["query"] == "hello"
        assert result["count"] == 10

        with pytest.raises(ValidationError):
            validate_tool_parameters("test_tool", params, {})


class TestPolicyGate:
    """Tests für die Policy-Gate Funktionen."""

    def test_allowed_tool(self):
        from utils.policy_gate import check_tool_policy

        allowed, reason = check_tool_policy("search_web", {})
        assert allowed is True
        assert reason is None

    def test_blocked_tool(self):
        from utils.policy_gate import check_tool_policy

        allowed, reason = check_tool_policy("delete_file", {"path": "/test"})
        assert allowed is False
        assert "Policy blockiert" in reason

    def test_always_allowed_whitelist(self):
        from utils.policy_gate import check_tool_policy

        for tool in ["search_web", "get_text", "read_file", "list_files", "screenshot"]:
            allowed, _ = check_tool_policy(tool, {})
            assert allowed is True

    def test_dangerous_query_detection(self):
        from utils.policy_gate import check_query_policy

        safe, warning = check_query_policy("lösche die datei test.txt")
        assert safe is False
        assert "destruktive" in warning.lower()

        safe, warning = check_query_policy("wie spät ist es?")
        assert safe is True
        assert warning is None

    def test_sensitive_param_detection(self):
        from utils.policy_gate import check_tool_policy

        allowed, _ = check_tool_policy("some_tool", {"password": "secret123"})
        assert allowed is True

        allowed, _ = check_tool_policy("some_tool", {"api_key": "key123"})
        assert allowed is True

    def test_audit_tool_call(self):
        from utils.policy_gate import audit_tool_call

        audit_tool_call("test_tool", {"query": "test"}, {"result": "ok"})
        audit_tool_call("test_tool", {"password": "secret"}, {"error": "failed"})


class TestToolRegistryValidation:
    """Tests für die erweiterte Tool-Registry mit Validierung."""

    def test_execute_with_validation(self):
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
            ValidationError,
        )

        registry_v2.clear()

        @tool(
            name="validated_tool_v2",
            description="Validiertes Tool",
            parameters=[
                P(
                    name="number",
                    type="integer",
                    description="Eine Zahl",
                    required=True,
                ),
                P(
                    name="text",
                    type="string",
                    description="Ein Text",
                    required=False,
                    default="default",
                ),
            ],
            capabilities=["test"],
            category=C.SYSTEM,
        )
        def validated_tool_v2(number: int, text: str = "default"):
            return {"number": number, "text": text}

        import asyncio

        result = asyncio.run(registry_v2.execute("validated_tool_v2", number=42))
        assert result["number"] == 42
        assert result["text"] == "default"

        with pytest.raises(ValidationError):
            asyncio.run(registry_v2.execute("validated_tool_v2", number="not a number"))

    def test_validate_tool_call_method(self):
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
            ValidationError,
        )

        registry_v2.clear()

        @tool(
            name="preflight_test",
            description="Pre-flight Test",
            parameters=[
                P(name="value", type="string", description="Value", required=True)
            ],
            capabilities=["test"],
            category=C.SYSTEM,
        )
        def preflight_test(value: str):
            return {"value": value}

        validated = registry_v2.validate_tool_call("preflight_test", value="test")
        assert validated["value"] == "test"

        with pytest.raises(ValidationError):
            registry_v2.validate_tool_call("preflight_test", value=123)


class TestAgentToolCallIntegration:
    """Tests für die Agent Tool-Call Integration mit Policy."""

    @pytest.mark.asyncio
    async def test_policy_check_in_call_tool(self):
        from agent.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            def __init__(self):
                self.system_prompt_template = "Test Agent"
                self.tools_description_string = "Test Tools"
                self.max_iterations = 5
                self.agent_type = "executor"
                super().__init__(
                    system_prompt_template="Test Agent",
                    tools_description_string="Test Tools",
                    max_iterations=5,
                    agent_type="executor",
                )

        agent = TestAgent()

        result = await agent._call_tool("delete_file", {"path": "/test"})
        assert result.get("blocked_by_policy") is True


class TestServerPolicyIntegration:
    """Tests für die serverseitige Policy-Integration."""

    def test_server_imports(self):
        try:
            from server.mcp_server import app, check_tool_policy, registry_v2

            assert app is not None
        except ImportError:
            pytest.skip("Server module nicht verfügbar")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
