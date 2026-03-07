import pytest

from agent.agents.shell import ShellAgent


@pytest.mark.asyncio
async def test_build_shell_context_matches_prompt_contract(monkeypatch):
    agent = ShellAgent.__new__(ShellAgent)

    async def fake_git_status(self):
        return "Git: branch=main | Änderungen: docs/plan.md"

    async def fake_service_status(self):
        return "Services: timus-mcp=active, timus-dispatcher=active"

    async def fake_disk_usage(self, _path, label):
        if label == "/home":
            return "Disk /home: 10G verwendet, 90G frei (10%)"
        if label == "/tmp":
            return "Disk /tmp: 1G verwendet, 19G frei (5%)"
        return ""

    monkeypatch.setattr(ShellAgent, "_get_git_status", fake_git_status)
    monkeypatch.setattr(ShellAgent, "_get_service_status", fake_service_status)
    monkeypatch.setattr(ShellAgent, "_get_disk_usage", fake_disk_usage)
    monkeypatch.setattr(ShellAgent, "_get_last_audit_entry", lambda self: "2026-03-07 run_command pytest -q")
    monkeypatch.setattr(ShellAgent, "_list_scripts", lambda self: "restart_timus.sh, smoke_test.py")

    context = await agent._build_shell_context()

    assert "Git: branch=main | Änderungen: docs/plan.md" in context
    assert "Services: timus-mcp=active, timus-dispatcher=active" in context
    assert "Disk /home: 10G verwendet, 90G frei (10%)" in context
    assert "Disk /tmp: 1G verwendet, 19G frei (5%)" in context
    assert "Letzter Audit-Eintrag: 2026-03-07 run_command pytest -q" in context
    assert "Skripte in scripts/: restart_timus.sh, smoke_test.py" in context
    assert "Projektpfad:" in context
    assert "Audit-Log:" in context
