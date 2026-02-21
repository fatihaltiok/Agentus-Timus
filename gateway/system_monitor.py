"""
gateway/system_monitor.py

Überwacht CPU, RAM, Disk und Netzwerk.
Sendet Telegram-Alert wenn Schwellwerte überschritten werden.

Konfiguration (.env):
    MONITOR_ENABLED          = true/false (default: true)
    MONITOR_INTERVAL_MINUTES = Intervall (default: 5)
    MONITOR_CPU_THRESHOLD    = CPU % (default: 85)
    MONITOR_RAM_THRESHOLD    = RAM % (default: 85)
    MONITOR_DISK_THRESHOLD   = Disk % (default: 90)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import psutil

log = logging.getLogger("SystemMonitor")

# Damit nicht jede Minute derselbe Alert kommt
_last_alerts: dict[str, datetime] = {}
ALERT_COOLDOWN_MINUTES = 30


def _cfg(key: str, default: str) -> str:
    return os.getenv(key, default)


def _should_alert(alert_key: str) -> bool:
    """Verhindert Alert-Spam: selber Alert max. alle 30 Min."""
    last = _last_alerts.get(alert_key)
    if last is None:
        _last_alerts[alert_key] = datetime.now()
        return True
    delta = (datetime.now() - last).total_seconds() / 60
    if delta >= ALERT_COOLDOWN_MINUTES:
        _last_alerts[alert_key] = datetime.now()
        return True
    return False


def get_system_stats() -> dict:
    """Liest aktuelle Systemwerte."""
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    stats = {
        "cpu_percent":   round(cpu, 1),
        "ram_percent":   round(ram.percent, 1),
        "ram_used_gb":   round(ram.used / 1e9, 1),
        "ram_total_gb":  round(ram.total / 1e9, 1),
        "disk_percent":  round(disk.percent, 1),
        "disk_used_gb":  round(disk.used / 1e9, 1),
        "disk_total_gb": round(disk.total / 1e9, 1),
        "timestamp":     datetime.now().isoformat(),
    }
    return stats


def _build_alert(stats: dict, triggered: list[str]) -> str:
    return (
        f"⚠️ *System-Alert*\n\n"
        f"🔴 Ausgelöst: {', '.join(triggered)}\n\n"
        f"CPU:  {stats['cpu_percent']}%\n"
        f"RAM:  {stats['ram_percent']}% "
        f"({stats['ram_used_gb']} / {stats['ram_total_gb']} GB)\n"
        f"Disk: {stats['disk_percent']}% "
        f"({stats['disk_used_gb']} / {stats['disk_total_gb']} GB)\n\n"
        f"_{stats['timestamp'][:19]}_"
    )


async def _send_telegram_alert(msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    allowed = os.getenv("TELEGRAM_ALLOWED_IDS", "")
    if not token or not allowed:
        return
    try:
        from telegram import Bot
        from telegram.constants import ParseMode
        bot = Bot(token=token)
        for uid_str in allowed.split(","):
            uid_str = uid_str.strip()
            if uid_str:
                try:
                    await bot.send_message(
                        chat_id=int(uid_str),
                        text=msg,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception as e:
                    log.warning(f"Alert-Versand an {uid_str} fehlgeschlagen: {e}")
        await bot.close()
    except Exception as e:
        log.error(f"Telegram-Alert Fehler: {e}")


class SystemMonitor:
    """Periodischer System-Check mit Telegram-Alerts."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.interval = int(_cfg("MONITOR_INTERVAL_MINUTES", "5"))
        self.cpu_threshold  = float(_cfg("MONITOR_CPU_THRESHOLD",  "85"))
        self.ram_threshold  = float(_cfg("MONITOR_RAM_THRESHOLD",  "85"))
        self.disk_threshold = float(_cfg("MONITOR_DISK_THRESHOLD", "90"))

    async def start(self) -> None:
        if _cfg("MONITOR_ENABLED", "true").lower() not in ("1", "true", "yes"):
            log.info("System-Monitor deaktiviert (MONITOR_ENABLED=false)")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="system-monitor")
        log.info(
            f"✅ System-Monitor aktiv (alle {self.interval} min | "
            f"CPU>{self.cpu_threshold}% RAM>{self.ram_threshold}% "
            f"Disk>{self.disk_threshold}%)"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.interval * 60)
            if self._running:
                await self._check()

    async def _check(self) -> None:
        try:
            stats = await asyncio.to_thread(get_system_stats)
            triggered = []

            if stats["cpu_percent"] >= self.cpu_threshold:
                triggered.append(f"CPU {stats['cpu_percent']}%")
            if stats["ram_percent"] >= self.ram_threshold:
                triggered.append(f"RAM {stats['ram_percent']}%")
            if stats["disk_percent"] >= self.disk_threshold:
                triggered.append(f"Disk {stats['disk_percent']}%")

            if triggered:
                key = "|".join(triggered)
                if _should_alert(key):
                    log.warning(f"System-Alert: {triggered}")
                    await _send_telegram_alert(_build_alert(stats, triggered))
            else:
                log.debug(
                    f"System OK: CPU={stats['cpu_percent']}% "
                    f"RAM={stats['ram_percent']}% Disk={stats['disk_percent']}%"
                )
        except Exception as e:
            log.error(f"System-Check Fehler: {e}")
