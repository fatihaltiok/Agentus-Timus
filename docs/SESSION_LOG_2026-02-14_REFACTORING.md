# Session Log: Agent-Architektur Refactoring

**Datum:** 2026-02-14
**Ziel:** Code-Duplikation eliminieren und `timus_consolidated.py` (2290 Zeilen / 92KB) in wartbare Module aufteilen

---

## Ausgangslage

| Problem | Details |
|---------|---------|
| Code-Duplikation | ~450-500 Zeilen ueber 4 Agent-Dateien (MCP-Calls, Screenshot, Action-Parsing, Vision-Formatting je 3-5x dupliziert) |
| Mono-File | `timus_consolidated.py` = 2290 Zeilen / 92KB mit Multi-Provider-Infrastruktur, BaseAgent, 7 Prompts, 7 Agenten |

---

## Phase 1: Shared Utilities (`agent/shared/`)

5 neue Dateien erstellt die duplizierte Logik zentralisieren:

| Datei | Zeilen | Ersetzt |
|-------|--------|---------|
| `agent/shared/__init__.py` | 16 | Re-Exports |
| `agent/shared/mcp_client.py` | 70 | 4 duplizierte JSON-RPC Clients (timus_consolidated, visual_agent, visual_nemotron_agent_v4, developer_agent_v2) |
| `agent/shared/screenshot.py` | 101 | 5 duplizierte Screenshot-Funktionen (2x timus_consolidated, visual_agent, visual_nemotron_agent_v4, diverse Tools) |
| `agent/shared/action_parser.py` | 67 | 4 duplizierte Action-Parser (timus_consolidated 3-Priority, visual_agent 2-Methoden, developer_agent_v2 2-Pattern, visual_nemotron _extract_json) |
| `agent/shared/vision_formatter.py` | 83 | 2 duplizierte Vision-Message-Formatter (BaseAgent._build_vision_message, VisualAgent._call_anthropic_vision Konvertierung) |

---

## Phase 2: Aufspaltung von `timus_consolidated.py`

### Neue Module

| Datei | Zeilen | Inhalt | Quelle (Zeilen in Original) |
|-------|--------|--------|---------------------------|
| `agent/providers.py` | 165 | ModelProvider Enum, MultiProviderClient, AgentModelConfig, get_provider_client() | 71-238 |
| `agent/prompts.py` | 247 | SINGLE_ACTION_WARNING + 7 System Prompts (Executor, Research, Reasoning, Visual, Creative, Developer, Meta) | 244-481 |
| `agent/base_agent.py` | 751 | AGENT_CAPABILITY_MAP + BaseAgent Klasse (Loop-Detection, ROI, Screen-Change-Gate, Navigation, LLM Calls) | 488-1383 |
| `agent/agents/__init__.py` | 18 | Re-Exports aller Agenten |  |
| `agent/agents/executor.py` | 9 | ExecutorAgent | 1390-1392 |
| `agent/agents/research.py` | 22 | DeepResearchAgent (mit session_id Tracking) | 1395-1407 |
| `agent/agents/reasoning.py` | 22 | ReasoningAgent (Nemotron + enable_thinking) | 1410-1424 |
| `agent/agents/creative.py` | 174 | CreativeAgent (GPT-5.1 + Nemotron Hybrid Workflow) | 1427-1608 |
| `agent/agents/developer.py` | 9 | DeveloperAgent | 1611-1613 |
| `agent/agents/meta.py` | 97 | MetaAgent (Skill-Orchestrierung, Registry, Progressive Disclosure) | 1616-1753 |
| `agent/agents/visual.py` | 441 | VisualAgent (Screenshot-Analyse, Anthropic Vision, ROI, Navigation) | 1756-2279 |

### Re-Export Shim

`agent/timus_consolidated.py` wurde zu einem 56-Zeilen Re-Export Shim reduziert. Alle bestehenden Imports (`from agent.timus_consolidated import ...`) funktionieren unveraendert.

---

## Phase 3: Standalone-Agents auf Shared Utilities umgestellt

### `agent/visual_agent.py`
- `get_screenshot_base64()` -> delegiert an `agent.shared.screenshot.capture_screenshot_base64`
- `call_tool()` -> delegiert an `agent.shared.mcp_client.MCPClient`
- `parse_action()` -> delegiert an `agent.shared.action_parser.parse_action`
- Ca. 80 Zeilen duplizierter Code entfernt

### `agent/visual_nemotron_agent_v4.py`
- `MCPToolClient` Basis-RPC -> delegiert an `agent.shared.mcp_client.MCPClient` (Convenience-Methoden bleiben)
- `DesktopController.screenshot()` -> delegiert an `agent.shared.screenshot.capture_screenshot_image`
- `NemotronClient._extract_json()` -> aufgeraeumt (shared parser als Referenz)

