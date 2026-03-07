# Timus Roadmap

Current version: **v4.4** (2026-03-07)

---

## What's Live Today

| Module | Status | Description |
|--------|--------|-------------|
| **13 Specialized Agents** | ✅ | meta, research, visual, developer, reasoning, creative, communication, data, document, system, shell, image, executor |
| **80+ MCP Tools** | ✅ | file system, web search, OCR, browser automation, email, deep research, etc. |
| **Deep Research v7.0** | ✅ | 5-stage pipeline: web + ArXiv + GitHub + HuggingFace + Edison. 3 outputs: analytical MD, narrative MD, A4 PDF |
| **Soul Engine** | ✅ | 5 personality axes drifting over time (confidence, formality, humor, verbosity, risk_appetite) |
| **Curiosity Engine** | ✅ | Proactive knowledge search (3–14h sleep cycle, Telegram push) |
| **M1 Goal Generator** | ✅ | Signal-based goal creation from memory + curiosity + events |
| **M2 Long-Term Planner** | ✅ | 3-horizon planning + automatic replanning on missed commitments |
| **M3 Self-Healing** | ✅ | LLM-driven incident diagnosis + recovery playbooks + circuit breaker |
| **M5 Autonomy Scorecard** | ✅ | Score 0–100 from 4 pillars, control loop (promote / rollback) |
| **M8 Session Reflection** | ✅ | Idle-triggered LLM reflection, pattern accumulation → improvement suggestions |
| **M9 Agent Blackboard** | ✅ | TTL-based shared memory across all agents |
| **M10 Proactive Triggers** | ✅ | Scheduled routines (morning 08:00, evening 20:00) |
| **M11 Goal Queue Manager** | ✅ | Hierarchical goals, milestones, progress rollup |
| **M12 Self-Improvement Engine** | ✅ | Tool success rate + routing confidence tracking → weekly suggestions |
| **M13 Tool Generator** | ✅ | AST-validated runtime tool creation, Telegram review gate, importlib activation |
| **M14 Email Autonomy** | ✅ | Policy-checked autonomous emails (whitelist + confidence 0.85, SMTP/msgraph, Telegram approval) |
| **M15 Ambient Context Engine** | ✅ | Push-autonomy: file watcher, goal staleness, system alerts → tasks without user input |
| **M16 Feedback Learning** | ✅ | 👍/👎/🤷 → Soul hook weights, CuriosityEngine topic scores, session reflection |
| **Qdrant Migration** | ✅ | Drop-in replacement for ChromaDB, 1585 entries migrated |
| **Lean 4 Formal Proofs** | ✅ | 73 theorems in `lean_verify/CiSpecs.lean` (all `by omega`, CI-ready in ~5s) |
| **Hypothesis Property Tests** | ✅ | 200+ property-based tests covering delegation, artifacts, timeouts, parallel aggregation |
| **CrossHair Contracts** | ✅ | Pre/postconditions on autonomy_scorecard, curiosity_engine, policy_gate, blackboard write, artifact normalization |
| **Canvas UI v4** | ✅ | 4-tab layout: CANVAS, AUTONOMY, KAMERA, FLOW (interactive Cytoscape.js architecture diagram) |
| **Voice Loop** | ✅ | Faster-Whisper STT + Inworld.AI TTS, native canvas integration |
| **RealSense D435** | ✅ | Physical camera integration for environment awareness |
| **Agent Improvements v4.2** | ✅ | Dedup+ranking (Research), auto-test-run (Developer), click retry (Visual), decomposition hint (Meta), draft review (Communication) |
| **M17 Meta-Agent Intelligence v4.3** | ✅ | AgentResult.metadata, bidirectional Blackboard-Write, Replan-Protocol, RESEARCH_TIMEOUT 180→600s |
| **Communication Contract Hardening v4.4** | ✅ | AgentResult.artifacts, Tool-Wrapper normalization (tool_registry_v2), artifacts→metadata→regex fallback policy, 73 Lean theorems |
| **Interactive Flow Diagram v4.4** | ✅ | Cytoscape.js FLOW-Tab: live architecture graph, real-time status colors, collapsible groups, clickable node details |

