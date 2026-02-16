# tests/test_context_guard.py
"""
Umfassende Unit-Tests fuer den Context-Window-Guard.

Testet alle Kernfunktionen:
- Token-Schaetzung
- Context-Status-Erkennung
- Komprimierung
- Loop-Detection
- Message-Trimming
- Iteration-Checks
"""

import pytest
import time
from utils.context_guard import ContextGuard, ContextStatus, GuardStats, LoopState


# === FIXTURES ===


@pytest.fixture
def guard():
    """Standard ContextGuard mit kleinen Limits fuer Tests."""
    return ContextGuard(
        max_tokens=1000,
        max_output_tokens=200,
        compression_threshold=100,
        max_repeated_actions=3,
        loop_window=5,
    )


@pytest.fixture
def large_guard():
    """ContextGuard mit realistischen Limits."""
    return ContextGuard(max_tokens=128000, max_output_tokens=8000)


@pytest.fixture
def sample_messages():
    """Beispiel-Messages fuer Tests."""
    return [
        {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
        {"role": "user", "content": "Hallo, wie geht es dir?"},
        {"role": "assistant", "content": "Mir geht es gut! Wie kann ich dir helfen?"},
    ]


# === TOKEN-SCHAETZUNG ===


class TestEstimateTokens:
    def test_empty_string(self, guard):
        assert guard.estimate_tokens("") == 0

    def test_short_text(self, guard):
        tokens = guard.estimate_tokens("Hallo Welt")
        assert tokens > 0
        assert tokens < 20

    def test_long_text(self, guard):
        text = "Dies ist ein langer Text. " * 100
        tokens = guard.estimate_tokens(text)
        assert tokens > 100

    def test_code_text(self, guard):
        code = "def hello():\n    print('Hello World')\n    return True\n"
        tokens = guard.estimate_tokens(code)
        assert tokens > 5

    def test_none_returns_zero(self, guard):
        assert guard.estimate_tokens(None) == 0


# === COUNT MESSAGES TOKENS ===


class TestCountMessagesTokens:
    def test_empty_list(self, guard):
        tokens = guard.count_messages_tokens([])
        assert tokens == 3  # Base overhead

    def test_simple_messages(self, guard, sample_messages):
        tokens = guard.count_messages_tokens(sample_messages)
        assert tokens > 10

    def test_multimodal_content(self, guard):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Was siehst du auf dem Bild?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            }
        ]
        tokens = guard.count_messages_tokens(messages)
        assert tokens > 5

    def test_role_overhead(self, guard):
        one_msg = [{"role": "user", "content": "Hi"}]
        two_msgs = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hi"},
        ]
        tokens_one = guard.count_messages_tokens(one_msg)
        tokens_two = guard.count_messages_tokens(two_msgs)
        assert tokens_two > tokens_one


# === CONTEXT STATUS ===


class TestGetStatus:
    def test_ok_status(self, guard):
        messages = [{"role": "user", "content": "Kurz"}]
        status = guard.get_status(messages)
        assert status == ContextStatus.OK

    def test_warning_status(self, guard):
        # 75% von 1000 tokens = 750 tokens; "Wort " * 750 ~ 750 tokens
        messages = [{"role": "user", "content": "Wort " * 770}]
        status = guard.get_status(messages)
        assert status in (ContextStatus.WARNING, ContextStatus.CRITICAL, ContextStatus.OVERFLOW)

    def test_critical_status(self, guard):
        # 90% von 1000 tokens = 900 tokens
        messages = [{"role": "user", "content": "Wort " * 920}]
        status = guard.get_status(messages)
        assert status in (ContextStatus.CRITICAL, ContextStatus.OVERFLOW)

    def test_overflow_status(self, guard):
        # > 1000 tokens
        messages = [{"role": "user", "content": "Wort " * 1100}]
        status = guard.get_status(messages)
        assert status == ContextStatus.OVERFLOW

    def test_stats_updated(self, guard, sample_messages):
        guard.get_status(sample_messages)
        assert guard.stats.total_tokens_used > 0
        assert guard.stats.max_tokens_seen > 0


# === SHOULD COMPRESS ===


