from __future__ import annotations


def test_quick_intent_routes_camera_analysis_to_image():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "Schau mit der RealSense Kamera und beschreibe, was du siehst."
    )
    assert decision == "image"


def test_quick_intent_does_not_force_setup_questions_to_image():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "Wie kann ich meine D435 Kamera einrichten und die Firmware updaten?"
    )
    assert decision != "image"


def test_quick_intent_routes_camera_shortcut_to_image_when_camera_available(monkeypatch):
    import main_dispatcher

    monkeypatch.setattr(main_dispatcher, "_has_any_local_camera_device", lambda: True)
    decision = main_dispatcher.quick_intent_check("Kannst du mich sehen?")
    assert decision == "image"


def test_quick_intent_keeps_non_camera_shortcut_outside_image(monkeypatch):
    import main_dispatcher

    monkeypatch.setattr(main_dispatcher, "_has_any_local_camera_device", lambda: True)
    decision = main_dispatcher.quick_intent_check("Schau dir das an: https://example.com")
    assert decision != "image"


def test_quick_intent_routes_tiefen_recherche_with_follow_up_to_meta():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "mach eine tiefen recherche zu moe modellen und erstelle anschliessend eine pdf"
    )
    assert decision == "meta"


def test_quick_intent_routes_tiefe_recherche_without_follow_up_to_research():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "mach eine tiefe recherche zu chinesischen llms"
    )
    assert decision == "research"
