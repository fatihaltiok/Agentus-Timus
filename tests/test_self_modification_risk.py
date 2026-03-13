from orchestration.self_modification_policy import evaluate_self_modification_policy
from orchestration.self_modification_risk import classify_self_modification_risk


def test_docs_change_is_low_risk():
    policy = evaluate_self_modification_policy("docs/report.md", change_type="documentation")
    risk = classify_self_modification_risk(
        file_path="docs/report.md",
        change_description="tighten wording",
        original_code="# alt\n",
        modified_code="# neu\n",
        policy=policy,
    )
    assert risk.risk_level == "low"


def test_meta_orchestration_large_diff_is_medium_or_higher():
    policy = evaluate_self_modification_policy("orchestration/meta_orchestration.py")
    modified = "def new_value():\n" + "".join(f"    value_{idx} = {idx}\n" for idx in range(40))
    risk = classify_self_modification_risk(
        file_path="orchestration/meta_orchestration.py",
        change_description="expand orchestration flow",
        original_code="def old_value():\n    return 1\n",
        modified_code=modified,
        policy=policy,
    )
    assert risk.risk_level in {"medium", "high"}


def test_dangerous_markers_push_risk_high():
    policy = evaluate_self_modification_policy("orchestration/meta_orchestration.py")
    risk = classify_self_modification_risk(
        file_path="orchestration/meta_orchestration.py",
        change_description="run subprocess for deployment",
        original_code="def old_value():\n    return 1\n",
        modified_code="import subprocess\nsubprocess.run(['sudo', 'systemctl', 'restart', 'x'])\n",
        policy=policy,
    )
    assert risk.risk_level == "high"
    assert "kritische_marker" in risk.reason
