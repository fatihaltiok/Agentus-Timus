# Timus System Inventory
**Datum:** 2026-02-10
**Status:** Vor DOM-First Refactoring

---

## 🔧 Vorhandene Tools (49 Total)

### ✅ KRITISCH für DOM-First Browser Controller

| Tool | Funktion | Status | Nutzung |
|------|----------|--------|---------|
| **browser_tool** | Playwright Firefox, DOM-Zugriff, Cookie-Selectors | ✅ Vorhanden | **ERWEITERN für DOM-First** |
| **verification_tool** | Screenshot-Diff, UI-Stabilität, Fehler-Erkennung | ✅ Vorhanden | **BESSER INTEGRIEREN** |
| **som_tool** | Set-of-Mark UI-Erkennung (Moondream) | ✅ Vorhanden | Vision-Fallback |
| **mouse_tool** | PyAutoGUI Maus/Keyboard-Steuerung | ✅ Vorhanden | Fallback für non-DOM |
| **cookie_banner_tool** | Cookie-Banner Handling | ✅ Vorhanden | Auto-Integration |
| **screen_change_detector** | Screen-Änderungen erkennen | ✅ Vorhanden | State-Tracking |
| **decision_verifier** | Entscheidungs-Verifikation | ✅ Vorhanden | Fact-Checking |
| **validation_tool** | Validierung | ✅ Vorhanden | Post-Check |

### 🎨 Vision & UI Tools

| Tool | Funktion | Status |
|------|----------|--------|
| **qwen_vl_tool** | Qwen 2.5 VL (RTX 3090, 60s+ latency) | ✅ Vorhanden, LANGSAM |
| **moondream_tool** | Moondream Vision (legacy) | ⚠️ Legacy |
| **visual_agent_tool** | Visual Agent Wrapper | ✅ Vorhanden |
| **visual_grounding_tool** | Visual Grounding | ✅ Vorhanden |
| **visual_click_tool** | Visual Click Detection | ✅ Vorhanden |
| **visual_segmentation_tool** | Segmentierung | ✅ Vorhanden |
| **ocr_tool** | OCR (Text-Extraktion) | ✅ Vorhanden |
| **text_finder_tool** | Text auf Screen finden | ✅ Vorhanden |
| **icon_recognition_tool** | Icon-Erkennung | ✅ Vorhanden |
| **hybrid_detection_tool** | Hybrid Detection | ✅ Vorhanden |

### 🧠 Research & Reasoning

| Tool | Funktion | Status |
|------|----------|--------|
| **deep_research** | Web-Research (für Evidence Packs!) | ✅ Vorhanden, **ERWEITERN** |
| **fact_corroborator** | Fakten-Überprüfung | ✅ Vorhanden |
| **search_tool** | Web-Suche | ✅ Vorhanden |
| **document_parser** | Dokument-Parsing | ✅ Vorhanden |
| **summarizer** | Zusammenfassungen | ✅ Vorhanden |

### 🛠️ Development & System

| Tool | Funktion | Status |
|------|----------|--------|
| **developer_tool** | Code-Entwicklung | ✅ Vorhanden |
| **file_system_tool** | Dateisystem-Operationen | ✅ Vorhanden |
| **planner** | Multi-Step Planning, Skills | ✅ Vorhanden, **ERWEITERN** |
| **skill_manager_tool** | Skill-Verwaltung | ✅ Vorhanden |
| **skill_recorder** | Skill-Recording | ✅ Vorhanden |
| **init_skill_tool** | Skill-Initialisierung | ✅ Vorhanden |
| **memory_tool** | Memory-System | ✅ Vorhanden |

### 📊 Monitoring & Debug

| Tool | Funktion | Status |
|------|----------|--------|
| **system_monitor_tool** | System-Monitoring | ✅ Vorhanden |
| **debug_tool** | Debugging | ✅ Vorhanden |
| **timing_tool** | Performance-Timing | ✅ Vorhanden |
| **reflection_tool** | Reflexion | ✅ Vorhanden |
| **meta_tool** | Meta-Operationen | ✅ Vorhanden |
| **maintenance_tool** | Wartung | ✅ Vorhanden |

### 📄 Content & Output