### `agent/developer_agent_v2.py`
- `call_tool()` -> delegiert an `agent.shared.mcp_client.MCPClient.call_sync()`
- `extract_action_json()` -> delegiert an `agent.shared.action_parser.parse_action`
- Ca. 30 Zeilen duplizierter Code entfernt

---

## Phase 4: Verifikation

### Syntax-Checks (py_compile) - Alle bestanden
- `agent/shared/__init__.py` OK
- `agent/shared/mcp_client.py` OK
- `agent/shared/screenshot.py` OK
- `agent/shared/action_parser.py` OK
- `agent/shared/vision_formatter.py` OK
- `agent/providers.py` OK
- `agent/prompts.py` OK
- `agent/base_agent.py` OK
- `agent/agents/__init__.py` OK
- `agent/agents/executor.py` OK
- `agent/agents/research.py` OK
- `agent/agents/reasoning.py` OK
- `agent/agents/creative.py` OK
- `agent/agents/developer.py` OK
- `agent/agents/meta.py` OK
- `agent/agents/visual.py` OK
- `agent/timus_consolidated.py` OK (Re-Export)
- `agent/visual_agent.py` OK
- `agent/visual_nemotron_agent_v4.py` OK
- `agent/developer_agent_v2.py` OK

### Import-Tests - Alle bestanden
- `from agent.timus_consolidated import ExecutorAgent, CreativeAgent, MetaAgent, VisualAgent, BaseAgent` OK
- `from agent.agents import ExecutorAgent, VisualAgent, ...` OK
- `from agent.shared.mcp_client import MCPClient` OK
- `from agent.shared.screenshot import capture_screenshot_base64` OK
- `from agent.shared.action_parser import parse_action` OK
- `from agent.shared.vision_formatter import build_openai_vision_message, convert_openai_to_anthropic` OK
- `from agent.providers import ModelProvider, MultiProviderClient, AgentModelConfig, get_provider_client` OK
- `from agent.base_agent import BaseAgent, AGENT_CAPABILITY_MAP` OK
- `from main_dispatcher import *` OK

### Bestehende Abhaengigkeiten (10 Dateien importieren aus timus_consolidated)
Alle funktionieren weiterhin dank Re-Export Shim:
- `main_dispatcher.py`
- `test_project/test_visual_parse.py`
- `test_executor_navigation.py`
- `test_improved_scenario2.py`
- `test_loop_detection.py`
- `test_roi_support.py`
- `test_structured_navigation.py`
- `test_production_navigation.py`
- `test_agent_integration.py`
- `run_autonomous.py`

---

## Metriken (Vorher -> Nachher)

| Metrik | Vorher | Nachher | Aenderung |
|--------|--------|---------|-----------|
| `timus_consolidated.py` | 2290 Zeilen | 56 Zeilen | **-97.6%** |
| Code-Duplikation | ~450 Zeilen | ~0 Zeilen | **-100%** |
| Groesste Einzeldatei | 92KB (timus_consolidated) | ~25KB (base_agent.py) | **-73%** |
| Fokussierte Module | 1 Mono-File | 15 Module | +15 |
| Shared Utilities | 0 | 4 (MCP, Screenshot, Parser, Vision) | +4 |

---

## Neue Verzeichnisstruktur

```
agent/
  shared/
    __init__.py          (16 Z.)  - Re-Exports
    mcp_client.py        (70 Z.)  - Einheitlicher JSON-RPC Client
    screenshot.py       (101 Z.)  - Screenshot Capture (JPEG/PNG, configurable)
    action_parser.py     (67 Z.)  - 3-Priority Action/JSON Parser
    vision_formatter.py  (83 Z.)  - OpenAI/Anthropic Vision Messages
  agents/
    __init__.py          (18 Z.)  - Re-Exports
    executor.py           (9 Z.)  - ExecutorAgent
    research.py          (22 Z.)  - DeepResearchAgent
    reasoning.py         (22 Z.)  - ReasoningAgent
    creative.py         (174 Z.)  - CreativeAgent (Hybrid)
    developer.py          (9 Z.)  - DeveloperAgent
    meta.py              (97 Z.)  - MetaAgent (Skills)
    visual.py           (441 Z.)  - VisualAgent (Vision)
  providers.py          (165 Z.)  - Multi-Provider Infrastruktur
  prompts.py            (247 Z.)  - System Prompts
  base_agent.py         (751 Z.)  - BaseAgent Klasse
  timus_consolidated.py  (56 Z.)  - Re-Export Shim (Backwards-Compat)
```
