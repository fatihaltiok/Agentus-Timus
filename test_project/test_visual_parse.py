from agent.timus_consolidated import VisualAgent


def test_parse_action():
    agent = VisualAgent("test tools")

    test_replies = [
        '{"thought": "Test", "action": {"method": "start_visual_browser", "params": {"url": "https://gemini.google.com"}}}',
        'Thought: Ich öffne den Browser\nAction: {"method": "start_visual_browser", "params": {"url": "https://gemini.google.com"}}',
    ]

    for reply in test_replies:
        action, err = agent._parse_action(reply)
        assert err is None
        assert action is not None
        assert action.get("method") == "start_visual_browser"