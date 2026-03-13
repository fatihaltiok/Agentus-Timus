from __future__ import annotations

from dataclasses import dataclass

from orchestration.self_modification_policy import SelfModificationPolicyDecision


_ZONE_BASELINE = {
    "docs": 0,
    "tests": 0,
    "prompt_policy": 1,
    "browser_workflow": 1,
    "meta_orchestration": 1,
}

_CHANGE_BASELINE = {
    "documentation": 0,
    "evaluation_tests": 0,
    "prompt_policy": 1,
    "analytics_observability": 1,
    "orchestration_policy": 1,
}

_DANGEROUS_MARKERS = (
    "subprocess.",
    "os.system",
    "systemctl",
    "sudo ",
    "rm -rf",
    "httpx.post(",
    "requests.post(",
)


@dataclass(frozen=True)
class SelfModificationRiskDecision:
    risk_level: str
    score: int
    reason: str
    changed_lines: int
    dangerous_markers_found: tuple[str, ...] = ()


def _changed_line_count(original_code: str, modified_code: str) -> int:
    original_lines = str(original_code or "").splitlines()
    modified_lines = str(modified_code or "").splitlines()
    max_len = max(len(original_lines), len(modified_lines))
    changed = 0
    for idx in range(max_len):
        left = original_lines[idx] if idx < len(original_lines) else None
        right = modified_lines[idx] if idx < len(modified_lines) else None
        if left != right:
            changed += 1
    return changed


def classify_self_modification_risk(
    *,
    file_path: str,
    change_description: str,
    original_code: str,
    modified_code: str,
    policy: SelfModificationPolicyDecision,
) -> SelfModificationRiskDecision:
    if not policy.allowed:
        return SelfModificationRiskDecision(
            risk_level="high",
            score=999,
            reason=policy.reason,
            changed_lines=0,
        )

    score = 0
    factors: list[str] = []
    zone_id = str(policy.zone_id or "")
    change_type = str(policy.effective_change_type or "")

    score += _ZONE_BASELINE.get(zone_id, 3)
    score += _CHANGE_BASELINE.get(change_type, 2)

    changed_lines = _changed_line_count(original_code, modified_code)
    if changed_lines > 80:
        score += 3
        factors.append("grosses_diff")
    elif changed_lines > 30:
        score += 2
        factors.append("mittleres_diff")
    elif changed_lines > 12:
        score += 1
        factors.append("kleines_diff")

    if zone_id not in {"docs", "tests"} and not policy.required_test_targets:
        score += 2
        factors.append("fehlende_pflichttests")

    text_to_scan = f"{change_description}\n{modified_code}".lower()
    markers_found = tuple(marker for marker in _DANGEROUS_MARKERS if marker.lower() in text_to_scan)
    if markers_found:
        score += 4
        factors.append("kritische_marker")

    if score <= 2:
        risk_level = "low"
    elif score <= 5:
        risk_level = "medium"
    else:
        risk_level = "high"

    if not factors:
        reason = "niedriges_risiko"
    else:
        reason = ",".join(factors)
    return SelfModificationRiskDecision(
        risk_level=risk_level,
        score=score,
        reason=reason,
        changed_lines=changed_lines,
        dangerous_markers_found=markers_found,
    )
