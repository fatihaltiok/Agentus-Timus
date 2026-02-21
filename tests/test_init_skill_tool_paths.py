from pathlib import Path

import pytest

from tools.init_skill_tool import tool as init_skill_tool_mod


@pytest.mark.asyncio
async def test_init_skill_tool_resolves_relative_path_from_project_root(tmp_path, monkeypatch):
    # Simuliere fehlerhaften CWD (z.B. server/), der zuvor Skills an falscher Stelle erzeugte.
    server_cwd = tmp_path / "server"
    server_cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(server_cwd)
    monkeypatch.setattr(init_skill_tool_mod, "PROJECT_ROOT", tmp_path)

    result = await init_skill_tool_mod.init_skill_tool(
        name="path-resolution-skill",
        description="Test für stabile Pfadauflösung",
        resources=["scripts", "references"],
        examples=True,
        path="skills",
    )

    assert result["success"] is True
    assert (tmp_path / "skills" / "path-resolution-skill" / "SKILL.md").exists()
    assert not (server_cwd / "skills" / "path-resolution-skill").exists()


def test_resolve_base_path_keeps_absolute_path(tmp_path):
    absolute = tmp_path / "my-skills"
    resolved = init_skill_tool_mod._resolve_base_path(str(absolute))
    assert resolved == absolute
