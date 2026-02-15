# tests/test_dynamic_tool_discovery.py
"""
Tests für Dynamic Tool Discovery System.

Run:
    pytest tests/test_dynamic_tool_discovery.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestToolRegistryV2:
    """Tests für die erweiterte Tool-Registry."""
    
    def test_registry_singleton(self):
        from tools.tool_registry_v2 import ToolRegistryV2, registry_v2
        
        registry = ToolRegistryV2()
        assert registry is registry_v2
        
        registry2 = ToolRegistryV2()
        assert registry is registry2
    
    def test_tool_registration(self):
        from tools.tool_registry_v2 import registry_v2, tool, ToolParameter as P, ToolCategory as C
        
        registry_v2.clear()
        
        @tool(
            name="test_tool",
            description="Ein Test-Tool",
            parameters=[P(name="input", type="string", description="Eingabe", required=True)],
            capabilities=["test"],
            category=C.SYSTEM
        )
        def test_tool_func(input: str):
            return {"result": input}
        
        assert "test_tool" in registry_v2.list_all_tools()
        
        meta = registry_v2.get_tool("test_tool")
        assert meta.description == "Ein Test-Tool"
        assert "test" in meta.capabilities
    
    def test_openai_schema_generation(self):
        from tools.tool_registry_v2 import registry_v2, tool, ToolParameter as P, ToolCategory as C
        
        registry_v2.clear()
        
        @tool(
            name="schema_test",
            description="Schema Test",
            parameters=[
                P(name="query", type="string", description="Suchanfrage", required=True),
                P(name="count", type="integer", description="Anzahl", required=False),
            ],
            capabilities=["test"],
            category=C.SYSTEM
        )
        def schema_test(query: str, count: int = 10):
            return {}
        
        schema = registry_v2.get_openai_tools_schema()
        
        assert len(schema) == 1
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "schema_test"
        assert "query" in schema[0]["function"]["parameters"]["properties"]
        assert schema[0]["function"]["parameters"]["required"] == ["query"]
    
    def test_capability_filtering(self):
        from tools.tool_registry_v2 import registry_v2, tool, ToolParameter as P, ToolCategory as C
        
        registry_v2.clear()
        
        @tool(
            name="browser_tool",
            description="Browser",
            parameters=[],
            capabilities=["browser", "navigation"],
            category=C.BROWSER
        )
        def browser_tool():
            return {}
        
        @tool(
            name="search_tool",
            description="Search",
            parameters=[],
            capabilities=["search", "research"],
            category=C.SEARCH
        )
        def search_tool():
            return {}
        
        @tool(
            name="mouse_tool",
            description="Mouse",
            parameters=[],
            capabilities=["mouse", "browser"],
            category=C.MOUSE
        )
        def mouse_tool():
            return {}
        
        filtered = registry_v2.get_tools_for_agent(["browser"])
        names = [t.name for t in filtered]
        
        assert "browser_tool" in names
        assert "mouse_tool" in names
        assert "search_tool" not in names
    
    def test_manifest_generation(self):
        from tools.tool_registry_v2 import registry_v2, tool, ToolParameter as P, ToolCategory as C
        
        registry_v2.clear()
        
        @tool(
            name="example_tool",
            description="Beispiel Tool",
            parameters=[P(name="x", type="integer", description="X-Wert", required=True)],
            capabilities=["example"],
            category=C.SYSTEM,
            examples=['example_tool(x=42)']
        )
        def example_tool(x: int):
            return {"x": x}
        
        manifest = registry_v2.get_tool_manifest()
        
        assert "example_tool" in manifest
        assert "Beispiel Tool" in manifest


class TestDynamicToolAgent:
    """Tests für DynamicToolAgent."""
    
    def test_agent_initialization(self):
        from agent.dynamic_tool_agent import DynamicToolAgent
        
        class TestAgent(DynamicToolAgent):
            def get_system_prompt(self):
                return "Test Agent"
        
        agent = TestAgent(model="gpt-4o")
        
        assert agent.model == "gpt-4o"
        assert agent.execution_mode.value == "function_calling"
    
    def test_capability_filtering(self):
        from agent.dynamic_tool_agent import DynamicToolAgent
        from tools.tool_registry_v2 import registry_v2, tool, ToolParameter as P, ToolCategory as C
        
        registry_v2.clear()
        
        @tool(
            name="cap_test",
            description="Cap Test",
            parameters=[],
            capabilities=["test_cap"],
            category=C.SYSTEM
        )
        def cap_test():
            return {}
        
        class TestAgent(DynamicToolAgent):
            def get_system_prompt(self):
                return "Test"
            def get_capabilities(self):
                return ["test_cap"]
        
        agent = TestAgent(model="gpt-4o")
        agent.filter_tools_by_capabilities(["test_cap"])
        
        assert "cap_test" in agent._available_tools
    
    @pytest.mark.asyncio
    async def test_tool_execution(self):
        from tools.tool_registry_v2 import registry_v2, tool, ToolParameter as P, ToolCategory as C
        
        registry_v2.clear()
        
        @tool(
            name="async_test",
            description="Async Test",
            parameters=[P(name="value", type="string", description="Value", required=True)],
            capabilities=["test"],
            category=C.SYSTEM
        )
        async def async_test(value: str):
            return {"echo": value}
        
        result = await registry_v2.execute("async_test", value="hello")
        
        assert result == {"echo": "hello"}
    
    def test_browser_agent(self):
        from agent.dynamic_tool_agent import BrowserAgent
        
        agent = BrowserAgent()
        
        assert "browser" in agent.get_capabilities()
        assert agent._available_tools is not None
    
    def test_research_agent(self):
        from agent.dynamic_tool_agent import ResearchAgent
        
        agent = ResearchAgent()
        
        assert "search" in agent.get_capabilities()
        assert "research" in agent.get_capabilities()


class TestToolIntegration:
    """Integration Tests für Tool-Migration."""
    
    @pytest.mark.asyncio
    async def test_browser_tool_v2_registration(self):
        try:
            from tools.browser_tool_v2.tool import browser_open_url
            
            from tools.tool_registry_v2 import registry_v2
            
            if "browser_open_url" in registry_v2.list_all_tools():
                meta = registry_v2.get_tool("browser_open_url")
                assert meta.category.value == "browser"
        except ImportError:
            pytest.skip("browser_tool_v2 nicht verfügbar")
    
    @pytest.mark.asyncio
    async def test_search_tool_v2_registration(self):
        try:
            from tools.search_tool_v2.tool import search_web
            
            from tools.tool_registry_v2 import registry_v2
            
            if "search_web" in registry_v2.list_all_tools():
                meta = registry_v2.get_tool("search_web")
                assert meta.category.value == "search"
        except ImportError:
            pytest.skip("search_tool_v2 nicht verfügbar")
    
    @pytest.mark.asyncio
    async def test_mouse_tool_v2_registration(self):
        try:
            from tools.mouse_tool_v2.tool import mouse_click
            
            from tools.tool_registry_v2 import registry_v2
            
            if "mouse_click" in registry_v2.list_all_tools():
                meta = registry_v2.get_tool("mouse_click")
                assert meta.category.value == "mouse"
        except ImportError:
            pytest.skip("mouse_tool_v2 nicht verfügbar")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
