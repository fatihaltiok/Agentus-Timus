from pathlib import Path

from orchestration.self_modification_patch_pipeline import (
    cleanup_isolated_patch_workspace,
    create_isolated_patch_workspace,
    promote_isolated_patch,
)


def test_patch_workspace_keeps_live_repo_untouched_until_promote(tmp_path: Path) -> None:
    project = tmp_path
    target = project / "orchestration" / "meta_orchestration.py"
    target.parent.mkdir(parents=True)
    original = "def old():\n    return 1\n"
    modified = "def new():\n    return 2\n"
    target.write_text(original, encoding="utf-8")

    workspace = create_isolated_patch_workspace(
        project_root=project,
        relative_path="orchestration/meta_orchestration.py",
        original_code=original,
        modified_code=modified,
        change_description="rename function",
    )
    try:
        assert target.read_text(encoding="utf-8") == original
        assert workspace.target_path.read_text(encoding="utf-8") == modified
        assert workspace.diff_path.exists()
        promote_isolated_patch(project_root=project, workspace=workspace)
        assert target.read_text(encoding="utf-8") == modified
    finally:
        cleanup_isolated_patch_workspace(project_root=project, workspace=workspace)


def test_patch_workspace_falls_back_to_mirror_copy_without_git(tmp_path: Path) -> None:
    project = tmp_path
    target = project / "docs" / "note.md"
    target.parent.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")

    workspace = create_isolated_patch_workspace(
        project_root=project,
        relative_path="docs/note.md",
        original_code="old\n",
        modified_code="new\n",
        change_description="update note",
    )
    try:
        assert workspace.mode == "mirror_copy"
        assert workspace.metadata_path.exists()
        assert workspace.root_path.exists()
    finally:
        cleanup_isolated_patch_workspace(project_root=project, workspace=workspace)
