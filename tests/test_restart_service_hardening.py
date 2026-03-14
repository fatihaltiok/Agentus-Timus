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
    assert "qdrant.service" in unit


def test_qdrant_service_exists_and_timus_units_wait_for_it():
    qdrant_unit = (PROJECT_ROOT / "qdrant.service").read_text(encoding="utf-8")
    dispatcher_unit = (PROJECT_ROOT / "timus-dispatcher.service").read_text(encoding="utf-8")

    assert "ExecStart=/home/fatih-ubuntu/dev/timus/scripts/start_qdrant_server.sh" in qdrant_unit
    assert "Wants=network.target local-fs.target" in qdrant_unit
    assert "After=network.target timus-mcp.service qdrant.service" in dispatcher_unit
    assert "Wants=network.target qdrant.service" in dispatcher_unit


def test_restart_script_resets_failed_state_before_restart():
    script = (PROJECT_ROOT / "scripts" / "restart_timus.sh").read_text(encoding="utf-8")

    assert 'systemctl reset-failed "$MCP_SERVICE"' in script
    assert 'systemctl reset-failed "$DISPATCHER_SERVICE"' in script


def test_sudoers_allows_reset_failed_for_timus_services():
    sudoers = (PROJECT_ROOT / "scripts" / "sudoers_timus").read_text(encoding="utf-8")

    assert "/usr/bin/systemctl reset-failed timus-mcp.service" in sudoers
    assert "/usr/bin/systemctl reset-failed timus-dispatcher.service" in sudoers
    assert "/usr/bin/systemctl reset-failed qdrant.service" in sudoers
    assert "/usr/bin/systemctl status qdrant.service" in sudoers
