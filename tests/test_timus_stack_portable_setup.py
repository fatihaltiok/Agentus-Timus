from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_setup_timus_host_renders_portable_units(tmp_path: Path) -> None:
    project_root = tmp_path / "portable-timus"
    scripts_dir = project_root / "scripts"
    venv_bin = project_root / ".venv" / "bin"
    output_dir = tmp_path / "generated"
    config_file = tmp_path / "timus_stack_host.env"
    scripts_dir.mkdir(parents=True)
    venv_bin.mkdir(parents=True)
    start_qdrant = scripts_dir / "start_qdrant_server.sh"
    start_qdrant.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    start_qdrant.chmod(0o755)
    fake_python = venv_bin / "python"
    fake_python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    fake_uvicorn = venv_bin / "uvicorn"
    fake_uvicorn.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_uvicorn.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "TIMUS_STACK_NONINTERACTIVE": "1",
            "TIMUS_STACK_SETUP_ENV_FILE": str(config_file),
            "TIMUS_STACK_OUTPUT_DIR": str(output_dir),
            "TIMUS_SYSTEM_USER": "alice",
            "TIMUS_PROJECT_ROOT": str(project_root),
            "TIMUS_PYTHON": str(fake_python),
            "TIMUS_PYTHON_UVICORN": str(fake_uvicorn),
            "TIMUS_DISPLAY": ":1",
            "TIMUS_XAUTHORITY": "/home/alice/.Xauthority",
        }
    )

    subprocess.run(
        ["bash", "scripts/setup_timus_host.sh"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    mcp = (output_dir / "timus-mcp.service").read_text(encoding="utf-8")
    dispatcher = (output_dir / "timus-dispatcher.service").read_text(encoding="utf-8")
    qdrant = (output_dir / "qdrant.service").read_text(encoding="utf-8")
    stack = (output_dir / "timus-stack.target").read_text(encoding="utf-8")
    rendered_config = config_file.read_text(encoding="utf-8")

    assert "User=alice" in mcp
    assert f"WorkingDirectory={project_root}" in mcp
    assert f"ExecStart={fake_uvicorn} \\" in mcp
    assert "Environment=DISPLAY=:1" in mcp
    assert "Environment=XAUTHORITY=/home/alice/.Xauthority" in mcp

    assert "User=alice" in dispatcher
    assert f"WorkingDirectory={project_root}" in dispatcher
    assert f"ExecStart={fake_python} main_dispatcher.py" in dispatcher

    assert "User=alice" in qdrant
    assert f"ExecStart={project_root}/scripts/start_qdrant_server.sh" in qdrant

    assert "Requires=qdrant.service timus-mcp.service timus-dispatcher.service" in stack
    assert "TIMUS_SYSTEM_USER=alice" in rendered_config
    assert f"TIMUS_PROJECT_ROOT={project_root}" in rendered_config


def test_install_script_supports_unit_dir() -> None:
    content = _read("scripts/install_timus_stack.sh")
    assert "--unit-dir PATH" in content
    assert 'UNIT_DIR="${TIMUS_STACK_UNITS_DIR:-${PROJECT_ROOT}}"' in content
    assert 'src="${UNIT_DIR}/${unit}"' in content


def test_timusctl_supports_host_setup_and_generated_units() -> None:
    content = _read("scripts/timusctl.sh")
    assert 'HOST_SETUP_SCRIPT=' in content
    assert 'GENERATED_SYSTEMD_DIR=' in content
    assert "setup-host [--install]" in content
    assert '--unit-dir "$GENERATED_SYSTEMD_DIR"' in content
    assert '--install --enable --start' in content
