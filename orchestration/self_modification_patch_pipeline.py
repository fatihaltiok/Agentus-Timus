from __future__ import annotations

import difflib
import json
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class IsolatedPatchWorkspace:
    workspace_id: str
    mode: str
    root_path: Path
    relative_path: str
    target_path: Path
    diff_path: Path
    metadata_path: Path


def _temp_workspace_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="timus_self_modify_", dir=tempfile.gettempdir()))


def _supports_git_worktree(project_root: Path) -> bool:
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _ignore_copy_dir(_path: str, names: list[str]) -> set[str]:
    ignored = {".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis", ".venv", "node_modules"}
    ignored.update(name for name in names if name == "__pycache__" or name.endswith(".pyc"))
    return ignored


def create_isolated_patch_workspace(
    *,
    project_root: Path,
    relative_path: str,
    original_code: str,
    modified_code: str,
    change_description: str,
    session_id: str = "",
) -> IsolatedPatchWorkspace:
    workspace_id = uuid.uuid4().hex[:12]
    container = _temp_workspace_root()
    workspace_root = container / "workspace"
    mode = "mirror_copy"

    if _supports_git_worktree(project_root):
        subprocess.run(
            ["git", "-C", str(project_root), "worktree", "add", "--detach", str(workspace_root), "HEAD"],
            check=True,
            timeout=60,
            capture_output=True,
            text=True,
        )
        mode = "git_worktree"
    else:
        shutil.copytree(project_root, workspace_root, ignore=_ignore_copy_dir)

    target_path = workspace_root / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(modified_code, encoding="utf-8")

    diff_path = container / "patch.diff"
    diff_text = "\n".join(
        difflib.unified_diff(
            original_code.splitlines(),
            modified_code.splitlines(),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
    )
    diff_path.write_text(diff_text, encoding="utf-8")

    metadata_path = container / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "mode": mode,
                "relative_path": relative_path,
                "change_description": change_description,
                "session_id": session_id,
                "created_at": datetime.utcnow().isoformat(),
                "workspace_root": str(workspace_root),
                "diff_path": str(diff_path),
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    return IsolatedPatchWorkspace(
        workspace_id=workspace_id,
        mode=mode,
        root_path=workspace_root,
        relative_path=relative_path,
        target_path=target_path,
        diff_path=diff_path,
        metadata_path=metadata_path,
    )


def promote_isolated_patch(*, project_root: Path, workspace: IsolatedPatchWorkspace) -> None:
    live_target = project_root / workspace.relative_path
    live_target.parent.mkdir(parents=True, exist_ok=True)
    live_target.write_text(workspace.target_path.read_text(encoding="utf-8"), encoding="utf-8")


def cleanup_isolated_patch_workspace(*, project_root: Path, workspace: IsolatedPatchWorkspace) -> None:
    container = workspace.root_path.parent
    try:
        if workspace.mode == "git_worktree":
            subprocess.run(
                ["git", "-C", str(project_root), "worktree", "remove", "--force", str(workspace.root_path)],
                check=True,
                timeout=60,
                capture_output=True,
                text=True,
            )
        elif workspace.root_path.exists():
            shutil.rmtree(workspace.root_path, ignore_errors=True)
    finally:
        if container.exists():
            shutil.rmtree(container, ignore_errors=True)
