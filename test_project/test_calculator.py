
import pytest
from config_manager import ConfigManager


def test_config_manager():
    config_manager = ConfigManager('test_project/config.json')
    assert config_manager.get_value('version') == '1.0'
