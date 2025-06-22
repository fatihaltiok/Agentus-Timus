import pytest
import asyncio
from test_project.calculator import subtract
from config_manager import ConfigManager


@pytest.mark.asyncio
async def test_subtract():
    result = await subtract(10, 5)
    assert result.result['result'] == 5
    config_manager = ConfigManager('test_project/config.json')
    assert config_manager.get_value('version') == '1.0'
