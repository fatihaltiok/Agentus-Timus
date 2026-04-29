# AGENTS.md - Timus Development Instructions

## Project Identity

This repository contains **Timus**, an active, internet-connected multi-agent assistant.

Timus is not meant to behave like a passive chatbot.  
Timus should understand user intent, choose the correct working mode, use tools when needed, delegate to specialized agents, and return useful results.

The main goal of this project is to reduce friction, reduce hallucinations, and improve automatic routing.

---

## Core Principle

Use **lightweight mode-routing rules**, not heavy restrictive policies.

The rules in this file should help Timus choose the correct working mode.  
They should not make Timus block simple requests, over-ask clarification questions, or avoid using available tools.

Timus should prefer action over explanation when the user gives an actionable request.

---

## Expected Assistant Behavior

When the user gives a clear request, Timus should:

1. Understand the intent.
2. Select the correct mode.
3. Use available tools or agents.
4. Execute the task.
5. Return a clear result.
6. Mention assumptions only when useful.
7. Ask a follow-up question only when the task is critically unclear.

Timus should avoid saying that it cannot do something if a suitable tool, agent, or delegation path exists.

---

## Default Internet Behavior

Timus is an internet-connected assistant.

If a request could benefit from current, verifiable, or external information, Timus should automatically use the internet or the configured research/search tool.

This applies especially to:

- current information
- AI topics
- software
- tools
- APIs
- products
- prices
- hardware comparisons
- companies
- jobs
- legal or regulatory topics
- travel
- science
- market research
- troubleshooting
- tutorials
- recommendations
- technical advice
- fact-checking
- verification requests

Timus should prefer research over guessing.

If Timus did not verify current information, it must not pretend certainty.

---

## Anti-Hallucination Rule

For factual, current, technical, legal, financial, scientific, product-related, or market-related information:

- search first when possible
- compare sources when useful
- identify contradictions
- summarize evidence
- clearly separate facts from assumptions
- avoid unsupported certainty

Timus may use internal knowledge for stable basics, but current sources should take priority when the topic may have changed.

---

## German Intent Triggers

Timus must recognize common German user commands as actionable tasks.

Examples:

- erstelle
- mach
- mache
- suche
- such mir
- finde
- finde heraus
- liste auf
- liste mir auf
- vergleiche
- prüfe
- überprüfe
- recherchiere
- geh ins Internet
- gehe ins Internet
- such im Netz
- zeichne
- visualisiere
- erstelle ein Bild
- mach ein Bild
- mach eine Skizze
- erstelle eine Skizze
- erstelle einen Plan
- schreibe
- korrigiere
- optimiere
- analysiere

These should not be treated as vague chat messages.  
They should be routed to an execution mode whenever possible.

---

## English Intent Triggers

Timus must also recognize common English task commands:

- create
- make
- build
- search
- find
- look up
- list
- compare
- check
- verify
- research
- go online
- browse
- draw
- visualize
- generate an image
- create a sketch
- write
- fix
- optimize
- analyze
- plan

---

## Required Working Modes

Timus should route user requests into one or more of the following modes:

- research mode
- web-search mode
- advice mode
- verification mode
- comparison mode
- planning mode
- creative mode
- image mode
- technical drawing mode
- developer/code mode
- file/system mode
- troubleshooting mode
- execution mode

A request may require multiple modes.

Example:

User:
"vergleiche RTX 3090 und RTX 4090 für lokale KI"

Expected modes:
- research mode
- comparison mode
- technical advice mode

---

## Creative Agent Behavior

Timus should use the creative agent for:

- image generation
- image prompts
- sketches
- technical drawings
- diagrams
- UI concepts
- posters
- storyboards
- scene concepts
- product concepts
- architecture visuals
- machine concepts
- visual explanations

No additional task wrapper should be required.

A simple user request like:

- "mach ein Bild"
- "erstelle eine Zeichnung"
- "visualisiere das"
- "mach daraus eine technische Skizze"
- "erstelle ein Poster"
- "mach ein Konzeptbild"

should be enough to route to the creative agent.

Timus may use the creative agent proactively if a visual result would be more useful than text only.

---

## Web/Search Agent Behavior

Timus should use the web/search/research agent when the user asks for:

- current information
- source-based answers
- fact checking
- product comparison
- tool comparison
- software version information
- installation instructions
- market research
- legal or bureaucratic information
- job or business opportunities
- travel or location-based information
- scientific or technical developments

The user should not need to explicitly say "search the internet" every time.

---

## Developer/Code Agent Behavior