class TestShouldCompress:
    def test_short_text_no_compress(self, guard):
        assert guard.should_compress("Kurzer Text") is False

    def test_long_text_compress(self, guard):
        # compression_threshold=100 tokens; "Wort " * 120 ~ 120 tokens
        assert guard.should_compress("Wort " * 120) is True

    def test_empty_text_no_compress(self, guard):
        assert guard.should_compress("") is False

    def test_none_no_compress(self, guard):
        assert guard.should_compress(None) is False


# === COMPRESS ===


class TestCompress:
    def test_short_text_unchanged(self, guard):
        text = "Kurzer Text"
        result = guard.compress(text)
        assert result == text

    def test_removes_excessive_newlines(self, guard):
        text = "Zeile 1\n\n\n\n\nZeile 2" + "x" * 1000
        result = guard.compress(text)
        assert "\n\n\n" not in result

    def test_removes_excessive_spaces(self, guard):
        text = "Wort     Wort" + "x" * 1000
        result = guard.compress(text)
        assert "     " not in result

    def test_truncates_code_blocks(self, guard):
        code_block = "```python\n" + "print('hello')\n" * 50 + "```"
        text = "Vorher\n" + code_block + "\nNachher" + "x" * 500
        result = guard.compress(text)
        assert "[code truncated]" in result

    def test_truncates_long_output(self, guard):
        text = "\n".join([f"Zeile {i}" for i in range(200)])
        result = guard.compress(text, max_tokens=50)
        assert len(result) < len(text)
        assert "[truncated]" in result or "lines omitted" in result

    def test_stats_updated(self, guard):
        text = "x" * 2000
        guard.compress(text, max_tokens=100)
        assert guard.stats.compressions_done >= 1
        assert guard.stats.chars_removed > 0

    def test_empty_text(self, guard):
        assert guard.compress("") == ""
        assert guard.compress(None) is None


# === SUMMARIZE ERROR ===


class TestSummarizeError:
    def test_short_error_unchanged(self, guard):
        error = "ValueError: invalid literal"
        result = guard.summarize_error(error)
        assert result == error

    def test_long_error_shortened(self, guard):
        lines = [f"  File 'module{i}.py', line {i}" for i in range(50)]
        error = "Traceback (most recent call last):\n" + "\n".join(lines)
        result = guard.summarize_error(error)
        assert len(result) < len(error)
        assert "Traceback" in result
        assert "lines total" in result


# === CHECK ITERATION ===


class TestCheckIteration:
    def test_within_limit(self, guard):
        should_continue, reason = guard.check_iteration(5, 20)
        assert should_continue is True
        assert reason is None

    def test_at_limit(self, guard):
        should_continue, reason = guard.check_iteration(20, 20)
        assert should_continue is False
        assert "Maximum iterations" in reason

    def test_over_limit(self, guard):
        should_continue, reason = guard.check_iteration(25, 20)
        assert should_continue is False

    def test_hard_stop_counted(self, guard):
        guard.check_iteration(20, 20)
        assert guard.stats.hard_stops >= 1


# === RECORD ACTION (LOOP DETECTION) ===


class TestRecordAction:
    def test_no_loop_initially(self, guard):
        is_loop, reason = guard.record_action("search", {"query": "test"})
        assert is_loop is False
        assert reason is None

    def test_loop_after_repeated_action(self, guard):
        for i in range(2):
            is_loop, _ = guard.record_action("search", {"query": "test"})
            assert is_loop is False

        is_loop, reason = guard.record_action("search", {"query": "test"})
        assert is_loop is True
        assert "Loop detected" in reason

    def test_different_params_no_repeated_loop(self, guard):
        """Verschiedene Params verhindern 'repeated action' Loop,
        aber rapid loop (gleicher Name) kann trotzdem triggern."""
        for i in range(3):
            is_loop, _ = guard.record_action("search", {"query": f"test_{i}"})
            assert is_loop is False

    def test_different_actions_no_loop(self, guard):
        """Verschiedene Action-Namen loesen keinen Loop aus."""
        actions = ["search", "click", "read", "write", "navigate"]
        for action in actions:
            is_loop, _ = guard.record_action(action, {"param": "value"})
            assert is_loop is False

    def test_rapid_loop_detection(self, guard):
        # loop_window=5, Schwelle ist 4 gleiche Aktionen
        for i in range(3):
            guard.record_action("click", {"x": i, "y": i})

        # 4 gleiche Aktionen (verschiedene Params aber gleicher Name) in window
        guard.record_action("click", {"x": 10, "y": 10})
        is_loop, reason = guard.record_action("click", {"x": 20, "y": 20})
        # Bei 5 Aktionen gleichen Namens im Window von 5 sollte rapid loop erkannt werden
        # Da recent_same >= 4 bei 5 "click" Aktionen
        # Aber erst wenn record_action selbst zaehlt
        # Wir hatten 3 + 1 + 1 = 5 clicks, alle im window von 5
        # recent_same = 5 >= 4 -> loop
        assert is_loop is True
        assert "Rapid loop" in reason

    def test_loops_detected_counted(self, guard):
        for i in range(3):
            guard.record_action("search", {"query": "test"})
        assert guard.stats.loops_detected >= 1

    def test_reset_clears_state(self, guard):
        for i in range(3):
            guard.record_action("search", {"query": "test"})
        guard.reset_loop_state()
        is_loop, _ = guard.record_action("search", {"query": "test"})
        assert is_loop is False


