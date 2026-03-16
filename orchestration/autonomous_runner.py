"""
orchestration/autonomous_runner.py

Verbindet den ProactiveScheduler mit run_agent().
Bei jedem Heartbeat werden pending Tasks aus der SQLite-Queue autonom ausgeführt.
"""

import asyncio
import io
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta
from typing import Optional

from orchestration.scheduler import ProactiveScheduler, SchedulerEvent, init_scheduler
from orchestration.self_hardening_runtime import record_self_hardening_event
from orchestration.task_queue import Priority, TaskType, get_queue
from utils.stable_hash import stable_text_digest

log = logging.getLogger("AutonomousRunner")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _parse_iso(value: object) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _parse_task_metadata(raw_metadata: object) -> dict:
    if isinstance(raw_metadata, dict):
        return dict(raw_metadata)
    if isinstance(raw_metadata, str):
        text = raw_metadata.strip()
        if not text:
            return {}
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            return {}
    return {}


def _build_incident_notification_key(description: str, metadata: dict) -> str:
    incident_key = str((metadata or {}).get("incident_key") or "").strip()
    if incident_key:
        return incident_key
    template = str((metadata or {}).get("playbook_template") or "").strip()
    component = str((metadata or {}).get("component") or "").strip()
    signal = str((metadata or {}).get("signal") or "").strip()
    parts = [part for part in [template, component, signal, description.strip()] if part]
    fingerprint_basis = " | ".join(parts) if parts else "autonomous-incident"
    return f"derived:{stable_text_digest(fingerprint_basis, hex_chars=24)}"


def _incident_notification_state_key(notification_key: str) -> str:
    clean = (notification_key or "").strip().lower()
    return f"incident_notify:{clean}"


def _incident_quarantine_state_key(incident_key: str) -> str:
    clean = (incident_key or "").strip().lower()
    return f"incident_quarantine:{clean}"


def _resource_guard_state_key() -> str:
    return "resource_guard"


def _incident_notification_cooldown_active(
    *,
    last_sent_at: object,
    now: datetime,
    cooldown_minutes: int,
) -> bool:
    if cooldown_minutes <= 0:
        return False
    last_sent_dt = _parse_iso(last_sent_at)
    if last_sent_dt is None:
        return False
    return now < (last_sent_dt + timedelta(minutes=max(0, int(cooldown_minutes))))


def _goals_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_GOALS_ENABLED", False)


def _planning_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_PLANNING_ENABLED", False)


def _replanning_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_REPLANNING_ENABLED", False)


def _self_healing_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_SELF_HEALING_ENABLED", False)


def _policy_gates_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_POLICY_GATES_STRICT", False) or _env_bool("AUTONOMY_AUDIT_DECISIONS_ENABLED", False)


def _scorecard_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_SCORECARD_ENABLED", False)


def _hardening_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_HARDENING_ENABLED", False)


def _audit_report_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_REPORT_ENABLED", False)


def _audit_change_requests_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", False)


def _meta_analysis_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_META_ANALYSIS_ENABLED", False)


def _reflection_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_REFLECTION_ENABLED", False)


def _trigger_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_PROACTIVE_TRIGGERS_ENABLED", False)


def _goal_queue_feature_enabled() -> bool:
    # sofort aktiv (nutzt bestehende Tabellen), COMPAT_MODE respected
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_GOAL_QUEUE_ENABLED", True)


def _improvement_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_SELF_IMPROVEMENT_ENABLED", False)


def _self_modify_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_SELF_MODIFY_ENABLED", False)


def _ambient_context_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AMBIENT_CONTEXT_ENABLED", True)


def _m16_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_M16_ENABLED", False)


def _m14_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_M14_ENABLED", False)


def _m13_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_M13_ENABLED", False)


def _self_hardening_feature_enabled() -> bool:
    return _env_bool("AUTONOMY_SELF_HARDENING_ENABLED", False)


