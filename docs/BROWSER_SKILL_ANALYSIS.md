# Analyse & Implementierungsplan: Browser-Isolation & Skill-Generierung

**Datum:** 2026-02-17 (ueberarbeitet)
**Prioritaet:** ★★★★☆ (Browser-Isolation) / ★★★☆☆ (Skill-Generierung)
**Status:** Plan v2.0 - Architektur-Review eingearbeitet

---

## 1. Architektur-Analyse

### 1.1 Bestehende Browser-Infrastruktur

| Komponente | Datei | Status |
|------------|-------|--------|
| **BrowserSession** (Klasse) | `tools/browser_tool/tool.py:120` | ⚠️ Single global Singleton |
| **browser_session** (Dict) | `tools/shared_context.py` | ⚠️ Zweite globale Session (Dict-basiert) |
| **HybridBrowserController** | `tools/browser_controller/controller.py` | ✅ DOM-First, delegiert via MCP-HTTP |
| **Playwright Context** | - | ❌ Kein persistent storage_path |

**Kritisches Problem - Doppelte Browser-Sessions:**
Es existieren **zwei unabhaengige, globale Browser-Instanzen**:
1. `BrowserSession` Klasse in `tools/browser_tool/tool.py` (Zeile 120: `browser_session_manager = BrowserSession()`)
2. `browser_session` Dict in `tools/shared_context.py` mit eigener `ensure_browser_initialized()`

Beide starten jeweils Firefox headless, erstellen je einen Context und eine Page.
Der `HybridBrowserController` besitzt keinen eigenen Browser und delegiert via JSON-RPC an `browser_tool`.

**Weitere Probleme:**
- Cookies/LocalStorage gehen bei Restart verloren
- Keine Trennung zwischen Sessions (Race Conditions bei parallelen Agenten)
- Keine automatische Retry-Logik bei CAPTCHA/Network-Fehlern
- Firefox wird genutzt - `launch_persistent_context()` ist nur fuer Chromium stabil

### 1.2 Bestehendes Skill-System

| Komponente | Datei | Typ | Status |
|------------|-------|-----|--------|
| **Skill Manager** | `tools/skill_manager_tool/tool.py` | Python `*_skill.py` | ✅ `learn_new_skill()` ruft `implement_feature` auf |
| **Skill Recorder** | `tools/skill_recorder/tool.py` | YAML `skills.yml` | ✅ pynput-basierte Aufzeichnung |
| **Skills Directory** | `skills/*.py` | Python | ✅ Funktionierende Skills |
| **Developer Agent** | `agent/developer_agent_v2.py` | - | ✅ Hat `implement_feature` + AST-Validierung |
| **Reflection Engine** | `memory/reflection_engine.py` | - | ✅ Post-Task Analyse |
| **Tool Registry** | `tools/tool_registry_v2.py` | - | ✅ `@tool` Decorator + JSON-RPC Registrierung |

**Wichtig - Zwei getrennte Skill-Systeme:**
1. **Python-Tools** (`skill_manager_tool`): Generiert `skills/*_skill.py` via Inception/Mercury-Coder, registriert via `register_new_tool_in_server()`
2. **YAML-Steps** (`skill_recorder`): Zeichnet Maus/Tastatur-Aktionen auf, speichert in `agent/skills.yml`

**Aktuelle Probleme:**
- Keine automatische Skill-Generierung aus Fehlern
- Skill-Recorder ist manuell (Benutzer muss aufnehmen)
- Keine Verknuepfung zwischen Reflexion und Skill-Creation
- Kein Quality-Gate fuer generierten Skill-Code

---

## 2. Machbarkeitsanalyse

### 2.1 Browser-Isolation & Persistente Kontexte

| Anforderung | Machbarkeit | Aufwand | Hinweis |
|-------------|-------------|---------|---------|
| Session-Konsolidierung | ✅ Refactoring | 1.5h | **Voraussetzung** fuer alles andere |
| Persistente Browser-Contexts | ✅ `new_context()` + `storage_state()` | Mittel | NICHT `launch_persistent_context` (Firefox!) |
| Cookies/LocalStorage behalten | ✅ `context.storage_state(path=...)` beim Cleanup | Niedrig | Manuelles Save/Load |
| Session-Isolation | ✅ `PersistentContextManager` | Mittel | Pro session_id ein Context |
| Retry-Logik Network | ✅ Exponential Backoff | Niedrig | |
| CAPTCHA-Erkennung | ⚠️ Heuristik (Cloudflare existiert schon in open_url) | Mittel | |
| HybridBrowserController Integration | ✅ session_id durchreichen | Niedrig | |

