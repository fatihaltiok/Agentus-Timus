from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_GITIGNORE_PATTERNS = (
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/",
    ".hypothesis/",
    ".venv/",
    "venv/",
)


def _git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def test_no_tracked_pyc_files() -> None:
    assert _git_lines("ls-files", "*.pyc") == []


def test_no_tracked_pycache_paths() -> None:
    tracked = _git_lines("ls-files")
    assert not [path for path in tracked if "/__pycache__/" in path or path.startswith("__pycache__/")]


def test_gitignore_contains_python_runtime_artifact_patterns() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    missing = [pattern for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in gitignore]
    assert missing == []
