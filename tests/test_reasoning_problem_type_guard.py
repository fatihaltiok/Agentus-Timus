from agent.agents.reasoning import _detect_problem_type


def test_reasoning_problem_type_does_not_label_personal_job_context_as_architecture_review():
    text = (
        "ich arbeite seit 2010 in meinem job, verstehe software architektur, "
        "will aber in 12 monaten raus und habe kein finanzielles polster"
    )
    assert _detect_problem_type(text) != "Architektur-Review"


def test_reasoning_problem_type_keeps_real_technical_architecture_review():
    text = "Welche Architektur passt fuer diese Python API mit Worker, Postgres und zwei Services?"
    assert _detect_problem_type(text) == "Architektur-Review"