**Gesamtaufwand:** ~5h (inkl. Session-Konsolidierung)

### 2.2 Selbstverbesserung & Tool-Generierung

| Anforderung | Machbarkeit | Aufwand | Hinweis |
|-------------|-------------|---------|---------|
| Tool-Generierung aus Fehlern | ✅ `learn_new_skill()` erweitern | Mittel | Kein neuer Agent noetig |
| Fehleranalyse → Tool | ✅ ReflectionEngine + Pattern-Counter | Mittel | Mindest-Haeufigkeit beachten |
| Duplikat-Erkennung | ✅ Name/Pattern-Hash Check | Niedrig | |
| AST-Validierung vor Registrierung | ✅ Existiert in developer_agent_v2 | Niedrig | `validate_python_syntax()` |
| Automatische Tool-Registrierung | ✅ `register_new_tool_in_server()` existiert | Niedrig | |
| UI-Pattern-Templates | ⚠️ Optional | Mittel | Kann spaeter erweitert werden |

**Gesamtaufwand:** ~4h

---

## 3. Implementierungsplan

### Phase A: Browser-Isolation (★★★★☆)

#### A0: Browser-Session Konsolidierung (VORAUSSETZUNG)

**Problem:** Zwei konkurrierende globale Browser-Sessions muessen zu einer einzigen Quelle zusammengefuehrt werden, bevor Isolation aufgebaut werden kann.

**Aenderungen:**

| Datei | Aenderung |
|-------|-----------|
| `tools/shared_context.py` | `browser_session` Dict + `ensure_browser_initialized()` entfernen |
| `tools/browser_tool/tool.py` | `BrowserSession` wird zur einzigen Browser-Quelle |
| Abhaengige Tools | Imports von `shared_context.browser_session` auf `browser_tool` umleiten |

```python
# tools/shared_context.py - ENTFERNEN:
# browser_session = {"play": None, "browser_instance": None, ...}
# async def ensure_browser_initialized() -> Page: ...

# STATTDESSEN: Referenz auf den neuen PersistentContextManager
browser_context_manager: Optional["PersistentContextManager"] = None
```

**Vorgehen:**
1. Grep nach allen `shared_context.browser_session` und `shared_context.ensure_browser_initialized` Nutzungen
2. Alle auf `browser_tool.ensure_browser_initialized()` umleiten (oder spaeter auf PersistentContextManager)
3. Dict + Funktion aus `shared_context.py` entfernen

**Aufwand:** 1.5h

---

#### A1: PersistentContextManager erstellen

**Neue Datei:** `tools/browser_tool/persistent_context.py`

**Wichtig:** Verwendet `new_context()` + manuelles `storage_state()` Save/Load statt `launch_persistent_context()`, weil Timus **Firefox** nutzt und `launch_persistent_context` nur mit Chromium stabil funktioniert.

