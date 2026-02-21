from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory.reflection_engine import ReflectionEngine
from tools.hybrid_detection_tool.tool import HybridDetectionEngine


def _prepare_config_with_pending(path: Path) -> None:
    config = {
        "version": 1,
        "updated_at": "2026-02-20T00:00:00",
        "policy": {"require_human_approval": True, "auto_apply": False},
        "active": {"opencv_template_threshold": 0.82, "template_candidates": []},
        "pending_changes": [
            {
                "id": "chg_approve",
                "status": "pending",
                "signature": "sig-approve",
                "proposed_changes": {
                    "opencv_template_threshold": 0.74,
                    "template_candidates": ["submit_button"],
                },
            },
            {
                "id": "chg_reject",
                "status": "pending",
                "signature": "sig-reject",
                "proposed_changes": {
                    "opencv_template_threshold": 0.70,
                    "template_candidates": ["dangerous_template"],
                },
            },
        ],
        "history": [],
    }
    path.write_text(json.dumps(config), encoding="utf-8")


def test_approve_and_reject_adaptations_require_explicit_action(tmp_path):
    config_path = tmp_path / "vision_adaptive_config.json"
    _prepare_config_with_pending(config_path)
    engine = ReflectionEngine()

    before = engine.load_vision_adaptive_config(config_path=str(config_path))
    assert before["active"]["opencv_template_threshold"] == 0.82

    approved = engine.approve_vision_adaptation(
        change_id="chg_approve",
        approved_by="qa-human",
        config_path=str(config_path),
        notes="Looks good",
    )
    assert approved["success"] is True

    after_approve = engine.load_vision_adaptive_config(config_path=str(config_path))
    assert after_approve["active"]["opencv_template_threshold"] == 0.74
    assert "submit_button" in after_approve["active"]["template_candidates"]

    rejected = engine.reject_vision_adaptation(
        change_id="chg_reject",
        rejected_by="qa-human",
        reason="unsafe",
        config_path=str(config_path),
    )
    assert rejected["success"] is True

    final_config = engine.load_vision_adaptive_config(config_path=str(config_path))
    assert final_config["active"]["opencv_template_threshold"] == 0.74
    assert "dangerous_template" not in final_config["active"]["template_candidates"]
    assert len(final_config["pending_changes"]) == 0
    statuses = {item["status"] for item in final_config["history"]}
    assert statuses == {"approved", "rejected"}


def test_hybrid_engine_reads_only_active_adaptive_values(tmp_path, monkeypatch):
    config_path = tmp_path / "vision_adaptive_config.json"
    _prepare_config_with_pending(config_path)
    monkeypatch.setenv("VISION_ADAPTIVE_CONFIG_PATH", str(config_path))

    engine = HybridDetectionEngine()
    assert engine._adaptive_template_threshold() == 0.82
    assert engine._adaptive_template_candidates() == []
