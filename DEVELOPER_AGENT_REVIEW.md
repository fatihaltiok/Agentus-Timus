# Developer Agent (D.A.V.E.) - Code Review
**Datum:** 27. Januar 2026
**Reviewer:** Claude Sonnet 4.5
**Datei:** `agent/developer_agent.py`

---

## ⭐ GESAMTBEWERTUNG: 7/10

**Gut für:** Schnelle Code-Generierung mit Inception API
**Nicht gut für:** Komplexe Multi-Step Entwicklung, Code-Validierung

---

## ✅ STÄRKEN (Was gut funktioniert)

### 1. Klare Spezialisierung ⭐⭐⭐⭐⭐
- Fokussiert auf `implement_feature` (Inception Tool)
- Single-Responsibility Principle
- Keine Feature-Bloat

### 2. Robuste Fehlerbehandlung ⭐⭐⭐⭐
- `inception_ready()` Preflight-Check
- Retry-Logik mit `failures` Counter
- `REQUIRE_INCEPTION` Flag für strikte Kontrolle

### 3. Strukturierter ReAct-Loop ⭐⭐⭐⭐⭐
- Klares Pattern: Thought → Action → Observation
- LLM bekommt strukturierte Anweisungen
- Observations werden sauber zurückgegeben

### 4. Learning Integration ⭐⭐⭐⭐
- `log_learning_entry()` bei Erfolg UND Misserfolg
- Ermöglicht kontinuierliche Verbesserung
- Wichtig für langfristige Performance

### 5. Flexible LLM-Unterstützung ⭐⭐⭐⭐
- GPT-5 und GPT-4o Support
- Korrekte Token-Parameter (`max_completion_tokens` vs. `max_tokens`)
- Konfigurierbar via `.env`

---

## ⚠️ SCHWÄCHEN (Was verbessert werden sollte)

### 1. ZU EINGESCHRÄNKT ❌ (Kritisch)

**Problem:**
```python
if method != "implement_feature" and REQUIRE_INCEPTION:
    return "Dieser Agent erfordert implement_feature..."
```

Agent kann nur Code generieren, aber nicht:
- ❌ Dateien lesen (für Kontext)
- ❌ Projektstruktur analysieren
- ❌ Dependencies prüfen
- ❌ Tests ausführen
- ❌ Code validieren

**Impact:** Niedrige Code-Qualität, fehlender Kontext

**Lösung:**
```python
ALLOWED_TOOLS = [
    "implement_feature",   # Code generieren
    "read_file_content",   # Kontext sammeln
    "list_agent_files",    # Projektstruktur
    "run_tests",           # Validierung
    "syntax_check",        # Syntax-Prüfung
]

# Im Loop:
if method not in ALLOWED_TOOLS:
    return f"Tool nicht erlaubt. Nutze: {', '.join(ALLOWED_TOOLS)}"
```

---

### 2. KEINE CODE-VALIDIERUNG ⚠️ (Hoch)

**Problem:**
```python
# Zeilen 262-277
if generated and target:
    call_tool("write_file", {"path": target, "content": generated})
    return final  # Direkt geschrieben, ohne Prüfung!
```

- Syntax-Fehler werden nicht erkannt
- Keine Tests vor dem Schreiben
- Kein Code-Review
- Direkt in Produktion

**Impact:** Fehlerhafte Dateien im Repository

**Lösung:**
```python
if generated and target:
    # 1. Syntax-Check
    syntax_result = call_tool("syntax_check", {
        "code": generated,
        "language": "python"
    })

    if not syntax_result.get("valid"):
        failures += 1
        messages.append({
            "role": "user",
            "content": f"Observation: Syntax-Fehler: {syntax_result.get('errors')}"
        })
        continue

    # 2. Tests (falls vorhanden)
    test_result = call_tool("run_tests", {
        "file": target,
        "dry_run": True  # Mit generiertem Code
    })

    # 3. Erst dann schreiben
    if syntax_result["valid"] and test_result.get("success", True):
        call_tool("write_file", {"path": target, "content": generated})
        return f"✅ Datei '{target}' erstellt und validiert."
    else:
        failures += 1
        messages.append({
            "role": "user",
            "content": f"Observation: Tests fehlgeschlagen: {test_result}"
        })
```

