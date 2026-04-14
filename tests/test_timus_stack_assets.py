from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_timus_stack_target_references_all_three_services() -> None:
    content = _read("timus-stack.target")
    assert "qdrant.service" in content
    assert "timus-mcp.service" in content
    assert "timus-dispatcher.service" in content
    assert "WantedBy=multi-user.target" in content


def test_install_timus_stack_script_installs_units_and_target() -> None:
    content = _read("scripts/install_timus_stack.sh")
    assert "qdrant.service" in content
    assert "timus-mcp.service" in content
    assert "timus-dispatcher.service" in content
    assert "timus-stack.target" in content
    assert "systemctl daemon-reload" in content
    assert "systemctl enable timus-stack.target" in content


def test_timusctl_health_and_install_cover_dispatcher_and_stack_target() -> None:
    content = _read("scripts/timusctl.sh")
    assert 'STACK_TARGET="timus-stack.target"' in content
    assert 'DISPATCHER_HEALTH_URL="http://127.0.0.1:5010/health"' in content
    assert "timusctl.sh install [--no-start]" in content
    assert "curl -fsS \"$DISPATCHER_HEALTH_URL\"" in content
    assert 'installer_args=(--enable --start)' in content
    assert 'PRODUCTION_GATES_SCRIPT=' in content
