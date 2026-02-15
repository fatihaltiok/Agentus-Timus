import shutil
from pathlib import Path

import pytest

from tools.file_system_tool.tool import list_directory


@pytest.mark.asyncio
async def test_list_directory(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    test_dir = project_root / f"tmp_test_fs_{tmp_path.name}"

    if test_dir.exists():
        shutil.rmtree(test_dir)

    try:
        test_dir.mkdir(parents=True)
        (test_dir / "file1.txt").write_text("content1")
        (test_dir / "file2.txt").write_text("content2")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "file3.txt").write_text("content3")

        result = await list_directory(str(test_dir.relative_to(project_root)))
        if hasattr(result, "result"):
            payload = result.result
        elif hasattr(result, "_value") and hasattr(result._value, "result"):
            payload = result._value.result
        elif hasattr(result, "value"):
            payload = result.value
        elif isinstance(result, dict):
            payload = result.get("result", result)
        else:
            payload = result

        assert payload["status"] == "success"
        assert set(payload["contents"]) == {"file1.txt", "file2.txt", "subdir"}
    finally:
        if test_dir.exists():
            shutil.rmtree(test_dir)