---

### 3. AUTOMATISCHES SCHREIBEN ⚠️ (Mittel)

**Problem:**
```python
# Zeilen 256-299: Agent entscheidet SELBST zu schreiben
# LLM verliert Kontrolle über den Workflow!
if generated and target:
    wr = call_tool("write_file", ...)
    return final  # Loop bricht ab, LLM kann nicht mehr reagieren
```

- LLM könnte weitere Schritte planen wollen
- Keine Bestätigung durch LLM
- Agent übernimmt eigenständig
- Workflow-Flexibilität verloren

**Impact:** Reduzierte Kontrolle, keine Multi-Step-Workflows möglich

**Lösung:**
```python
# Option A: Nur Feedback geben, LLM entscheidet
if generated and target:
    messages.append({
        "role": "user",
        "content": f"Observation: {json.dumps({
            'success': True,
            'generated_code': generated[:200] + '...',  # Preview
            'file_path': target,
            'next_step': 'Nutze write_file um zu speichern, oder request_review für Review'
        })}"
    })
    # Lass LLM entscheiden ob/wann geschrieben wird
    continue  # Loop weiterlaufen lassen

# Option B: Explizite Bestätigung erforderlich
if generated and target:
    confirm = call_tool("ask_user_confirmation", {
        "message": f"Code für '{target}' generiert. Schreiben?",
        "preview": generated[:500]
    })

    if confirm.get("approved"):
        call_tool("write_file", ...)
    else:
        messages.append({"role": "user", "content": "Nutzer hat abgelehnt. Überarbeiten?"})
```

---

### 4. WENIG PROJEKT-KONTEXT ⚠️ (Mittel)

**Problem:**
```python
# System-Prompt Zeile 64:
"context_file_path": "<optional>"  # Nur EINE Datei, optional!
```

Agent kennt nicht:
- ❌ Projektstruktur (welche Dateien existieren?)
- ❌ Dependencies (welche Bibliotheken verfügbar?)
- ❌ Coding-Style (PEP8, Black, Ruff?)
- ❌ Bestehende Patterns (wie sehen ähnliche Dateien aus?)
- ❌ Tests (wo sind sie, wie laufen sie?)

**Impact:** Inkonsistenter Code, falsche Dependencies, Style-Violations

**Lösung:**
```python
def gather_project_context(dest_folder: str) -> str:
    """Sammelt umfassenden Projekt-Kontext."""
    context_parts = []

    # 1. Projektstruktur (wichtige Dateien)
    structure = call_tool("list_agent_files", {
        "path": dest_folder,
        "pattern": "*.py",
        "max_depth": 3
    })
    context_parts.append(f"## Projektstruktur:\n{structure}")

    # 2. Dependencies
    deps_files = ["requirements.txt", "pyproject.toml", "setup.py"]
    for dep_file in deps_files:
        dep_path = f"{dest_folder}/{dep_file}"
        deps = call_tool("read_file_content", {"path": dep_path})
        if not deps.get("error"):
            context_parts.append(f"## Dependencies ({dep_file}):\n{deps}")

    # 3. Coding Style (wenn vorhanden)
    style_files = [".pylintrc", "pyproject.toml", ".flake8"]
    for style_file in style_files:
        style = call_tool("read_file_content", {"path": f"{dest_folder}/{style_file}"})
        if not style.get("error"):
            context_parts.append(f"## Style Config ({style_file}):\n{style}")

    # 4. Ähnliche bestehende Dateien (Patterns lernen)
    similar = call_tool("find_similar_files", {
        "path": dest_folder,
        "pattern": "*.py",
        "limit": 3
    })
    if similar:
        context_parts.append(f"## Bestehende Code-Patterns:\n{similar}")

    # 5. Tests (wo sind sie?)
    tests = call_tool("list_agent_files", {
        "path": f"{dest_folder}/tests",
        "pattern": "test_*.py"
    })
    if tests:
        context_parts.append(f"## Vorhandene Tests:\n{tests}")

    return "\n\n".join(context_parts)

# Im System-Prompt:
SYSTEM_PROMPT = f"""Du bist D.A.V.E., ein Dev-Agent.

PROJEKT-KONTEXT:
{gather_project_context(dest_folder)}

Nutze diesen Kontext um:
- Konsistenten Code-Style einzuhalten
- Richtige Dependencies zu verwenden
- Bestehende Patterns zu folgen
- Tests im richtigen Format zu schreiben
"""
```

