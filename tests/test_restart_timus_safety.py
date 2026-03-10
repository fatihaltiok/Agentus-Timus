import deal
import pytest
from hypothesis import given, strategies as st
import json

from tools.shell_tool.tool import restart_timus, run_command, run_script
import tools.shell_tool.tool as shell_tool


@deal.post(lambda r: isinstance(r, bool))
def _restart_script_detected(command: str) -> bool:
    return shell_tool._contains_direct_restart_script(command)


@pytest.mark.asyncio
async def test_run_command_blocks_direct_restart_script():
    result = await run_command("scripts/restart_timus.sh full")
    assert result["status"] == "blocked"
    assert "restart_timus(mode" in result["reason"]


@pytest.mark.asyncio
async def test_run_command_blocks_direct_timus_service_stop():
    result = await run_command("sudo systemctl stop timus-mcp.service")
    assert result["status"] == "blocked"
    assert "Timus-Services" in result["reason"]


@pytest.mark.asyncio
async def test_run_command_allows_timus_service_status(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout, cwd=None):
        class Proc:
            returncode = 0
            stdout = "active\n"
            stderr = ""
        return Proc()

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    result = await run_command("systemctl status timus-mcp.service --no-pager")
    assert result["status"] == "success"
    assert result["returncode"] == 0


@pytest.mark.asyncio
async def test_run_script_blocks_restart_script():
    result = await run_script("scripts/restart_timus.sh")
    assert result["status"] == "blocked"
    assert "restart_timus(mode" in result["reason"]


@pytest.mark.asyncio
async def test_restart_timus_full_uses_detached_launcher(monkeypatch):
    monkeypatch.setattr(shell_tool, "_can_run_noninteractive_restart", lambda: (True, "ok"))
    monkeypatch.setattr(shell_tool, "_launch_detached_restart", lambda mode: {
        "status": "pending_restart",
        "mode": mode,
        "launcher_pid": 123,
        "log_path": "/tmp/timus_restart.log",
        "message": "Detached Timus-Neustart gestartet",
    })
    result = await restart_timus("full")
    assert result["status"] == "pending_restart"
    assert result["mode"] == "full"
    assert result["launcher_pid"] == 123


@pytest.mark.asyncio
async def test_restart_timus_mcp_uses_detached_launcher(monkeypatch):
    monkeypatch.setattr(shell_tool, "_can_run_noninteractive_restart", lambda: (True, "ok"))
    monkeypatch.setattr(shell_tool, "_launch_detached_restart", lambda mode: {
        "status": "pending_restart",
        "mode": mode,
        "launcher_pid": 321,
        "log_path": "/tmp/timus_restart.log",
        "message": "Detached Timus-Neustart gestartet",
    })
    result = await restart_timus("mcp")
    assert result["status"] == "pending_restart"
    assert result["mode"] == "mcp"


@pytest.mark.asyncio
async def test_restart_timus_full_blocks_without_noninteractive_sudo(monkeypatch):
    monkeypatch.setattr(shell_tool, "_can_run_noninteractive_restart", lambda: (False, "sudo unavailable"))
    called = {"value": False}

    def _unexpected_launch(mode):
        called["value"] = True
        return {"status": "pending_restart", "mode": mode}

    monkeypatch.setattr(shell_tool, "_launch_detached_restart", _unexpected_launch)
    result = await restart_timus("full")
    assert result["status"] == "blocked"
    assert result["preflight_ok"] is False
    assert "sudo/systemctl" in result["message"]
    assert called["value"] is False


@pytest.mark.asyncio
async def test_restart_timus_dispatcher_fails_when_not_active(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, timeout, cwd=None):
        calls.append(cmd)
        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""
        rendered = " ".join(cmd)
        if "systemctl is-active" in rendered:
            Proc.stdout = "inactive\n"
        return Proc()

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    result = await restart_timus("dispatcher")
    assert result["status"] == "error"
    assert "Dispatcher antwortet nicht" in result["message"]
    assert any("systemctl is-active" in " ".join(call) for call in calls)


