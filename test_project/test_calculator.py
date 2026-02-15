from test_project.calculator import Calculator
from test_project.utils import ConfigManager


def test_subtract():
    result = Calculator.subtract(10, 5)
    assert result == 5.0


def test_config_manager():
    config_manager = ConfigManager("test_project/config.json")
    assert config_manager.get_value("version") == "1.0"