---

### 5. KEINE FEHLER-RECOVERY ⚠️ (Niedrig)

**Problem:**
```python
if failures >= 3:
    return "Ich konnte die Aufgabe nicht abschließen..."
    # Game Over, keine Alternativen versucht
```

- Bei 3 Fehlern: Aufgabe abgebrochen
- Keine alternativen Strategien
- Kein Debugging-Versuch
- Keine Analyse WARUM es fehlschlug

**Impact:** Niedrige Erfolgsrate bei komplexen Aufgaben

**Lösung:**
```python
if failures >= 2:
    # Strategie-Wechsel bei wiederholten Fehlern
    logger.warning("⚠️ Mehrere Fehler - wechsle Strategie")

    # Analyse des Problems
    error_analysis = analyze_failure_pattern(messages)

    # Neue Strategie basierend auf Fehler-Typ
    if "syntax" in error_analysis.lower():
        strategy = """
        Neuer Ansatz:
        1. Generiere kleinere Code-Snippets (< 50 Zeilen)
        2. Prüfe Syntax nach jedem Snippet
        3. Inkrementell zusammensetzen
        """
    elif "context" in error_analysis.lower():
        strategy = """
        Neuer Ansatz:
        1. Mehr Kontext sammeln (read_file_content)
        2. Projektstruktur analysieren
        3. Mit mehr Information neu versuchen
        """
    else:
        strategy = """
        Neuer Ansatz:
        1. Aufgabe in Teilschritte zerlegen
        2. Jeden Schritt einzeln testen
        3. Debug-Informationen sammeln
        """

    messages.append({
        "role": "user",
        "content": f"Fehler-Analyse: {error_analysis}\n\n{strategy}"
    })

    failures = 0  # Reset nach Strategie-Wechsel
    continue

if failures >= 5:
    # Nur nach Strategie-Wechsel und weiteren Fehlern
    return "Aufgabe zu komplex, mehrere Strategien fehlgeschlagen."
```

---

### 6. HARDCODED SYSTEM-PROMPT ⚠️ (Niedrig)

**Problem:**
```python
SYSTEM_PROMPT = """Du bist D.A.V.E., ein Dev-Agent..."""
# Nicht erweiterbar, nicht anpassbar, nicht projekt-spezifisch
```

- Ein Prompt für alle Projekte
- Keine Anpassung an Coding-Style
- Keine Projekt-spezifischen Anweisungen
- Schwer zu testen/iterieren

**Impact:** Suboptimale Code-Generierung

**Lösung:**
```python
def build_system_prompt(
    allowed_tools: List[str],
    coding_style: str = "PEP8",
    project_context: str = "",
    examples: List[str] = []
) -> str:
    """Dynamischer System-Prompt basierend auf Projekt."""

    tools_desc = "\n".join([f"- {tool}" for tool in allowed_tools])

    examples_section = ""
    if examples:
        examples_section = "\n\nBEISPIELE:\n" + "\n---\n".join(examples)

    return f"""Du bist D.A.V.E., ein spezialisierter Dev-Agent.

VERFÜGBARE TOOLS:
{tools_desc}

CODING STYLE: {coding_style}
- Befolge {coding_style} Konventionen strikt
- Nutze Type Hints (Python 3.10+)
- Docstrings für alle Funktionen
- Comprehensive Error Handling

PROJEKT-KONTEXT:
{project_context}

WORKFLOW (IMMER in dieser Reihenfolge):
1. Kontext sammeln (read_file_content, list_agent_files)
2. Bestehende Patterns analysieren
3. Code generieren (implement_feature)
4. Syntax validieren (syntax_check)
5. Tests erstellen/ausführen (run_tests)
6. Review & Schreiben (write_file)
7. Finalisieren

WICHTIG:
- Niemals direkt schreiben ohne Validierung
- Immer Tests schreiben
- Bestehende Patterns befolgen
- Bei Unsicherheit: Mehr Kontext sammeln

{examples_section}

ANTWORTFORMAT:
Thought: <Plan>
Action: {{"method": "...", "params": {{...}}}}
"""

# Verwendung:
SYSTEM_PROMPT = build_system_prompt(
    allowed_tools=ALLOWED_TOOLS,
    coding_style="PEP8 + Black",
    project_context=gather_project_context(dest_folder),
    examples=load_code_examples(dest_folder)
)
```

