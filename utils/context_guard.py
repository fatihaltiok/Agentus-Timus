# utils/context_guard.py
"""
Context-Window-Guard - Schutz vor Kontext-Explosion.

FEATURES:
- Token-Budget-Ueberwachung
- Automatische Output-Komprimierung
- Hard-Stop bei Endlosschleifen
- Conversation-Window-Management

USAGE:
    from utils.context_guard import ContextGuard

    guard = ContextGuard(max_tokens=128000, max_output_tokens=8000)

    # Vor Tool-Call
    if guard.should_compress(result_str):
        result_str = guard.compress(result_str)

    # In Agent-Loop
    guard.check_iteration(step, max_iterations)

    # Token-Zaehlung
    tokens = guard.count_tokens(messages)

AUTOR: Timus Development
DATUM: Februar 2026
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

log = logging.getLogger("ContextGuard")

# tiktoken fuer praezise Token-Zaehlung (Fallback auf Heuristik)
_tiktoken_encoder = None
try:
    import tiktoken
    _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
    log.info("tiktoken geladen - praezise Token-Zaehlung aktiv")
except ImportError:
    log.warning("tiktoken nicht verfuegbar - nutze Heuristik (4 chars/token)")


class ContextStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    OVERFLOW = "overflow"


@dataclass
class GuardStats:
    total_tokens_used: int = 0
    max_tokens_seen: int = 0
    compressions_done: int = 0
    chars_removed: int = 0
    loops_detected: int = 0
    hard_stops: int = 0


@dataclass
class LoopState:
    action_history: List[str] = field(default_factory=list)
    repeated_actions: Dict[str, int] = field(default_factory=dict)
    last_n_actions: List[Tuple[str, float]] = field(default_factory=list)


class ContextGuard:
    """
    Context-Window-Guard fuer Agenten.

    Verhindert:
    - Kontext-Overflow durch grosse Tool-Outputs
    - Endlosschleifen durch wiederholte Aktionen
    - Token-Budget-Ueberschreitung
    """

    DEFAULT_MAX_TOKENS = 128000
    DEFAULT_MAX_OUTPUT_TOKENS = 8000
    DEFAULT_COMPRESSION_THRESHOLD = 4000
    DEFAULT_MAX_REPEATED_ACTIONS = 3
    DEFAULT_LOOP_WINDOW = 10

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        compression_threshold: int = DEFAULT_COMPRESSION_THRESHOLD,
        max_repeated_actions: int = DEFAULT_MAX_REPEATED_ACTIONS,
        loop_window: int = DEFAULT_LOOP_WINDOW,
        model_prefix: str = "gpt",
    ):
        self.max_tokens = max_tokens
        self.max_output_tokens = max_output_tokens
        self.compression_threshold = compression_threshold
        self.max_repeated_actions = max_repeated_actions
        self.loop_window = loop_window
        self.model_prefix = model_prefix

        self._stats = GuardStats()
        self._loop_state = LoopState()
        self._iteration_count = 0
        self._start_time = time.time()

    @property
    def stats(self) -> GuardStats:
        return self._stats

    def estimate_tokens(self, text: str) -> int:
        """
        Zaehlt die Token-Anzahl eines Textes.

        Nutzt tiktoken (cl100k_base) fuer praezise Zaehlung.
        Fallback auf Heuristik (~4 chars/token) wenn tiktoken nicht verfuegbar.
        """
        if not text:
            return 0

        if _tiktoken_encoder is not None:
            return len(_tiktoken_encoder.encode(text))

        # Fallback-Heuristik
        chars = len(text)
        words = len(text.split())
        estimated = max(chars // 4, words * 1.3)
        return int(estimated)

    def count_messages_tokens(self, messages: List[Dict]) -> int:
        """Zaehlt Token in einer Message-List."""
        total = 0

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        total += self.estimate_tokens(item["text"])

            role = msg.get("role", "")
            total += 4

        total += 3

        return total

    def get_status(self, messages: List[Dict]) -> ContextStatus:
        """Prueft den Context-Status."""
        tokens = self.count_messages_tokens(messages)
        self._stats.total_tokens_used = tokens

        if tokens > self._stats.max_tokens_seen:
            self._stats.max_tokens_seen = tokens

        ratio = tokens / self.max_tokens

        if ratio >= 1.0:
            return ContextStatus.OVERFLOW
        elif ratio >= 0.9:
            return ContextStatus.CRITICAL
        elif ratio >= 0.75:
            return ContextStatus.WARNING
        else:
            return ContextStatus.OK

    def should_compress(self, text: str) -> bool:
        """Prueft ob ein Text komprimiert werden sollte."""
        if not text:
            return False

        tokens = self.estimate_tokens(text)
        return tokens > self.compression_threshold

    def compress(self, text: str, max_tokens: int = None) -> str:
        """
        Komprimiert einen Text durch:
        1. Entfernung von Redundanzen
        2. Zusammenfassung langer Listen
        3. Kuerzung auf max_tokens
        """
        if not text:
            return text

        effective_max = max_tokens or self.max_output_tokens

        if len(text) <= effective_max * 4:
            return text

        original_len = len(text)

        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        text = re.sub(r"```[\s\S]*?```", lambda m: "```...[code truncated]...```", text)

        lines = text.split("\n")
        if len(lines) > 50:
            half = 25
            lines = (
                lines[:half]
                + [f"... [{len(lines) - 2 * half} lines omitted] ..."]
                + lines[-half:]
            )
            text = "\n".join(lines)

        if len(text) > effective_max * 4:
            text = text[: effective_max * 4] + "\n... [truncated]"

        self._stats.compressions_done += 1
        self._stats.chars_removed += original_len - len(text)

        log.debug(f"Compressed output: {original_len} -> {len(text)} chars")

        return text

    def summarize_error(self, error_text: str) -> str:
        """Fasst einen Fehler-Text zusammen."""
        if len(error_text) <= 500:
            return error_text

        error_lines = error_text.split("\n")

        first_line = error_lines[0] if error_lines else ""
        last_lines = error_lines[-3:] if len(error_lines) > 3 else error_lines

        summary = (
            f"{first_line}\n... [{len(error_lines)} lines total] ...\n"
            + "\n".join(last_lines)
        )

        return summary

    def check_iteration(
        self, step: int, max_iterations: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Prueft ob die Iteration fortgesetzt werden sollte.

        Returns:
            (should_continue, reason) - reason ist None wenn ok
        """
        self._iteration_count = step

        if step >= max_iterations:
            self._stats.hard_stops += 1
            return False, f"Maximum iterations reached ({max_iterations})"

        elapsed = time.time() - self._start_time
        if elapsed > 600:
            self._stats.hard_stops += 1
            return False, f"Maximum time exceeded ({elapsed:.0f}s)"

        return True, None

    def record_action(
        self, action_name: str, params: dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Zeichnet eine Aktion auf und prueft auf Loops.

        Returns:
            (is_loop, reason) - is_loop ist True wenn ein Loop erkannt wurde
        """
        action_key = f"{action_name}:{hash(str(sorted(params.items())))}"

        self._loop_state.action_history.append(action_key)
        self._loop_state.last_n_actions.append((action_name, time.time()))

        if len(self._loop_state.last_n_actions) > self.loop_window:
            self._loop_state.last_n_actions.pop(0)

        if action_key not in self._loop_state.repeated_actions:
            self._loop_state.repeated_actions[action_key] = 0
        self._loop_state.repeated_actions[action_key] += 1

        repeat_count = self._loop_state.repeated_actions[action_key]

        if repeat_count >= self.max_repeated_actions:
            self._stats.loops_detected += 1
            return True, f"Loop detected: '{action_name}' repeated {repeat_count} times"

        recent_same = sum(
            1 for a, _ in self._loop_state.last_n_actions if a == action_name
        )
        if recent_same >= 4:
            self._stats.loops_detected += 1
            return (
                True,
                f"Rapid loop detected: '{action_name}' called {recent_same} times in last {self.loop_window} actions",
            )

        return False, None

    def reset_loop_state(self):
        """Setzt den Loop-State zurueck."""
        self._loop_state = LoopState()
        self._start_time = time.time()
        self._iteration_count = 0

    def trim_messages(
        self, messages: List[Dict], keep_first: int = 2, keep_last: int = 5
    ) -> List[Dict]:
        """
        Kuerzt eine Message-List wenn noetig.

        Behaelt:
        - System-Message (keep_first)
        - Letzte N Messages (keep_last)
        """
        if len(messages) <= keep_first + keep_last:
            return messages

        tokens = self.count_messages_tokens(messages)
        if tokens < self.max_tokens * 0.9:
            return messages

        trimmed = messages[:keep_first]

        middle_count = len(messages) - keep_first - keep_last
        trimmed.append(
            {
                "role": "system",
                "content": f"[{middle_count} earlier messages omitted for context space]",
            }
        )

        trimmed.extend(messages[-keep_last:])

        new_tokens = self.count_messages_tokens(trimmed)
        log.info(f"Trimmed messages: {tokens} -> {new_tokens} tokens")

        return trimmed

    def get_report(self) -> Dict[str, Any]:
        """Gibt einen Status-Bericht zurueck."""
        elapsed = time.time() - self._start_time
        return {
            "iteration_count": self._iteration_count,
            "elapsed_seconds": round(elapsed, 2),
            "total_tokens_used": self._stats.total_tokens_used,
            "max_tokens_seen": self._stats.max_tokens_seen,
            "compressions_done": self._stats.compressions_done,
            "chars_removed": self._stats.chars_removed,
            "loops_detected": self._stats.loops_detected,
            "hard_stops": self._stats.hard_stops,
            "max_tokens_limit": self.max_tokens,
            "utilization_percent": round(
                self._stats.total_tokens_used / self.max_tokens * 100, 1
            )
            if self.max_tokens > 0
            else 0,
        }


context_guard = ContextGuard()