class AutonomousRunner:
    """
    Führt pending Tasks autonom aus, ausgelöst durch den Scheduler-Heartbeat.
    Läuft im Hintergrund parallel zur CLI-Schleife.
    Tasks werden nach Priorität abgearbeitet (CRITICAL zuerst).
    """

    def __init__(self, interval_minutes: int = 15):
        self.interval_minutes = interval_minutes
        self._scheduler: Optional[ProactiveScheduler] = None
        self._tools_desc: Optional[str] = None
        self._running = False
        self._work_signal: asyncio.Event = asyncio.Event()
        self._curiosity_engine = None
        self._goal_generator = None
        self._long_term_planner = None
        self._commitment_review_engine = None
        self._replanning_engine = None
        self._self_healing_engine = None
        self._meta_analyzer = None
        self._heartbeat_count = 0
        # M8–M12
        self._reflection_loop = None
        self._trigger_engine = None
        self._goal_manager = None
        self._improvement_engine = None
        self._self_modifier_engine = None
        # M15
        self._ambient_engine = None
        # M16
        self._feedback_engine = None

    def _incident_notification_context(self, task_id: str, description: str, metadata: dict) -> Optional[dict]:
        metadata_payload = metadata if isinstance(metadata, dict) else {}
        is_self_healing = bool(metadata_payload.get("self_healing")) or description.startswith("Self-Healing Playbook")
        if not is_self_healing:
            return None

        notification_key = _build_incident_notification_key(description, metadata_payload)
        incident_key = str(metadata_payload.get("incident_key") or notification_key).strip()
        component = str(metadata_payload.get("component") or "unknown").strip() or "unknown"
        signal = str(metadata_payload.get("signal") or "unknown_signal").strip() or "unknown_signal"
        playbook_template = str(metadata_payload.get("playbook_template") or "").strip()
        return {
            "task_id": task_id,
            "incident_key": incident_key,
            "notification_key": notification_key,
            "state_key": _incident_notification_state_key(notification_key),
            "component": component,
            "signal": signal,
            "playbook_template": playbook_template,
            "description": description,
        }

    def _self_healing_task_context(self, task_id: str, description: str, metadata: dict) -> Optional[dict]:
        context = self._incident_notification_context(task_id, description, metadata)
        if context is None:
            return None
        breaker_key = f"{context['component']}:{context['signal']}"
        context["breaker_key"] = breaker_key
        context["quarantine_state_key"] = _incident_quarantine_state_key(context["incident_key"])
        return context

    def _self_healing_quarantine_decision(self, queue, task_id: str, description: str, metadata: dict) -> Optional[dict]:
        context = self._self_healing_task_context(task_id, description, metadata)
        if context is None:
            return None

        breaker = queue.get_self_healing_circuit_breaker(context["breaker_key"]) or {}
        if str(breaker.get("state") or "") != "open":
            return None

        opened_until = _parse_iso(breaker.get("opened_until"))
        now = datetime.now()
        if opened_until is None or now >= opened_until:
            return None

        current = queue.get_self_healing_runtime_state(context["quarantine_state_key"]) or {}
        current_meta = current.get("metadata", {}) or {}
        quarantine_count = int(current_meta.get("quarantine_count", 0) or 0) + 1
        context.update(
            {
                "breaker": breaker,
                "current_quarantine_state": current,
                "current_quarantine_meta": current_meta,
                "quarantine_until": opened_until.isoformat(),
                "quarantine_count": quarantine_count,
                "reason": "breaker_open",
                "now": now,
            }
        )
        return context

    def _record_self_healing_quarantine_state(self, queue, context: dict) -> None:
        queue.set_self_healing_runtime_state(
            context["quarantine_state_key"],
            "active",
            metadata_update={
                "incident_key": context.get("incident_key", ""),
                "breaker_key": context.get("breaker_key", ""),
                "component": context.get("component", ""),
                "signal": context.get("signal", ""),
                "last_task_id": context.get("task_id", ""),
                "reason": context.get("reason", "breaker_open"),
                "quarantine_until": context.get("quarantine_until", ""),
                "quarantine_count": int(context.get("quarantine_count", 0) or 0),
                "open_incident": True,
            },
            observed_at=(context.get("now") or datetime.now()).isoformat(),
        )

    def _is_resource_heavy_task(self, description: str, target_agent: Optional[str], metadata: dict) -> bool:
        agent = str(target_agent or "").strip().lower()
        if agent in {"research", "visual", "creative", "development", "data", "document", "self_modify"}:
            return True

        text = f"{description} {json.dumps(metadata or {}, ensure_ascii=True)}".lower()
        heavy_markers = (
            "deep research",
            "recherche",
            "browser",
            "booking.com",
            "screenshot",
            "pdf",
            "bericht",
            "video",
            "youtube",
            "scrape",
            "crawl",
        )
        return any(marker in text for marker in heavy_markers)

    def _resource_guard_decision(self, queue, *, task_id: str, description: str, priority: int, target_agent: Optional[str], metadata: dict) -> Optional[dict]:
        if int(priority) <= int(Priority.HIGH):
            return None
        if not self._is_resource_heavy_task(description, target_agent, metadata):
            return None

        now = datetime.now()
        reasons: list[str] = []
        degrade_state = queue.get_self_healing_runtime_state("degrade_mode") or {}
        degrade_mode = str(degrade_state.get("state_value", "normal") or "normal")
        if degrade_mode in {"degraded", "emergency"}:
            reasons.append(f"degrade_mode={degrade_mode}")

        for incident_key in ("m3_system_pressure", "m3_queue_backlog"):
            incident = queue.get_self_healing_incident(incident_key)
            if incident and str(incident.get("status") or "") == "open":
                reasons.append(incident_key)

        if not reasons:
            return None

        defer_minutes = max(1, _env_int("AUTONOMY_RESOURCE_GUARD_DEFER_MINUTES", 20))
        run_at = (now + timedelta(minutes=defer_minutes)).isoformat()
        return {
            "task_id": task_id,
            "reason": ",".join(reasons),
            "reasons": reasons,
            "defer_minutes": defer_minutes,
            "run_at": run_at,
            "now": now,
        }

    def _record_resource_guard_state(self, queue, context: dict) -> None:
        queue.set_self_healing_runtime_state(
            _resource_guard_state_key(),
            "active",
            metadata_update={
                "last_task_id": context.get("task_id", ""),
                "reason": context.get("reason", ""),
                "reasons": list(context.get("reasons", []) or []),
                "defer_minutes": int(context.get("defer_minutes", 0) or 0),
                "deferred_until": context.get("run_at", ""),
                "updated_from": "autonomous_runner",
            },
            observed_at=(context.get("now") or datetime.now()).isoformat(),
        )

    def _notification_guard_decision(self, queue, task_id: str, description: str, metadata: dict) -> Optional[dict]:
        context = self._incident_notification_context(task_id, description, metadata)
        if context is None:
            return None

        cooldown_minutes = max(0, _env_int("AUTONOMY_INCIDENT_NOTIFICATION_COOLDOWN_MINUTES", 120))
        now = datetime.now()
        current = queue.get_self_healing_runtime_state(context["state_key"]) or {}
        current_meta = current.get("metadata", {}) or {}
        cooldown_active = _incident_notification_cooldown_active(
            last_sent_at=current_meta.get("last_sent_at"),
            now=now,
            cooldown_minutes=cooldown_minutes,
        )
        context.update(
            {
                "current_state": current,
                "current_meta": current_meta,
                "cooldown_minutes": cooldown_minutes,
                "now": now,
                "send": not cooldown_active,
                "reason": "cooldown_active" if cooldown_active else "allowed",
            }
        )
        return context

    def _record_incident_notification_state(
        self,
        queue,
        context: dict,
        *,
        state_value: str,
        telegram_sent: bool,
        email_sent: bool,
        result_preview: str,
        suppression_reason: str = "",
    ) -> None:
        current_meta = dict((context or {}).get("current_meta", {}) or {})
        now = context.get("now") if isinstance(context.get("now"), datetime) else datetime.now()
        sent_count = int(current_meta.get("sent_count", 0) or 0)
        suppressed_count = int(current_meta.get("suppressed_count", 0) or 0)
        if state_value == "sent":
            sent_count += 1
        elif state_value == "cooldown_active":
            suppressed_count += 1

        channels = []
        if telegram_sent:
            channels.append("telegram")
        if email_sent:
            channels.append("email")

        last_sent_at = current_meta.get("last_sent_at")
        cooldown_until = current_meta.get("cooldown_until")
        if state_value == "sent":
            last_sent_at = now.isoformat()
            cooldown_until = (now + timedelta(minutes=int(context.get("cooldown_minutes", 0) or 0))).isoformat()

        queue.set_self_healing_runtime_state(
            context["state_key"],
            state_value,
            metadata_update={
                "incident_key": context.get("incident_key", ""),
                "notification_key": context.get("notification_key", ""),
                "component": context.get("component", ""),
                "signal": context.get("signal", ""),
                "playbook_template": context.get("playbook_template", ""),
                "last_task_id": context.get("task_id", ""),
                "last_description": context.get("description", "")[:240],
                "last_result_preview": result_preview[:280],
                "last_channels": channels,
                "last_sent_at": last_sent_at,
                "cooldown_until": cooldown_until,
                "cooldown_minutes": int(context.get("cooldown_minutes", 0) or 0),
                "sent_count": sent_count,
                "suppressed_count": suppressed_count,
                "suppression_reason": suppression_reason,
                "open_incident": True,
            },
            observed_at=now.isoformat(),
        )

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    async def start(self, tools_desc: str) -> None:
        """Startet den Runner mit gecachten Tool-Beschreibungen."""
        self._tools_desc = tools_desc
        self._running = True

        # Migration beim ersten Start: tasks.json → SQLite
        self._run_migration()

        self._scheduler = init_scheduler(
            interval_minutes=self.interval_minutes,
            on_wake=self._on_wake_sync,
        )
        await self._scheduler.start()

        asyncio.create_task(self._worker_loop(), name="autonomous-worker")
        log.info(f"AutonomousRunner gestartet (Intervall: {self.interval_minutes} min)")

        # Goal-Generator hinter Feature-Flags starten (M1.2)
        if _goals_feature_enabled():
            try:
                from orchestration.goal_generator import GoalGenerator

                self._goal_generator = GoalGenerator(queue=get_queue())
                log.info("🎯 GoalGenerator aktiviert")
            except Exception as e:
                log.warning("GoalGenerator konnte nicht gestartet werden: %s", e)

        # Long-Term-Planung hinter Feature-Flags starten (M2.1)
        if _planning_feature_enabled():
            try:
                from orchestration.long_term_planner import LongTermPlanner

                self._long_term_planner = LongTermPlanner(queue=get_queue())
                log.info("🗓️ LongTermPlanner aktiviert")
            except Exception as e:
                log.warning("LongTermPlanner konnte nicht gestartet werden: %s", e)

            try:
                from orchestration.commitment_review_engine import CommitmentReviewEngine

                self._commitment_review_engine = CommitmentReviewEngine(queue=get_queue())
                log.info("📋 CommitmentReviewEngine aktiviert")
            except Exception as e:
                log.warning("CommitmentReviewEngine konnte nicht gestartet werden: %s", e)

        # Replanning hinter Feature-Flags starten (M2.2)
        if _replanning_feature_enabled():
            try:
                from orchestration.replanning_engine import ReplanningEngine

                self._replanning_engine = ReplanningEngine(queue=get_queue())
                log.info("🔁 ReplanningEngine aktiviert")
            except Exception as e:
                log.warning("ReplanningEngine konnte nicht gestartet werden: %s", e)

        # Self-Healing hinter Feature-Flags starten (M3.1)
        if _self_healing_feature_enabled():
            try:
                from orchestration.self_healing_engine import SelfHealingEngine

                self._self_healing_engine = SelfHealingEngine(queue=get_queue())
                log.info("🛠️ SelfHealingEngine aktiviert")
            except Exception as e:
                log.warning("SelfHealingEngine konnte nicht gestartet werden: %s", e)

        # Meta-Analyzer hinter Feature-Flag starten (Schicht 3)
        if _meta_analysis_feature_enabled():
            try:
                from orchestration.meta_analyzer import MetaAnalyzer

                self._meta_analyzer = MetaAnalyzer(queue=get_queue())
                log.info("🔬 MetaAnalyzer aktiviert")
            except Exception as e:
                log.warning("MetaAnalyzer konnte nicht gestartet werden: %s", e)

        # M8: Session Reflection Loop
        if _reflection_feature_enabled():
            try:
                from orchestration.session_reflection import SessionReflectionLoop
                self._reflection_loop = SessionReflectionLoop()
                log.info("🪞 SessionReflectionLoop aktiviert")
            except Exception as e:
                log.warning("SessionReflectionLoop konnte nicht gestartet werden: %s", e)

        # M9: Agent Blackboard (immer initialisieren für cleanup)
        if os.getenv("AUTONOMY_BLACKBOARD_ENABLED", "true").lower() == "true":
            try:
                from memory.agent_blackboard import get_blackboard
                get_blackboard()  # Singleton initialisieren + Tabellen anlegen
                log.info("📋 Agent Blackboard aktiviert")
            except Exception as e:
                log.warning("Agent Blackboard konnte nicht initialisiert werden: %s", e)

        # M10: Proactive Triggers
        if _trigger_feature_enabled():
            try:
                from orchestration.proactive_triggers import get_trigger_engine
                self._trigger_engine = get_trigger_engine()
                log.info("⏰ ProactiveTriggerEngine aktiviert")
            except Exception as e:
                log.warning("ProactiveTriggerEngine konnte nicht gestartet werden: %s", e)

        # M11: Goal Queue Manager
        if _goal_queue_feature_enabled():
            try:
                from orchestration.goal_queue_manager import get_goal_manager
                self._goal_manager = get_goal_manager()
                log.info("🎯 GoalQueueManager aktiviert")
            except Exception as e:
                log.warning("GoalQueueManager konnte nicht gestartet werden: %s", e)

        # M12: Self-Improvement Engine
        if _improvement_feature_enabled():
            try:
                from orchestration.self_improvement_engine import get_improvement_engine
                self._improvement_engine = get_improvement_engine()
                log.info("🔬 SelfImprovementEngine aktiviert")
            except Exception as e:
                log.warning("SelfImprovementEngine konnte nicht gestartet werden: %s", e)

        if _self_modify_feature_enabled():
            try:
                from orchestration.self_modifier_engine import get_self_modifier_engine

                self._self_modifier_engine = get_self_modifier_engine()
                log.info("🛠️ SelfModifierEngine aktiviert")
            except Exception as e:
                log.warning("SelfModifierEngine konnte nicht gestartet werden: %s", e)

        # M15: Ambient Context Engine
        if _ambient_context_feature_enabled():
            try:
                from orchestration.ambient_context_engine import get_ambient_engine
                self._ambient_engine = get_ambient_engine()
                log.info("🌐 AmbientContextEngine aktiviert")
            except Exception as e:
                log.warning("AmbientContextEngine konnte nicht gestartet werden: %s", e)

        # M16: Feedback Engine
        if _m16_feature_enabled():
            try:
                from orchestration.feedback_engine import get_feedback_engine
                self._feedback_engine = get_feedback_engine()
                log.info("🧠 FeedbackEngine (M16) aktiviert")
            except Exception as e:
                log.warning("FeedbackEngine konnte nicht gestartet werden: %s", e)

        # Curiosity Engine als separaten asyncio.Task starten
        if os.getenv("CURIOSITY_ENABLED", "true").lower() == "true":
            try:
                from orchestration.curiosity_engine import CuriosityEngine
                self._curiosity_engine = CuriosityEngine(telegram_app=None)
                asyncio.create_task(
                    self._curiosity_engine._curiosity_loop(),
                    name="curiosity-engine",
                )
                log.info("🔍 Curiosity Engine gestartet")
            except Exception as e:
                log.warning("Curiosity Engine konnte nicht gestartet werden: %s", e)

    async def stop(self) -> None:
        """Stoppt den Runner."""
        self._running = False
        self._work_signal.set()  # Worker aus dem Warten wecken
        if self._scheduler:
            await self._scheduler.stop()
        log.info("AutonomousRunner gestoppt")

    async def trigger_now(self) -> None:
        """Manueller Heartbeat — sofort ausführen."""
        if self._scheduler:
            await self._scheduler.trigger_manual_heartbeat()

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _run_migration(self) -> None:
        """Importiert tasks.json in SQLite falls noch nicht geschehen."""
        try:
            from orchestration.task_queue import migrate_from_json
            n = migrate_from_json(get_queue())
            if n:
                log.info(f"Migration: {n} Tasks aus tasks.json übernommen")
        except Exception as e:
            log.warning(f"Migration übersprungen: {e}")

    # ------------------------------------------------------------------
    # Scheduler-Callback
    # ------------------------------------------------------------------

    def _on_wake_sync(self, event: SchedulerEvent) -> None:
        """Wird vom Scheduler aufgerufen. Signalisiert dem Worker neue Arbeit."""
        self._heartbeat_count += 1
        queue = get_queue()

        if self._self_healing_engine and _self_healing_feature_enabled():
            try:
                healing_summary = self._self_healing_engine.run_cycle()
                if healing_summary.get("status") == "ok" and (
                    healing_summary.get("incidents_opened", 0)
                    or healing_summary.get("incidents_reopened", 0)
                    or healing_summary.get("incidents_resolved", 0)
                    or healing_summary.get("incidents_escalated", 0)
                    or healing_summary.get("circuit_breaker_trips", 0)
                    or healing_summary.get("playbooks_suppressed", 0)
                    or healing_summary.get("playbook_attempts_blocked", 0)
                    or healing_summary.get("degrade_mode_changed", False)
                ):
                    log.info(
                        "🛠️ Heartbeat Self-Healing: opened=%s reopened=%s resolved=%s escalated=%s playbooks=%s suppressed=%s attempts_blocked=%s trips=%s degrade=%s reason=%s",
                        healing_summary.get("incidents_opened", 0),
                        healing_summary.get("incidents_reopened", 0),
                        healing_summary.get("incidents_resolved", 0),
                        healing_summary.get("incidents_escalated", 0),
                        healing_summary.get("playbooks_triggered", 0),
                        healing_summary.get("playbooks_suppressed", 0),
                        healing_summary.get("playbook_attempts_blocked", 0),
                        healing_summary.get("circuit_breaker_trips", 0),
                        healing_summary.get("degrade_mode", "normal"),
                        healing_summary.get("degrade_reason", ""),
                    )
            except Exception as e:
                log.warning("Self-Healing-Zyklus fehlgeschlagen: %s", e)

        if self._goal_generator and _goals_feature_enabled():
            try:
                generated = self._goal_generator.run_cycle(max_goals=3)
                if generated:
                    log.info("🎯 Heartbeat: %d Ziel-Signal(e) verarbeitet", len(generated))
            except Exception as e:
                log.warning("GoalGenerator-Zyklus fehlgeschlagen: %s", e)

        if self._long_term_planner and _planning_feature_enabled():
            try:
                planning_summary = self._long_term_planner.run_cycle()
                if planning_summary.get("status") == "ok":
                    log.info(
                        "🗓️ Heartbeat Planung: %s Planfenster | %s Commitments",
                        planning_summary.get("plans_touched", 0),
                        planning_summary.get("commitments_touched", 0),
                    )
            except Exception as e:
                log.warning("LongTermPlanner-Zyklus fehlgeschlagen: %s", e)

        if self._commitment_review_engine and _planning_feature_enabled():
            try:
                review_summary = self._commitment_review_engine.run_cycle()
                if review_summary.get("status") == "ok" and review_summary.get("reviews_due", 0):
                    log.info(
                        "📋 Heartbeat Reviews: due=%s | escalated=%s | replan_events=%s",
                        review_summary.get("reviews_due", 0),
                        review_summary.get("reviews_escalated", 0),
                        review_summary.get("replan_events_created", 0),
                    )
            except Exception as e:
                log.warning("CommitmentReview-Zyklus fehlgeschlagen: %s", e)

        if self._replanning_engine and _replanning_feature_enabled():
            try:
                replanning_summary = self._replanning_engine.run_cycle()
                if replanning_summary.get("status") == "ok" and replanning_summary.get("events_detected", 0):
                    log.info(
                        "🔁 Heartbeat Replanning: detected=%s | created=%s | actions=%s",
                        replanning_summary.get("events_detected", 0),
                        replanning_summary.get("events_created", 0),
                        replanning_summary.get("actions_applied", 0),
                    )
            except Exception as e:
                log.warning("Replanning-Zyklus fehlgeschlagen: %s", e)

        if _goals_feature_enabled():
            try:
                conflict_summary = queue.sync_goal_conflicts(auto_block=False, max_pairs=60)
                detected = int(conflict_summary.get("conflicts_detected", 0))
                if detected:
                    log.warning("⚠️ Goal-Konflikte erkannt: %d", detected)
            except Exception as e:
                log.warning("Goal-Konflikt-Sync fehlgeschlagen: %s", e)

            self._export_goal_kpi_snapshot()

        if _planning_feature_enabled():
            self._export_planning_kpi_snapshot()
            self._export_commitment_review_kpi_snapshot()
        if _replanning_feature_enabled():
            self._export_replanning_kpi_snapshot()
        if _self_healing_feature_enabled():
            self._export_self_healing_kpi_snapshot()
        if _policy_gates_feature_enabled():
            self._apply_policy_rollout_guard()
            self._export_policy_kpi_snapshot()
        scorecard = None
        if _scorecard_feature_enabled():
            scorecard = self._export_autonomy_scorecard_snapshot()
            e2e_gate = self._collect_e2e_release_gate_sync()
            ops_gate = self._collect_ops_release_gate_sync()
            self._apply_autonomy_scorecard_control(scorecard=scorecard, e2e_gate=e2e_gate, ops_gate=ops_gate)
        if _hardening_feature_enabled():
            self._evaluate_rollout_hardening(scorecard=scorecard)
        if _scorecard_feature_enabled():
            if _audit_report_feature_enabled():
                export_payload = self._export_autonomy_audit_report(scorecard=scorecard)
                if _audit_change_requests_feature_enabled() and isinstance(export_payload, dict):
                    self._apply_autonomy_audit_change_request(export_payload=export_payload)
        if _audit_change_requests_feature_enabled():
            self._apply_pending_autonomy_audit_change_requests()

        if self._meta_analyzer and _meta_analysis_feature_enabled():
            meta_interval = max(1, _env_int("AUTONOMY_META_ANALYSIS_INTERVAL_HEARTBEATS", 12))
            if self._heartbeat_count % meta_interval == 0:
                try:
                    meta_result = self._meta_analyzer.run_analysis()
                    insights = meta_result.get("insights") or {}
                    log.info(
                        "🔬 Meta-Analyse: trend=%s risk=%s insight=%s...",
                        insights.get("trend", "?"),
                        insights.get("risk_level", "?"),
                        str(insights.get("key_insight", "?"))[:80],
                    )
                except Exception as e:
                    log.warning("Meta-Analyse-Zyklus fehlgeschlagen: %s", e)

        # M8: Session Reflection Loop
        if _reflection_feature_enabled() and self._reflection_loop:
            try:
                _loop = asyncio.get_event_loop()
                if _loop.is_running():
                    asyncio.ensure_future(self._reflection_loop.check_and_reflect())
            except RuntimeError:
                pass
            except Exception as e:
                log.debug("SessionReflectionLoop fehlgeschlagen: %s", e)

        # M9: Blackboard — abgelaufene Einträge bereinigen
        if os.getenv("AUTONOMY_BLACKBOARD_ENABLED", "true").lower() == "true":
            try:
                from memory.agent_blackboard import get_blackboard
                expired = get_blackboard().clear_expired()
                if expired > 0:
                    log.debug("Blackboard: %d abgelaufene Einträge gelöscht", expired)
            except Exception as e:
                log.debug("Blackboard clear_expired fehlgeschlagen: %s", e)

        # M10: Proactive Triggers
        if _trigger_feature_enabled() and self._trigger_engine:
            try:
                fired = self._trigger_engine.check_and_fire()
                if fired:
                    log.info("⏰ %d Trigger ausgelöst", len(fired))
            except Exception as e:
                log.debug("ProactiveTriggers fehlgeschlagen: %s", e)

        # M11: Goal Queue Progress Rollup
        if _goal_queue_feature_enabled() and self._goal_manager:
            try:
                self._goal_manager.run_progress_cycle()
            except Exception as e:
                log.debug("GoalQueueManager Rollup fehlgeschlagen: %s", e)

        # M12: Self-Improvement Wochenanalyse
        if _improvement_feature_enabled() and self._improvement_engine:
            if self._improvement_engine._should_run_analysis():
                try:
                    _loop = asyncio.get_event_loop()
                    if _loop.is_running():
                        asyncio.ensure_future(self._improvement_engine.run_analysis_cycle())
                except RuntimeError:
                    pass
                except Exception as e:
                    log.debug("SelfImprovementEngine fehlgeschlagen: %s", e)

        if _self_modify_feature_enabled() and self._self_modifier_engine:
            try:
                modify_summary = self._self_modifier_engine.run_cycle()
                if modify_summary.get("status") == "enabled" and (
                    modify_summary.get("applied", 0)
                    or modify_summary.get("pending", 0)
                ):
                    log.info(
                        "🛠️ Heartbeat Self-Modify: applied=%s pending=%s max_per_cycle=%s",
                        modify_summary.get("applied", 0),
                        modify_summary.get("pending", 0),
                        modify_summary.get("max_per_cycle", 0),
                    )
            except Exception as e:
                log.debug("SelfModifierEngine fehlgeschlagen: %s", e)

        # M15: Ambient Context Engine
        if _ambient_context_feature_enabled() and self._ambient_engine:
            try:
                _loop = asyncio.get_event_loop()
                if _loop.is_running():
                    asyncio.ensure_future(self._ambient_engine.run_cycle())
            except RuntimeError:
                pass
            except Exception as e:
                log.debug("AmbientContextEngine fehlgeschlagen: %s", e)

        # M16: FeedbackEngine + Soul Hook Decay (täglich)
        if _m16_feature_enabled():
            # process_pending: heute gesendete Feedbacks zählen
            if self._feedback_engine:
                try:
                    count = self._feedback_engine.process_pending()
                    if count > 0:
                        log.debug("M16: %d Feedback-Events heute", count)
                except Exception as e:
                    log.debug("FeedbackEngine.process_pending fehlgeschlagen: %s", e)

            # Täglicher Hook-Decay (1× pro Tag)
            _daily_ticks = max(1, round(24 * 60 / self.interval_minutes))
            if self._heartbeat_count % _daily_ticks == 0:
                try:
                    from memory.soul_engine import get_soul_engine
                    changed = get_soul_engine().decay_hooks()
                    if changed > 0:
                        log.info("M16: Hook-Decay: %d Hooks angepasst", changed)
                except Exception as e:
                    log.debug("Hook-Decay fehlgeschlagen: %s", e)

        # M14: E-Mail-Autonomie — pending Approvals loggen
        if _m14_feature_enabled():
            try:
                from orchestration.email_autonomy_engine import get_email_autonomy_engine
                count = get_email_autonomy_engine().process_pending()
                if count > 0:
                    log.debug("M14: %d E-Mail-Approvals ausstehend", count)
            except Exception as e:
                log.debug("EmailAutonomyEngine.process_pending fehlgeschlagen: %s", e)

        # M18: Self-Hardening Engine — alle 5 Heartbeats Log + Blackboard analysieren
        if _self_hardening_feature_enabled() and self._heartbeat_count % 5 == 0:
            try:
                from orchestration.self_hardening_engine import get_self_hardening_engine
                hardening_summary = get_self_hardening_engine().run_cycle()
                if hardening_summary.get("proposals", 0) > 0:
                    log.info(
                        "🔧 M18 Self-Hardening: %d neue Vorschläge, %d übersprungen",
                        hardening_summary["proposals"],
                        hardening_summary.get("skipped", 0),
                    )
            except Exception as e:
                log.debug("SelfHardeningEngine fehlgeschlagen: %s", e)

        pending = queue.get_pending()
        if not pending:
            log.debug("Heartbeat: keine offenen Tasks")
            return
        log.info(f"Heartbeat: {len(pending)} offene Task(s) | Top-Priorität: {pending[0]['priority']}")
        self._work_signal.set()

    def _export_goal_kpi_snapshot(self) -> None:
        """Exportiert Goal-KPIs in Log + Canvas (falls vorhanden)."""
        try:
            queue = get_queue()
            metrics = queue.get_goal_alignment_metrics(include_conflicts=True)
            log.info(
                "🎯 Goal-KPI | open=%s/%s (%.2f%%) | conflicts=%s",
                metrics.get("open_aligned_tasks", 0),
                metrics.get("open_tasks", 0),
                float(metrics.get("open_alignment_rate", 0.0)),
                metrics.get("conflict_count", 0),
            )
        except Exception as e:
            log.debug("Goal-KPI Berechnung fehlgeschlagen: %s", e)
            return

        try:
            from orchestration.canvas_store import canvas_store

            items = canvas_store.list_canvases(limit=1).get("items", [])
            if not items:
                return
            canvas_id = str(items[0].get("id", ""))
            if not canvas_id:
                return
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="goal_kpi",
                status="info",
                message=(
                    "goal-alignment "
                    f"{metrics.get('open_aligned_tasks', 0)}/{metrics.get('open_tasks', 0)} "
                    f"({metrics.get('open_alignment_rate', 0.0)}%)"
                ),
                payload=metrics,
            )
        except Exception:
            # Canvas ist optional; fehlender Export darf den Runner nicht stoeren.
            return

    def _export_planning_kpi_snapshot(self) -> None:
        """Exportiert Planungsmetriken in Log + Canvas (falls vorhanden)."""
        try:
            queue = get_queue()
            metrics = queue.get_planning_metrics()
            log.info(
                "🗓️ Planning-KPI | active_plans=%s | commitments=%s | overdue=%s | deviation=%.2f",
                metrics.get("active_plans", 0),
                metrics.get("commitments_total", 0),
                metrics.get("overdue_commitments", 0),
                float(metrics.get("plan_deviation_score", 0.0)),
            )
        except Exception as e:
            log.debug("Planning-KPI Berechnung fehlgeschlagen: %s", e)
            return

        try:
            from orchestration.canvas_store import canvas_store

            items = canvas_store.list_canvases(limit=1).get("items", [])
            if not items:
                return
            canvas_id = str(items[0].get("id", ""))
            if not canvas_id:
                return
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="planning_kpi",
                status="info",
                message=(
                    "planning "
                    f"plans={metrics.get('active_plans', 0)} "
                    f"commitments={metrics.get('commitments_total', 0)} "
                    f"overdue={metrics.get('overdue_commitments', 0)} "
                    f"deviation={metrics.get('plan_deviation_score', 0.0)}"
                ),
                payload=metrics,
            )
        except Exception:
            return

    def _export_replanning_kpi_snapshot(self) -> None:
        """Exportiert Replanning-Metriken in Log + Canvas (falls vorhanden)."""
        try:
            queue = get_queue()
            metrics = queue.get_replanning_metrics()
            log.info(
                "🔁 Replanning-KPI | events=%s | last24h=%s | overdue_candidates=%s | top_prio=%.2f",
                metrics.get("events_total", 0),
                metrics.get("events_last_24h", 0),
                metrics.get("overdue_candidates", 0),
                float(metrics.get("top_priority_score", 0.0)),
            )
        except Exception as e:
            log.debug("Replanning-KPI Berechnung fehlgeschlagen: %s", e)
            return

        try:
            from orchestration.canvas_store import canvas_store

            items = canvas_store.list_canvases(limit=1).get("items", [])
            if not items:
                return
            canvas_id = str(items[0].get("id", ""))
            if not canvas_id:
                return
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="replanning_kpi",
                status="info",
                message=(
                    "replanning "
                    f"events={metrics.get('events_total', 0)} "
                    f"last24h={metrics.get('events_last_24h', 0)} "
                    f"overdue={metrics.get('overdue_candidates', 0)} "
                    f"top_prio={metrics.get('top_priority_score', 0.0)}"
                ),
                payload=metrics,
            )
        except Exception:
            return

    def _export_commitment_review_kpi_snapshot(self) -> None:
        """Exportiert Commitment-Review-Metriken in Log + Canvas (falls vorhanden)."""
        try:
            queue = get_queue()
            metrics = queue.get_commitment_review_metrics()
            log.info(
                "📋 Review-KPI | due=%s | scheduled=%s | escalated_7d=%s | avg_gap_7d=%.2f",
                metrics.get("due_reviews", 0),
                metrics.get("scheduled_reviews", 0),
                metrics.get("escalated_last_7d", 0),
                float(metrics.get("avg_gap_last_7d", 0.0)),
            )
        except Exception as e:
            log.debug("Review-KPI Berechnung fehlgeschlagen: %s", e)
            return

        try:
            from orchestration.canvas_store import canvas_store

            items = canvas_store.list_canvases(limit=1).get("items", [])
            if not items:
                return
            canvas_id = str(items[0].get("id", ""))
            if not canvas_id:
                return
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="commitment_review_kpi",
                status="info",
                message=(
                    "reviews "
                    f"due={metrics.get('due_reviews', 0)} "
                    f"scheduled={metrics.get('scheduled_reviews', 0)} "
                    f"escalated7d={metrics.get('escalated_last_7d', 0)} "
                    f"avg_gap7d={metrics.get('avg_gap_last_7d', 0.0)}"
                ),
                payload=metrics,
            )
        except Exception:
            return

    def _export_self_healing_kpi_snapshot(self) -> None:
        """Exportiert Self-Healing-Metriken in Log + Canvas (falls vorhanden)."""
        try:
            queue = get_queue()
            metrics = queue.get_self_healing_metrics()
            log.info(
                "🛠️ SelfHealing-KPI | mode=%s | open=%s | escalated_open=%s | max_open_age_min=%s | breakers_open=%s | created24h=%s | recovered24h=%s | recovery_rate24h=%.2f%%",
                metrics.get("degrade_mode", "normal"),
                metrics.get("open_incidents", 0),
                metrics.get("open_escalated_incidents", 0),
                metrics.get("max_open_incident_age_min", 0.0),
                metrics.get("circuit_breakers_open", 0),
                metrics.get("created_last_24h", 0),
                metrics.get("recovered_last_24h", 0),
                float(metrics.get("recovery_rate_24h", 0.0)),
            )
        except Exception as e:
            log.debug("SelfHealing-KPI Berechnung fehlgeschlagen: %s", e)
            return

        try:
            from orchestration.canvas_store import canvas_store

            items = canvas_store.list_canvases(limit=1).get("items", [])
            if not items:
                return
            canvas_id = str(items[0].get("id", ""))
            if not canvas_id:
                return
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="self_healing_kpi",
                status="info",
                message=(
                    "self-healing "
                    f"mode={metrics.get('degrade_mode', 'normal')} "
                    f"open={metrics.get('open_incidents', 0)} "
                    f"escalated_open={metrics.get('open_escalated_incidents', 0)} "
                    f"max_open_age_min={metrics.get('max_open_incident_age_min', 0.0)} "
                    f"breakers_open={metrics.get('circuit_breakers_open', 0)} "
                    f"created24h={metrics.get('created_last_24h', 0)} "
                    f"recovered24h={metrics.get('recovered_last_24h', 0)} "
                    f"recovery_rate24h={metrics.get('recovery_rate_24h', 0.0)}"
                ),
                payload=metrics,
            )
        except Exception:
            return

    def _export_policy_kpi_snapshot(self) -> None:
        """Exportiert Policy-Entscheidungsmetriken in Log + Canvas (falls vorhanden)."""
        try:
            from utils.policy_gate import get_policy_decision_metrics

            metrics = get_policy_decision_metrics(window_hours=24)
            log.info(
                "🛡️ Policy-KPI | decisions24h=%s | blocked24h=%s | observed24h=%s | strict24h=%s | canary_deferred24h=%s",
                metrics.get("decisions_total", 0),
                metrics.get("blocked_total", 0),
                metrics.get("observed_total", 0),
                metrics.get("strict_decisions", 0),
                metrics.get("canary_deferred_total", 0),
            )
        except Exception as e:
            log.debug("Policy-KPI Berechnung fehlgeschlagen: %s", e)
            return

        try:
            from orchestration.canvas_store import canvas_store

            items = canvas_store.list_canvases(limit=1).get("items", [])
            if not items:
                return
            canvas_id = str(items[0].get("id", ""))
            if not canvas_id:
                return
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="policy_kpi",
                status="info",
                message=(
                    "policy "
                    f"decisions24h={metrics.get('decisions_total', 0)} "
                    f"blocked24h={metrics.get('blocked_total', 0)} "
                    f"observed24h={metrics.get('observed_total', 0)} "
                    f"strict24h={metrics.get('strict_decisions', 0)} "
                    f"canary_deferred24h={metrics.get('canary_deferred_total', 0)}"
                ),
                payload=metrics,
            )
        except Exception:
            return

    def _apply_policy_rollout_guard(self) -> None:
        """Wendet bei Policy-Spikes automatische Rollback-Regeln an (M4.4)."""
        try:
            from utils.policy_gate import evaluate_and_apply_rollout_guard

            guard = evaluate_and_apply_rollout_guard()
            action = str(guard.get("action") or "none")
            if action in {"rollback_applied", "cooldown_active"}:
                log.warning(
                    "🛡️ Policy-Rollout-Guard: action=%s | blocked=%s/%s | rate=%s%%",
                    action,
                    guard.get("blocked_total", 0),
                    guard.get("decisions_total", 0),
                    guard.get("block_rate_pct", 0.0),
                )
        except Exception as e:
            log.debug("Policy-Rollout-Guard fehlgeschlagen: %s", e)

    def _export_autonomy_scorecard_snapshot(self) -> Optional[dict]:
        """Exportiert und persistiert den aggregierten Autonomie-Reifegrad (M5.3)."""
        try:
            from orchestration.autonomy_scorecard import build_autonomy_scorecard

            window_hours = max(1, int(os.getenv("AUTONOMY_SCORECARD_WINDOW_HOURS", "24")))
            queue = get_queue()
            scorecard = build_autonomy_scorecard(queue=queue, window_hours=window_hours)
            queue.record_autonomy_scorecard_snapshot(scorecard)
            trend = scorecard.get("trends", {}) if isinstance(scorecard.get("trends"), dict) else {}
            log.info(
                "🧭 Autonomy-Score | overall=%s/100 (%.2f/10) | level=%s | ready_9_10=%s | goals=%s planning=%s healing=%s policy=%s | trend24h=%.2f (%s)",
                scorecard.get("overall_score", 0.0),
                scorecard.get("overall_score_10", 0.0),
                scorecard.get("autonomy_level", "low"),
                scorecard.get("ready_for_very_high_autonomy", False),
                scorecard.get("pillars", {}).get("goals", {}).get("score", 0.0),
                scorecard.get("pillars", {}).get("planning", {}).get("score", 0.0),
                scorecard.get("pillars", {}).get("self_healing", {}).get("score", 0.0),
                scorecard.get("pillars", {}).get("policy", {}).get("score", 0.0),
                float(trend.get("trend_delta", 0.0) or 0.0),
                str(trend.get("trend_direction", "stable") or "stable"),
            )
        except Exception as e:
            log.debug("Autonomy-Scorecard Berechnung fehlgeschlagen: %s", e)
            return None

        try:
            from orchestration.canvas_store import canvas_store

            items = canvas_store.list_canvases(limit=1).get("items", [])
            if not items:
                return
            canvas_id = str(items[0].get("id", ""))
            if not canvas_id:
                return
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="autonomy_scorecard",
                status="info",
                message=(
                    "autonomy-score "
                    f"overall={scorecard.get('overall_score', 0.0)} "
                    f"level={scorecard.get('autonomy_level', 'low')} "
                    f"ready9_10={scorecard.get('ready_for_very_high_autonomy', False)}"
                ),
                payload=scorecard,
            )
        except Exception:
            return scorecard

        return scorecard

    async def _collect_e2e_release_gate(self) -> Optional[dict]:
        """Sammelt die aktuelle E2E-Release-Gate-Entscheidung fuer Runtime-Steuerung."""
        try:
            from orchestration.browser_workflow_eval import (
                BROWSER_WORKFLOW_EVAL_CASES,
                evaluate_browser_workflow_case,
            )
            from orchestration.e2e_regression_matrix import build_e2e_regression_matrix
            from orchestration.e2e_release_gate import evaluate_e2e_release_gate
            from gateway.status_snapshot import collect_status_snapshot
            from tools.email_tool.tool import get_email_status
            from orchestration.task_queue import get_queue

            queue = get_queue()
            canary_state = queue.get_policy_runtime_state("canary_percent_override")
            current_canary = int((canary_state or {}).get("state_value", 0) or 0)
            snapshot = await collect_status_snapshot()
            email_status = get_email_status()
            browser_results = [
                evaluate_browser_workflow_case(case)
                for case in BROWSER_WORKFLOW_EVAL_CASES
            ]
            matrix = build_e2e_regression_matrix(
                snapshot=snapshot,
                email_status=email_status,
                browser_eval_results=browser_results,
            )
            return evaluate_e2e_release_gate(matrix, current_canary_percent=current_canary)
        except Exception as e:
            log.debug("E2E-Release-Gate-Sammlung fehlgeschlagen: %s", e)
            return None

    async def _collect_ops_release_gate(self) -> Optional[dict]:
        """Sammelt die aktuelle Ops-/Budget-Gate-Entscheidung fuer Runtime-Steuerung."""
        try:
            from gateway.status_snapshot import collect_status_snapshot
            from orchestration.ops_release_gate import evaluate_ops_release_gate
            from orchestration.task_queue import get_queue

            queue = get_queue()
            canary_state = queue.get_policy_runtime_state("canary_percent_override")
            current_canary = int((canary_state or {}).get("state_value", 0) or 0)
            snapshot = await collect_status_snapshot()
            return evaluate_ops_release_gate(snapshot.get("ops", {}), current_canary_percent=current_canary)
        except Exception as e:
            log.debug("Ops-Release-Gate-Sammlung fehlgeschlagen: %s", e)
            return None

    def _collect_e2e_release_gate_sync(self) -> Optional[dict]:
        """Sync-Wrapper fuer den Scheduler-Callback."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                return asyncio.run(self._collect_e2e_release_gate())
            except RuntimeError as e:
                log.debug("E2E-Release-Gate Sync-Wrapper uebersprungen: %s", e)
                return None

        result_box: dict[str, Optional[dict]] = {"value": None}
        error_box: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result_box["value"] = asyncio.run(self._collect_e2e_release_gate())
            except BaseException as exc:  # pragma: no cover - defensive guard for thread handoff
                error_box["error"] = exc

        worker = threading.Thread(
            target=_runner,
            name="autonomous-runner-e2e-gate",
            daemon=True,
        )
        worker.start()
        worker.join(timeout=max(5, _env_int("AUTONOMY_E2E_GATE_SYNC_TIMEOUT_SEC", 30)))
        if worker.is_alive():
            log.warning("E2E-Release-Gate Sync-Wrapper Timeout nach %ss", max(5, _env_int("AUTONOMY_E2E_GATE_SYNC_TIMEOUT_SEC", 30)))
            return None
        if error_box:
            log.debug("E2E-Release-Gate Sync-Wrapper fehlgeschlagen: %s", error_box["error"])
            return None
        return result_box["value"]

    def _collect_ops_release_gate_sync(self) -> Optional[dict]:
        """Sync-Wrapper fuer das Ops-/Budget-Gate."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                return asyncio.run(self._collect_ops_release_gate())
            except RuntimeError as e:
                log.debug("Ops-Release-Gate Sync-Wrapper uebersprungen: %s", e)
                return None

        result_box: dict[str, Optional[dict]] = {"value": None}
        error_box: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result_box["value"] = asyncio.run(self._collect_ops_release_gate())
            except BaseException as exc:  # pragma: no cover - defensive guard for thread handoff
                error_box["error"] = exc

        worker = threading.Thread(
            target=_runner,
            name="autonomous-runner-ops-gate",
            daemon=True,
        )
        worker.start()
        worker.join(timeout=max(5, _env_int("AUTONOMY_OPS_GATE_SYNC_TIMEOUT_SEC", 30)))
        if worker.is_alive():
            log.warning("Ops-Release-Gate Sync-Wrapper Timeout nach %ss", max(5, _env_int("AUTONOMY_OPS_GATE_SYNC_TIMEOUT_SEC", 30)))
            return None
        if error_box:
            log.debug("Ops-Release-Gate Sync-Wrapper fehlgeschlagen: %s", error_box["error"])
            return None
        return result_box["value"]

    def _apply_autonomy_scorecard_control(
        self,
        *,
        scorecard: Optional[dict] = None,
        e2e_gate: Optional[dict] = None,
        ops_gate: Optional[dict] = None,
    ) -> None:
        """M5.2/M5.3: Scorecard-Control mit optional adaptiven Schwellen anwenden."""
        try:
            from orchestration.autonomy_scorecard import evaluate_and_apply_scorecard_control

            control = evaluate_and_apply_scorecard_control(
                scorecard=scorecard,
                e2e_gate_decision=e2e_gate,
                ops_gate_decision=ops_gate,
            )
            action = str(control.get("action") or "none")
            governance = control.get("governance") if isinstance(control.get("governance"), dict) else {}
            governance_state = str(governance.get("state", "allow") or "allow")
            if action in {
                "promote_canary",
                "rollback_applied",
                "cooldown_active",
                "governance_hold",
                "governance_force_rollback",
                "e2e_gate_hold",
                "e2e_gate_blocked",
                "ops_gate_hold",
                "ops_gate_blocked",
            }:
                log.warning(
                    "🧭 Scorecard-Control: action=%s | score=%s | canary=%s->%s | strict_off=%s | thresholds=%.1f/%.1f | adaptive=%s | governance=%s | e2e=%s | ops=%s",
                    action,
                    control.get("overall_score", 0.0),
                    control.get("current_canary_percent"),
                    control.get("next_canary_percent", control.get("current_canary_percent")),
                    control.get("strict_force_off", False),
                    float(control.get("promote_threshold", 0.0) or 0.0),
                    float(control.get("rollback_threshold", 0.0) or 0.0),
                    str(control.get("adaptive_mode", "off") or "off"),
                    governance_state,
                    str((control.get("e2e_gate") or {}).get("state", "pass")),
                    str((control.get("ops_gate") or {}).get("state", "pass")),
                )
        except Exception as e:
            log.debug("Autonomy-Scorecard-Control fehlgeschlagen: %s", e)

    def _evaluate_rollout_hardening(self, *, scorecard: Optional[dict] = None) -> None:
        """M7: Bewertet Hardening-/Rollout-Reife und wendet optional Schutzaktionen an."""
        try:
            from orchestration.autonomy_hardening_engine import evaluate_and_apply_rollout_hardening

            queue = get_queue()
            result = evaluate_and_apply_rollout_hardening(queue=queue, scorecard=scorecard)
            if result.get("status") != "ok":
                return
            state = str(result.get("state") or "green")
            action = str(result.get("action") or "none")
            reasons = result.get("reasons", []) if isinstance(result.get("reasons"), list) else []
            if state != "green" or action != "none":
                log.warning(
                    "🧱 Hardening | state=%s | action=%s | reasons=%s",
                    state,
                    action,
                    ",".join(str(r) for r in reasons[:5]),
                )
        except Exception as e:
            log.debug("Rollout-Hardening fehlgeschlagen: %s", e)

    def _export_autonomy_audit_report(self, *, scorecard: Optional[dict] = None) -> Optional[dict]:
        """M6.1: Exportiert periodisch einen Autonomy-Audit-Report."""
        try:
            from orchestration.autonomy_audit_report import (
                export_autonomy_audit_report,
                should_export_audit_report,
            )

            queue = get_queue()
            cadence_hours = max(1, int(os.getenv("AUTONOMY_AUDIT_REPORT_CADENCE_HOURS", "6")))
            should = should_export_audit_report(queue=queue, cadence_hours=cadence_hours)
            if not should.get("should_export", False):
                return None

            window_days = max(1, int(os.getenv("AUTONOMY_AUDIT_REPORT_WINDOW_DAYS", "7")))
            baseline_days = max(2, int(os.getenv("AUTONOMY_AUDIT_REPORT_BASELINE_DAYS", "30")))
            report_export = export_autonomy_audit_report(
                queue=queue,
                scorecard=scorecard,
                window_days=window_days,
                baseline_days=baseline_days,
            )
            recommendation = str(report_export.get("recommendation", "hold") or "hold")
            report = report_export.get("report") if isinstance(report_export.get("report"), dict) else {}
            rollout = report.get("rollout_policy") if isinstance(report.get("rollout_policy"), dict) else {}
            log.info(
                "🧾 Autonomy-Audit | recommendation=%s | reason=%s | risk_flags=%s | path=%s",
                recommendation,
                rollout.get("reason", "n/a"),
                ",".join(rollout.get("risk_flags", [])[:5]) if isinstance(rollout.get("risk_flags"), list) else "",
                report_export.get("path", ""),
            )

            try:
                from orchestration.canvas_store import canvas_store

                items = canvas_store.list_canvases(limit=1).get("items", [])
                if items:
                    canvas_id = str(items[0].get("id", ""))
                    if canvas_id:
                        canvas_store.add_event(
                            canvas_id=canvas_id,
                            event_type="autonomy_audit_report",
                            status="info",
                            message=(
                                "autonomy-audit "
                                f"recommendation={recommendation} "
                                f"reason={rollout.get('reason', 'n/a')}"
                            ),
                            payload=report,
                        )
            except Exception:
                return report_export
            return report_export
        except Exception as e:
            log.debug("Autonomy-Audit-Export fehlgeschlagen: %s", e)
            return None

    def _apply_autonomy_audit_change_request(self, *, export_payload: Optional[dict] = None) -> None:
        """M6.2: Uebersetzt Audit-Empfehlungen in formale Change-Requests."""
        try:
            from orchestration.autonomy_change_control import evaluate_and_apply_audit_change_request

            queue = get_queue()
            report = None
            report_path = None
            if isinstance(export_payload, dict):
                report = export_payload.get("report") if isinstance(export_payload.get("report"), dict) else None
                report_path = str(export_payload.get("path") or "").strip() or None

            result = evaluate_and_apply_audit_change_request(
                queue=queue,
                report=report,
                report_path=report_path,
            )
            action = str(result.get("action") or "none")
            if action in {
                "promote_canary",
                "rollback",
                "hold",
                "skipped",
                "duplicate_noop",
                "awaiting_approval",
            }:
                log.info(
                    "🧾 Audit-ChangeRequest | action=%s | request_id=%s | audit_id=%s | recommendation=%s | reason=%s",
                    action,
                    result.get("request_id", ""),
                    result.get("audit_id", ""),
                    result.get("recommendation", ""),
                    result.get("reason", ""),
                )

            try:
                from orchestration.canvas_store import canvas_store

                items = canvas_store.list_canvases(limit=1).get("items", [])
                if items:
                    canvas_id = str(items[0].get("id", ""))
                    if canvas_id:
                        canvas_store.add_event(
                            canvas_id=canvas_id,
                            event_type="autonomy_audit_change_request",
                            status="info",
                            message=(
                                "audit-change "
                                f"action={action} "
                                f"recommendation={result.get('recommendation', '')}"
                            ),
                            payload=result,
                        )
            except Exception:
                return
        except Exception as e:
            log.debug("Autonomy-Audit-ChangeRequest fehlgeschlagen: %s", e)

    def _apply_pending_autonomy_audit_change_requests(self) -> None:
        """M6.3: Wendet zuvor freigegebene Change-Requests asynchron im Heartbeat an."""
        try:
            from orchestration.autonomy_change_control import (
                enforce_pending_approval_sla,
                evaluate_and_apply_pending_approved_change_requests,
            )

            queue = get_queue()
            result = evaluate_and_apply_pending_approved_change_requests(queue=queue, limit=5)
            processed = int(result.get("processed", 0) or 0)
            if processed > 0:
                log.info("🧾 Pending ChangeRequests verarbeitet: %s", processed)
            sla_result = enforce_pending_approval_sla(queue=queue, limit=100)
            if int(sla_result.get("timed_out", 0) or 0) > 0:
                log.warning(
                    "🧾 Approval-SLA | timed_out=%s | escalated=%s | auto_rejected=%s | tasks=%s",
                    sla_result.get("timed_out", 0),
                    sla_result.get("escalated", 0),
                    sla_result.get("auto_rejected", 0),
                    sla_result.get("escalation_tasks_created", 0),
                )
        except Exception as e:
            log.debug("Pending Audit-ChangeRequests fehlgeschlagen: %s", e)

    # ------------------------------------------------------------------
    # Worker-Loop
    # ------------------------------------------------------------------

    async def _worker_loop(self) -> None:
        """Wartet auf Signal, holt dann Tasks aus SQLite und führt sie aus."""
        while self._running:
            # Warten bis Heartbeat signalisiert oder Timeout
            try:
                await asyncio.wait_for(self._work_signal.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass
            self._work_signal.clear()

            if not self._running:
                break

            # Alle verfügbaren Tasks sequenziell abarbeiten
            queue = get_queue()
            while self._running:
                task = queue.claim_next()
                if not task:
                    break
                await self._execute_task(task)

    # ------------------------------------------------------------------
    # Task-Ausführung
    # ------------------------------------------------------------------

    async def _execute_task(self, task: dict) -> None:
        """Führt einen Task mit automatischem Failover aus."""
        task_id = task.get("id", "?")
        description = task.get("description", "")
        target_agent = task.get("target_agent")
        priority = task.get("priority", Priority.NORMAL)
        goal_id = task.get("goal_id")
        metadata = _parse_task_metadata(task.get("metadata"))
        queue = get_queue()

        if not description:
            queue.complete(task_id, "Übersprungen: leere Beschreibung")
            return

        prio_name = {0: "CRITICAL", 1: "HIGH", 2: "NORMAL", 3: "LOW"}.get(priority, str(priority))
        log.info(f"▶ [{prio_name}] Task [{task_id[:8]}]: {description[:80]}")

        quarantine_guard = self._self_healing_quarantine_decision(queue, task_id, description, metadata)
        if quarantine_guard is not None:
            queue.requeue(
                task_id,
                run_at=quarantine_guard["quarantine_until"],
                error=f"quarantined:{quarantine_guard['reason']}",
                metadata_update={
                    "quarantined": True,
                    "quarantine_reason": quarantine_guard["reason"],
                    "quarantine_until": quarantine_guard["quarantine_until"],
                },
            )
            self._record_self_healing_quarantine_state(queue, quarantine_guard)
            log.info(
                "⛔ Self-Healing-Task quarantined [%s]: %s bis %s",
                task_id[:8],
                quarantine_guard.get("incident_key", ""),
                quarantine_guard.get("quarantine_until", ""),
            )
            return

        resource_guard = self._resource_guard_decision(
            queue,
            task_id=task_id,
            description=description,
            priority=int(priority),
            target_agent=target_agent,
            metadata=metadata,
        )
        if resource_guard is not None:
            queue.requeue(
                task_id,
                run_at=resource_guard["run_at"],
                error=f"resource_guard:{resource_guard['reason']}",
                metadata_update={
                    "resource_guarded": True,
                    "resource_guard_reason": resource_guard["reason"],
                    "resource_guard_until": resource_guard["run_at"],
                },
            )
            self._record_resource_guard_state(queue, resource_guard)
            log.info(
                "⏸️ Resource-Guard deferred [%s]: %s bis %s",
                task_id[:8],
                resource_guard.get("reason", ""),
                resource_guard.get("run_at", ""),
            )
            return

        if _policy_gates_feature_enabled():
            try:
                from utils.policy_gate import audit_policy_decision, evaluate_policy_gate

                policy_decision = evaluate_policy_gate(
                    gate="autonomous_task",
                    subject=description,
                    payload={
                        "task": description,
                        "task_id": task_id,
                        "target_agent": target_agent or "auto",
                        "priority": priority,
                    },
                    source="autonomous_runner._execute_task",
                )
                audit_policy_decision(policy_decision)
                if policy_decision.get("blocked"):
                    reason = str(policy_decision.get("reason") or "Policy blockiert autonomen Task.")
                    queue.fail(task_id, reason[:500])
                    if goal_id and _goals_feature_enabled():
                        queue.refresh_goal_progress(goal_id, last_task_id=task_id, last_event="task_policy_blocked")
                    log.warning("🛡️ Task [%s] policy-blocked: %s", task_id[:8], reason)
                    return
                if policy_decision.get("action") == "observe":
                    log.warning(
                        "🛡️ Task [%s] policy-observe: %s",
                        task_id[:8],
                        str(policy_decision.get("reason") or ""),
                    )
            except Exception as e:
                log.debug("Policy-Gate fuer autonomen Task fehlgeschlagen: %s", e)

        hardening_result = await self._try_execute_self_hardening_autofix(
            queue=queue,
            task_id=task_id,
            description=description,
            goal_id=goal_id,
            metadata=metadata,
        )
        if hardening_result is not None:
            status, result_text = hardening_result
            if status in {"success", "pending_approval"}:
                queue.complete(task_id, result_text[:2000])
                if goal_id and _goals_feature_enabled():
                    queue.refresh_goal_progress(goal_id, last_task_id=task_id, last_event="task_completed")
                log.info("✅ Self-Hardening-Task [%s] abgeschlossen (%s)", task_id[:8], status)
            else:
                queue.fail(task_id, result_text[:500])
                if goal_id and _goals_feature_enabled():
                    queue.refresh_goal_progress(goal_id, last_task_id=task_id, last_event="task_failed")
                log.warning("❌ Self-Hardening-Task [%s] fehlgeschlagen (%s)", task_id[:8], status)
            return

        try:
            from main_dispatcher import get_agent_decision
            from utils.model_failover import failover_run_agent

            session_id = f"auto_{uuid.uuid4().hex[:8]}"
            agent = target_agent if target_agent else await get_agent_decision(description, session_id=session_id)

            result = await failover_run_agent(
                agent_name=agent,
                query=description,
                tools_description=self._tools_desc or "",
                session_id=session_id,
                on_alert=self._send_failure_alert,
            )

            if result is not None:
                result_str = str(result)
                queue.complete(task_id, result_str[:2000])
                if goal_id and _goals_feature_enabled():
                    queue.refresh_goal_progress(goal_id, last_task_id=task_id, last_event="task_completed")
                log.info(f"✅ Task [{task_id[:8]}] abgeschlossen")
                notification_guard = self._notification_guard_decision(queue, task_id, description, metadata)
                if notification_guard and not notification_guard.get("send", True):
                    self._record_incident_notification_state(
                        queue,
                        notification_guard,
                        state_value="cooldown_active",
                        telegram_sent=False,
                        email_sent=False,
                        result_preview=result_str,
                        suppression_reason=str(notification_guard.get("reason") or "cooldown_active"),
                    )
                    log.info(
                        "🔕 Incident-Notification unterdrückt [%s]: %s",
                        task_id[:8],
                        notification_guard.get("incident_key", ""),
                    )
                else:
                    telegram_sent = await self._send_result_to_telegram(description, result_str)
                    email_sent = await self._send_result_to_email(description, result_str)
                    if notification_guard is not None:
                        self._record_incident_notification_state(
                            queue,
                            notification_guard,
                            state_value="sent" if (telegram_sent or email_sent) else "send_failed",
                            telegram_sent=telegram_sent,
                            email_sent=email_sent,
                            result_preview=result_str,
                        )
            else:
                queue.fail(task_id, "Alle Failover-Versuche erschöpft")
                if goal_id and _goals_feature_enabled():
                    queue.refresh_goal_progress(goal_id, last_task_id=task_id, last_event="task_failover_exhausted")

        except Exception as e:
            log.error(f"❌ Task [{task_id[:8]}] Fehler: {e}", exc_info=True)
            queue.fail(task_id, str(e))
            if goal_id and _goals_feature_enabled():
                queue.refresh_goal_progress(goal_id, last_task_id=task_id, last_event="task_failed")

    async def _try_execute_self_hardening_autofix(
        self,
        *,
        queue,
        task_id: str,
        description: str,
        goal_id: Optional[str],
        metadata: dict,
    ) -> Optional[tuple[str, str]]:
        del queue, goal_id
        if str((metadata or {}).get("source") or "").strip() != "self_hardening":
            return None
        if str((metadata or {}).get("execution_mode") or "").strip() != "self_modify_safe":
            return None

        pattern_name = str((metadata or {}).get("pattern_name") or "").strip()
        component = str((metadata or {}).get("component") or "").strip()
        requested_fix_mode = str((metadata or {}).get("requested_fix_mode") or "").strip()
        target_file_path = str((metadata or {}).get("target_file_path") or "").strip()
        change_type = str((metadata or {}).get("change_type") or "auto").strip() or "auto"
        dedup_key = str((metadata or {}).get("hardening_dedup_key") or "").strip() or f"task:{task_id}"
        if not target_file_path:
            try:
                record_self_hardening_event(
                    queue=get_queue(),
                    stage="self_modify_missing_target_file",
                    status="error",
                    pattern_name=pattern_name,
                    component=component,
                    requested_fix_mode=requested_fix_mode,
                    execution_mode="self_modify_safe",
                    route_target="self_modify",
                    reason="missing_target_file",
                    task_id=task_id,
                    target_file_path=target_file_path,
                    change_type=change_type,
                )
            except Exception:
                pass
            return ("error", "self_hardening:self_modify_missing_target_file")

        try:
            from orchestration.self_modifier_engine import get_self_modifier_engine

            engine = get_self_modifier_engine()
            result = engine.execute_self_hardening_fix(
                source_id=dedup_key,
                file_path=target_file_path,
                change_description=description,
                change_type=change_type,
                pattern_name=pattern_name,
                component=component,
                requested_fix_mode=requested_fix_mode,
                session_id=f"m18:{task_id[:8]}",
            )
            summary = (
                f"Self-hardening {result.status}: {result.file_path} | "
                f"verification={result.verification_summary or result.test_result or 'n/a'}"
            )
            return (result.status, summary)
        except Exception as exc:
            log.error("Self-Hardening-Autofix [%s] fehlgeschlagen: %s", task_id[:8], exc, exc_info=True)
            try:
                record_self_hardening_event(
                    queue=get_queue(),
                    stage="self_modify_exception",
                    status="error",
                    pattern_name=pattern_name,
                    component=component,
                    requested_fix_mode=requested_fix_mode,
                    execution_mode="self_modify_safe",
                    route_target="self_modify",
                    reason=str(exc),
                    task_id=task_id,
                    target_file_path=target_file_path,
                    change_type=change_type,
                    increment_metrics={"self_modify_errors_total": 1},
                )
            except Exception:
                pass
            return ("error", f"self_hardening:self_modify_exception:{exc}")

    async def _send_failure_alert(
        self,
        agent: str,
        query: str,
        attempts: list,
        last_error: str,
    ) -> None:
        """Sendet Telegram-Alert wenn alle Failover-Versuche erschöpft sind."""
        try:
            token = __import__("os").getenv("TELEGRAM_BOT_TOKEN", "")
            allowed_ids = __import__("os").getenv("TELEGRAM_ALLOWED_IDS", "")
            if not token or not allowed_ids:
                return

            from telegram import Bot
            bot = Bot(token=token)
            chat_ids = [int(x.strip()) for x in allowed_ids.split(",") if x.strip()]

            msg = (
                f"🚨 *Timus Autonomer Ausfall*\n\n"
                f"Agent: `{agent}`\n"
                f"Versuche: `{' → '.join(attempts)}`\n"
                f"Fehler: `{last_error[:200]}`\n\n"
                f"Task: _{query[:100]}_"
            )
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
            await bot.close()
            log.info("🚨 Failure-Alert via Telegram gesendet")
        except Exception as e:
            log.warning(f"Alert-Versand fehlgeschlagen: {e}")


    async def _send_result_to_telegram(self, description: str, result: str) -> bool:
        """
        Sendet das Task-Ergebnis an alle erlaubten Telegram-User.

        - Kurze Ergebnisse (≤ 3800 Zeichen) → Textnachricht
        - Lange Ergebnisse (Recherchen, Reports) → .md-Dokument-Anhang
        - Bilder (results/*.png + DALL-E URLs) → reply_photo
        """
        import os, re
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        allowed_ids = os.getenv("TELEGRAM_ALLOWED_IDS", "")
        if not token or not allowed_ids:
            return False

        try:
            from telegram import Bot
            bot = Bot(token=token)
            chat_ids = [int(x.strip()) for x in allowed_ids.split(",") if x.strip()]
            delivered = False

            header = f"✅ *Autonomer Task abgeschlossen*\n_{description[:120]}_\n\n"
            MAX_TEXT = 3800

            for chat_id in chat_ids:
                try:
                    # Bild-Erkennung (selbe Logik wie TelegramGateway)
                    image_sent = False

                    path_match = re.search(r'results/[^\n"\']+\.(?:png|jpg|jpeg|webp)', result, re.IGNORECASE)
                    if path_match:
                        from pathlib import Path
                        project_root = Path(__file__).parent.parent
                        image_path = project_root / path_match.group(0).strip()
                        if image_path.exists():
                            prompt_match = re.search(r'(?:Verwendeter Prompt|Prompt)[:\s]+(.{10,300})', result)
                            caption = prompt_match.group(1).strip()[:1024] if prompt_match else description[:200]
                            with open(image_path, "rb") as f:
                                await bot.send_photo(chat_id=chat_id, photo=f, caption=caption)
                            image_sent = True
                            delivered = True

                    if not image_sent:
                        url_match = re.search(r'URL:\s*(https://[^\s\n]+)', result, re.IGNORECASE)
                        if url_match:
                            import httpx
                            image_url = url_match.group(1).rstrip('.,)')
                            try:
                                async with httpx.AsyncClient(timeout=30) as client:
                                    resp = await client.get(image_url)
                                    resp.raise_for_status()
                                await bot.send_photo(chat_id=chat_id, photo=resp.content)
                                image_sent = True
                                delivered = True
                            except Exception as img_e:
                                log.warning(f"Bild-URL-Versand fehlgeschlagen: {img_e}")

                    if image_sent:
                        continue  # Bild gesendet, kein Text mehr nötig

                    # Text-Ergebnis senden
                    if len(result) <= MAX_TEXT:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=header + result,
                            parse_mode="Markdown",
                        )
                        delivered = True
                    else:
                        # Zu lang → als .md-Dokument senden
                        await bot.send_message(
                            chat_id=chat_id,
                            text=header + result[:MAX_TEXT] + f"\n\n…_(vollständig als Dokument)_",
                            parse_mode="Markdown",
                        )
                        doc_content = f"# {description}\n\n{result}"
                        safe_name = re.sub(r'[^\w\s\-]', '', description[:40]).strip().replace(' ', '_')
                        await bot.send_document(
                            chat_id=chat_id,
                            document=io.BytesIO(doc_content.encode("utf-8")),
                            filename=f"timus_recherche_{safe_name}.md",
                            caption="📄 Vollständiger Bericht",
                        )
                        delivered = True

                except Exception as e:
                    log.warning(f"Ergebnis-Versand an {chat_id} fehlgeschlagen: {e}")

            await bot.close()
            log.info("📨 Task-Ergebnis via Telegram gesendet")
            return delivered

        except Exception as e:
            log.warning(f"_send_result_to_telegram fehlgeschlagen: {e}")
            return False

    async def _send_result_to_email(self, description: str, result: str) -> bool:
        """Sendet das Task-Ergebnis per E-Mail (Resend/SMTP je nach EMAIL_BACKEND)."""
        import os
        recipient = os.getenv("USER_EMAIL_PRIMARY", "")
        if not recipient:
            return False
        try:
            from utils.resend_email import send_email_resend
            from utils.smtp_email import send_email_smtp
            backend = os.getenv("EMAIL_BACKEND", "resend").lower()

            subject = f"Timus: {description[:80]}"
            body = f"Autonomer Task abgeschlossen\n\n{description}\n\n{'='*60}\n\n{result}"

            if backend == "resend":
                await send_email_resend(to=recipient, subject=subject, body=body)
            else:
                await send_email_smtp(to=recipient, subject=subject, body=body)

            log.info("📧 Task-Ergebnis via E-Mail gesendet")
            return True
        except Exception as e:
            log.warning(f"_send_result_to_email fehlgeschlagen: {e}")
            return False


# ------------------------------------------------------------------
# Öffentliche Hilfsfunktion: Task hinzufügen
# ------------------------------------------------------------------

def add_task(
    description: str,
    target_agent: Optional[str] = None,
    priority: int = Priority.NORMAL,
    task_type: str = TaskType.MANUAL,
) -> str:
    """
    Fügt einen neuen Task zur SQLite-Queue hinzu.
    Gibt die Task-ID zurück.
    """
    return get_queue().add(
        description=description,
        priority=priority,
        task_type=task_type,
        target_agent=target_agent,
    )
