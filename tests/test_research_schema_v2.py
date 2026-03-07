from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_deep_research_session_initializes_contract_v2():
    from tools.deep_research.tool import DeepResearchSession

    session = DeepResearchSession("Vergleiche offene Modelle", ["Benchmarks"])

    assert session.contract_v2 is not None
    assert session.contract_v2.question.text == "Vergleiche offene Modelle"
    assert session.contract_v2.question.profile.value in {
        "vendor_comparison",
        "fact_check",
    }


def test_deep_research_session_exports_contract_v2_with_limitations_as_open_questions():
    from tools.deep_research.tool import DeepResearchSession

    session = DeepResearchSession("Pruefe aktuelle Regulierung")
    session.limitations = [
        "Nicht alle Gerichtsurteile gefunden",
        "Nicht alle Gerichtsurteile gefunden",
        "Zeitliche Volatilitaet hoch",
    ]

    exported = session.export_contract_v2()

    assert exported["question"]["text"] == "Pruefe aktuelle Regulierung"
    assert exported["open_questions"] == [
        "Nicht alle Gerichtsurteile gefunden",
        "Zeitliche Volatilitaet hoch",
    ]
    assert isinstance(exported["claims"], list)
    assert isinstance(exported["sources"], list)
    assert isinstance(exported["evidences"], list)

