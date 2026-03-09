from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_timus_mcp_service_has_bounded_graceful_shutdown():
    unit = (PROJECT_ROOT / "timus-mcp.service").read_text(encoding="utf-8")

    assert "--lifespan on" in unit
    assert "--timeout-keep-alive 2" in unit
    assert "--timeout-graceful-shutdown 10" in unit
    assert "KillSignal=SIGINT" in unit
    assert "TimeoutStopSec=20" in unit
    assert "TimeoutStartSec=45" in unit


def test_restart_script_resets_failed_state_before_restart():
    script = (PROJECT_ROOT / "scripts" / "restart_timus.sh").read_text(encoding="utf-8")

    assert 'systemctl reset-failed "$MCP_SERVICE"' in script
    assert 'systemctl reset-failed "$DISPATCHER_SERVICE"' in script


def test_sudoers_allows_reset_failed_for_timus_services():
    sudoers = (PROJECT_ROOT / "scripts" / "sudoers_timus").read_text(encoding="utf-8")

    assert "/usr/bin/systemctl reset-failed timus-mcp.service" in sudoers
    assert "/usr/bin/systemctl reset-failed timus-dispatcher.service" in sudoers
