import deal
import pytest
from hypothesis import given, strategies as st

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

    def fake_run(cmd, shell, capture_output, text, timeout, cwd=None):
        calls.append(cmd)
        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""
        if "systemctl is-active" in cmd:
            Proc.stdout = "inactive\n"
        return Proc()

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    result = await restart_timus("dispatcher")
    assert result["status"] == "error"
    assert "Dispatcher antwortet nicht" in result["message"]
    assert any("systemctl is-active" in call for call in calls)


def test_detached_restart_command_uses_nohup():
    command = shell_tool._detached_restart_command("full")
    assert command.startswith("nohup ")
    assert "restart_supervisor.py" in command
    assert "--status-file" in command
    assert "< /dev/null &" in command


@pytest.mark.asyncio
async def test_restart_status_reads_supervisor_file(tmp_path, monkeypatch):
    monkeypatch.setattr(shell_tool, "_DETACHED_RESTART_STATUS", tmp_path / "timus_restart_status.json")
    shell_tool._DETACHED_RESTART_STATUS.write_text(
        '{"status":"completed","phase":"completed","mode":"full"}',
        encoding="utf-8",
    )

    def fake_run(cmd, shell, capture_output, text, timeout, cwd=None):
        class Proc:
            returncode = 0
            stdout = "active\n"
            stderr = ""
        return Proc()

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    result = await restart_timus("status")
    assert result["status"] == "ok"
    assert result["restart_supervisor"]["status"] == "completed"


@given(st.sampled_from([
    "scripts/restart_timus.sh full",
    "/home/fatih-ubuntu/dev/timus/scripts/restart_timus.sh mcp",
    "python scripts/restart_supervisor.py full",
]))
def test_hypothesis_restart_script_detection(command: str):
    assert _restart_script_detected(command) is True
