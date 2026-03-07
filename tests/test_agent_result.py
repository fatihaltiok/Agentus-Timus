"""Tests für AgentResult Dataclass (M17)."""
import pytest
from dataclasses import fields, asdict
from agent.agent_registry import AgentResult


# ── 1. Felder und Typen ────────────────────────────────────────────────────

def test_agent_result_success_fields():
    r = AgentResult(status="success", agent="shell", result="ok", quality=80, blackboard_key="delegation:shell:123")
    assert r.status == "success"
    assert r.agent == "shell"
    assert r.result == "ok"
    assert r.quality == 80
    assert r.blackboard_key == "delegation:shell:123"
    assert r.error == ""


def test_agent_result_error_fields():
    r = AgentResult(status="error", agent="research", result="", quality=0,
                    blackboard_key="delegation:research:456", error="Timeout")
    assert r.status == "error"
    assert r.quality == 0
    assert r.error == "Timeout"


def test_agent_result_partial_fields():
    r = AgentResult(status="partial", agent="data", result="teilweise", quality=40, blackboard_key="")
    assert r.status == "partial"
    assert r.quality == 40


# ── 2. Quality-Bounds: 0–100 ──────────────────────────────────────────────

def test_agent_result_quality_success_is_80():
    r = AgentResult(status="success", agent="shell", result="ok", quality=80, blackboard_key="k")
    assert 0 <= r.quality <= 100
    assert r.quality == 80


def test_agent_result_quality_error_is_0():
    r = AgentResult(status="error", agent="shell", result="", quality=0, blackboard_key="k")
    assert 0 <= r.quality <= 100
    assert r.quality == 0


def test_agent_result_quality_partial_is_40():
    r = AgentResult(status="partial", agent="shell", result="x", quality=40, blackboard_key="k")
    assert 0 <= r.quality <= 100
    assert r.quality == 40


def test_agent_result_success_quality_gt_error():
    """Lean Th.51: success quality (80) > error quality (0)."""
    success = AgentResult(status="success", agent="a", result="ok", quality=80, blackboard_key="")
    error = AgentResult(status="error", agent="a", result="", quality=0, blackboard_key="")
    assert error.quality < success.quality


# ── 3. Status-Enum (nur erlaubte Werte) ───────────────────────────────────

def test_agent_result_status_values():
    for status, quality in [("success", 80), ("partial", 40), ("error", 0)]:
        r = AgentResult(status=status, agent="x", result="", quality=quality, blackboard_key="")
        assert r.status in {"success", "partial", "error"}


# ── 4. Blackboard-Key Format ──────────────────────────────────────────────

def test_blackboard_key_format():
    key = "delegation:shell:1234567890"
    r = AgentResult(status="success", agent="shell", result="", quality=80, blackboard_key=key)
    parts = r.blackboard_key.split(":")
    assert parts[0] == "delegation"
    assert parts[1] == "shell"
    assert parts[2].isdigit()


def test_blackboard_key_empty_on_error():
    r = AgentResult(status="error", agent="x", result="", quality=0, blackboard_key="")
    assert r.blackboard_key == ""


# ── 5. Dict-Konvertierung (asdict round-trip) ─────────────────────────────

def test_agent_result_asdict():
    r = AgentResult(status="success", agent="shell", result="done", quality=80, blackboard_key="k1")
    d = asdict(r)
    assert d["status"] == "success"
    assert d["agent"] == "shell"
    assert d["result"] == "done"
    assert d["quality"] == 80
    assert d["blackboard_key"] == "k1"
    assert d["error"] == ""


def test_agent_result_from_dict():
    d = {"status": "partial", "agent": "data", "result": "x", "quality": 40,
         "blackboard_key": "delegation:data:999", "error": ""}
    r = AgentResult(**d)
    assert r.status == "partial"
    assert r.quality == 40
