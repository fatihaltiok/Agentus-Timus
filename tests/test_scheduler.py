"""
Tests für ProactiveScheduler - Heartbeat Mechanismus.
"""
import pytest
import asyncio
import json
from pathlib import Path
from datetime import datetime
import tempfile
import sys

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.scheduler import (
    ProactiveScheduler,
    SchedulerEvent,
    init_scheduler,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
    _set_scheduler_instance
)


class TestProactiveScheduler:
    """Tests für ProactiveScheduler."""
    
    @pytest.fixture
    def temp_tasks_file(self):
        """Erstellt temporäre tasks.json für Tests."""
        # Create temp file with content
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        temp_file.write(json.dumps({
            "tasks": [
                {"id": 1, "status": "pending", "description": "Test task 1"},
                {"id": 2, "status": "in_progress", "description": "Test task 2"},
                {"id": 3, "status": "completed", "description": "Done task"}
            ]
        }))
        temp_file.flush()
        temp_file.close()
        yield Path(temp_file.name)
        # Cleanup after test
        Path(temp_file.name).unlink(missing_ok=True)
    
    @pytest.fixture
    def empty_tasks_file(self):
        """Erstellt leere tasks.json."""
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        temp_file.write(json.dumps({"tasks": []}))
        temp_file.flush()
        temp_file.close()
        yield Path(temp_file.name)
        Path(temp_file.name).unlink(missing_ok=True)
    
    def test_init_default_values(self):
        """Testet Default-Initialisierung."""
        scheduler = ProactiveScheduler()
        
        assert scheduler.interval.total_seconds() == 15 * 60  # 15 min
        assert scheduler.self_model_refresh_interval.total_seconds() == 60 * 60  # 60 min
        assert scheduler.running is False
        assert scheduler.heartbeat_count == 0
    
    def test_init_custom_values(self):
        """Testet Custom-Initialisierung."""
        scheduler = ProactiveScheduler(
            interval_minutes=5,
            self_model_refresh_interval_minutes=30
        )
        
        assert scheduler.interval.total_seconds() == 5 * 60
        assert scheduler.self_model_refresh_interval.total_seconds() == 30 * 60
    
    def test_get_status(self):
        """Testet Status-Abruf."""
        scheduler = ProactiveScheduler()
        status = scheduler.get_status()
        
        assert status["running"] is False
        assert status["heartbeat_count"] == 0
        assert status["interval_minutes"] == 15
        assert status["last_heartbeat"] is None
    
    @pytest.mark.asyncio
    async def test_check_pending_tasks(self, temp_tasks_file):
        """Testet Task-Check."""
        scheduler = ProactiveScheduler(tasks_file=temp_tasks_file)
        
        pending = await scheduler._check_pending_tasks()
        
        assert len(pending) == 2  # pending + in_progress
        assert all(t["status"] in ("pending", "in_progress") for t in pending)
    
    @pytest.mark.asyncio
    async def test_check_pending_tasks_empty(self, empty_tasks_file):
        """Testet Task-Check mit leerer Datei."""
        scheduler = ProactiveScheduler(tasks_file=empty_tasks_file)
        
        pending = await scheduler._check_pending_tasks()
        
        assert pending == []
    
    @pytest.mark.asyncio
    async def test_check_pending_tasks_nonexistent(self):
        """Testet Task-Check ohne Datei."""
        scheduler = ProactiveScheduler(tasks_file=Path("/nonexistent/tasks.json"))
        
        pending = await scheduler._check_pending_tasks()
        
        assert pending == []
    
    def test_should_refresh_self_model(self):
        """Testet Self-Model Refresh Timing."""
        scheduler = ProactiveScheduler()
        
        # Initial should refresh
        assert scheduler._should_refresh_self_model() is True
        
        # After refresh, should not refresh immediately
        scheduler.last_self_model_refresh = datetime.now()
        assert scheduler._should_refresh_self_model() is False
    
    @pytest.mark.asyncio
    async def test_manual_heartbeat(self, temp_tasks_file):
        """Testet manuellen Heartbeat."""
        events = []
        
        def on_wake(event):
            events.append(event)
        
        scheduler = ProactiveScheduler(
            interval_minutes=1,
            tasks_file=temp_tasks_file,
            on_wake=on_wake
        )
        
        event = await scheduler.trigger_manual_heartbeat()
        
        assert isinstance(event, SchedulerEvent)
        assert event.event_type == "heartbeat"
        assert len(event.pending_tasks) == 2
        assert scheduler.heartbeat_count == 1
    
    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Testet Start und Stop."""
        scheduler = ProactiveScheduler(interval_minutes=0.05)  # 3 seconds
        
        await scheduler.start()
        assert scheduler.running is True
        assert scheduler.task is not None
        
        # Wait briefly
        await asyncio.sleep(0.1)
        
        await scheduler.stop()
        assert scheduler.running is False
    
    @pytest.mark.asyncio
    async def test_callback_with_event(self, temp_tasks_file):
        """Testet Callback mit Event."""
        received_events = []
        
        async def async_callback(event):
            received_events.append(event)
        
        scheduler = ProactiveScheduler(
            tasks_file=temp_tasks_file,
            on_wake=async_callback
        )
        
        event = await scheduler.trigger_manual_heartbeat()
        
        assert len(received_events) == 1
        assert received_events[0] is event


class TestSchedulerSingleton:
    """Tests für Singleton-Funktionen."""
    
    def test_init_scheduler(self):
        """Testet init_scheduler."""
        global _scheduler
        
        scheduler = init_scheduler(interval_minutes=10)
        
        assert scheduler is not None
        assert scheduler.interval.total_seconds() == 10 * 60
    
    def test_get_scheduler(self):
        """Testet get_scheduler."""
        scheduler = get_scheduler()
        
        assert scheduler is not None
        assert isinstance(scheduler, ProactiveScheduler)
    
    @pytest.mark.asyncio
    async def test_start_stop_scheduler(self):
        """Testet start_scheduler und stop_scheduler."""
        # Reset singleton
        scheduler = init_scheduler(interval_minutes=0.1)
        
        await start_scheduler()
        assert scheduler.running is True
        
        await stop_scheduler()
        assert scheduler.running is False


class TestSchedulerEvent:
    """Tests für SchedulerEvent Dataclass."""
    
    def test_event_creation(self):
        """Testet Event-Erstellung."""
        event = SchedulerEvent(
            event_type="test",
            timestamp=datetime.now().isoformat()
        )
        
        assert event.event_type == "test"
        assert event.pending_tasks == []
        assert event.self_model_updated is False
        assert event.actions_taken == []
    
    def test_event_with_data(self):
        """Testet Event mit Daten."""
        event = SchedulerEvent(
            event_type="heartbeat",
            timestamp="2026-02-17T12:00:00",
            pending_tasks=[{"id": 1, "status": "pending"}],
            self_model_updated=True,
            actions_taken=["self_model_refresh", "memory_sync"]
        )
        
        assert len(event.pending_tasks) == 1
        assert event.self_model_updated is True
        assert len(event.actions_taken) == 2


def test_scheduler_import():
    """Testet dass Scheduler-Modul importiert werden kann."""
    from orchestration import scheduler, init_scheduler, ProactiveScheduler
    
    assert ProactiveScheduler is not None
    assert init_scheduler is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
