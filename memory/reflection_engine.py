"""
Reflection Engine - Automatisierte Post-Task Analyse.

FEATURES:
- Analyse abgeschlossener Aufgaben
- Erfolgs-/Fehler-Pattern-Erkennung
- Automatisches Speichern von Learnings
- Pattern-Extraktion für zukünftige Aufgaben

USAGE:
    from memory.reflection_engine import ReflectionEngine
    
    engine = ReflectionEngine(memory_manager, llm_client)
    result = await engine.reflect_on_task(task, actions, final_result)
    
    # Learnings werden automatisch in memory gespeichert

AUTOR: Timus Development
DATUM: Februar 2026
"""

import os
import json
import logging
import hashlib
import re
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

log = logging.getLogger("ReflectionEngine")


@dataclass
class ReflectionResult:
    """Ergebnis einer Task-Reflexion."""
    success: bool
    what_worked: List[str] = field(default_factory=list)
    what_failed: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    patterns_to_remember: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    confidence: float = 0.8
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


REFLECTION_PROMPT = """
Analysiere die folgende abgeschlossene Aufgabe und erstelle eine Reflexion.

AUFGABE:
{task_description}

AUSGEFÜHRTE AKTIONEN:
{actions_taken}

ERGEBNIS:
{result}

ANALYSIERE:
1. Was hat gut funktioniert?
2. Was hat nicht funktioniert oder war ineffizient?
3. Welche Verbesserungen sollten für ähnliche Aufgaben implementiert werden?
4. Welche Muster/Patterns sollten für zukünftige Aufgaben gespeichert werden?
5. Welche Folgeaktionen sind nötig?

Antworte NUR als gültiges JSON (kein Markdown, keine Erklärungen):
{{
    "success": true,
    "what_worked": ["Punkt 1", "Punkt 2"],
    "what_failed": ["Problem 1", "Problem 2"],
    "improvements": ["Verbesserung 1", "Verbesserung 2"],
    "patterns_to_remember": ["Pattern 1", "Pattern 2"],
    "next_actions": ["Aktion 1"],
    "confidence": 0.8
}}
"""