| Tool | Funktion | Status |
|------|----------|--------|
| **report_generator** | Report-Generierung | ✅ Vorhanden |
| **annotator_tool** | Annotation | ✅ Vorhanden |
| **curator_tool** | Content-Kuration | ✅ Vorhanden |
| **creative_tool** | Kreative Inhalte | ✅ Vorhanden |
| **save_results** | Ergebnisse speichern | ✅ Vorhanden |
| **voice_tool** | Voice I/O | ✅ Vorhanden |

### 🌐 Navigation & Browser

| Tool | Funktion | Status |
|------|----------|--------|
| **visual_browser_tool** | Sichtbarer Browser-Start | ✅ Vorhanden |
| **smart_navigation_tool** | Intelligente Navigation | ✅ Vorhanden |
| **application_launcher** | App-Launcher | ✅ Vorhanden |
| **screen_contract_tool** | Screen-Kontrakte | ✅ Vorhanden |
| **mouse_feedback_tool** | Maus-Feedback | ✅ Vorhanden |

### 🔍 Specialized

| Tool | Funktion | Status |
|------|----------|--------|
| **inception_tool** | Inception (Nested Tasks) | ✅ Vorhanden |
| **verified_vision_tool** | Verified Vision | ✅ Vorhanden |

---

## 🤖 Vorhandene Agenten (18 Total)

### Hauptagenten (timus_consolidated.py v4.4)

| Agent | Provider | Model | Funktion |
|-------|----------|-------|----------|
| **ExecutorAgent** | OpenAI | gpt-5-mini | Task-Ausführung, Tool-Calls |
| **ReasoningAgent** | DeepSeek/Nemotron | deepseek-reasoner | Strategisches Denken |
| **CreativeAgent** | GPT-5.1 + Nemotron | Hybrid | Bildgenerierung (GPT-Prompts + Nemotron-Struktur) |
| **ResearchAgent** | DeepSeek | deepseek-reasoner | Deep Research |
| **VisualAgent** | Anthropic/OpenAI | claude-3.5-sonnet | Vision-basierte Aufgaben |

### Vision Agents (Standalone)

| Agent | Vision-System | Status | Performance |
|-------|---------------|--------|-------------|
| **visual_nemotron_agent_v4** | GPT-4 Vision (PRIMARY) + Qwen VL (Fallback) | ✅ Neueste | 3-5s (GPT-4), 60s+ (Qwen) |
| **qwen_visual_agent** | Qwen 2.5 VL (lokal) | ✅ Standalone | 60s+, kostenlos |
| **vision_executor_agent** | Vision + Executor | ✅ Vorhanden | - |
| **vision_cookie_agent** | Vision + Cookie-Handling | ✅ Vorhanden | - |
| **visual_agent** | Generic Vision | ✅ Vorhanden | - |

### Development Agents

| Agent | Funktion | Status |
|-------|----------|--------|
| **developer_agent_v2** | Code-Entwicklung v2 | ✅ Vorhanden |
| **developer_agent** | Code-Entwicklung v1 | ⚠️ Legacy |

### Reasoning & Research

| Agent | Funktion | Status |
|-------|----------|--------|
| **reasoning_agent_improved** | Verbessertes Reasoning | ✅ Vorhanden |
| **reasoning_agent** | Standard Reasoning | ⚠️ Legacy |
| **deep_research_agent** | Deep Research Standalone | ✅ Vorhanden |

### Meta & Orchestration

| Agent | Funktion | Status |
|-------|----------|--------|
| **meta_agent** | Meta-Level Orchestration | ✅ Vorhanden |
| **creative_agent** | Standalone Creative | ✅ Vorhanden |

### ReAct Variants

| Agent | Funktion | Status |
|-------|----------|--------|
| **timus_deep_react** | Deep ReAct Pattern | ✅ Vorhanden |
| **timus_react** | Standard ReAct | ✅ Vorhanden |

---

## 🔧 Vision Engines (tools/engines/)

| Engine | Technologie | Performance | Status |
|--------|-------------|-------------|--------|
| **qwen_vl_engine** | Qwen2-VL-2B (RTX 3090) | ~60s+ | ✅ Vorhanden, LANGSAM |
| **ocr_engine** | Tesseract/EasyOCR | Fast | ✅ Vorhanden |

