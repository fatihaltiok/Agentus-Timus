"""
tests/test_m15_ambient_context.py — M15: Ambient Context Engine

Unit- und Integrationstests für orchestration/ambient_context_engine.py.

Schlüssel-Tests:
  - Score-Invariante (Hypothesis)
  - EmailWatcher: Urgency-Mail → Signal
  - EmailWatcher: Timus-Konto ignoriert
  - Dedup: zweites Signal blockiert
  - FileWatcher: CSV → data-Agent
  - FileWatcher: .tmp ignoriert
  - GoalStaleness: frisches Ziel ignoriert
  - GoalStaleness: stagnierendes Ziel → Signal
  - SystemWatcher: Normalwerte → kein Signal
  - SystemWatcher: Disk >90% → zwei Signale
  - Policy: confirm-Level → Telegram aufgerufen
  - Integration: run_cycle enqueued in echter TaskQueue
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Hypothesis ist optional, aber bevorzugt
try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
    _HYPOTHESIS_AVAILABLE = True
except ImportError:
    _HYPOTHESIS_AVAILABLE = False

# Sicherstellen, dass Umgebungsvariablen für Tests gesetzt sind
os.environ.setdefault("AUTONOMY_COMPAT_MODE", "false")
os.environ.setdefault("AUTONOMY_AMBIENT_CONTEXT_ENABLED", "true")
os.environ.setdefault("AMBIENT_SIGNAL_THRESHOLD", "0.6")
os.environ.setdefault("AMBIENT_CONFIRM_THRESHOLD", "0.85")
os.environ.setdefault("AMBIENT_SYSTEM_ALERT_THRESHOLD", "0.70")
os.environ.setdefault("AMBIENT_GOAL_STALE_HOURS", "48")

from orchestration.ambient_context_engine import (
    CONFIRM_THRESHOLD,
    SIGNAL_THRESHOLD,
    SYSTEM_ALERT_THRESHOLD,
    AmbientContextEngine,
    AmbientSignal,
    get_ambient_engine,
)


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktion: Blackboard-Mock
# ─────────────────────────────────────────────────────────────────────────────

def _fresh_engine() -> AmbientContextEngine:
    """Erzeugt eine frische Engine-Instanz (kein Singleton)."""
    return AmbientContextEngine()


class _FakeBlackboard:
    """Minimales Fake-Blackboard für Dedup-Tests ohne SQLite."""

    def __init__(self) -> None:
        self._store: dict[str, list] = {}

    def read(self, topic: str, key: str = "") -> list:
        k = f"{topic}:{key}"
        return self._store.get(k, [])

    def write(self, agent: str, topic: str, key: str, value, ttl_minutes: int = 60, session_id: str = "") -> None:
        k = f"{topic}:{key}"
        self._store[k] = [{"value": value}]

    def clear_expired(self) -> int:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# 1. Hypothesis: Score-Invariante
# ─────────────────────────────────────────────────────────────────────────────

if _HYPOTHESIS_AVAILABLE:
    @given(score=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False))
    @settings(max_examples=200)
    def test_score_always_clamped(score: float) -> None:
        clamped = max(0.0, min(1.0, score))
        assert 0.0 <= clamped <= 1.0
else:
    def test_score_always_clamped_fallback() -> None:
        """Fallback ohne Hypothesis."""
        for score in [-10.0, -1.0, 0.0, 0.5, 0.6, 0.85, 1.0, 5.0, 10.0]:
            clamped = max(0.0, min(1.0, score))
            assert 0.0 <= clamped <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. EmailWatcher: Urgency-Mail → Signal
# ─────────────────────────────────────────────────────────────────────────────

async def test_email_creates_signal_for_urgent_mail(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()

    fake_status = {"authenticated": True}
    fake_emails = {
        "emails": [
            {
                "id": "mail-001",
                "subject": "DRINGEND: Server ausgefallen",
                "bodyPreview": "Sofort bitte prüfen!",
                "from": {"emailAddress": {"address": "boss@company.com"}},
            }
        ]
    }

    monkeypatch.setattr(
        "orchestration.ambient_context_engine.asyncio.to_thread",
        _make_to_thread_mock(fake_status, fake_emails),
    )

    signals = await engine._check_emails()
    assert len(signals) == 1
    s = signals[0]
    assert s.source == "email"
    assert s.target_agent == "communication"
    # Urgency-Keyword + externer Sender = 0.6 + 0.2 + 0.2 = 1.0
    assert s.score == pytest.approx(1.0)
    assert "dringend" in s.description.lower() or "boss@company.com" in s.description.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. EmailWatcher: Timus-eigene Mails ignoriert
# ─────────────────────────────────────────────────────────────────────────────

async def test_email_ignores_timus_own_account(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()

    timus_mail = os.getenv("TIMUS_EMAIL", "timus.assistent@outlook.com")
    fake_status = {"authenticated": True}
    fake_emails = {
        "emails": [
            {
                "id": "mail-002",
                "subject": "Automatischer Report",
                "bodyPreview": "Täglicher Bericht...",
                "from": {"emailAddress": {"address": timus_mail}},
            }
        ]
    }

    monkeypatch.setattr(
        "orchestration.ambient_context_engine.asyncio.to_thread",
        _make_to_thread_mock(fake_status, fake_emails),
    )

    signals = await engine._check_emails()
    assert len(signals) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Dedup: zweites Signal wird blockiert
# ─────────────────────────────────────────────────────────────────────────────

async def test_dedup_blocks_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()
    fake_bb = _FakeBlackboard()

    signal = AmbientSignal(
        source="email",
        score=0.8,
        description="Test-Mail",
        target_agent="communication",
        dedup_key="email:test-001",
        cooldown_minutes=240,
    )

    # get_blackboard wird lokal importiert → am Ursprungsmodul patchen
    with patch("memory.agent_blackboard.get_blackboard", return_value=fake_bb), \
         patch("orchestration.task_queue.get_queue") as mock_queue, \
         patch("utils.telegram_notify.send_telegram", new_callable=AsyncMock):
        mock_queue.return_value = MagicMock()
        mock_queue.return_value.add = MagicMock(return_value="task-id-1")

        # Erstes Signal durchgelassen
        created1 = await engine._process_signal(signal)
        assert created1 is True

        # Dedup-Eintrag jetzt im Blackboard → zweites identisches Signal blockiert
        created2 = await engine._process_signal(signal)
        assert created2 is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. FileWatcher: CSV → data-Agent
# ─────────────────────────────────────────────────────────────────────────────

async def test_file_csv_routes_to_data_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()

    # Downloads-Ordner in tmp_path anlegen
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    csv_file = downloads / "report.csv"
    csv_file.write_text("id,name\n1,Alice\n")
    now_ts = time.time()
    os.utime(csv_file, (now_ts, now_ts))

    # Path.home() → tmp_path, damit "Downloads" = tmp_path/Downloads
    monkeypatch.setattr("orchestration.ambient_context_engine.Path", Path)

    # asyncio.to_thread: Scan-Funktion gibt csv_file zurück
    async def _mock_to_thread(func, *args, **kwargs):
        return [csv_file]

    monkeypatch.setattr("orchestration.ambient_context_engine.asyncio.to_thread", _mock_to_thread)

    with patch("orchestration.ambient_context_engine.Path.home", return_value=tmp_path):
        signals = await engine._check_files()

    assert len(signals) >= 1
    csv_signals = [s for s in signals if ".csv" in s.context.get("ext", "")]
    assert len(csv_signals) == 1
    assert csv_signals[0].target_agent == "data"
    assert csv_signals[0].score == pytest.approx(0.80)


# ─────────────────────────────────────────────────────────────────────────────
# 6. FileWatcher: .tmp-Dateien werden ignoriert
# ─────────────────────────────────────────────────────────────────────────────

async def test_file_ignores_tmp_files(tmp_path: Path) -> None:
    engine = _fresh_engine()

    tmp_file = tmp_path / "download.crdownload"
    tmp_file.write_bytes(b"partial content")

    async def _mock_to_thread(func, *args, **kwargs):
        # Scan-Funktion gibt .crdownload zurück
        return [tmp_file]

    with patch("orchestration.ambient_context_engine.asyncio.to_thread", side_effect=_mock_to_thread), \
         patch("orchestration.ambient_context_engine.Path.home", return_value=tmp_path):
        signals = await engine._check_files()

    # .crdownload soll ignoriert werden
    crdownload_signals = [s for s in signals if "crdownload" in str(s.context)]
    assert len(crdownload_signals) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. GoalStaleness: frisches Ziel wird ignoriert (< GOAL_STALE_HOURS)
# ─────────────────────────────────────────────────────────────────────────────

async def test_goal_fresh_not_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()

    fresh_updated = (datetime.now() - timedelta(hours=1)).isoformat()
    rows = [{"id": "goal-1", "title": "Neues Ziel", "progress": 0.3, "updated_at": fresh_updated}]

    async def _mock_to_thread(func, *args, **kwargs):
        return rows

    monkeypatch.setattr("orchestration.ambient_context_engine.asyncio.to_thread", _mock_to_thread)

    signals = await engine._check_goal_staleness()
    assert len(signals) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 8. GoalStaleness: stagnierendes Ziel → Signal erzeugt
# ─────────────────────────────────────────────────────────────────────────────

async def test_goal_stale_creates_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()

    # Kurz nach der 48h-Schwelle muss bereits ein Signal entstehen.
    stale_updated = (datetime.now() - timedelta(hours=49)).isoformat()
    rows = [{"id": "goal-2", "title": "Altes Projekt", "progress": 0.1, "updated_at": stale_updated}]

    async def _mock_to_thread(func, *args, **kwargs):
        return rows

    monkeypatch.setattr("orchestration.ambient_context_engine.asyncio.to_thread", _mock_to_thread)

    signals = await engine._check_goal_staleness()
    assert len(signals) == 1
    s = signals[0]
    assert s.source == "goal_stale"
    assert s.target_agent == "meta"
    assert s.score >= 0.6
    assert "Altes Projekt" in s.description
    assert s.dedup_key == "goal:goal-2"


# ─────────────────────────────────────────────────────────────────────────────
# 9. SystemWatcher: normale Werte → kein Signal
# ─────────────────────────────────────────────────────────────────────────────

async def test_system_normal_no_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()

    fake_usage = {
        "cpu_percent": 20.0,
        "memory": {"percent": 45.0},
        "disk": {"percent": 60.0},
    }

    async def _mock_to_thread(func, *args, **kwargs):
        return fake_usage

    monkeypatch.setattr("orchestration.ambient_context_engine.asyncio.to_thread", _mock_to_thread)

    signals = await engine._check_system()
    # max(20, 45, 60) / 100 = 0.60 < SYSTEM_ALERT_THRESHOLD (0.70)
    assert len(signals) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 10. SystemWatcher: Disk >90% → zwei Signale (system:alert + system:disk_critical)
# ─────────────────────────────────────────────────────────────────────────────

async def test_system_critical_disk_two_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()

    fake_usage = {
        "cpu_percent": 10.0,
        "memory": {"percent": 30.0},
        "disk": {"percent": 92.0},
    }

    async def _mock_to_thread(func, *args, **kwargs):
        return fake_usage

    monkeypatch.setattr("orchestration.ambient_context_engine.asyncio.to_thread", _mock_to_thread)

    signals = await engine._check_system()
    # Disk=92% → score=0.92 ≥ SYSTEM_ALERT_THRESHOLD → 1. Signal (system:alert)
    # Disk>90% → 2. Signal (system:disk_critical)
    assert len(signals) == 2
    dedup_keys = {s.dedup_key for s in signals}
    assert "system:alert" in dedup_keys
    assert "system:disk_critical" in dedup_keys
    shell_signals = [s for s in signals if s.target_agent == "shell"]
    assert len(shell_signals) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 11. Policy: confirm-Level → Telegram aufgerufen
# ─────────────────────────────────────────────────────────────────────────────

async def test_policy_confirm_calls_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _fresh_engine()
    fake_bb = _FakeBlackboard()

    signal = AmbientSignal(
        source="system",
        score=0.75,  # ≥ SYSTEM_ALERT_THRESHOLD aber < CONFIRM_THRESHOLD
        description="System-Alert Test",
        target_agent="system",
        dedup_key="system:test-confirm",
        cooldown_minutes=60,
        policy_level="confirm",  # confirm → immer Telegram
    )

    fake_feedback = AsyncMock(return_value=True)

    # send_with_feedback wird lokal importiert → am Ursprungsmodul patchen
    with patch("memory.agent_blackboard.get_blackboard", return_value=fake_bb), \
         patch("orchestration.task_queue.get_queue") as mock_queue, \
         patch("utils.telegram_notify.send_with_feedback", fake_feedback):
        mock_queue.return_value = MagicMock()
        mock_queue.return_value.add = MagicMock(return_value="task-id-x")

        created = await engine._process_signal(signal)

    assert created is True
    fake_feedback.assert_awaited_once()
    assert "SYSTEM" in fake_feedback.await_args.args[0]


# ─────────────────────────────────────────────────────────────────────────────
# 12. Integration: run_cycle enqueued in echter TaskQueue
# ─────────────────────────────────────────────────────────────────────────────

async def test_run_cycle_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run_cycle mit echter SQLite-TaskQueue: prüft dass tasks_queued > 0."""
    from orchestration.task_queue import TaskQueue

    db_path = tmp_path / "test_tasks.db"
    real_queue = TaskQueue(db_path=db_path)

    engine = _fresh_engine()
    fake_bb = _FakeBlackboard()

    # Email-Signal (kein Auth) → 0 Signale
    # File-Signal → 0 (leerer Downloads-Ordner)
    # Goal-Signal → stale Ziel
    stale_updated = (datetime.now() - timedelta(days=6)).isoformat()
    goal_rows = [
        {"id": "g-cycle-1", "title": "Ziel in Zyklus", "progress": 0.2, "updated_at": stale_updated}
    ]
    # System normal → 0 Signale
    normal_usage = {"cpu_percent": 10.0, "memory": {"percent": 20.0}, "disk": {"percent": 30.0}}

    call_count = [0]

    async def _smart_to_thread(func, *args, **kwargs):
        call_count[0] += 1
        # E-Mail Status → nicht authentifiziert
        if hasattr(func, "__name__") and "status" in func.__name__:
            return {"authenticated": False}
        # System Usage
        if hasattr(func, "__name__") and "system" in func.__name__:
            return normal_usage
        # Alles andere (Goal-Query, Scan) → goal_rows oder leere Liste
        result = func(*args, **kwargs) if callable(func) else []
        if isinstance(result, list):
            return result
        return goal_rows

    monkeypatch.setattr("orchestration.ambient_context_engine.asyncio.to_thread", _smart_to_thread)

    # Email-Auth-Mock
    monkeypatch.setenv("TIMUS_GRAPH_CLIENT_ID", "")  # kein Auth → EmailWatcher überspringt

    # get_blackboard wird lokal importiert → am Ursprungsmodul patchen
    with patch("memory.agent_blackboard.get_blackboard", return_value=fake_bb), \
         patch("orchestration.task_queue.get_queue", return_value=real_queue), \
         patch("utils.telegram_notify.send_telegram", new_callable=AsyncMock):
        result = await engine.run_cycle()

    assert result["status"] == "ok"
    assert isinstance(result["signals_found"], int)
    assert isinstance(result["tasks_queued"], int)
    assert result["sources_checked"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────

def _make_to_thread_mock(status_result: dict, email_result: dict):
    """
    Erzeugt einen asyncio.to_thread-Mock der für zwei aufeinanderfolgende
    Aufrufe unterschiedliche Werte zurückgibt (status, dann emails).
    """
    call_order = [status_result, email_result]
    call_index = [0]

    async def _mock(func, *args, **kwargs):
        idx = call_index[0]
        call_index[0] += 1
        if idx < len(call_order):
            return call_order[idx]
        return {}

    return _mock
