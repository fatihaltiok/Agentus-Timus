import ast
from pathlib import Path


def test_reload_skills_tool_module_is_registered_in_mcp_loader():
    mcp_server_path = Path("server/mcp_server.py")
    source = mcp_server_path.read_text(encoding="utf-8")
    module = ast.parse(source)

    tool_modules = None
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOOL_MODULES":
                    if isinstance(node.value, ast.List):
                        tool_modules = [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
                    break
        if tool_modules is not None:
            break

    assert tool_modules is not None, "TOOL_MODULES assignment not found in server/mcp_server.py"
    assert "tools.skill_manager_tool.reload_tool" in tool_modules
    assert "tools.init_skill_tool.tool" in tool_modules
