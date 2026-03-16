"""
orchestration/self_hardening_engine.py — M18: Self-Hardening Engine

Timus liest seine eigenen Logs und das Blackboard, erkennt wiederkehrende
Fehler oder Ungenauigkeiten und erzeugt daraus strukturierte Härtungs-Vorschläge
(HardeningProposals) — ohne manuellen Eingriff.

Ablauf pro Zyklus:
1. Letzte N Log-Zeilen aus dem systemd-Journal lesen (WARNING/ERROR)
2. Blackboard auf incident:* und error:* Einträge prüfen
3. Pattern-Matcher gruppiert Fehler nach Modul + Fehlertyp
4. Bei Überschreitung des Schwellenwerts → HardeningProposal erstellen
5. Proposal ins Blackboard schreiben + als Goal anlegen + Telegram (gebuffert)

Feature-Flag: AUTONOMY_SELF_HARDENING_ENABLED=false
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger("SelfHardeningEngine")

# ── Konfiguration ─────────────────────────────────────────────────────────────

_JOURNAL_LINES = int(os.getenv("HARDENING_JOURNAL_LINES", "300"))
_MIN_OCCURRENCES = int(os.getenv("HARDENING_MIN_OCCURRENCES", "3"))
_BLACKBOARD_TTL = int(os.getenv("HARDENING_BLACKBOARD_TTL", "7200"))  # 2h
_GOAL_COOLDOWN_H = int(os.getenv("HARDENING_GOAL_COOLDOWN_HOURS", "24"))

# Alle produktiven systemd-Units die Timus-Fehler erzeugen können
_JOURNAL_UNITS = [
    u.strip()
    for u in os.getenv("HARDENING_JOURNAL_UNITS", "timus-dispatcher,timus-mcp").split(",")
    if u.strip()
]

# ── Bekannte Fehler-Pattern → Härtungs-Empfehlung ─────────────────────────────

@dataclass
class ErrorPattern:
    name: str           # interner Bezeichner
    regex: str          # Regex gegen Log-Zeile
    component: str      # betroffenes Modul
    suggestion: str     # Was soll gehärtet werden
    severity: str       # low / medium / high


_PATTERNS: List[ErrorPattern] = [
    ErrorPattern(
        name="goal_conflict_false_positive",
        regex=r"Goal-Konflikte erkannt",
        component="task_queue._conflict_reason",
        suggestion="Stopwort-Filter oder Präfix-Ausschluss für Auto-Ziele ausbauen",
        severity="low",
    ),
    ErrorPattern(
        name="delegation_timeout",
        regex=r"Delegation.*[Tt]imeout|TimeoutError.*deleg",
        component="autonomous_runner._delegate",
        suggestion="Timeout-Wert erhöhen oder Retry-Strategie anpassen",
        severity="medium",
    ),
    ErrorPattern(
        name="llm_provider_error",
        regex=r"Error: Provider.*nicht unterstuetzt|LLM Fehler",
        component="base_agent._call_llm",
        suggestion="Provider-Branch in _call_llm prüfen, fehlende Providers ergänzen",
        severity="high",
    ),
    ErrorPattern(
        name="blackboard_key_expired",
        regex=r"Blackboard.*abgelaufene.*Eintr|clear_expired.*[1-9]",
        component="memory.agent_blackboard",
        suggestion="TTL-Werte für häufig ablaufende Blackboard-Einträge erhöhen",
        severity="low",
    ),
    ErrorPattern(
        name="smtp_connection_failed",
        regex=r"SMTP.*[Ff]ehler|SMTPException|Connection refused.*smtp",
        component="utils.smtp_email",
        suggestion="SMTP-Retry-Logik und Verbindungs-Guard einbauen",
        severity="medium",
    ),
    ErrorPattern(
        name="tool_import_error",
        regex=r"ModuleNotFoundError|ImportError.*tool",
        component="tool_registry",
        suggestion="Fehlende Dependency in requirements-ci.txt ergänzen",
        severity="high",
    ),
    ErrorPattern(
        name="narrative_synthesis_empty",
        regex=r"Narrative.*leer|narrative.*empty|0 W.rter",
        component="deep_research.tool._create_narrative",
        suggestion="Narrative-Fallback-Schwelle prüfen oder LLM-Prompt verbessern",
        severity="medium",
    ),
    ErrorPattern(
        name="executor_fallback_triggered",
        regex=r"trending deutschland|Fallback.*executor|executor.*fallback",
        component="agent.agents.executor",
        suggestion="Query-Extraktion oder topic_recall-Fallback im Executor prüfen",
        severity="medium",
    ),
]


# ── Datenstruktur ──────────────────────────────────────────────────────────────

@dataclass
class HardeningProposal:
    pattern_name: str
    component: str
    suggestion: str
    severity: str
    occurrences: int
    sample_lines: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)

    def as_goal_title(self) -> str:
        return f"Harden: {self.component} ({self.occurrences}× erkannt)"

    def as_telegram_msg(self) -> str:
        sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(self.severity, "⚪")
        lines = [
            f"{sev_emoji} *Härtungs-Vorschlag: {self.component}*",
            f"Muster: `{self.pattern_name}`",
            f"Häufigkeit: {self.occurrences}× in letzten Logs",
            f"Empfehlung: {self.suggestion}",
        ]
        if self.sample_lines:
            lines.append(f"Beispiel: `{self.sample_lines[0][:120]}`")
        return "\n".join(lines)


# ── Engine ─────────────────────────────────────────────────────────────────────

class SelfHardeningEngine:
    """
    Analysiert Logs und Blackboard — erzeugt Härtungs-Proposals bei
    wiederkehrenden Fehlern oder Ungenauigkeiten.
    """

    def __init__(self) -> None:
        self._known_proposals: Dict[str, str] = {}  # pattern_name → created_at
        self._load_cooldown_from_blackboard()

    def _load_cooldown_from_blackboard(self) -> None:
        """Lädt persistierte Cooldown-Timestamps aus dem Blackboard (restart-fest)."""
        try:
            from memory.agent_blackboard import get_blackboard
            bb = get_blackboard()
            entries = bb.search(topic_prefix="hardening:cooldown") or []
            for entry in entries:
                pattern_name = entry.get("key", "")
                val = entry.get("value") or {}
                ts = val.get("created_at") if isinstance(val, dict) else None
                if pattern_name and ts:
                    self._known_proposals[pattern_name] = ts
            if self._known_proposals:
                log.debug("SelfHardening: %d Cooldowns aus Blackboard geladen", len(self._known_proposals))
        except Exception as e:
            log.debug("Cooldown-Restore fehlgeschlagen: %s", e)

    def _read_journal(self) -> List[str]:
        """Liest letzte N WARNING/ERROR Zeilen aus allen konfigurierten systemd-Units."""
        lines: List[str] = []
        for unit in _JOURNAL_UNITS:
            try:
                result = subprocess.run(
                    [
                        "journalctl", "-u", unit,
                        "--no-pager", "-n", str(_JOURNAL_LINES),
                        "--output=short",
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    lines.extend(
                        l for l in result.stdout.splitlines()
                        if "WARNING" in l or "ERROR" in l or "CRITICAL" in l
                    )
            except Exception as e:
                log.debug("Journal lesen fehlgeschlagen (%s): %s", unit, e)
        return lines

    def _read_blackboard_incidents(self) -> List[str]:
        """Liest incident:* und error:* Einträge aus dem Blackboard."""
        try:
            from memory.agent_blackboard import get_blackboard
            bb = get_blackboard()
            incidents = bb.search(topic_prefix="incident") or []
            errors = bb.search(topic_prefix="error") or []
            lines = []
            for entry in incidents + errors:
                val = entry.get("value") or entry.get("data") or ""
                if isinstance(val, dict):
                    val = str(val.get("message") or val.get("error") or val)
                lines.append(str(val))
            return lines
        except Exception as e:
            log.debug("Blackboard-Incidents lesen fehlgeschlagen: %s", e)
        return []

    def _match_patterns(self, log_lines: List[str]) -> List[HardeningProposal]:
        """Gruppiert Log-Zeilen nach bekannten Fehler-Patterns."""
        counts: Dict[str, List[str]] = {p.name: [] for p in _PATTERNS}

        for line in log_lines:
            for pattern in _PATTERNS:
                if re.search(pattern.regex, line, re.IGNORECASE):
                    counts[pattern.name].append(line.strip()[:160])

        proposals = []
        for pattern in _PATTERNS:
            hits = counts[pattern.name]
            if len(hits) < _MIN_OCCURRENCES:
                continue
            proposals.append(HardeningProposal(
                pattern_name=pattern.name,
                component=pattern.component,
                suggestion=pattern.suggestion,
                severity=pattern.severity,
                occurrences=len(hits),
                sample_lines=hits[:3],
            ))
        proposals.sort(key=lambda p: {"high": 0, "medium": 1, "low": 2}.get(p.severity, 3))
        return proposals

    def _already_proposed_recently(self, pattern_name: str) -> bool:
        """Verhindert dass derselbe Vorschlag zu oft wiederholt wird."""
        if pattern_name not in self._known_proposals:
            return False
        try:
            last = datetime.fromisoformat(self._known_proposals[pattern_name])
            delta_h = (datetime.now() - last).total_seconds() / 3600
            return delta_h < _GOAL_COOLDOWN_H
        except Exception:
            return False

    def _write_to_blackboard(self, proposal: HardeningProposal) -> None:
        try:
            from memory.agent_blackboard import get_blackboard
            bb = get_blackboard()
            # Proposal-Daten
            bb.write(
                agent="self_hardening",
                topic=f"hardening:{proposal.pattern_name}",
                key=proposal.pattern_name,
                value=proposal.to_dict(),
                ttl=_BLACKBOARD_TTL,
            )
            # Cooldown persistieren (TTL = Cooldown + 1h Puffer)
            cooldown_ttl = _GOAL_COOLDOWN_H * 3600 + 3600
            bb.write(
                agent="self_hardening",
                topic=f"hardening:cooldown:{proposal.pattern_name}",
                key=proposal.pattern_name,
                value={"created_at": proposal.created_at, "pattern": proposal.pattern_name},
                ttl=cooldown_ttl,
            )
        except Exception as e:
            log.debug("Blackboard write fehlgeschlagen: %s", e)

    def _create_hardening_goal(self, proposal: HardeningProposal) -> None:
        try:
            from orchestration.task_queue import get_queue
            queue = get_queue()
            title = proposal.as_goal_title()
            # Kein Duplikat anlegen wenn ähnliches Ziel bereits offen ist.
            # Goals kennen ACTIVE/BLOCKED/COMPLETED/CANCELLED — kein pending/in_progress.
            active = queue.list_goals(status="active") or []
            blocked = queue.list_goals(status="blocked") or []
            for g in active + blocked:
                if proposal.component in (g.get("title") or ""):
                    log.debug("Härtungs-Ziel bereits vorhanden: %s", title)
                    return
            queue.create_goal(
                title=title,
                description=f"Härtungs-Vorschlag (automatisch erkannt):\n{proposal.suggestion}\n\n"
                            f"Muster: {proposal.pattern_name} — {proposal.occurrences}× aufgetreten",
                priority_score={"high": 0.85, "medium": 0.65, "low": 0.45}.get(proposal.severity, 0.5),
                source="self_hardening",
            )
            log.info("Härtungs-Ziel angelegt: %s", title)
        except Exception as e:
            log.warning("Härtungs-Ziel erstellen fehlgeschlagen: %s", e)

    def _notify_telegram(self, proposal: HardeningProposal) -> None:
        try:
            import asyncio
            from utils.telegram_notify import send_telegram
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(send_telegram(proposal.as_telegram_msg()))
            else:
                loop.run_until_complete(send_telegram(proposal.as_telegram_msg()))
        except Exception as e:
            log.debug("Telegram-Notify fehlgeschlagen: %s", e)

    def run_cycle(self) -> Dict:
        """
        Haupt-Analysezyklus: Logs lesen → Patterns matchen → Proposals erzeugen.
        Gibt Zusammenfassung zurück.
        """
        log_lines = self._read_journal()
        bb_lines = self._read_blackboard_incidents()
        all_lines = log_lines + bb_lines

        if not all_lines:
            log.debug("SelfHardeningEngine: Keine Log-Daten verfügbar")
            return {"proposals": 0, "skipped": 0}

        proposals = self._match_patterns(all_lines)
        new_count = 0
        skipped = 0

        for proposal in proposals:
            if self._already_proposed_recently(proposal.pattern_name):
                skipped += 1
                log.debug("Härtungs-Proposal übersprungen (Cooldown): %s", proposal.pattern_name)
                continue

            log.warning(
                "🔧 Härtungs-Bedarf erkannt: %s (%d× in Logs) — %s",
                proposal.component,
                proposal.occurrences,
                proposal.suggestion,
            )
            self._write_to_blackboard(proposal)
            self._create_hardening_goal(proposal)
            self._notify_telegram(proposal)
            self._known_proposals[proposal.pattern_name] = proposal.created_at
            new_count += 1

        return {"proposals": new_count, "skipped": skipped, "total_patterns": len(proposals)}


# ── Singleton ──────────────────────────────────────────────────────────────────

_engine_instance: Optional[SelfHardeningEngine] = None


def get_self_hardening_engine() -> SelfHardeningEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = SelfHardeningEngine()
    return _engine_instance