---

## 🎯 PRIORISIERTE VERBESSERUNGEN

### 🔴 KRITISCH (Sofort umsetzen)

1. **Multi-Tool Support** - Agent muss mehr als nur `implement_feature` nutzen können
   - Mindestens: `read_file_content`, `list_agent_files`, `syntax_check`
   - Ermöglicht: Kontext-Sammlung, Validierung, bessere Entscheidungen

2. **Code-Validierung** - Vor dem Schreiben IMMER validieren
   - Syntax-Check (Python AST)
   - Tests ausführen (falls vorhanden)
   - Style-Check (Black, Ruff)

### 🟡 HOCH (Diese Woche)

3. **Projekt-Kontext-Sammlung** - Agent braucht mehr Informationen
   - Projektstruktur, Dependencies, Style-Guides
   - Bestehende Code-Patterns
   - Test-Setup

4. **LLM-Kontrolle beibehalten** - Nicht automatisch schreiben
   - Observations zurückgeben
   - LLM entscheiden lassen WANN geschrieben wird
   - Ermöglicht Multi-Step-Workflows

### 🟢 MITTEL (Nächster Sprint)

5. **Fehler-Recovery** - Strategien bei wiederholten Fehlern
   - Fehler-Analyse
   - Alternative Ansätze
   - Inkrementelle Teilschritte

6. **Dynamischer System-Prompt** - Projekt-spezifisch anpassen
   - Coding-Style aus Projekt lesen
   - Beispiele aus bestehendem Code
   - Tool-Liste anpassbar

### 🔵 NIEDRIG (Nice to have)

7. **Interaktive Rückfragen** - Bei Unklarheiten nachfragen
8. **Code-Review Phase** - Vor Schreiben Review anfordern
9. **Performance-Tracking** - Erfolgsraten messen
10. **A/B Testing** - Verschiedene Prompts vergleichen

---

## 📝 IMPLEMENTIERUNGS-BEISPIEL

### Verbesserter Developer Agent (Konzept):

