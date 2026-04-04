from __future__ import annotations

from unittest.mock import patch

from agent.base_agent import BaseAgent
from agent.agents.shell import ShellAgent


def _base_agent_stub() -> BaseAgent:
    return BaseAgent.__new__(BaseAgent)


def test_extract_primary_task_text_from_meta_augmented_task() -> None:
    task = (
        "# TIMUS SYSTEM-KONTEXT (automatisch geladen)\n"
        "Verfügbare Agenten: visual, browser, research\n\n"
        "# AUFGABE\n"
        "hey timus kannst du meinen googlekalender einsehen\n\n"
        "Prüfe ob verfügbare Skills zur Aufgabe passen und nutze sie entsprechend.\n\n"
        "## DECOMPOSITION-REGEL (automatisch aktiviert)\n"
        "Diese Aufgabe hat >3 Teilschritte.\n"
    )

    assert (
        BaseAgent._extract_primary_task_text(task)
        == "hey timus kannst du meinen googlekalender einsehen"
    )


def test_google_calendar_file_lookup_is_not_misclassified_as_navigation() -> None:
    agent = _base_agent_stub()
    task = (
        "# TIMUS SYSTEM-KONTEXT (automatisch geladen)\n"
        "browser navigation context\n\n"
        "# AUFGABE\n"
        "Lies skills/google-calendar/SKILL.md und prüfe ob OAuth2-Credentials konfiguriert sind.\n\n"
        "Prüfe ob verfügbare Skills zur Aufgabe passen und nutze sie entsprechend."
    )

    primary = BaseAgent._extract_primary_task_text(task).lower()

    assert BaseAgent._is_navigation_task(agent, primary) is False


def test_blackboard_query_ignores_browser_noise_in_context() -> None:
    agent = _base_agent_stub()
    task = (
        "# TIMUS SYSTEM-KONTEXT (automatisch geladen)\n"
        "Verfügbare Agenten: visual, browser, shell\n\n"
        "# AUFGABE\n"
        "was gibts auf dem blackboard\n\n"
        "Prüfe ob verfügbare Skills zur Aufgabe passen und nutze sie entsprechend."
    )

    primary = BaseAgent._extract_primary_task_text(task).lower()

    assert primary == "was gibts auf dem blackboard"
    assert BaseAgent._is_navigation_task(agent, primary) is False


def test_open_google_domain_still_counts_as_navigation() -> None:
    agent = _base_agent_stub()
    assert BaseAgent._is_navigation_task(agent, "öffne google.com und suche hotels") is True


def test_shell_agent_disables_auto_vision_even_if_base_enabled() -> None:
    def _fake_base_init(self, *args, **kwargs):
        self._vision_enabled = True

    with patch.object(BaseAgent, "__init__", _fake_base_init):
        agent = ShellAgent("tools")

    assert agent._vision_enabled is False