```python
"""
Persistent Browser Context Manager - Session-Isolierung mit Cookie-Persistence.

Ansatz: new_context() + storage_state() (Firefox-kompatibel)
NICHT launch_persistent_context() (nur Chromium).

Features:
- Pro-Session isolierte Browser-Contexts
- Persistent Storage (Cookies, LocalStorage) via storage_state JSON
- Context-Pooling mit MAX_CONTEXTS Limit
- Automatisches Cleanup nach Session-Timeout
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

log = logging.getLogger("PersistentContextManager")

MAX_CONTEXTS = 5
SESSION_TIMEOUT_MINUTES = 60

@dataclass
class SessionContext:
    """Isolierte Browser-Session mit persistentem State."""
    session_id: str
    context: BrowserContext
    page: Page
    storage_path: Path
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)

class PersistentContextManager:
    """Verwaltet isolierte, persistente Browser-Contexts."""

    def __init__(self, base_storage_dir: Path = None):
        self.base_storage_dir = base_storage_dir or Path("data/browser_contexts")
        self.base_storage_dir.mkdir(parents=True, exist_ok=True)
        self.contexts: Dict[str, SessionContext] = {}
        self._playwright = None
        self._browser: Optional[Browser] = None

    async def initialize(self):
        """Startet Playwright und Browser (einmalig)."""
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.firefox.launch(headless=True)
        log.info("PersistentContextManager initialisiert (Firefox)")

    async def get_or_create_context(
        self,
        session_id: str = "default"
    ) -> SessionContext:
        """Holt existierenden oder erstellt neuen Context."""
        # Existierenden Context zurueckgeben
        if session_id in self.contexts:
            ctx = self.contexts[session_id]
            ctx.last_used = datetime.now()
            return ctx

        # Context-Limit pruefen, aeltesten evicten
        if len(self.contexts) >= MAX_CONTEXTS:
            await self._evict_oldest_context()

        # Storage-Pfad vorbereiten
        storage_dir = self.base_storage_dir / session_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_file = storage_dir / "storage.json"

        # Context erstellen - MIT storage_state nur wenn Datei existiert
        context_kwargs = {}
        if storage_file.exists():
            context_kwargs["storage_state"] = str(storage_file)
            log.info(f"Session '{session_id}': Lade gespeicherten State")

        context = await self._browser.new_context(**context_kwargs)
        page = await context.new_page()

        session = SessionContext(
            session_id=session_id,
            context=context,
            page=page,
            storage_path=storage_dir
        )
        self.contexts[session_id] = session
        log.info(f"Session '{session_id}': Neuer Context erstellt")
        return session

    async def save_context_state(self, session_id: str) -> bool:
        """Speichert Cookies/LocalStorage fuer spaetere Wiederherstellung."""
        if session_id not in self.contexts:
            return False
        ctx = self.contexts[session_id]
        storage_file = ctx.storage_path / "storage.json"
        await ctx.context.storage_state(path=str(storage_file))
        log.info(f"Session '{session_id}': State gespeichert")
        return True

    async def close_context(self, session_id: str, save_state: bool = True):
        """Schliesst einen Context und speichert optional den State."""
        if session_id not in self.contexts:
            return
        ctx = self.contexts[session_id]
        if save_state:
            await self.save_context_state(session_id)
        await ctx.context.close()
        del self.contexts[session_id]
        log.info(f"Session '{session_id}': Context geschlossen")

    async def _evict_oldest_context(self):
        """Entfernt den aeltesten ungenutzten Context."""
        if not self.contexts:
            return
        oldest_id = min(self.contexts, key=lambda k: self.contexts[k].last_used)
        if oldest_id != "default":  # Default nie evicten
            await self.close_context(oldest_id, save_state=True)

    async def cleanup_expired(self):
        """Entfernt abgelaufene Sessions."""
        now = datetime.now()
        expired = [
            sid for sid, ctx in self.contexts.items()
            if (now - ctx.last_used) > timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            and sid != "default"
        ]
        for sid in expired:
            await self.close_context(sid, save_state=True)

    async def shutdown(self):
        """Speichert alle States und faehrt herunter."""
        for session_id in list(self.contexts.keys()):
            await self.close_context(session_id, save_state=True)
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        log.info("PersistentContextManager heruntergefahren")

    def get_status(self) -> dict:
        """Gibt Status aller aktiven Sessions zurueck."""
        return {
            "active_contexts": len(self.contexts),
            "max_contexts": MAX_CONTEXTS,
            "sessions": {
                sid: {
                    "created_at": ctx.created_at.isoformat(),
                    "last_used": ctx.last_used.isoformat(),
                    "has_saved_state": (ctx.storage_path / "storage.json").exists()
                }
                for sid, ctx in self.contexts.items()
            }
        }
```

**Aufwand:** 1.5h

---

#### A2: BrowserSession Refactoring + Controller-Integration

**Aenderungen in:** `tools/browser_tool/tool.py`

Alle Browser-Tools bekommen einen optionalen `session_id` Parameter. Der globale `browser_session_manager` wird durch den `PersistentContextManager` aus `shared_context` ersetzt.

