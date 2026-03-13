from pathlib import Path

import deal

from orchestration.self_modification_patch_pipeline import (
    cleanup_isolated_patch_workspace,
    create_isolated_patch_workspace,
)


@deal.pre(lambda relative_path: bool(str(relative_path).strip()))
@deal.post(lambda r: r.relative_path.endswith(".py") or r.relative_path.endswith(".md"))
def _workspace_contract(tmp_path: Path, relative_path: str):
    project = tmp_path
    target = project / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n", encoding="utf-8")
    workspace = create_isolated_patch_workspace(
        project_root=project,
        relative_path=relative_path,
        original_code="x\n",
        modified_code="y\n",
        change_description="demo",
    )
    cleanup_isolated_patch_workspace(project_root=project, workspace=workspace)
    return workspace


def test_workspace_contract_on_python_file(tmp_path: Path) -> None:
    workspace = _workspace_contract(tmp_path, "orchestration/demo.py")
    assert workspace.target_path.exists()
