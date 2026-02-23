"""Tests für die drei Fixes:
- Fix 1: MetaAgent blockiert run_command/run_script/add_cron
- Fix 2: Meta-Modell ist claude-sonnet-4-6
- Fix 3: Implicit Final Answer Erkennung
"""
import pytest
from agent.base_agent import BaseAgent
from agent.agents.meta import MetaAgent


# ── Fix 1: MetaAgent SYSTEM_ONLY_TOOLS ────────────────────────────────────────

class TestMetaShellBlockade:

    def _meta(self):
        agent = MetaAgent.__new__(MetaAgent)
        agent.action_call_counts = {}
        agent.last_skip_times = {}
        agent.recent_actions = []
        return agent

    def test_run_command_blockiert_bei_meta(self):
        """MetaAgent darf run_command nicht direkt aufrufen."""
        meta = self._meta()
        skip, reason = meta.should_skip_action("run_command", {"command": "mv a b"})
        assert skip is True
        assert reason is not None

    def test_run_script_blockiert_bei_meta(self):
        meta = self._meta()
        skip, _ = meta.should_skip_action("run_script", {"script": "#!/bin/bash"})
        assert skip is True

    def test_add_cron_blockiert_bei_meta(self):
        meta = self._meta()
        skip, _ = meta.should_skip_action("add_cron", {"cron": "* * * * *"})
        assert skip is True

    def test_shell_agent_darf_run_command(self):
        """ShellAgent ist NICHT betroffen — run_command nicht global blockiert."""
        from agent.agents.shell import ShellAgent
        shell = ShellAgent.__new__(ShellAgent)
        shell.action_call_counts = {}
        shell.last_skip_times = {}
        shell.recent_actions = []
        # run_command ist nicht in BaseAgent.SYSTEM_ONLY_TOOLS
        assert "run_command" not in BaseAgent.SYSTEM_ONLY_TOOLS

    def test_meta_erbt_basis_blockaden(self):
        """MetaAgent behält alle BaseAgent-Blockaden."""
        expected = {"add_interaction", "end_session", "run_tool", "communicate", "final_answer"}
        assert expected.issubset(MetaAgent.SYSTEM_ONLY_TOOLS)

    def test_meta_hat_shell_extras(self):
        """MetaAgent hat die Shell-Extras zusätzlich."""
        assert {"run_command", "run_script", "add_cron"}.issubset(MetaAgent.SYSTEM_ONLY_TOOLS)

    def test_meta_tool_set_superset_von_base(self):
        """MetaAgent.SYSTEM_ONLY_TOOLS ist echte Obermenge von BaseAgent.SYSTEM_ONLY_TOOLS."""
        assert BaseAgent.SYSTEM_ONLY_TOOLS < MetaAgent.SYSTEM_ONLY_TOOLS


# ── Fix 2: Meta-Modell ist claude-sonnet-4-6 ─────────────────────────────────

class TestMetaModelUpgrade:

    def test_meta_default_model_ist_sonnet_4_6(self):
        """providers.py: Meta-Agent Fallback-Modell ist claude-sonnet-4-6."""
        from agent.providers import AgentModelConfig
        config = AgentModelConfig.AGENT_CONFIGS["meta"]
        # config = (env_var_model, env_var_provider, fallback_model, fallback_provider)
        fallback_model = config[2]
        assert fallback_model == "claude-sonnet-4-6", (
            f"Meta sollte claude-sonnet-4-6 nutzen, nutzt aber: {fallback_model}"
        )

    def test_shell_model_bleibt_sonnet_4_6(self):
        """ShellAgent-Modell unverändert."""
        from agent.providers import AgentModelConfig
        assert AgentModelConfig.AGENT_CONFIGS["shell"][2] == "claude-sonnet-4-6"


# ── Fix 3: Implicit Final Answer Erkennung ────────────────────────────────────

class TestImplicitFinalAnswer:
    """_looks_like_implicit_final_answer() erkennt Abschluss-Meldungen."""

    def _check(self, text: bool) -> bool:
        return BaseAgent._looks_like_implicit_final_answer(text)

    # Positive Fälle (sollen als Final Answer erkannt werden)

    def test_erfolgreich_erstellt(self):
        assert self._check("Das Bild wurde erfolgreich erstellt und gespeichert.") is True

    def test_aufgabe_erfolgreich(self):
        assert self._check("Aufgabe erfolgreich abgeschlossen! Das Cover liegt unter ~/Bilder.") is True

    def test_checkmark_emoji(self):
        assert self._check("✅ COVERBILD GENERIERT — Tech-Magazin-Style zu 'AI Agent Systems 2026'") is True

    def test_englisch_successfully_created(self):
        assert self._check("Image successfully created and saved to results/.") is True

    def test_task_complete(self):
        assert self._check("Task complete. All steps finished.") is True

    def test_gemischter_text_mit_checkmark(self):
        text = (
            "Perfekt! Das Bild wurde erfolgreich erstellt. ✅\n\n"
            "**Ergebnis:**\nGröße: 1024x1024\nGespeichert unter: /home/..."
        )
        assert self._check(text) is True

    # Negative Fälle (sollen NICHT als Final Answer erkannt werden)

    def test_json_vorhanden_kein_match(self):
        """Wenn JSON im Text → kein implicit final answer."""
        text = 'Action: {"method": "delegate_to_agent", "params": {"agent_type": "shell"}}'
        assert self._check(text) is False

    def test_gewoehnlicher_text_kein_match(self):
        """Normaler Zwischenstand → kein match."""
        assert self._check("Ich recherchiere jetzt die neuesten KI-Trends.") is False

    def test_leerer_string(self):
        assert self._check("") is False

    def test_nur_leerzeichen(self):
        assert self._check("   ") is False

    def test_kurioser_json_substring(self):
        """Text mit { → nicht als Final Answer eingestuft."""
        assert self._check("Das Ergebnis {data} wurde gespeichert. ✅") is False
