# tests/test_orchestration_lanes.py
"""
Tests für Phase 2: Orchestrierungs-Lanes und Queueing.

Run:
    pytest tests/test_orchestration_lanes.py -v
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLaneManager:
    """Tests für den LaneManager."""

    def test_lane_manager_import(self):
        from orchestration.lane_manager import LaneManager, Lane, LaneStatus

        assert LaneManager is not None
        assert Lane is not None
        assert LaneStatus is not None

    def test_lane_manager_initialization(self):
        from orchestration.lane_manager import LaneManager

        manager = LaneManager(max_lanes=10, default_timeout=60.0)
        assert manager.max_lanes == 10
        assert manager.default_timeout == 60.0
        assert len(manager.list_lanes()) == 0

    def test_lane_status_enum(self):
        from orchestration.lane_manager import LaneStatus

        assert LaneStatus.IDLE.value == "idle"
        assert LaneStatus.BUSY.value == "busy"
        assert LaneStatus.QUEUED.value == "queued"
        assert LaneStatus.ERROR.value == "error"
        assert LaneStatus.CLOSED.value == "closed"

    @pytest.mark.asyncio
    async def test_create_lane(self):
        from orchestration.lane_manager import LaneManager
        from tools.tool_registry_v2 import registry_v2

        manager = LaneManager()
        manager.set_registry(registry_v2)

        lane = await manager.create_lane("test_lane_1")
        assert lane.lane_id == "test_lane_1"
        assert lane.status.value == "idle"

        assert "test_lane_1" in manager.list_lanes()

    @pytest.mark.asyncio
    async def test_get_or_create_lane(self):
        from orchestration.lane_manager import LaneManager
        from tools.tool_registry_v2 import registry_v2

        manager = LaneManager()
        manager.set_registry(registry_v2)

        lane1 = await manager.get_or_create_lane("shared_lane")
        lane2 = await manager.get_or_create_lane("shared_lane")

        assert lane1.lane_id == lane2.lane_id
        assert len(manager.list_lanes()) == 1

    @pytest.mark.asyncio
    async def test_close_lane(self):
        from orchestration.lane_manager import LaneManager
        from tools.tool_registry_v2 import registry_v2

        manager = LaneManager()
        manager.set_registry(registry_v2)

        await manager.create_lane("temp_lane")
        assert "temp_lane" in manager.list_lanes()

        closed = await manager.close_lane("temp_lane")
        assert closed is True
        assert "temp_lane" not in manager.list_lanes()

        closed_again = await manager.close_lane("temp_lane")
        assert closed_again is False


class TestLane:
    """Tests für einzelne Lanes."""

    @pytest.mark.asyncio
    async def test_lane_tool_execution(self):
        from orchestration.lane_manager import Lane
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="test_lane_tool",
            description="Test Tool",
            parameters=[
                P(name="value", type="string", description="Value", required=True)
            ],
            capabilities=["test"],
            category=C.SYSTEM,
        )
        def test_lane_tool(value: str):
            return {"echo": value}

        lane = Lane(lane_id="test", registry=registry_v2)

        result = await lane.execute_tool("test_lane_tool", {"value": "hello"})

        assert result.success is True
        assert result.result == {"echo": "hello"}
        assert result.tool_name == "test_lane_tool"

    @pytest.mark.asyncio
    async def test_lane_stats(self):
        from orchestration.lane_manager import Lane
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="stats_tool",
            description="Stats Test",
            parameters=[],
            capabilities=["test"],
            category=C.SYSTEM,
        )
        def stats_tool():
            return {"ok": True}

        lane = Lane(lane_id="stats_test", registry=registry_v2)

        await lane.execute_tool("stats_tool", {})
        await lane.execute_tool("stats_tool", {})

        assert lane.stats.total_calls == 2
        assert lane.stats.successful_calls == 2

    @pytest.mark.asyncio
    async def test_lane_timeout(self):
        from orchestration.lane_manager import Lane
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="slow_tool",
            description="Slow Tool",
            parameters=[],
            capabilities=["test"],
            category=C.SYSTEM,
        )
        async def slow_tool():
            await asyncio.sleep(5)
            return {"done": True}

        lane = Lane(lane_id="timeout_test", registry=registry_v2, default_timeout=0.1)

        result = await lane.execute_tool("slow_tool", {}, timeout=0.1)

        assert result.success is False
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_lane_status_report(self):
        from orchestration.lane_manager import Lane
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="report_tool",
            description="Report Test",
            parameters=[],
            capabilities=["test"],
            category=C.SYSTEM,
        )
        def report_tool():
            return {"ok": True}

        lane = Lane(lane_id="report_test", registry=registry_v2)

        await lane.execute_tool("report_tool", {})

        report = lane.get_status_report()

        assert report["lane_id"] == "report_test"
        assert report["total_calls"] == 1
        assert report["successful_calls"] == 1


class TestParallelExecution:
    """Tests für parallele Tool-Ausführung."""

    @pytest.mark.asyncio
    async def test_parallel_allowed_tool(self):
        from orchestration.lane_manager import Lane
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="parallel_tool",
            description="Parallel Safe Tool",
            parameters=[P(name="id", type="integer", description="ID", required=True)],
            capabilities=["test"],
            category=C.SYSTEM,
            parallel_allowed=True,
        )
        async def parallel_tool(id: int):
            await asyncio.sleep(0.1)
            return {"id": id}

        lane = Lane(lane_id="parallel_test", registry=registry_v2)

        calls = [
            ("parallel_tool", {"id": 1}),
            ("parallel_tool", {"id": 2}),
            ("parallel_tool", {"id": 3}),
        ]

        start = time.time()
        results = await lane.execute_parallel(calls, max_concurrent=3)
        duration = time.time() - start

        assert len(results) == 3
        assert all(r.success for r in results)
        assert duration < 0.5

    @pytest.mark.asyncio
    async def test_parallel_not_allowed_tool(self):
        from orchestration.lane_manager import Lane
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="serial_tool",
            description="Serial Only Tool",
            parameters=[P(name="id", type="integer", description="ID", required=True)],
            capabilities=["test"],
            category=C.SYSTEM,
            parallel_allowed=False,
        )
        def serial_tool(id: int):
            return {"id": id}

        lane = Lane(lane_id="serial_test", registry=registry_v2)

        calls = [
            ("serial_tool", {"id": 1}),
            ("serial_tool", {"id": 2}),
        ]

        results = await lane.execute_parallel(calls)

        assert len(results) == 2
        assert all(not r.success for r in results)
        assert all("not allowed" in r.error.lower() for r in results)


class TestToolMetadata:
    """Tests für erweiterte Tool-Metadaten."""

    def test_parallel_allowed_in_metadata(self):
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="parallel_meta",
            description="Test",
            parameters=[],
            capabilities=["test"],
            category=C.SYSTEM,
            parallel_allowed=True,
        )
        def parallel_meta():
            return {}

        meta = registry_v2.get_tool("parallel_meta")
        assert meta.parallel_allowed is True

    def test_timeout_in_metadata(self):
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="timeout_meta",
            description="Test",
            parameters=[],
            capabilities=["test"],
            category=C.SYSTEM,
            timeout=30.0,
        )
        def timeout_meta():
            return {}

        meta = registry_v2.get_tool("timeout_meta")
        assert meta.timeout == 30.0

    def test_priority_in_metadata(self):
        from tools.tool_registry_v2 import (
            registry_v2,
            tool,
            ToolParameter as P,
            ToolCategory as C,
        )

        registry_v2.clear()

        @tool(
            name="priority_meta",
            description="Test",
            parameters=[],
            capabilities=["test"],
            category=C.SYSTEM,
            priority=10,
        )
        def priority_meta():
            return {}

        meta = registry_v2.get_tool("priority_meta")
        assert meta.priority == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