```python
# tools/browser_tool/tool.py

# ALT: browser_session_manager = BrowserSession()
# NEU: Nutzt shared_context.browser_context_manager

async def ensure_browser_initialized(session_id: str = "default") -> Page:
    """Stellt sicher dass ein Browser-Context fuer die Session existiert."""
    import tools.shared_context as shared_context
    manager = shared_context.browser_context_manager
    if not manager:
        raise RuntimeError("PersistentContextManager nicht initialisiert")
    session = await manager.get_or_create_context(session_id)
    return session.page

@tool(
    name="open_url",
    parameters=[
        P("url", "string", "Die zu oeffnende URL"),
        P("session_id", "string", "Browser-Session ID", default="default"),
    ]
)
async def open_url(url: str, session_id: str = "default") -> dict:
    page = await ensure_browser_initialized(session_id)
    # ... bestehende Logik mit page ...
```

**Aenderungen in:** `tools/browser_controller/controller.py`

Der HybridBrowserController muss `session_id` bei MCP-Calls durchreichen:

```python
class HybridBrowserController:
    def __init__(self, mcp_url: str = "http://127.0.0.1:5000",
                 headless: bool = True,
                 session_id: str = "default"):  # NEU
        self.session_id = session_id
        # ...

    async def navigate(self, url: str, wait_for_load: bool = True):
        result = await self._call_mcp_tool("open_url", {
            "url": url,
            "session_id": self.session_id  # NEU: durchreichen
        })
        # ...
```

**Aufwand:** 1.5h

---

#### A3: Retry-Logik & CAPTCHA-Detection

**Neue Datei:** `tools/browser_tool/retry_handler.py`

**Hinweis:** `open_url` in `browser_tool/tool.py` hat bereits eine einfache Cloudflare-Erkennung. Der RetryHandler erweitert dies um exponential backoff und zentrale Fehlerbehandlung.

```python
"""
Browser Retry Handler - Exponential Backoff und CAPTCHA-Erkennung.

Erweitert die bestehende Cloudflare-Detection in open_url um:
- Exponential Backoff bei Network-Fehlern
- Zentrale CAPTCHA-Heuristik
- Page-Recovery bei abgestuerzten Contexts
"""
import asyncio
import logging
from typing import Callable, Any, Optional

log = logging.getLogger("BrowserRetryHandler")

class BrowserRetryHandler:
    """Automatische Retry-Logik fuer Browser-Fehler."""

    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]  # Exponential Backoff in Sekunden

    CAPTCHA_INDICATORS = [
        "cf-browser-verification",
        "challenge-platform",
        "cf-turnstile",
        "recaptcha",
        "hcaptcha",
        "Checking if the site connection is secure",
        "Just a moment...",
        "Attention Required"
    ]

    async def execute_with_retry(
        self,
        action: Callable,
        *args,
        on_captcha: Optional[Callable] = None,
        **kwargs
    ) -> Any:
        """Fuehrt eine Browser-Aktion mit Retry-Logik aus."""
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                result = await action(*args, **kwargs)

                # CAPTCHA-Check auf dem Ergebnis
                if isinstance(result, dict) and self._is_captcha_blocked(result):
                    log.warning(f"CAPTCHA erkannt (Versuch {attempt + 1})")
                    if on_captcha:
                        return await on_captcha(result)
                    return {"error": "CAPTCHA detected", "captcha": True}

                return result

            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    log.warning(
                        f"Browser-Fehler (Versuch {attempt + 1}/{self.MAX_RETRIES}): {e}. "
                        f"Retry in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    log.error(f"Alle {self.MAX_RETRIES} Versuche fehlgeschlagen: {e}")

        return {"error": str(last_error), "retries_exhausted": True}

    def _is_captcha_blocked(self, result: dict) -> bool:
        """Prueft ob das Ergebnis auf eine CAPTCHA-Blockade hindeutet."""
        text = str(result.get("text", "") or result.get("content", "")).lower()
        return any(indicator.lower() in text for indicator in self.CAPTCHA_INDICATORS)

# Globale Instanz
retry_handler = BrowserRetryHandler()
```

**Aufwand:** 1h

---

### Phase B: Tool-Generierung aus Fehlern (★★★☆☆)

#### B1: `learn_new_skill()` erweitern statt neuen Agent

**Warum kein eigener SkillCreatorAgent:**
`BaseAgent` hat den vollen Agent-Loop mit Vision, Screenshots, ROI, Lane-Management etc. - massiver Overhead fuer reine Code-Generierung. Die bestehende `learn_new_skill()` Funktion im `skill_manager_tool` ruft bereits `implement_feature` (Inception/Mercury-Coder) auf und ist der richtige Erweiterungspunkt.

