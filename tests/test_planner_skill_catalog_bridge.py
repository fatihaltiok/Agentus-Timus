import pytest

from tools.planner import tool as planner_tool


def _write_skill_md(base_dir, name: str, description: str, with_script: bool = False):
    skill_dir = base_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "---\n\n"
            "# Skill\n\n"
            "Nutze diesen Skill für reproduzierbare Abläufe.\n"
        ),
        encoding="utf-8",
    )
    if with_script:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "main.py").write_text(
            (
                "import sys\n"
                "if __name__ == '__main__':\n"
                "    print('ok:' + ','.join(sys.argv[1:]))\n"
            ),
            encoding="utf-8",
        )


@pytest.mark.asyncio
async def test_list_available_skills_merges_yaml_and_skill_md(tmp_path, monkeypatch):
    skills_yml_path = tmp_path / "skills.yml"
    skills_yml_path.write_text(
        (
            "yaml_skill:\n"
            "  meta:\n"
            "    description: YAML workflow skill\n"
            "    params:\n"
            "      query: query text\n"
            "  steps:\n"
            "    - method: search_web\n"
            "      params:\n"
            "        query: '{{query}}'\n"
        ),
        encoding="utf-8",
    )

    skills_md_dir = tmp_path / "skills"
    _write_skill_md(
        base_dir=skills_md_dir,
        name="md-skill",
        description="Instructional SKILL.md skill",
        with_script=True,
    )

    monkeypatch.setattr(planner_tool, "SKILLS_PATH", skills_yml_path)
    monkeypatch.setattr(planner_tool, "SKILL_MD_DIR", skills_md_dir)

    result = await planner_tool.list_available_skills()
    skills = {item["name"]: item for item in result["skills"]}

    assert "yaml_skill" in skills
    assert skills["yaml_skill"]["source"] == "skills_yml"
    assert skills["yaml_skill"]["execution_mode"] == "workflow"
    assert skills["yaml_skill"]["required_params"] == ["query"]

    assert "md-skill" in skills
    assert skills["md-skill"]["source"] == "skill_md"
    assert skills["md-skill"]["execution_mode"] == "script"


@pytest.mark.asyncio
async def test_get_skill_details_returns_source_specific_metadata(tmp_path, monkeypatch):
    skills_yml_path = tmp_path / "skills.yml"
    skills_yml_path.write_text(
        (
            "yaml_only:\n"
            "  meta:\n"
            "    description: YAML only skill\n"
            "    params:\n"
            "      url: target url\n"
            "  steps:\n"
            "    - method: open_url\n"
            "      params:\n"
            "        url: '{{url}}'\n"
        ),
        encoding="utf-8",
    )

    skills_md_dir = tmp_path / "skills"
    _write_skill_md(
        base_dir=skills_md_dir,
        name="md-only",
        description="Skill with optional script",
        with_script=True,
    )

    monkeypatch.setattr(planner_tool, "SKILLS_PATH", skills_yml_path)
    monkeypatch.setattr(planner_tool, "SKILL_MD_DIR", skills_md_dir)

    yaml_details = await planner_tool.get_skill_details("yaml_only")
    assert yaml_details["source"] == "skills_yml"
    assert yaml_details["required_params"] == ["url"]
    assert yaml_details["execution_mode"] == "workflow"

    md_details = await planner_tool.get_skill_details("md-only")
    assert md_details["source"] == "skill_md"
    assert md_details["execution_mode"] == "script"
    assert md_details["entry_script"] == "main.py"
    assert "main.py" in md_details["available_scripts"]


@pytest.mark.asyncio
async def test_run_skill_executes_yaml_workflow(tmp_path, monkeypatch):
    skills_yml_path = tmp_path / "skills.yml"
    skills_yml_path.write_text(
        (
            "yaml_skill:\n"
            "  meta:\n"
            "    description: YAML workflow skill\n"
            "    params:\n"
            "      query: query text\n"
            "  steps:\n"
            "    - method: search_web\n"
            "      params:\n"
            "        query: '{{query}}'\n"
        ),
        encoding="utf-8",
    )

    skills_md_dir = tmp_path / "skills"
    skills_md_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(planner_tool, "SKILLS_PATH", skills_yml_path)
    monkeypatch.setattr(planner_tool, "SKILL_MD_DIR", skills_md_dir)

    async def fake_call_tool_internal(method, params):
        return {"status": "success", "method": method, "params": params}

    monkeypatch.setattr(planner_tool, "call_tool_internal", fake_call_tool_internal)

    result = await planner_tool.run_skill("yaml_skill", params={"query": "stockholm cafes"})
    assert result["plan_status"] == "done"
    assert result["final_result"]["search_web"]["params"]["query"] == "stockholm cafes"


@pytest.mark.asyncio
async def test_run_skill_executes_skill_md_script(tmp_path, monkeypatch):
    skills_yml_path = tmp_path / "skills.yml"
    skills_yml_path.write_text("", encoding="utf-8")

    skills_md_dir = tmp_path / "skills"
    _write_skill_md(
        base_dir=skills_md_dir,
        name="script-skill",
        description="Script skill for runtime execution",
        with_script=True,
    )

    monkeypatch.setattr(planner_tool, "SKILLS_PATH", skills_yml_path)
    monkeypatch.setattr(planner_tool, "SKILL_MD_DIR", skills_md_dir)

    result = await planner_tool.run_skill("script-skill", params={"foo": "bar"})
    assert result["plan_status"] == "done"
    assert result["source"] == "skill_md"
    assert result["execution_mode"] == "script"
    assert result["result"]["success"] is True


@pytest.mark.asyncio
async def test_run_skill_returns_instructional_payload_for_skill_md_without_script(tmp_path, monkeypatch):
    skills_yml_path = tmp_path / "skills.yml"
    skills_yml_path.write_text("", encoding="utf-8")

    skills_md_dir = tmp_path / "skills"
    _write_skill_md(
        base_dir=skills_md_dir,
        name="instruction-only",
        description="Instructional skill without script",
        with_script=False,
    )

    monkeypatch.setattr(planner_tool, "SKILLS_PATH", skills_yml_path)
    monkeypatch.setattr(planner_tool, "SKILL_MD_DIR", skills_md_dir)

    result = await planner_tool.run_skill("instruction-only")
    assert result["plan_status"] == "done"
    assert result["execution_mode"] == "instructional"
    assert "instructions" in result