---

## Near-Term (Next 4–8 Weeks)

### Demo Video (Priority 1)
- Record a 5–7 min live demo showing M15 ambient push, M8 session reflection, M16 soul drift, M3 self-healing
- No cuts — a genuine live run is more convincing than edited footage
- Deploy to YouTube + link from README + share on X/Twitter

### GitHub Repo Polish (Priority 2)
- Architecture diagram (visual, not ASCII) → `docs/architecture.png`
- Docker tested end-to-end on a clean machine
- CI via GitHub Actions: `lean lean/CiSpecs.lean` + `pytest tests/ -q`

### HuggingFace Space Demo (Priority 3)
- Minimal live demo without local hardware (no RealSense, no voice)
- Shows: chat → agent delegation → deep research result
- Entry point for external visitors

---

## Medium-Term (1–3 Months)

### M17 — Structured Memory Consolidation
- Periodic background consolidation: group related Blackboard entries into long-term YAML snapshots
- "Memory decay" for low-relevance entries (inspired by human memory research)
- ChromaDB / Qdrant TTL-aware recall with recency bias

### M18 — Multi-Turn Planning Canvas
- Interactive goal tree editor in Canvas UI
- Drag-and-drop milestone reordering
- Real-time progress visualization (animated Cytoscape tree)

### Agent Intelligence Upgrades
- Research agent: streaming results to Canvas as they arrive (SSE partial updates)
- Developer agent: cross-file refactoring support (multi-file context window)
- Visual agent: learned click patterns per application (persistent action memory)

### CI / CD
- GitHub Actions workflow: test + lean + optional Docker build
- Badge in README: `Tests: passing`, `Lean: 49 theorems`
- Dependabot for Python dependency updates

---

## Long-Term Vision

Timus is built around the thesis that a single developer — with access to the right models and time — can build infrastructure that normally requires an SRE team.

The long-term direction:

1. **Full push-autonomy**: Timus wakes up every morning, checks goals, executes the next step, sends a summary. Zero user interaction required for routine work.

2. **Multi-instance coordination**: Two Timus instances share a Blackboard over a network. One focuses on research; one on development. Meta coordinates between them.

3. **Hardware-in-the-loop**: RealSense + microphone + speaker → Timus perceives and responds to the physical environment, not just digital screens.

4. **Open-source release**: Clean public repo, Docker one-liner, English README, contribution guide. Goal: 100+ GitHub stars within 90 days of launch.

---

## Completed Milestones

| Date | Milestone |
|------|-----------|
| 2026-03-06 | Phase 3 agent improvements (49 Lean theorems, 92 Hypothesis tests, CrossHair contracts) |
| 2026-03-06 | M13 + M14 live, Qdrant migration (1585 entries) |
| 2026-03-06 | Hypothesis + Lean bridge: 44 theorems, 64 property-based tests |
| 2026-03-05 | M15 Ambient Context Engine + M16 Feedback Learning |
| 2026-03-04 | M8–M12: reflection, blackboard, triggers, goal queue, self-improvement |
| 2026-03-03 | Deep Research v7.0: all 5 root causes fixed, 144 tests green |
| 2026-03-02 | Canvas delegation animation + DeveloperAgentV2 unified |
| 2026-03-01 | Email integration (Microsoft Graph OAuth2), all 13 agents reachable |
| 2026-02-28 | Canvas v3: Cytoscape, Autonomy tab, Voice loop |
| 2026-02-27 | M1–M5 autonomy layers live in production |
| 2026-02-25 | Soul Engine + Curiosity Engine |
| Early 2025 | Project start: single-agent browser automation script |
