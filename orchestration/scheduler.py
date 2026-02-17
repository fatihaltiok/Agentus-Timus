"""
Proaktiver Scheduler - Periodischer Wake-up für autonome Fortsetzung.

FEATURES:
- Heartbeat-Mechanismus (konfigurierbar 5-30 min)
- Prüft offene tasks.json auf pending/in_progress Tasks
- Regelmäßiges Self-Model Refresh
- Autonomous Continuation für unterbrochene Aufgaben

KONFIGURATION (ENV):
- HEARTBEAT_ENABLED (default: true)
- HEARTBEAT_INTERVAL_MINUTES (default: 15)
- HEARTBEAT_SELF_MODEL_REFRESH_INTERVAL (default: 60 minutes)

USAGE:
    from orchestration.scheduler import init_scheduler, scheduler
    
    # In startup:
    await scheduler.start()
    
    # In shutdown:
    await scheduler.stop()

AUTOR: Timus Development
DATUM: Februar 2026
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, field

log = logging.getLogger("Scheduler")


@dataclass
class SchedulerEvent:
    """Event das bei jedem Wake-up generiert wird."""
    event_type: str
    timestamp: str
    pending_tasks: List[Dict[str, Any]] = field(default_factory=list)
    self_model_updated: bool = False
    actions_taken: List[str] = field(default_factory=list)


class ProactiveScheduler:
    """
    Heartbeat-Mechanismus für autonome Agent-Aktivität.
    
    Der Scheduler führt in konfigurierbaren Intervallen folgende Aktionen aus:
    1. Prüfen auf offene Tasks (tasks.json)
    2. Self-Model Refresh (alle N Intervalle)
    3. Callback für Custom Actions
    """
    
    def __init__(
        self,
        interval_minutes: int = 15,
        self_model_refresh_interval_minutes: int = 60,
        on_wake: Optional[Callable[[SchedulerEvent], None]] = None,
        tasks_file: Optional[Path] = None
    ):
        """
        Initialisiert den Scheduler.
        
        Args:
            interval_minutes: Heartbeat-Intervall in Minuten
            self_model_refresh_interval_minutes: Self-Model Refresh Intervall
            on_wake: Callback der bei jedem Wake-up aufgerufen wird
            tasks_file: Pfad zur tasks.json (default: project_root/tasks.json)
        """
        self.interval = timedelta(minutes=interval_minutes)
        self.self_model_refresh_interval = timedelta(minutes=self_model_refresh_interval_minutes)
        self.on_wake = on_wake
        self.running = False
        self.task: Optional[asyncio.Task] = None
        
        # Tasks file
        project_root = Path(__file__).resolve().parent.parent
        self.tasks_file = tasks_file or project_root / "tasks.json"
        
        # Tracking
        self.heartbeat_count: int = 0
        self.last_heartbeat: Optional[datetime] = None
        self.last_self_model_refresh: Optional[datetime] = None
        self._start_time: Optional[datetime] = None
    
    async def start(self) -> None:
        """Startet den Heartbeat-Loop."""
        if self.running:
            log.warning("Scheduler läuft bereits")
            return
        
        self.running = True
        self._start_time = datetime.now()
        self.task = asyncio.create_task(self._heartbeat_loop())
        
        log.info(
            f"💓 Scheduler gestartet | "
            f"Interval: {self.interval.total_seconds()/60:.0f}min | "
            f"Self-Model Refresh: {self.self_model_refresh_interval.total_seconds()/60:.0f}min"
        )
    
    async def stop(self) -> None:
        """Stoppt den Scheduler gracefully."""
        if not self.running:
            return
        
        log.info("Scheduler wird gestoppt...")
        self.running = False
        
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        log.info(
            f"Scheduler gestoppt | "
            f"Total Heartbeats: {self.heartbeat_count} | "
            f"Runtime: {datetime.now() - self._start_time if self._start_time else 'n/a'}"
        )
    
    async def _heartbeat_loop(self) -> None:
        """Haupt-Loop mit periodischem Wake-up."""
        while self.running:
            try:
                # Sleep for interval
                await asyncio.sleep(self.interval.total_seconds())
                
                if not self.running:
                    break
                
                # Execute heartbeat
                await self._execute_heartbeat()
                
            except asyncio.CancelledError:
                log.debug("Heartbeat-Loop abgebrochen")
                break
            except Exception as e:
                log.error(f"Heartbeat-Fehler: {e}", exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(60)  # Brief pause before retry
    
    async def _execute_heartbeat(self) -> SchedulerEvent:
        """Führt einen einzelnen Heartbeat aus."""
        self.heartbeat_count += 1
        self.last_heartbeat = datetime.now()
        
        event = SchedulerEvent(
            event_type="heartbeat",
            timestamp=self.last_heartbeat.isoformat()
        )
        
        log.info(f"💓 Wake-up #{self.heartbeat_count} @ {self.last_heartbeat.strftime('%H:%M:%S')}")
        
        # 1. Pending Tasks prüfen
        pending_tasks = await self._check_pending_tasks()
        event.pending_tasks = pending_tasks
        
        if pending_tasks:
            log.info(f"📋 {len(pending_tasks)} offene Tasks gefunden")
            for t in pending_tasks[:3]:  # Show max 3
                log.info(f"   → [{t.get('status', '?')}] {t.get('description', t.get('task', '?'))[:50]}")
        
        # 2. Self-Model Refresh (wenn fällig)
        if self._should_refresh_self_model():
            refreshed = await self._refresh_self_model()
            event.self_model_updated = refreshed
            if refreshed:
                event.actions_taken.append("self_model_refresh")
        
        # 3. Memory Sync (optional, alle 4 Heartbeats)
        if self.heartbeat_count % 4 == 0:
            synced = await self._sync_memory()
            if synced:
                event.actions_taken.append("memory_sync")
        
        # 4. Custom Callback
        if self.on_wake:
            try:
                await self._call_callback(event)
                event.actions_taken.append("custom_callback")
            except Exception as e:
                log.warning(f"Callback fehlgeschlagen: {e}")
        
        return event
    
    async def _check_pending_tasks(self) -> List[Dict[str, Any]]:
        """Prüft tasks.json auf offene Einträge."""
        if not self.tasks_file.exists():
            log.debug(f"Tasks file nicht gefunden: {self.tasks_file}")
            return []
        
        try:
            content = self.tasks_file.read_text(encoding="utf-8")
            if not content.strip():
                return []
            
            data = json.loads(content)
            
            # Handle different task formats
            tasks = data.get("tasks", data.get("items", []))
            if isinstance(data, list):
                tasks = data
            
            # Filter pending/in_progress
            pending = [
                t for t in tasks
                if isinstance(t, dict) and t.get("status") in ("pending", "in_progress", "open")
            ]
            
            return pending
            
        except json.JSONDecodeError as e:
            log.warning(f"Tasks file JSON-Fehler: {e}")
            return []
        except Exception as e:
            log.error(f"Task-Check fehlgeschlagen: {e}")
            return []
    
    def _should_refresh_self_model(self) -> bool:
        """Prüft ob Self-Model aktualisiert werden soll."""
        if self.last_self_model_refresh is None:
            return True
        
        time_since_refresh = datetime.now() - self.last_self_model_refresh
        return time_since_refresh >= self.self_model_refresh_interval
    
    async def _refresh_self_model(self) -> bool:
        """Aktualisiert das Self-Model via MemoryManager."""
        try:
            from memory.memory_system import memory_manager
            
            result = await memory_manager.update_self_model(force=True)
            
            if result:
                self.last_self_model_refresh = datetime.now()
                log.info("🧠 Self-Model aktualisiert via Heartbeat")
                return True
            else:
                log.debug("Self-Model Update nicht nötig oder fehlgeschlagen")
                return False
                
        except ImportError:
            log.debug("Memory Manager nicht verfügbar für Self-Model Refresh")
            return False
        except Exception as e:
            log.warning(f"Self-Model Refresh fehlgeschlagen: {e}")
            return False
    
    async def _sync_memory(self) -> bool:
        """Synchronisiert Memory mit Markdown."""
        try:
            from memory.memory_system import memory_manager
            
            result = memory_manager.sync_to_markdown()
            if result:
                log.info("📝 Memory → Markdown Sync via Heartbeat")
            return result
            
        except ImportError:
            return False
        except Exception as e:
            log.debug(f"Memory Sync fehlgeschlagen: {e}")
            return False
    
    async def _call_callback(self, event: SchedulerEvent) -> None:
        """Ruft den Custom Callback auf."""
        if asyncio.iscoroutinefunction(self.on_wake):
            await self.on_wake(event)
        else:
            self.on_wake(event)
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt aktuellen Scheduler-Status zurück."""
        return {
            "running": self.running,
            "heartbeat_count": self.heartbeat_count,
            "interval_minutes": self.interval.total_seconds() / 60,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_self_model_refresh": self.last_self_model_refresh.isoformat() if self.last_self_model_refresh else None,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "uptime_seconds": (datetime.now() - self._start_time).total_seconds() if self._start_time else 0,
            "tasks_file": str(self.tasks_file)
        }
    
    async def trigger_manual_heartbeat(self) -> SchedulerEvent:
        """Löst einen manuellen Heartbeat aus (für Testing/Debugging)."""
        log.info("🔧 Manueller Heartbeat ausgelöst")
        return await self._execute_heartbeat()