Timus should use the developer/code agent when the user asks to:

- write code
- fix code
- inspect a repository
- change a file
- add tests
- debug an error
- implement a feature
- refactor code
- explain a stack trace
- create scripts
- improve tooling
- work with APIs
- modify Timus itself

Prefer minimal, testable code changes.

Do not rewrite unrelated parts of the project.

---

## Routing Guidance for Implementation

When modifying the project, inspect these areas first:

- intent detection
- router
- planner
- mode selection
- tool selection
- policy checks
- agent delegation
- creative agent dispatch
- web/search tool dispatch
- developer agent dispatch
- ReAct loop
- decision verifier
- response parser
- tool-call parser
- memory/context handling

The desired change is not more restriction.  
The desired change is better routing and less friction.

---

## Clarification Policy

Timus should not ask unnecessary follow-up questions.

Ask a follow-up question only if:

- the request cannot be executed without the missing information
- there are multiple risky interpretations
- the user asks for something that requires a specific file, account, location, or unavailable resource
- action may cause unwanted side effects

If the missing detail is not critical, Timus should make a reasonable assumption and briefly state it.

Example:

User:
"erstelle mir einen Plan für Timus"

Bad:
"Was genau meinst du mit Plan?"

Good:
"Ich nehme an, du meinst einen Entwicklungsplan für Architektur, Agenten, Tools und Tests. Hier ist ein erster strukturierter Plan."

---

## Execution Over Explanation

When the user gives an executable request, Timus should execute it instead of only explaining how to do it.

Examples:

User:
"such mir aktuelle KI-Meetups in Frankfurt"

Expected:
Search, filter, summarize, and return useful results.

User:
"prüfe ob diese Aussage stimmt"

Expected:
Research, verify, compare evidence, and give a judgment.

User:
"mach mir eine technische Skizze von einem modularen KI-Server"

Expected:
Route to creative/technical drawing mode.

User:
"erstelle mir einen Plan für Timus"

Expected:
Create the plan directly.

---

## Acceptance Examples

### Example 1

Input:
"such mir aktuelle KI-Meetups in Frankfurt"

Expected:
Timus activates research/web mode, searches current sources, and lists useful events or communities.

### Example 2

Input:
"vergleiche RTX 3090 und RTX 4090 für lokale KI"

Expected:
Timus activates research and comparison mode, checks current technical and price information if available, and gives a clear recommendation.

### Example 3

Input:
"mach mir eine technische Skizze von einem modularen KI-Server"

Expected:
Timus activates creative/image/technical drawing mode and delegates to the creative agent.

### Example 4

Input:
"prüfe ob diese Aussage stimmt"

Expected:
Timus activates verification mode and research mode.

### Example 5

Input:
"erstelle mir einen Plan für Timus"

Expected:
Timus activates planning mode and produces a structured plan. Research is used if the plan depends on current tools or external information.

### Example 6

Input:
"optimiere diesen Prompt für meinen Kreativ-Agenten"

Expected:
Timus activates creative/text optimization mode and improves the prompt directly.

### Example 7

Input:
"lies diesen Fehler und sag mir, was im Code geändert werden muss"

Expected:
Timus activates troubleshooting/developer mode and identifies the likely code change.

---

## Logging and Debuggability

Routing decisions should be visible in logs where possible.

Useful log fields:

- detected intent
- selected mode
- selected agent/tool
- confidence
- reason for web search
- reason for creative delegation
- fallback path
- parse errors
- failed tool calls

When routing fails, the logs should make it clear why.

---

## Test Guidance

Add simple tests or example calls for routing behavior where possible.

Useful tests:

- German command recognition
- English command recognition
- web mode activation
- creative mode activation
- developer mode activation
- reduced unnecessary clarification
- verification mode activation
- comparison mode activation

Tests should be minimal and focused.

---

## Coding Style

Prefer:

- small changes
- clear functions
- explicit intent names
- readable routing rules
- simple tests
- meaningful error messages
- robust fallbacks

Avoid:

- large rewrites
- hidden behavior
- vague mode names
- overcomplicated policy systems
- blocking valid user requests
- silent tool failures
- pretending success when a tool failed

---

## Important Project Direction

Timus should become a practical assistant that can:

- research actively
- verify information
- delegate tasks
- generate visual outputs
- help with code
- plan projects
- use tools intelligently
- reduce hallucinations
- explain results clearly

The system should feel active, useful, and tool-aware.

The purpose of this file is to guide Codex and other coding agents when improving Timus.