# === TRIM MESSAGES ===


class TestTrimMessages:
    def test_short_list_unchanged(self, guard, sample_messages):
        result = guard.trim_messages(sample_messages)
        assert len(result) == len(sample_messages)

    def test_long_list_trimmed(self, guard):
        # Erstelle viele Messages die den Token-Limit ueberschreiten
        messages = [{"role": "system", "content": "System prompt " * 50}]
        for i in range(20):
            messages.append({"role": "user", "content": f"Nachricht {i} " * 30})
            messages.append({"role": "assistant", "content": f"Antwort {i} " * 30})

        result = guard.trim_messages(messages, keep_first=2, keep_last=5)
        assert len(result) < len(messages)
        # System-Message erhalten
        assert result[0]["role"] == "system"
        # Omitted-Marker vorhanden
        assert any("omitted" in m.get("content", "") for m in result)

    def test_keeps_first_and_last(self, guard):
        messages = [{"role": "system", "content": "Sys " * 100}]
        for i in range(20):
            messages.append({"role": "user", "content": f"Msg{i} " * 50})

        result = guard.trim_messages(messages, keep_first=1, keep_last=3)
        if len(result) < len(messages):
            assert result[0] == messages[0]  # Erster erhalten
            assert result[-1] == messages[-1]  # Letzter erhalten


# === GET REPORT ===


class TestGetReport:
    def test_report_structure(self, guard):
        report = guard.get_report()
        assert "iteration_count" in report
        assert "elapsed_seconds" in report
        assert "total_tokens_used" in report
        assert "max_tokens_seen" in report
        assert "compressions_done" in report
        assert "loops_detected" in report
        assert "hard_stops" in report
        assert "max_tokens_limit" in report
        assert "utilization_percent" in report

    def test_report_after_operations(self, guard, sample_messages):
        guard.get_status(sample_messages)
        guard.compress("x" * 2000, max_tokens=100)
        guard.check_iteration(10, 10)
        guard.record_action("test", {"a": 1})

        report = guard.get_report()
        assert report["total_tokens_used"] > 0
        assert report["compressions_done"] >= 1
        assert report["hard_stops"] >= 1
        assert report["utilization_percent"] > 0


# === INTEGRATION ===


class TestIntegration:
    def test_full_workflow(self, large_guard):
        """Simuliert einen kompletten Agent-Loop mit Context-Guard."""
        messages = [{"role": "system", "content": "Du bist ein Agent."}]
        actions = ["search", "click", "read", "analyze", "respond"]

        for step in range(5):
            status = large_guard.get_status(messages)
            assert status != ContextStatus.OVERFLOW

            should_continue, _ = large_guard.check_iteration(step, 10)
            assert should_continue is True

            # Verschiedene Actions um Rapid-Loop zu vermeiden
            is_loop, _ = large_guard.record_action(
                actions[step], {"query": f"query_{step}"}
            )
            assert is_loop is False

            result = f"Ergebnis fuer Schritt {step}: " + "data " * 20
            if large_guard.should_compress(result):
                result = large_guard.compress(result)

            messages.append({"role": "user", "content": f"Schritt {step}"})
            messages.append({"role": "assistant", "content": result})

        report = large_guard.get_report()
        assert report["iteration_count"] == 4
        assert report["loops_detected"] == 0