# === Singleton Instance ===
_scheduler: Optional[ProactiveScheduler] = None


def get_scheduler() -> Optional[ProactiveScheduler]:
    """Gibt die globale Scheduler-Instanz zurück."""
    return _scheduler


def init_scheduler(
    interval_minutes: Optional[int] = None,
    self_model_refresh_interval_minutes: Optional[int] = None,
    on_wake: Optional[Callable] = None,
    tasks_file: Optional[Path] = None
) -> ProactiveScheduler:
    """
    Initialisiert die globale Scheduler-Instanz.
    
    Args:
        interval_minutes: Override ENV HEARTBEAT_INTERVAL_MINUTES
        self_model_refresh_interval_minutes: Override für Self-Model Refresh
        on_wake: Custom Callback
        tasks_file: Pfad zur tasks.json
    
    Returns:
        ProactiveScheduler Instanz
    """
    global _scheduler
    
    # Load from ENV if not specified
    if interval_minutes is None:
        interval_minutes = int(os.getenv("HEARTBEAT_INTERVAL_MINUTES", "15"))
    
    if self_model_refresh_interval_minutes is None:
        self_model_refresh_interval_minutes = int(os.getenv("HEARTBEAT_SELF_MODEL_REFRESH_INTERVAL", "60"))
    
    _scheduler = ProactiveScheduler(
        interval_minutes=interval_minutes,
        self_model_refresh_interval_minutes=self_model_refresh_interval_minutes,
        on_wake=on_wake,
        tasks_file=tasks_file
    )
    
    return _scheduler


async def start_scheduler() -> None:
    """Startet den globalen Scheduler."""
    global _scheduler
    if _scheduler is None:
        init_scheduler()
    await _scheduler.start()


async def stop_scheduler() -> None:
    """Stoppt den globalen Scheduler."""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()


# Für einfachen Import
scheduler: Optional[ProactiveScheduler] = None

def _set_scheduler_instance(s: ProactiveScheduler) -> None:
    """Setzt die globale scheduler Variable (internal use)."""
    global scheduler
    scheduler = s