**Aenderungen in:** `tools/skill_manager_tool/tool.py`

```python
# Neue Funktion: Tool-Generierung mit Quality-Gate

async def create_tool_from_pattern(
    pattern_description: str,
    source_task: str,
    improvements: list
) -> dict:
    """
    Generiert ein neues Tool aus einem erkannten Fehler-Pattern.

    Quality-Gate:
    1. Duplikat-Check gegen bestehende Skills
    2. Code-Generierung via implement_feature
    3. AST-Validierung vor Registrierung
    4. Registrierung nur bei bestandener Validierung
    """
    import ast

    # 1. Duplikat-Check
    existing_skills = _list_skills_sync()
    skill_name = _sanitize_skill_name(pattern_description)

    for skill in existing_skills:
        if skill_name in skill.get("name", ""):
            return {"skipped": True, "reason": f"Skill '{skill_name}' existiert bereits"}

    # 2. Code generieren via implement_feature
    description = (
        f"Erstelle ein Python-Tool das folgendes Problem loest:\n"
        f"Pattern: {pattern_description}\n"
        f"Verbesserungen: {', '.join(improvements)}\n"
        f"Quelle: {source_task}"
    )

    result = await call_tool_internal("implement_feature", {
        "feature_description": description,
        "target_file": f"skills/{skill_name}_skill.py"
    })

    if not result or result.get("error"):
        return {"error": "Code-Generierung fehlgeschlagen", "detail": result}

    # 3. AST-Validierung
    skill_path = SKILLS_DIR / f"{skill_name}_skill.py"
    if skill_path.exists():
        code = skill_path.read_text()
        try:
            ast.parse(code)
        except SyntaxError as e:
            skill_path.unlink()  # Fehlerhaften Code entfernen
            return {"error": f"Generierter Code hat Syntax-Fehler: {e}"}

    # 4. Tool registrieren
    register_result = await call_tool_internal(
        "register_new_tool_in_server",
        {"tool_module_path": f"skills.{skill_name}_skill"}
    )

    return {
        "success": True,
        "skill_name": skill_name,
        "path": str(skill_path),
        "registered": bool(register_result)
    }
```

**Aufwand:** 2h

---

#### B2: Reflection-Skill Integration mit Safeguards

**Aenderungen in:** `memory/reflection_engine.py`

Die urspruengliche Bedingung (`what_failed >= 2`) war zu aggressiv - sie wuerde nach fast jeder fehlgeschlagenen Aufgabe einen Skill erstellen. Stattdessen:

1. **Pattern-Counter:** Gleiches Fehler-Pattern muss mindestens 3x auftreten
2. **Duplikat-Check:** Vor Erstellung pruefen ob Skill schon existiert
3. **Cooldown:** Max 1 Skill-Erstellung pro Stunde

```python
# memory/reflection_engine.py - Neue Felder und Methoden

class ReflectionEngine:
    def __init__(self, memory_manager=None, llm_client=None):
        # ... bestehende Felder ...
        self._pattern_counter: Dict[str, int] = {}  # pattern_hash -> count
        self._last_skill_creation: Optional[datetime] = None
        self._skill_creation_cooldown = timedelta(hours=1)

    async def _store_learnings(self, reflection: ReflectionResult, task: Dict):
        # ... bestehender Code ...

        # NEU: Skill-Trigger mit Safeguards
        if self._should_create_tool(reflection):
            await self._trigger_tool_creation(reflection, task)

    def _should_create_tool(self, reflection: ReflectionResult) -> bool:
        """
        Bestimmt ob ein neues Tool erstellt werden soll.

        Safeguards:
        - Pattern muss mindestens 3x aufgetreten sein
        - Cooldown von 1h zwischen Skill-Erstellungen
        - Mindestens 2 Fehler UND Verbesserungsvorschlaege
        - Confidence >= 0.7
        """
        if not reflection.what_failed or not reflection.improvements:
            return False

        if reflection.confidence < 0.7:
            return False

        # Cooldown pruefen
        if self._last_skill_creation:
            if datetime.now() - self._last_skill_creation < self._skill_creation_cooldown:
                return False

        # Pattern-Haeufigkeit pruefen
        pattern_key = self._get_pattern_hash(reflection.what_failed)
        self._pattern_counter[pattern_key] = self._pattern_counter.get(pattern_key, 0) + 1

        return self._pattern_counter[pattern_key] >= 3

    def _get_pattern_hash(self, failures: List[str]) -> str:
        """Erzeugt stabilen Hash fuer ein Fehler-Pattern."""
        import hashlib
        normalized = sorted([f.lower().strip() for f in failures])
        return hashlib.md5("|".join(normalized).encode()).hexdigest()[:12]

    async def _trigger_tool_creation(self, reflection: ReflectionResult, task: Dict):
        """Delegiert Tool-Erstellung an skill_manager_tool."""
        try:
            # Lazy import um zirkulaere Abhaengigkeiten zu vermeiden
            from tools.skill_manager_tool.tool import create_tool_from_pattern

            result = await create_tool_from_pattern(
                pattern_description="; ".join(reflection.what_failed[:3]),
                source_task=self._format_task(task),
                improvements=reflection.improvements[:3]
            )

            if result and result.get("success"):
                self._last_skill_creation = datetime.now()
                log.info(f"Neues Tool erstellt: {result.get('skill_name')}")
            elif result and result.get("skipped"):
                log.debug(f"Tool-Erstellung uebersprungen: {result.get('reason')}")
            else:
                log.warning(f"Tool-Erstellung fehlgeschlagen: {result}")

        except Exception as e:
            log.debug(f"Tool-Erstellung nicht moeglich: {e}")
```

