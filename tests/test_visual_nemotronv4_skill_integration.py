import time
import pytest

# Relativer Import des Skills
from skills.visual_nemotronv4_web_interaction_skill import dry_run

def test_dry_run_about_blank():
    """Testet, dass ein Dry-Run gegen about:blank die erwarteten Schritte liefert."""
    steps, success = dry_run(url="about:blank", timeout=5, retries=1)
    assert success is True
    assert steps == ["open", "scan", "ocr", "click"]

def test_dry_run_retry_mechanism(monkeypatch):
    """Testet, dass bei transienten Fehlern die Retry-Logik funktioniert."""
    # Zähler für Aufrufe
    call_counter = {"scan": 0, "ocr": 0}

    def fake_scan(*args, **kwargs):
        call_counter["scan"] += 1
        if call_counter["scan"] == 1:
            raise TimeoutError("Scan timed out")
        return "scan_success"

    def fake_ocr(*args, **kwargs):
        call_counter["ocr"] += 1
        if call_counter["ocr"] == 1:
            raise TimeoutError("OCR timed out")
        return "ocr_success"

    # Patch interne Funktionen
    monkeypatch.setattr("skills.visual_nemotronv4_web_interaction_skill.scan", fake_scan)
    monkeypatch.setattr("skills.visual_nemotronv4_web_interaction_skill.ocr", fake_ocr)

    # Durchführen
    steps, success = dry_run(url="about:blank", timeout=5, retries=2)
    assert success is True
    assert steps == ["open", "scan", "ocr", "click"]
    assert call_counter["scan"] == 2
    assert call_counter["ocr"] == 2

def test_dry_run_timeout(monkeypatch):
    """Testet, dass ein Timeout korrekt gehandhabt wird."""
    def fake_scan(*args, **kwargs):
        time.sleep(2)  # Simuliere lange Operation
        return "scan_success"

    monkeypatch.setattr("skills.visual_nemotronv4_web_interaction_skill.scan", fake_scan)

    with pytest.raises(TimeoutError):
        dry_run(url="about:blank", timeout=1, retries=0)  # Timeout kleiner als Sleep