"""Parser fuer strukturierte Specialist-Handoffs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


_HANDOFF_HEADER = "# DELEGATION HANDOFF"


@dataclass
class DelegationHandoff:
    target_agent: str = ""
    goal: str = ""
    expected_output: str = ""
    success_signal: str = ""
    constraints: List[str] = field(default_factory=list)
    handoff_data: Dict[str, str] = field(default_factory=dict)


def parse_delegation_handoff(task: str) -> Optional[DelegationHandoff]:
    text = str(task or "").strip()
    if not text.startswith(_HANDOFF_HEADER):
        return None

    payload = DelegationHandoff()
    mode: Optional[str] = None

    for raw_line in text.splitlines()[1:]:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("target_agent:"):
            payload.target_agent = stripped.split(":", 1)[1].strip()
            mode = None
            continue
        if stripped.startswith("goal:"):
            payload.goal = stripped.split(":", 1)[1].strip()
            mode = None
            continue
        if stripped.startswith("expected_output:"):
            payload.expected_output = stripped.split(":", 1)[1].strip()
            mode = None
            continue
        if stripped.startswith("success_signal:"):
            payload.success_signal = stripped.split(":", 1)[1].strip()
            mode = None
            continue
        if stripped == "constraints:":
            mode = "constraints"
            continue
        if stripped == "handoff_data:":
            mode = "handoff_data"
            continue

        if mode == "constraints" and stripped.startswith("- "):
            payload.constraints.append(stripped[2:].strip())
            continue

        if mode == "handoff_data" and stripped.startswith("- "):
            key_value = stripped[2:].strip()
            if ":" in key_value:
                key, value = key_value.split(":", 1)
                payload.handoff_data[key.strip()] = value.strip()
            continue

    return payload