**Aufwand:** 1.5h

---

#### B3: Skill-Templates (Optional)

**Neue Datei:** `skills/templates/ui_patterns.py`

Vordefinierte Templates fuer haeufige UI-Situationen. Werden vom Tool-Generator als Referenz verwendet.

```python
"""
UI Pattern Templates - Wiederverwendbare Patterns fuer haeufige UI-Situationen.

Diese Templates dienen als Vorlage fuer automatisch generierte Tools.
Der SkillManager kann sie als Kontext an implement_feature uebergeben.
"""

TEMPLATES = {
    "calendar_picker": {
        "description": "Datum aus einem Calendar-Widget auswaehlen",
        "pattern": "Calendar Navigation + Date Selection",
        "tools_needed": ["click_by_selector", "get_text"],
    },
    "modal_handler": {
        "description": "Modal-Dialoge behandeln (Cookie, Newsletter, Age-Verification)",
        "pattern": "Modal Detection + Button Click + Dismiss",
        "tools_needed": ["dismiss_overlays", "click_by_text"],
    },
    "form_filler": {
        "description": "Formulare automatisch ausfuellen",
        "pattern": "Field Detection + Type + Submit",
        "tools_needed": ["type_text", "click_by_selector"],
    },
    "infinite_scroll": {
        "description": "Infinite-Scroll Seiten vollstaendig laden",
        "pattern": "Scroll + Wait + Check for new content",
        "tools_needed": ["scroll", "get_text"],
    },
}

def get_template(pattern_name: str) -> dict:
    """Gibt ein Template zurueck falls vorhanden."""
    return TEMPLATES.get(pattern_name)

def find_matching_template(description: str) -> list:
    """Findet passende Templates basierend auf Beschreibung."""
    matches = []
    lower = description.lower()
    for name, template in TEMPLATES.items():
        if any(word in lower for word in template["description"].lower().split()):
            matches.append({"name": name, **template})
    return matches
```

**Aufwand:** 0.5h

---

## 4. Integration in MCP Server

### Startup-Erweiterung

```python
# server/mcp_server.py - lifespan()

# === BROWSER CONTEXT MANAGER ===
try:
    from tools.browser_tool.persistent_context import PersistentContextManager
    shared_context.browser_context_manager = PersistentContextManager()
    await shared_context.browser_context_manager.initialize()
    log.info("Browser PersistentContextManager initialisiert")
except Exception as e:
    log.warning(f"PersistentContextManager konnte nicht gestartet werden: {e}")

# ... yield (Server laeuft) ...

# === SHUTDOWN: Browser Contexts speichern ===
if hasattr(shared_context, 'browser_context_manager') and shared_context.browser_context_manager:
    await shared_context.browser_context_manager.shutdown()
    log.info("Browser-Contexts gespeichert und geschlossen")
```

---

## 5. Zeitplan