```python
class ImprovedDeveloperAgent:
    """
    Verbesserter Developer Agent mit:
    - Multi-Tool Support
    - Code-Validierung
    - Kontext-Sammlung
    - Fehler-Recovery
    """

    ALLOWED_TOOLS = [
        "implement_feature",   # Code generieren
        "read_file_content",   # Dateien lesen
        "list_agent_files",    # Projektstruktur
        "syntax_check",        # Validierung
        "run_tests",           # Tests
        "write_file",          # Schreiben (nach Validierung)
    ]

    def __init__(self, dest_folder: str):
        self.dest_folder = dest_folder
        self.context = self.gather_context()
        self.system_prompt = self.build_prompt()

    def gather_context(self) -> str:
        """Sammelt umfassenden Projekt-Kontext."""
        return gather_project_context(self.dest_folder)

    def build_prompt(self) -> str:
        """Erstellt dynamischen System-Prompt."""
        return build_system_prompt(
            allowed_tools=self.ALLOWED_TOOLS,
            project_context=self.context,
            coding_style=self.detect_coding_style()
        )

    def validate_code(self, code: str, target: str) -> Tuple[bool, str]:
        """Validiert generierten Code."""
        # 1. Syntax
        syntax = call_tool("syntax_check", {"code": code})
        if not syntax.get("valid"):
            return False, f"Syntax-Fehler: {syntax.get('errors')}"

        # 2. Style
        style = call_tool("style_check", {"code": code, "rules": "PEP8"})
        if not style.get("compliant"):
            return False, f"Style-Violations: {style.get('issues')}"

        # 3. Tests (wenn vorhanden)
        tests = call_tool("run_tests", {"file": target, "dry_run": True})
        if tests.get("failed", 0) > 0:
            return False, f"Tests fehlgeschlagen: {tests.get('failures')}"

        return True, "✅ Code validiert"

    def run_task(self, user_query: str, max_steps: int = 10) -> str:
        """Führt Entwicklungsaufgabe aus."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_query}
        ]

        failures = 0
        for step in range(1, max_steps + 1):
            reply = chat(messages)
            messages.append({"role": "assistant", "content": reply})

            if "Final Answer:" in reply:
                return reply.split("Final Answer:", 1)[1].strip()

            action, err = extract_action_json(reply)
            if err or not action:
                failures += 1
                messages.append({
                    "role": "user",
                    "content": f"Observation: {json.dumps({'error': err})}"
                })
                continue

            method = action["method"]
            params = action.get("params", {})

            # Tool-Whitelist prüfen
            if method not in self.ALLOWED_TOOLS:
                failures += 1
                messages.append({
                    "role": "user",
                    "content": f"Observation: Tool '{method}' nicht erlaubt. Nutze: {self.ALLOWED_TOOLS}"
                })
                continue

            # Tool ausführen
            obs = call_tool(method, params)

            # Spezial-Handling für Code-Generierung
            if method == "implement_feature" and not obs.get("error"):
                generated = obs.get("generated_code")
                target = obs.get("file_path")

                if generated and target:
                    # VALIDIEREN statt direkt schreiben!
                    valid, validation_msg = self.validate_code(generated, target)

                    if not valid:
                        failures += 1
                        messages.append({
                            "role": "user",
                            "content": f"Observation: {json.dumps({
                                'validation_failed': True,
                                'reason': validation_msg,
                                'suggestion': 'Überarbeite den Code und berücksichtige die Fehler'
                            })}"
                        })
                        continue
                    else:
                        # Validierung OK - LLM kann entscheiden zu schreiben
                        obs["validation"] = validation_msg
                        obs["ready_to_write"] = True

            # Observation zurückgeben
            messages.append({
                "role": "user",
                "content": f"Observation: {json.dumps(obs)}"
            })

            # Fehler-Recovery
            if failures >= 2:
                strategy = self.analyze_and_pivot(messages)
                messages.append({
                    "role": "user",
                    "content": f"Strategie-Wechsel: {strategy}"
                })
                failures = 0

        return "⚠️ Max steps erreicht"
```

---

## 📊 ZUSAMMENFASSUNG

### Was funktioniert gut:
✅ Klare Spezialisierung (Inception/implement_feature)
✅ Robuste Fehlerbehandlung mit Preflight-Checks
✅ Strukturierter ReAct-Loop
✅ Learning Integration für kontinuierliche Verbesserung
✅ Flexible LLM-Unterstützung (GPT-5, GPT-4o)

### Was sollte verbessert werden:
❌ Nur ein Tool erlaubt → Multi-Tool Support nötig
❌ Keine Code-Validierung → Syntax/Style/Tests vor Schreiben
❌ Automatisches Schreiben → LLM-Kontrolle beibehalten
❌ Wenig Kontext → Projektstruktur/Dependencies/Patterns sammeln
❌ Keine Fehler-Recovery → Strategien bei wiederholten Fehlern
❌ Hardcoded Prompt → Dynamisch & projekt-spezifisch

### Gesamturteil:
**Guter Start, aber zu eingeschränkt für produktive Nutzung.**
Mit den vorgeschlagenen Verbesserungen könnte dies ein **hervorragender** Developer-Agent werden!

---

**Nächste Schritte:**
1. Multi-Tool Support implementieren (read_file_content, syntax_check)
2. Code-Validierungs-Pipeline hinzufügen
3. Projekt-Kontext-Sammlung integrieren
4. Tests schreiben für den Agent selbst

---

**Ende der Review**
