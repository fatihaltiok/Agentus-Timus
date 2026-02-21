from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory.reflection_engine import ReflectionEngine


def _write_artifact(path: Path, message: str, target_text: str, change_pct: float) -> None:
    payload = {
        "timestamp": 1_700_000_000,
        "message": message,
        "confidence": 0.71,
        "target": {"x": 200, "y": 120},
        "metadata": {
            "verify": {
                "expected_change": True,
                "min_change": 0.5,
                "change_percentage": change_pct,
                "message": message,
            },
            "context": {
                "target_text": target_text,
                "element_type": "button",
            },
        },
        "files": {"metadata": str(path)},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_analyze_visual_failures_creates_pending_changes_without_auto_apply(tmp_path):
    debug_dir = tmp_path / "debug"
    debug_dir.mkdir()
    config_path = tmp_path / "vision_adaptive_config.json"

    _write_artifact(debug_dir / "a1.json", "Keine Änderung erkannt", "Login Button", 0.1)
    _write_artifact(debug_dir / "a2.json", "Keine Änderung erkannt", "Login Button", 0.2)
    _write_artifact(debug_dir / "a3.json", "Keine Änderung erkannt", "Login Button", 0.3)

    engine = ReflectionEngine()
    result = engine.analyze_visual_failures(
        debug_dir=str(debug_dir),
        config_path=str(config_path),
        min_occurrences=2,
        limit=100,
    )

    assert result["analyzed_files"] == 3
    assert result["new_pending_changes"] >= 1

    config = engine.load_vision_adaptive_config(config_path=str(config_path))
    assert config["policy"]["require_human_approval"] is True
    assert config["policy"]["auto_apply"] is False
    assert config["active"]["opencv_template_threshold"] == 0.82
    assert len(config["pending_changes"]) >= 1
    assert "login_button" in config["pending_changes"][0]["proposed_changes"]["template_candidates"]