| Phase | Aufgabe | Dauer | Abhaengigkeit |
|-------|---------|-------|---------------|
| **A0** | Browser-Session Konsolidierung | 1.5h | - |
| **A1** | PersistentContextManager | 1.5h | A0 |
| **A2** | BrowserSession + Controller Refactoring | 1.5h | A1 |
| **A3** | Retry-Logik & CAPTCHA | 1h | A1 |
| **B1** | `learn_new_skill()` erweitern + Quality-Gate | 2h | - |
| **B2** | Reflection-Skill Integration mit Safeguards | 1.5h | B1 |
| **B3** | Skill-Templates (Optional) | 0.5h | - |
| **Integration** | MCP-Server + Tests | 1.5h | A0-A3, B1-B2 |
| **Gesamt** | | **~11h** | |

---

## 6. Priorisierung

### Empfohlene Reihenfolge:

1. **A0 (Session-Konsolidierung)** - Voraussetzung fuer alles
   - Entfernt die doppelte Browser-Session
   - Schafft saubere Grundlage

2. **A1-A3 (Browser-Isolation)** - Hoher Impact
   - Sofortiger Nutzen: Persistente Cookies, weniger Abstuerze
   - Deterministisches Verhalten bei Tests

3. **B1-B2 (Tool-Generierung)** - Mittlerer Impact
   - Langfristiger Nutzen: Selbstverbesserung
   - Safeguards verhindern Skill-Spam

4. **B3 (Templates)** - Optional, kann spaeter erweitert werden

---

## 7. Risiken & Mitigation

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| Breaking Changes bei A0 | Mittel | Alle `shared_context.browser_session` Nutzer vorher identifizieren |
| Browser-Context Disk-Leak | Mittel | `cleanup_expired()` im Scheduler-Heartbeat |
| Generierter Skill-Code fehlerhaft | Mittel | AST-Validierung + Sandbox-Test vor Registrierung |
| Skill-Spam durch zu aggressive Trigger | Niedrig | Pattern-Counter (3x) + Cooldown (1h) |
| CAPTCHA-Falsch-Positive | Niedrig | Manual-Override Flag |
| Parallel Contexts Memory | Mittel | MAX_CONTEXTS=5 + Eviction-Policy |
| Firefox storage_state Inkompatibilitaet | Niedrig | `new_context()` statt `launch_persistent_context()` |

---

## 8. Aenderungen gegenueber Plan v1.0

| Punkt | v1.0 (Alt) | v2.0 (Korrigiert) | Grund |
|-------|-----------|-------------------|-------|
| Browser-Sessions | Ignoriert doppelte Sessions | **A0: Konsolidierung zuerst** | Zwei globale Sessions wuerden zu drei werden |
| Persistent Context | `launch_persistent_context()` | `new_context()` + `storage_state()` | Firefox-Kompatibilitaet |
| HybridBrowserController | Nicht erwaehnt | **A2 erweitert:** session_id durchreichen | Controller delegiert via MCP, braucht session_id |
| SkillCreatorAgent | Neuer Agent (BaseAgent) | **Kein Agent:** `learn_new_skill()` erweitern | BaseAgent hat zu viel Overhead (Vision, ROI, Lanes) |
| Skill-Trigger | `what_failed >= 2` | **Pattern 3x + Cooldown 1h + Duplikat-Check** | Zu aggressiv, wuerde nach fast jedem Fehler triggern |
| Skill-Typ | Unklar (Python vs YAML) | **Python-Tools** via tool_registry_v2 | Maechtiger als YAML-Steps, direkt als MCP-Tool nutzbar |
| Quality-Gate | Nur "LLM-Validierung" | **AST-Parse + Duplikat-Check** | Konkrete Validierung statt vager Beschreibung |
| Zeitschaetzung | 9h | **~11h** | A0 + erweiterte Safeguards |

---

## 9. Fazit

**Beide Features sind machbar** und passen zur Timus-Architektur, benoetigen aber die identifizierten Korrekturen:

- **Browser-Isolation:** Setzt Browser-Session-Konsolidierung (A0) voraus, nutzt `new_context()` statt `launch_persistent_context()` fuer Firefox-Kompatibilitaet
- **Tool-Generierung:** Erweitert bestehenden `skill_manager_tool` statt neuen Agent, mit Pattern-Counter und Quality-Gate als Safeguards

**Empfehlung:** Phase A (A0 → A1 → A2 → A3) zuerst, dann Phase B (B1 → B2 → B3).
