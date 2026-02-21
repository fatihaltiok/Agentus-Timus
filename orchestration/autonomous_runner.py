"""
orchestration/autonomous_runner.py

Verbindet den ProactiveScheduler mit run_agent().
Bei jedem Heartbeat werden pending Tasks aus der SQLite-Queue autonom ausgeführt.
"""

import asyncio
import logging
import uuid
from typing import Optional

from orchestration.scheduler import ProactiveScheduler, SchedulerEvent, init_scheduler
from orchestration.task_queue import Priority, TaskType, get_queue

log = logging.getLogger("AutonomousRunner")


class AutonomousRunner:
    """
    Führt pending Tasks autonom aus, ausgelöst durch den Scheduler-Heartbeat.
    Läuft im Hintergrund parallel zur CLI-Schleife.
    Tasks werden nach Priorität abgearbeitet (CRITICAL zuerst).
    """

    def __init__(self, interval_minutes: int = 15):
        self.interval_minutes = interval_minutes
        self._scheduler: Optional[ProactiveScheduler] = None
        self._tools_desc: Optional[str] = None
        self._running = False
        self._work_signal: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    async def start(self, tools_desc: str) -> None:
        """Startet den Runner mit gecachten Tool-Beschreibungen."""
        self._tools_desc = tools_desc
        self._running = True

        # Migration beim ersten Start: tasks.json → SQLite
        self._run_migration()

        self._scheduler = init_scheduler(
            interval_minutes=self.interval_minutes,
            on_wake=self._on_wake_sync,
        )
        await self._scheduler.start()

        asyncio.create_task(self._worker_loop(), name="autonomous-worker")
        log.info(f"AutonomousRunner gestartet (Intervall: {self.interval_minutes} min)")

    async def stop(self) -> None:
        """Stoppt den Runner."""
        self._running = False
        self._work_signal.set()  # Worker aus dem Warten wecken
        if self._scheduler:
            await self._scheduler.stop()
        log.info("AutonomousRunner gestoppt")

    async def trigger_now(self) -> None:
        """Manueller Heartbeat — sofort ausführen."""
        if self._scheduler:
            await self._scheduler.trigger_manual_heartbeat()

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _run_migration(self) -> None:
        """Importiert tasks.json in SQLite falls noch nicht geschehen."""
        try:
            from orchestration.task_queue import migrate_from_json
            n = migrate_from_json(get_queue())
            if n:
                log.info(f"Migration: {n} Tasks aus tasks.json übernommen")
        except Exception as e:
            log.warning(f"Migration übersprungen: {e}")

    # ------------------------------------------------------------------
    # Scheduler-Callback
    # ------------------------------------------------------------------

    def _on_wake_sync(self, event: SchedulerEvent) -> None:
        """Wird vom Scheduler aufgerufen. Signalisiert dem Worker neue Arbeit."""
        queue = get_queue()
        pending = queue.get_pending()
        if not pending:
            log.debug("Heartbeat: keine offenen Tasks")
            return
        log.info(f"Heartbeat: {len(pending)} offene Task(s) | Top-Priorität: {pending[0]['priority']}")
        self._work_signal.set()

    # ------------------------------------------------------------------
    # Worker-Loop
    # ------------------------------------------------------------------

    async def _worker_loop(self) -> None:
        """Wartet auf Signal, holt dann Tasks aus SQLite und führt sie aus."""
        while self._running:
            # Warten bis Heartbeat signalisiert oder Timeout
            try:
                await asyncio.wait_for(self._work_signal.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass
            self._work_signal.clear()

            if not self._running:
                break

            # Alle verfügbaren Tasks sequenziell abarbeiten
            queue = get_queue()
            while self._running:
                task = queue.claim_next()
                if not task:
                    break
                await self._execute_task(task)

    # ------------------------------------------------------------------
    # Task-Ausführung
    # ------------------------------------------------------------------

    async def _execute_task(self, task: dict) -> None:
        """Führt einen Task mit automatischem Failover aus."""
        task_id = task.get("id", "?")
        description = task.get("description", "")
        target_agent = task.get("target_agent")
        priority = task.get("priority", Priority.NORMAL)
        queue = get_queue()

        if not description:
            queue.complete(task_id, "Übersprungen: leere Beschreibung")
            return

        prio_name = {0: "CRITICAL", 1: "HIGH", 2: "NORMAL", 3: "LOW"}.get(priority, str(priority))
        log.info(f"▶ [{prio_name}] Task [{task_id[:8]}]: {description[:80]}")

        try:
            from main_dispatcher import get_agent_decision
            from utils.model_failover import failover_run_agent

            agent = target_agent if target_agent else await get_agent_decision(description)
            session_id = f"auto_{uuid.uuid4().hex[:8]}"

            result = await failover_run_agent(
                agent_name=agent,
                query=description,
                tools_description=self._tools_desc or "",
                session_id=session_id,
                on_alert=self._send_failure_alert,
            )

            if result is not None:
                queue.complete(task_id, str(result)[:2000])
                log.info(f"✅ Task [{task_id[:8]}] abgeschlossen")
            else:
                queue.fail(task_id, "Alle Failover-Versuche erschöpft")

        except Exception as e:
            log.error(f"❌ Task [{task_id[:8]}] Fehler: {e}", exc_info=True)
            queue.fail(task_id, str(e))

    async def _send_failure_alert(
        self,
        agent: str,
        query: str,
        attempts: list,
        last_error: str,
    ) -> None:
        """Sendet Telegram-Alert wenn alle Failover-Versuche erschöpft sind."""
        try:
            token = __import__("os").getenv("TELEGRAM_BOT_TOKEN", "")
            allowed_ids = __import__("os").getenv("TELEGRAM_ALLOWED_IDS", "")
            if not token or not allowed_ids:
                return

            from telegram import Bot
            bot = Bot(token=token)
            chat_ids = [int(x.strip()) for x in allowed_ids.split(",") if x.strip()]

            msg = (
                f"🚨 *Timus Autonomer Ausfall*\n\n"
                f"Agent: `{agent}`\n"
                f"Versuche: `{' → '.join(attempts)}`\n"
                f"Fehler: `{last_error[:200]}`\n\n"
                f"Task: _{query[:100]}_"
            )
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
            await bot.close()
            log.info("🚨 Failure-Alert via Telegram gesendet")
        except Exception as e:
            log.warning(f"Alert-Versand fehlgeschlagen: {e}")


# ------------------------------------------------------------------
# Öffentliche Hilfsfunktion: Task hinzufügen
# ------------------------------------------------------------------

def add_task(
    description: str,
    target_agent: Optional[str] = None,
    priority: int = Priority.NORMAL,
    task_type: str = TaskType.MANUAL,
) -> str:
    """
    Fügt einen neuen Task zur SQLite-Queue hinzu.
    Gibt die Task-ID zurück.
    """
    return get_queue().add(
        description=description,
        priority=priority,
        task_type=task_type,
        target_agent=target_agent,
    )
