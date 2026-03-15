import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def test_voice_tool_import_exposes_numpy_alias():
    import tools.voice_tool.tool as voice_tool

    assert hasattr(voice_tool, "np")
    assert voice_tool.np.__name__ == "numpy"


def test_jsonrpcserver_oslash_import_chain_is_available():
    from jsonrpcserver import Success, Error
    from oslash.either import Left, Right

    success = Success({"ok": True})
    error = Error(code=1234, message="boom")

    assert success is not None
    assert error is not None
    assert Left("x") is not None
    assert Right("y") is not None


def test_tool_registry_imports_with_jsonrpcserver_stack():
    import tools.tool_registry_v2 as tool_registry

    assert hasattr(tool_registry, "registry_v2")
    assert tool_registry.registry_v2 is not None
