from __future__ import annotations

from utils.headless_service_guard import (
    desktop_open_block_reason,
    is_protected_runtime_artifact,
    is_service_headless_context,
)


def test_service_headless_context_detects_systemd(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEMD_EXEC_PID", "123")
    monkeypatch.delenv("TIMUS_FORCE_HEADLESS", raising=False)

    assert is_service_headless_context() is True


def test_protected_runtime_artifact_blocks_log_and_restart_files() -> None:
    assert is_protected_runtime_artifact("/home/fatih-ubuntu/dev/timus/timus_server.log") is True
    assert is_protected_runtime_artifact("/home/fatih-ubuntu/dev/timus/logs/timus_restart_status.json") is True
    assert is_protected_runtime_artifact("/home/fatih-ubuntu/dev/timus/results/report.pdf") is False


def test_desktop_open_block_reason_blocks_logs_even_outside_service(monkeypatch) -> None:
    monkeypatch.delenv("SYSTEMD_EXEC_PID", raising=False)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.delenv("TIMUS_FORCE_HEADLESS", raising=False)

    reason = desktop_open_block_reason(action_kind="file", target="/tmp/timus_server.log")

    assert reason is not None
    assert "Runtime-Artefakt" in reason
