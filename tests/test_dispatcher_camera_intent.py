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


def test_quick_intent_routes_complex_browser_booking_flow_to_meta():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "Starte den Browser, gehe auf booking.com, tippe Berlin, waehle 15. Maerz bis 17. Maerz und klicke auf Suchen"
    )
    assert decision == "meta"


def test_quick_intent_keeps_simple_browser_step_on_visual_nemotron():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "Starte den Browser und gehe auf booking.com"
    )
    assert decision == "visual_nemotron"


def test_quick_intent_routes_login_mask_setup_to_phase_d_visual():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "Oeffne github.com/login und fuehre mich bis zur Login-Maske."
    )
    assert decision == "visual_login"


def test_quick_intent_routes_natural_chrome_password_manager_login_to_phase_d_visual():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "Bitte melde mich in Chrome bei GitHub an und nutze den Passwortmanager."
    )
    assert decision == "visual_login"


def test_build_visual_login_handoff_wraps_phase_d_login_contract():
    import main_dispatcher

    handoff = main_dispatcher._build_visual_login_handoff(
        "Oeffne github.com/login und fuehre mich bis zur Login-Maske."
    )

    assert "# DELEGATION HANDOFF" in handoff
    assert "target_agent: visual" in handoff
    assert "expected_output: login_handoff" in handoff
    assert "success_signal: login maske sichtbar" in handoff
    assert "source_url: https://github.com/login" in handoff
    assert "expected_state: login_dialog" in handoff


def test_build_visual_login_handoff_preserves_auth_session_context():
    import main_dispatcher

    handoff = main_dispatcher._build_visual_login_handoff(
        "\n".join(
            [
                "# FOLLOW-UP CONTEXT",
                "auth_session_service: github",
                "auth_session_status: authenticated",
                "auth_session_url: https://github.com/settings/profile",
                "",
                "# CURRENT USER QUERY",
                "Oeffne github.com/login und fuehre mich bis zur Login-Maske.",
            ]
        )
    )

    assert "- source_url: https://github.com/login" in handoff
    assert "- auth_session_service: github" in handoff
    assert "- auth_session_status: authenticated" in handoff
    assert "- auth_session_url: https://github.com/settings/profile" in handoff


def test_build_visual_login_handoff_requests_chrome_credential_broker_when_explicit():
    import main_dispatcher

    handoff = main_dispatcher._build_visual_login_handoff(
        "Oeffne github.com/login in Chrome und nutze den Chrome Passwortmanager fuer den gespeicherten Login."
    )

    assert "- browser_type: chrome" in handoff
    assert "- credential_broker: chrome_password_manager" in handoff
    assert "- broker_profile: Default" in handoff
    assert "- domain: github.com" in handoff


def test_build_visual_login_handoff_normalizes_login_url_for_natural_prompt():
    import main_dispatcher

    handoff = main_dispatcher._build_visual_login_handoff(
        "Bitte melde mich in Chrome bei GitHub an und nutze den Passwortmanager."
    )

    assert "- source_url: https://github.com/login" in handoff
    assert "- browser_type: chrome" in handoff
    assert "- credential_broker: chrome_password_manager" in handoff


def test_visual_login_followup_context_is_preserved_for_resume():
    import main_dispatcher

    followup_query = "\n".join(
        [
            "# FOLLOW-UP CONTEXT",
            "pending_workflow_status: awaiting_user",
            "pending_workflow_reason: user_mediated_login",
            "pending_workflow_source_agent: visual_login",
            "",
            "# CURRENT USER QUERY",
            "ich sehe jetzt eine 2fa challenge",
        ]
    )

    assert main_dispatcher._should_preserve_visual_login_followup(followup_query) is True


def test_visual_login_new_task_is_still_wrapped():
    import main_dispatcher

    assert (
        main_dispatcher._should_preserve_visual_login_followup(
            "Oeffne github.com/login und fuehre mich bis zur Login-Maske."
        )
        is False
    )


def test_quick_intent_keeps_service_start_on_shell():
    import main_dispatcher

    decision = main_dispatcher.quick_intent_check(
        "Starte den MCP-Server neu"
    )
    assert decision == "shell"
