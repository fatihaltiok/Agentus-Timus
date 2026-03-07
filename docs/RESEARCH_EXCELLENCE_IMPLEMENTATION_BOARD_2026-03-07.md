# Research Excellence Implementation Board

Stand: 2026-03-07

## Ziel

`Deep Research` wird zu einer allgemeinen evidenzbasierten Research-Engine.
Nicht mehr: Quellensynthese mit globaler Verifikationsquote.
Sondern: `Question -> Claim -> Evidence -> Verdict -> Report`.

## Leitregeln

1. Kein Claim ohne Evidenzobjekt
2. Kein `confirmed` bei reinem Vendor-Claim
3. Kein `confirmed` bei nur schwachen Quellen
4. YouTube wird integriert, aber streng klassifiziert
5. Widerspruch und Unsicherheit bleiben sichtbar

## Meilensteine

### M0 Baseline
- Ist-Fluss dokumentieren
- Failure-Taxonomie aufbauen
- Gold-/Bad-Case-Recherchen definieren

### M1 Research Contract v2
- `ResearchQuestion`
- `SourceRecord`
- `EvidenceRecord`
- `ClaimRecord`
- `ResearchContract`
- Profilwahl + Verdict-Engine als reine Funktionen

### M2 Source Assessment
- Source-Typen
- Tiering A/B/C/D
- Bias / Zeitbezug / Primärquelle
- YouTube-Klassifikation

### M3 Claim Engine
- Claim-Extraktion
- Evidence-Linking
- Claim-Verdicts
- Widerspruchspfad

### M4 Profile
- `fact_check`
- `news`
- `scientific`
- `vendor_comparison`
- `market_intelligence`
- `policy_regulation`
- `competitive_landscape`

### M5 Report/PDF
- Executive Verdict Table
- Claim Register
- Conflict & Unknowns
- Quellenanhang mit Tier/Typ/Bias

### M6 Runtime Guardrails
- Telemetry
- Stopping Conditions
- Partial Research State statt falscher Sicherheit

## Verifikation

### Lean 4
- keine evidenzlosen starken Verdicts
- Vendor-only bleibt Vendor-only
- offene Fragen bleiben erhalten

### Hypothesis
- Verdict-Monotonie
- Tier-D nie `confirmed`
- Widersprüche machen Verdict nie stärker

### CrossHair
- reine Funktionen für Profilwahl, Tiering, Verdict-Engine
- Confidence im Bereich `[0, 1]`
- nur gültige Enum-Werte als Ergebnis

## Phase 1 Start

In dieser Phase umgesetzt:
- allgemeines Datenmodell `research_contracts.py`
- Session-Anbindung via `contract_v2`
- erste reine Funktionen:
  - `choose_research_profile`
  - `classify_source_tier`
  - `is_youtube_hard_evidence`
  - `compute_claim_verdict`
  - `aggregate_overall_confidence`

## Nächster Schritt

M2 Source Assessment:
- Legacy-Quellen in `SourceRecord` überführen
- YouTube-Channel-/Transcript-Klassifikation
- Claim-Evidence-Referenzen real befüllen