### 🚨 PROBLEM: Kein Florence-2, Molmo, PaliGemma!
**Empfehlung:** Florence-2 oder Molmo integrieren (~1-2s, lokal, kostenlos)

---

## 📋 Dispatcher & Orchestration

### main_dispatcher.py
- **Intent Detection** mit GPT-5-mini
- **Agent-Routing** zu Executor/Creative/Research/etc.
- ⚠️ **PROBLEM**: Primitiv, kein Task Queue, keine State Machine

### Skills-System
- **skills.yml** mit 5+ Skills
- **Planner-Tool** für Multi-Step Workflows
- **Variable Substitution** `{{var}}`

---

## 🔴 KRITISCHE LÜCKEN (aus Plan-Analyse)

### 1. DOM-First Browser Controller ❌
**Status:** FEHLT KOMPLETT
- browser_tool hat Playwright ABER nutzt es nicht für DOM-Actions
- Alles ist Vision-first (ineffizient!)

### 2. Verification Layer Integration ❌
**Status:** Tool vorhanden, aber nicht integriert
- verification_tool existiert
- Wird NICHT systematisch nach jeder Aktion genutzt

### 3. Evidence Pack System ❌
**Status:** TEILWEISE
- deep_research vorhanden
- Aber keine strukturierten Evidence Packs
- Kein Fact Verifier gegen Evidence

### 4. Orchestrator v2 ❌
**Status:** main_dispatcher ist primitiv
- Keine Task Queue
- Keine State Machine
- Keine Retry/Fallback-Strategien

### 5. UI-State Tracker ❌
**Status:** FEHLT
- Kein systematisches State-Tracking
- screen_change_detector vorhanden aber nicht integriert

---

## ✅ STÄRKEN (bereits vorhanden)

1. ✅ **Viele Tools** (49!) - gut für Modularität
2. ✅ **Planner + Skills** - Multi-Step Workflows möglich
3. ✅ **verification_tool** - nur besser integrieren
4. ✅ **browser_tool mit Playwright** - DOM-Zugriff möglich!
5. ✅ **Multi-Provider Support** - Flexibel
6. ✅ **som_tool** - Set-of-Mark für Vision
7. ✅ **deep_research** - Basis für Evidence Packs

---

## 🎯 IMPLEMENTIERUNGS-PRIORITÄTEN

### Phase 1: DOM-First Browser Controller (JETZT)
**Aufgabe:** browser_tool erweitern + HybridBrowserController erstellen

**Nutzt vorhandene Tools:**
- ✅ browser_tool (Playwright)
- ✅ verification_tool (Post-Check)
- ✅ som_tool (Vision-Fallback)
- ✅ mouse_tool (PyAutoGUI)
- ✅ cookie_banner_tool (Auto-Handling)

**Neu zu erstellen:**
- `tools/browser_controller/` - Hybrid Controller
- DOM-First Logik
- Vision-Fallback Integration
- State-Tracking

### Phase 2: Verification Integration (NEXT)
**Aufgabe:** verification_tool systematisch nutzen

**Nutzt:**
- ✅ verification_tool
- ✅ decision_verifier
- ✅ validation_tool

### Phase 3: Evidence System (DANN)
**Aufgabe:** deep_research erweitern

**Nutzt:**
- ✅ deep_research
- ✅ fact_corroborator
- ✅ search_tool

### Phase 4: Orchestrator v2 (SPÄTER)
**Aufgabe:** main_dispatcher ersetzen

---

## 📊 Performance-Ziele

| Metrik | Aktuell | Ziel (DOM-First) | Verbesserung |
|--------|---------|------------------|--------------|
| **Klick-Latenz** | 3-5s (GPT-4) | 0.1-0.5s (DOM) | **10-50x schneller** |
| **Kosten/Aktion** | $0.0015 | $0 (DOM) | **100% Einsparung** |
| **Genauigkeit** | 70-80% (Vision) | 95-99% (DOM) | **+20-25%** |
| **Robustheit** | Mittel (Koordinaten) | Hoch (Selectors) | **+++ stabiler** |

---

**Ende Inventory**
