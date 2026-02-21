import logging
import os
import tempfile
from pathlib import Path

import pytest

# Relativer Import des Skills
from skills.visual_nemotronv4_web_interaction_skill import get_config

def test_get_config_valid_inputs():
    """Testet, dass gültige Eingaben ein erwartetes Dict zurückgeben."""
    cfg = get_config(url="https://example.com", timeout=10, retries=3)
    assert cfg["url"] == "https://example.com"
    assert cfg["timeout"] == 10
    assert cfg["retries"] == 3

def test_get_config_missing_values():
    """Testet, dass fehlende Werte Standardwerte übernehmen."""
    cfg = get_config(url="https://example.com")
    assert cfg["timeout"] == 5  # Standardwert
    assert cfg["retries"] == 1  # Standardwert

def test_get_config_invalid_types():
    """Testet, dass ungültige Typen einen ValueError auslösen."""
    with pytest.raises(ValueError):
        get_config(url=123)  # url sollte ein String sein

def test_get_config_logging_error(tmp_path: Path):
    """Testet, dass ein Fehler im Logfile landet."""
    log_file = tmp_path / "error.log"
    # Logging konfigurieren
    logging.basicConfig(filename=str(log_file), level=logging.ERROR,
                        format='%(asctime)s %(levelname)s %(message)s')
    # Simuliere einen Fehler (z.B. falscher Typ)
    try:
        get_config(url=123)
    except ValueError:
        pass
    # Prüfen, dass Logfile den Fehler enthält
    assert log_file.exists()
    content = log_file.read_text()
    assert "ValueError" in content
    assert "url" in content