import pytest
from pathlib import Path
from tools.file_system_tool.tool import list_directory

@pytest.mark.asyncio
def test_list_directory(tmp_path):
    # Erstelle ein temporäres Verzeichnis mit Dateien
    (tmp_path / 'file1.txt').write_text('content1')
    (tmp_path / 'file2.txt').write_text('content2')
    (tmp_path / 'subdir').mkdir()
    (tmp_path / 'subdir' / 'file3.txt').write_text('content3')

    # Führe den Test aus
    result = await list_directory(str(tmp_path.relative_to(Path.cwd())))
    assert result['status'] == 'success'
    assert set(result['contents']) == {'file1.txt', 'file2.txt', 'subdir'}