class ReflectionEngine:
    """
    Analysiert abgeschlossene Aufgaben für kontinuierliche Verbesserung.
    
    Nach jeder Aufgabe wird eine LLM-basierte Reflexion durchgeführt
    und die Erkenntnisse im Memory-System gespeichert.
    
    v2.0 NEU: Skill-Generierung aus wiederkehrenden Fehlern mit Safeguards.
    """
    
    # Skill-Creation Safeguards
    PATTERN_THRESHOLD = 3  # Pattern muss 3x auftreten
    SKILL_COOLDOWN_HOURS = 1  # Min 1h zwischen Skill-Erstellungen
    
    def __init__(self, memory_manager=None, llm_client=None):
        """
        Initialisiert die Reflection Engine.
        
        Args:
            memory_manager: MemoryManager Instanz für Learning-Speicherung
            llm_client: OpenAI Client für Reflexions-LLM-Calls
        """
        self.memory = memory_manager
        self.llm = llm_client
        self._reflection_count = 0
        self._last_reflection: Optional[ReflectionResult] = None
        
        # NEU v2.0: Skill-Creation Safeguards
        self._pattern_counter: Dict[str, int] = {}  # pattern_hash -> count
        self._last_skill_creation: Optional[datetime] = None
        self._skill_creation_enabled = True  # Kann deaktiviert werden
    
    def set_memory_manager(self, memory_manager):
        """Setzt den Memory Manager nachträglich."""
        self.memory = memory_manager
    
    def set_llm_client(self, llm_client):
        """Setzt den LLM Client nachträglich."""
        self.llm = llm_client
    
    def enable_skill_creation(self, enabled: bool = True):
        """Aktiviert/Deaktiviert automatische Skill-Erstellung."""
        self._skill_creation_enabled = enabled
    
    def get_skill_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zur Skill-Erstellung zurück."""
        return {
            "pattern_counter": dict(self._pattern_counter),
            "last_skill_creation": self._last_skill_creation.isoformat() if self._last_skill_creation else None,
            "skill_creation_enabled": self._skill_creation_enabled,
            "cooldown_active": self._is_cooldown_active()
        }
    
    async def reflect_on_task(
        self,
        task: Dict[str, Any],
        actions: List[Dict[str, Any]],
        result: Any,
        force_reflection: bool = False
    ) -> Optional[ReflectionResult]:
        """
        Führt Reflexion nach Task-Abschluss durch.
        
        Args:
            task: Task-Beschreibung mit 'description' und optional 'type'
            actions: Liste der ausgeführten Aktionen
            result: Das Endergebnis der Aufgabe
            force_reflection: Auch bei kurzen/simple Tasks reflektieren
        
        Returns:
            ReflectionResult oder None bei Fehler
        """
        # Skip reflection für sehr kurze/simple Tasks
        if not force_reflection:
            if len(actions) < 2 and len(str(result)) < 100:
                log.debug("Überspringe Reflexion für simple Task")
                return None
        
        try:
            # Prompt bauen
            prompt = REFLECTION_PROMPT.format(
                task_description=self._format_task(task),
                actions_taken=self._format_actions(actions),
                result=self._format_result(result)
            )
            
            # LLM Call
            response = await self._call_llm(prompt)
            
            if not response:
                log.warning("Keine LLM-Antwort für Reflexion")
                return None
            
            # Parse Response
            parsed = self._parse_response(response)
            
            if not parsed:
                log.warning("Konnte Reflexions-Response nicht parsen")
                return None
            
            # Learnings speichern
            await self._store_learnings(parsed, task)
            
            self._reflection_count += 1
            self._last_reflection = parsed
            
            log.info(
                f"🪞 Reflexion abgeschlossen: "
                f"{'ERFOLG' if parsed.success else 'TEILERFOLG'} "
                f"({len(parsed.what_worked)} positiv, {len(parsed.what_failed)} negativ)"
            )
            
            return parsed
            
        except Exception as e:
            log.error(f"Reflexion fehlgeschlagen: {e}")
            return None
    
    def _format_task(self, task: Dict[str, Any]) -> str:
        """Formatiert Task für Prompt."""
        if isinstance(task, str):
            return task
        return task.get("description", str(task))
    
    def _format_actions(self, actions: List[Dict[str, Any]]) -> str:
        """Formatiert Aktionen für Prompt."""
        if not actions:
            return "Keine Aktionen aufgezeichnet"
        
        lines = []
        for i, action in enumerate(actions[:10], 1):  # Max 10 Aktionen
            if isinstance(action, dict):
                method = action.get("method", action.get("action", "unknown"))
                params = action.get("params", {})
                result = action.get("result", "")
                
                line = f"{i}. {method}"
                if params:
                    param_str = str(params)[:100]
                    line += f" | Params: {param_str}"
                if result:
                    result_str = str(result)[:100]
                    line += f" → {result_str}"
                lines.append(line)
            else:
                lines.append(f"{i}. {str(action)[:150]}")
        
        return "\n".join(lines)
    
    def _format_result(self, result: Any) -> str:
        """Formatiert Ergebnis für Prompt."""
        result_str = str(result)
        if len(result_str) > 500:
            return result_str[:500] + "... [gekürzt]"
        return result_str
    
    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Ruft LLM für Reflexion auf."""
        if not self.llm:
            # Fallback: Verwende globalen MemoryManager Client
            if self.memory and hasattr(self.memory, 'client'):
                self.llm = self.memory.client
            else:
                log.warning("Kein LLM Client für Reflexion verfügbar")
                return None

        try:
            from utils.openai_compat import prepare_openai_params

            llm_client = self._resolve_chat_client()
            if not llm_client:
                log.warning("Kein kompatibler Chat-Client für Reflexion verfügbar")
                return None

            response = await asyncio.to_thread(
                llm_client.chat.completions.create,
                **prepare_openai_params({
                    "model": os.getenv("REFLECTION_MODEL", "gpt-4o-mini"),
                    "messages": [
                        {
                            "role": "system",
                            "content": "Du bist ein Analytiker für KI-Agenten-Performance. "
                            "Du analysierst Aufgaben und extrahierst Verbesserungsmuster. "
                            "Antworte IMMER nur mit gültigem JSON, ohne Markdown-Code-Blöcke."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"}
                })
            )
            
            return response.choices[0].message.content
        except Exception as e:
            log.error(f"LLM Call für Reflexion fehlgeschlagen: {e}")
            return None

    def _resolve_chat_client(self):
        """Löst einen OpenAI-kompatiblen Chat-Client auf.

        Unterstützt:
        - direkten OpenAI-kompatiblen Client mit `.chat.completions`
        - MultiProviderClient via `.get_client(ModelProvider.XXX)`
        """
        if hasattr(self.llm, "chat") and hasattr(self.llm.chat, "completions"):
            return self.llm

        if not hasattr(self.llm, "get_client"):
            return None

        try:
            from agent.providers import ModelProvider
        except Exception as e:
            log.debug(f"ModelProvider Import fehlgeschlagen: {e}")
            return None

        provider_order = []
        preferred_provider = os.getenv("REFLECTION_PROVIDER", "openai").lower().strip()
        try:
            provider_order.append(ModelProvider(preferred_provider))
        except ValueError:
            pass

        for provider in (
            ModelProvider.OPENAI,
            ModelProvider.OPENROUTER,
            ModelProvider.DEEPSEEK,
            ModelProvider.NVIDIA,
            ModelProvider.INCEPTION,
        ):
            if provider not in provider_order:
                provider_order.append(provider)

        for provider in provider_order:
            try:
                client = self.llm.get_client(provider)
                if hasattr(client, "chat") and hasattr(client.chat, "completions"):
                    return client
            except Exception:
                continue

        return None
    
    def _parse_response(self, raw: Optional[str]) -> Optional[ReflectionResult]:
        """Parst LLM Response zu ReflectionResult."""
        if not raw or not raw.strip():
            return None
        
        text = raw.strip()
        
        # JSON aus Code-Block extrahieren falls nötig
        fenced = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.DOTALL)
        if not fenced:
            fenced = re.search(r"```([\s\S]*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        
        # JSON parse
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Versuche mit Repair
            try:
                # Entferne trailing commas
                text = re.sub(r",\s*([\}\]])", r"\1", text)
                data = json.loads(text)
            except:
                log.warning(f"Konnte Reflexions-JSON nicht parsen: {text[:200]}")
                return None
        
        if not isinstance(data, dict):
            return None
        
        return ReflectionResult(
            success=bool(data.get("success", True)),
            what_worked=data.get("what_worked", []),
            what_failed=data.get("what_failed", []),
            improvements=data.get("improvements", []),
            patterns_to_remember=data.get("patterns_to_remember", []),
            next_actions=data.get("next_actions", []),
            confidence=float(data.get("confidence", 0.8))
        )
    
    async def _store_learnings(self, reflection: ReflectionResult, task: Dict[str, Any]):
        """Speichert gelernte Muster und Verbesserungen im Memory."""
        if not self.memory:
            log.warning("Kein Memory Manager für Learning-Speicherung")
            return
        
        from memory.memory_system import MemoryItem
        
        task_desc = self._format_task(task)[:50]
        
        # Erfolgreiche Muster speichern
        for i, pattern in enumerate(reflection.patterns_to_remember[:5]):
            try:
                await self._store_item(MemoryItem(
                    category="patterns",
                    key=f"pattern_{datetime.now().strftime('%Y%m%d')}_{hashlib.md5(pattern.encode()).hexdigest()[:6]}",
                    value=pattern,
                    importance=0.8,
                    confidence=reflection.confidence,
                    reason=f"erfolgreich bei: {task_desc}"
                ))
            except Exception as e:
                log.debug(f"Pattern-Speicherung fehlgeschlagen: {e}")
        
        # Fehler mit Lösungen speichern
        if reflection.what_failed:
            try:
                await self._store_item(MemoryItem(
                    category="decisions",
                    key=f"failure_{datetime.now().strftime('%Y%m%d_%H%M')}",
                    value={
                        "problems": reflection.what_failed,
                        "improvements": reflection.improvements,
                        "task": task_desc
                    },
                    importance=0.7,
                    confidence=reflection.confidence,
                    reason="post_task_reflection"
                ))
            except Exception as e:
                log.debug(f"Failure-Speicherung fehlgeschlagen: {e}")
        
        # Verbesserungen als Arbeits-Notizen
        if reflection.improvements and reflection.success:
            for improvement in reflection.improvements[:3]:
                try:
                    await self._store_item(MemoryItem(
                        category="working_memory",
                        key=f"improvement_{hashlib.md5(improvement.encode()).hexdigest()[:6]}",
                        value=improvement,
                        importance=0.6,
                        confidence=reflection.confidence,
                        reason=f"suggested for: {task_desc}"
                    ))
                except Exception as e:
                    log.debug(f"Improvement-Speicherung fehlgeschlagen: {e}")
        
        # NEU v2.0: Skill-Trigger mit Safeguards
        if self._should_create_tool(reflection):
            await self._trigger_tool_creation(reflection, task)
    
    # =================================================================
    # SKILL-CREATION METHODEN (v2.0)
    # =================================================================
    
    def _get_pattern_hash(self, failures: List[str]) -> str:
        """Erzeugt stabilen Hash für ein Fehler-Pattern."""
        normalized = sorted([f.lower().strip() for f in failures if f])
        return hashlib.md5("|".join(normalized).encode()).hexdigest()[:12]
    
    def _is_cooldown_active(self) -> bool:
        """Prüft ob Cooldown für Skill-Erstellung aktiv ist."""
        if not self._last_skill_creation:
            return False
        cooldown = timedelta(hours=self.SKILL_COOLDOWN_HOURS)
        return (datetime.now() - self._last_skill_creation) < cooldown
    
    def _should_create_tool(self, reflection: ReflectionResult) -> bool:
        """
        Bestimmt ob ein neues Tool erstellt werden soll.

        Safeguards:
        - Pattern muss mindestens PATTERN_THRESHOLD (3x) aufgetreten sein
        - Cooldown von SKILL_COOLDOWN_HOURS (1h) zwischen Erstellungen
        - Mindestens 2 Fehler UND Verbesserungsvorschläge
        - Confidence >= 0.7
        - Skill-Creation muss aktiviert sein
        """
        # Basis-Checks
        if not self._skill_creation_enabled:
            return False
        
        if not reflection.what_failed or not reflection.improvements:
            return False
        
        if len(reflection.what_failed) < 2:
            return False
        
        if reflection.confidence < 0.7:
            return False
        
        # Cooldown prüfen
        if self._is_cooldown_active():
            log.debug("Skill-Creation Cooldown aktiv")
            return False
        
        # Pattern-Häufigkeit prüfen
        pattern_key = self._get_pattern_hash(reflection.what_failed)
        self._pattern_counter[pattern_key] = self._pattern_counter.get(pattern_key, 0) + 1
        
        threshold_reached = self._pattern_counter[pattern_key] >= self.PATTERN_THRESHOLD
        
        if threshold_reached:
            log.info(f"Pattern-Schwelle erreicht: {pattern_key} ({self._pattern_counter[pattern_key]}x)")
        
        return threshold_reached
    
    async def _trigger_tool_creation(self, reflection: ReflectionResult, task: Dict):
        """Delegiert Tool-Erstellung an skill_manager_tool."""
        try:
            # Lazy import um zirkuläre Abhängigkeiten zu vermeiden
            from tools.skill_manager_tool.tool import create_tool_from_pattern
            
            result = await create_tool_from_pattern(
                pattern_description="; ".join(reflection.what_failed[:3]),
                source_task=self._format_task(task),
                improvements=reflection.improvements[:5]
            )
            
            if result and result.get("success"):
                self._last_skill_creation = datetime.now()
                log.info(f"🛠️ Neues Tool erstellt: {result.get('skill_name')}")
            elif result and result.get("skipped"):
                log.debug(f"Tool-Erstellung übersprungen: {result.get('reason')}")
            elif result and result.get("error"):
                log.warning(f"Tool-Erstellung fehlgeschlagen: {result.get('error')}")
                
        except ImportError:
            log.debug("skill_manager_tool nicht verfügbar für Tool-Erstellung")
        except Exception as e:
            log.debug(f"Tool-Erstellung nicht möglich: {e}")
    
    async def _store_item(self, item):
        """Speichert MemoryItem mit Embedding."""
        if hasattr(self.memory, 'store_with_embedding'):
            self.memory.store_with_embedding(item)
        elif hasattr(self.memory, 'persistent'):
            self.memory.persistent.store_memory_item(item)
        else:
            log.warning("Memory Manager kann Items nicht speichern")
    
    def get_last_reflection(self) -> Optional[ReflectionResult]:
        """Gibt die letzte Reflexion zurück."""
        return self._last_reflection
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        return {
            "total_reflections": self._reflection_count,
            "last_reflection": self._last_reflection.timestamp if self._last_reflection else None,
            # v2.0: Skill-Stats
            "skill_stats": self.get_skill_stats()
        }


# Singleton Instance
_reflection_engine: Optional[ReflectionEngine] = None


def get_reflection_engine() -> ReflectionEngine:
    """Gibt die globale Reflection Engine zurück."""
    global _reflection_engine
    if _reflection_engine is None:
        _reflection_engine = ReflectionEngine()
    return _reflection_engine


def init_reflection_engine(memory_manager=None, llm_client=None) -> ReflectionEngine:
    """Initialisiert die globale Reflection Engine."""
    global _reflection_engine
    _reflection_engine = ReflectionEngine(memory_manager, llm_client)
    return _reflection_engine


async def reflect_on_task(
    task: Dict[str, Any],
    actions: List[Dict[str, Any]],
    result: Any
) -> Optional[ReflectionResult]:
    """Shortcut für Task-Reflexion."""
    engine = get_reflection_engine()
    return await engine.reflect_on_task(task, actions, result)
