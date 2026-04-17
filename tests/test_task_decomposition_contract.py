import json

from orchestration.task_decomposition_contract import (
    build_task_decomposition,
    parse_task_decomposition,
)


def test_build_task_decomposition_classifies_build_setup_requests() -> None:
    decomposition = build_task_decomposition(
        source_query="Recherchiere eine passende Home Assistant Integration und richte sie danach bei mir ein.",
        orchestration_policy={
            "task_type": "integration_setup",
            "response_mode": "execute",
            "action_count": 2,
            "capability_count": 3,
            "route_to_meta": False,
        },
    )

    assert decomposition["intent_family"] == "build_setup"
    assert decomposition["planning_needed"] is True
    assert decomposition["goal_satisfaction_mode"] == "goal_satisfied"
    assert decomposition["subtasks"][2]["id"] == "execute_setup"
    assert decomposition["subtasks"][-1]["id"] == "verify_setup"
    assert "unguardierte_shell_ausfuehrung" in decomposition["constraints"]["forbidden_actions"]
    assert decomposition["metadata"]["explicit_shell_execution"] == "no"


def test_build_task_decomposition_marks_explicit_shell_execution() -> None:
    decomposition = build_task_decomposition(
        source_query="pip install homeassistant und starte danach systemctl restart mosquitto",
        orchestration_policy={
            "task_type": "shell_execution",
            "response_mode": "execute",
            "action_count": 2,
            "capability_count": 2,
        },
    )

    assert decomposition["metadata"]["explicit_shell_execution"] == "yes"
    assert decomposition["planning_needed"] is False
    assert "expliziter_shell_pfand_vorhanden" in decomposition["constraints"]["soft"]


def test_parse_task_decomposition_roundtrips_json_shape() -> None:
    decomposition = build_task_decomposition(
        source_query="Hole aus einem YouTube-Video maximal viel Inhalt raus und schreibe einen Bericht dazu.",
        orchestration_policy={
            "task_type": "youtube_content_extraction",
            "site_kind": "youtube",
            "response_mode": "report",
            "action_count": 2,
            "capability_count": 4,
            "route_to_meta": True,
        },
    )

    parsed = parse_task_decomposition(json.dumps(decomposition, ensure_ascii=False))

    assert parsed == decomposition
