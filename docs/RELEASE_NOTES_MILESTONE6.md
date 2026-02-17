# Release Notes - Milestone 1-6 Memory Stabilization

Date: 2026-02-17

## Highlights
- Deterministisches Interaction-Logging zentralisiert in `run_agent(...)`.
- Working-Memory-Layer mit Budget und Prompt-Injektion im BaseAgent.
- Dynamische Relevanzlogik mit Decay (Kurzzeit/Langzeit) und adaptiver Gewichtung.
- Runtime-Telemetrie pro Agent-Run als Event-Metadaten persistiert.
- Quality-Gates und E2E-Readiness-Tests ergänzt.

## Added
- `tests/test_milestone5_quality_gates.py`
- `tests/test_milestone6_e2e_readiness.py`
- `verify_milestone6.py`
- `docs/MILESTONE6_RUNBOOK.md`

## Changed
- `main_dispatcher.py`
- `agent/base_agent.py`
- `memory/memory_system.py`
- `docs/MEMORY_ARCHITECTURE.md`

## Verification
- `pytest -q tests/test_milestone5_quality_gates.py`
- `pytest -q tests/test_milestone6_e2e_readiness.py`
- `python verify_milestone6.py`
