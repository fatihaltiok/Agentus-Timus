"""Tests für utils/bug_logger.py"""
import json
import pytest
from pathlib import Path


def _make_logger(tmp_path):
    """Erstellt BugLogger mit tmp_path als Log-Root."""
    from utils.bug_logger import BugLogger
    return BugLogger(base_dir=tmp_path)


def test_bug_file_erstellt(tmp_path):
    """JSONL-Datei wird angelegt und enthält gültiges JSON."""
    bl = _make_logger(tmp_path)
    path = bl.log_bug(
        bug_id="test_bug",
        severity="critical",
        agent="executor",
        error_msg="Something went wrong",
        context={"task_id": "t1"},
    )
    file = Path(path)
    assert file.exists(), "Bug-Datei wurde nicht angelegt"

    lines = file.read_text().strip().splitlines()
    assert len(lines) >= 1
    data = json.loads(lines[0])
    assert data["bug_id"] == "test_bug"
    assert data["severity"] == "critical"
    assert data["agent"] == "executor"
    assert "error" in data
    assert "timestamp" in data


def test_buglog_md_eintrag(tmp_path):
    """buglog.md enthält nach log_bug einen menschenlesbaren Eintrag."""
    bl = _make_logger(tmp_path)
    bl.log_bug(
        bug_id="creative_empty_prompt",
        severity="high",
        agent="creative",
        error_msg="Invalid 'prompt': empty string",
    )
    buglog = tmp_path / "buglog.md"
    assert buglog.exists(), "buglog.md wurde nicht angelegt"
    content = buglog.read_text()
    assert "creative_empty_prompt" in content
    assert "HIGH" in content
    assert "creative" in content


def test_bugs_dir_wird_auto_angelegt(tmp_path):
    """logs/bugs/ wird automatisch erstellt falls nicht vorhanden."""
    bl = _make_logger(tmp_path)
    assert bl._bugs_dir.exists(), "BUGS_DIR wurde nicht angelegt"


def test_mehrere_bugs_separate_dateien(tmp_path):
    """Zwei Bugs erzeugen zwei separate Dateien."""
    bl = _make_logger(tmp_path)
    p1 = bl.log_bug("bug_a", "low", "meta", "Error A")
    p2 = bl.log_bug("bug_b", "medium", "research", "Error B")
    assert p1 != p2
    assert Path(p1).exists()
    assert Path(p2).exists()


def test_stack_trace_wird_gespeichert(tmp_path):
    """Stack-Trace wird in der JSONL-Datei gespeichert."""
    bl = _make_logger(tmp_path)
    path = bl.log_bug(
        bug_id="trace_test",
        severity="high",
        agent="executor",
        error_msg="Crash",
        stack_trace="Traceback (most recent call last):\n  File 'x.py'",
    )
    data = json.loads(Path(path).read_text().strip().splitlines()[0])
    assert "Traceback" in data["stack_trace"]
