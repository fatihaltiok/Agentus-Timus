import pytest
from test_project.calculator import add
from test_project.utils import ConfigManager

def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
def test_config_manager():
    config_manager = ConfigManager('test_project/config.json')
    config_manager.load_config()
    assert config_manager.get_value('version') == '1.0'
