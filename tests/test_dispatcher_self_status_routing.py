import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def test_quick_intent_routes_self_status_to_executor():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("Was hast du fuer Probleme?") == "executor"
    assert main_dispatcher.quick_intent_check("sag du es mir") == "executor"
    assert main_dispatcher.quick_intent_check("und was kannst du dagegen tun") == "executor"
    assert main_dispatcher.quick_intent_check("und was davon machst du zuerst") == "executor"


def test_quick_intent_routes_location_only_queries_to_executor():
    import main_dispatcher

    assert main_dispatcher.quick_intent_check("Wo bin ich?") == "executor"
    assert main_dispatcher.quick_intent_check("Wo ist mein Standort gerade?") == "executor"