def test_detached_restart_command_uses_nohup():
    command = shell_tool._detached_restart_command("full", "req123")
    assert command.startswith("nohup ")
    assert "restart_supervisor.py" in command
    assert "--status-file" in command
    assert "--lock-file" in command
    assert "--request-id req123" in command
    assert "< /dev/null &" in command


def test_detached_restart_argv_is_explicit():
    argv = shell_tool._detached_restart_argv("full", "req123")
    assert argv[0].endswith("python") or "python" in argv[0]
    assert "restart_supervisor.py" in argv[1]
    assert argv[-2:] == ["--request-id", "req123"] or argv[-1] == "req123"


@pytest.mark.asyncio
async def test_restart_status_reads_supervisor_file(tmp_path, monkeypatch):
    monkeypatch.setattr(shell_tool, "_DETACHED_RESTART_STATUS", tmp_path / "timus_restart_status.json")
    shell_tool._DETACHED_RESTART_STATUS.write_text(
        '{"status":"completed","phase":"completed","mode":"full"}',
        encoding="utf-8",
    )

    def fake_run(cmd, capture_output, text, timeout, cwd=None):
        class Proc:
            returncode = 0
            stdout = "active\n"
            stderr = ""
        return Proc()

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    result = await restart_timus("status")
    assert result["status"] == "ok"
    assert result["restart_supervisor"]["status"] == "completed"


def test_launch_detached_restart_bootstraps_status_and_lock(tmp_path, monkeypatch):
    status_path = tmp_path / "timus_restart_status.json"
    log_path = tmp_path / "timus_restart_detached.log"
    lock_path = tmp_path / "timus_restart.lock"

    monkeypatch.setattr(shell_tool, "_DETACHED_RESTART_STATUS", status_path)
    monkeypatch.setattr(shell_tool, "_DETACHED_RESTART_LOG", log_path)
    monkeypatch.setattr(shell_tool, "_DETACHED_RESTART_LOCK", lock_path)

    class Proc:
        pid = 4242

    monkeypatch.setattr(shell_tool.subprocess, "Popen", lambda *args, **kwargs: Proc())

    result = shell_tool._launch_detached_restart("full")

    assert result["status"] == "pending_restart"
    assert result["request_id"]
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert status_payload["status"] == "launching"
    assert status_payload["mode"] == "full"
    assert status_payload["request_id"] == result["request_id"]
    assert lock_payload["mode"] == "full"
    assert lock_payload["request_id"] == result["request_id"]


def test_launch_detached_restart_blocks_when_lock_exists(tmp_path, monkeypatch):
    status_path = tmp_path / "timus_restart_status.json"
    log_path = tmp_path / "timus_restart_detached.log"
    lock_path = tmp_path / "timus_restart.lock"

    monkeypatch.setattr(shell_tool, "_DETACHED_RESTART_STATUS", status_path)
    monkeypatch.setattr(shell_tool, "_DETACHED_RESTART_LOG", log_path)
    monkeypatch.setattr(shell_tool, "_DETACHED_RESTART_LOCK", lock_path)

    lock_path.write_text(
        json.dumps({"request_id": "existing", "mode": "mcp", "created_at": "2026-03-08T19:49:00"}),
        encoding="utf-8",
    )

    result = shell_tool._launch_detached_restart("full")

    assert result["status"] == "blocked"
    assert result["reason"] == "restart_in_progress"
    assert result["lock_info"]["request_id"] == "existing"


@pytest.mark.asyncio
async def test_restart_timus_dispatcher_blocks_without_noninteractive_sudo(monkeypatch):
    monkeypatch.setattr(shell_tool, "_can_run_noninteractive_systemctl", lambda services: (False, "sudo unavailable"))

    result = await restart_timus("dispatcher")

    assert result["status"] == "blocked"
    assert result["preflight_ok"] is False
    assert "sudo/systemctl" in result["message"]


@given(st.sampled_from([
    "scripts/restart_timus.sh full",
    "/home/fatih-ubuntu/dev/timus/scripts/restart_timus.sh mcp",
    "python scripts/restart_supervisor.py full",
]))
def test_hypothesis_restart_script_detection(command: str):
    assert _restart_script_detected(command) is True
