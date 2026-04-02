# Changelog Dev

---

## ⚠️ NACHTRAG (dokumentiert am 2026-03-27, implementiert 2026-03-23 bis 2026-03-25)

Diese Einträge wurden nicht in Echtzeit protokolliert, sondern nachträglich aus dem Review-Verlauf rekonstruiert.

---

## 2026-03-23 bis 2026-03-25 — Ephemeral Workers für Deep Research + YouTube-Transcript-Fix

### Problemstellung

- Deep Research lieferte bei Depth-5-Läufen zu wenige und zu generische Query-Varianten.
- Semantische Duplikate in Claim-Listen wurden nur deterministisch erkannt, nicht inhaltlich.
- Widersprüche und Evidenzlücken wurden nicht strukturiert in den Report-Kontext eingespeist.
- YouTube-Transkripte wurden hart auf 8000 Zeichen abgeschnitten, wodurch lange Videos kaum analysierbar waren.
- Zusätzlich: `VISUAL_NEMOTRON_KEYWORDS` enthielt zu generische deutsche Wörter (`dann`, `danach`, `unterhaltung`), die normale Konversationstexte fälschlicherweise zum Visual-Nemotron-Agenten routeten.

---

### Ephemeral Workers — Phase 1: Query Variant Worker (2026-03-23)

**Ziel**

Kurzlebige LLM-Worker für Deep Research, ohne Registry, BaseAgent oder Canvas anzufassen. Nur LLM-only, env-gesteuert, budget-aware, mit hartem Fallback auf den deterministischen Pfad.

**Umgesetzt**

- Neue Utility-Schicht [`orchestration/ephemeral_workers.py`](/home/fatih-ubuntu/dev/timus/orchestration/ephemeral_workers.py)
  - `WorkerProfile`, `WorkerTask`, `WorkerResult` (frozen dataclasses)
  - `run_worker(...)` mit vollständiger Fehler-/Timeout-/Budget-Behandlung
  - `run_worker_batch(...)` mit Semaphor und `cap_parallelism_for_budget`
  - Budget unter `deep_research`-Scope, keine versteckten Kosten
  - alle 5 Exit-Pfade (`disabled`, `blocked`, `unsupported_provider`, `timeout`, `error`) liefern `fallback_used=True`
- Integration in [`tools/deep_research/tool.py`](/home/fatih-ubuntu/dev/timus/tools/deep_research/tool.py)
  - `_worker_query_variants_enabled()` — Feature-Flag
  - `_sanitize_worker_query_variants(...)` — Topic-Check + Längenvalidierung
  - `_augment_query_variants_with_worker(...)` — Hook vor Phase 1 der Suche
  - `skipped_no_capacity`-Kurzschluss wenn Query-Budget bereits voll
  - Metadaten unter `session.research_metadata["query_variant_worker"]`
- Env-Flags: `EPHEMERAL_WORKERS_ENABLED`, `EPHEMERAL_WORKER_MODEL`, `EPHEMERAL_WORKER_PROVIDER`, `EPHEMERAL_WORKER_MAX_PARALLEL`, `EPHEMERAL_WORKER_TIMEOUT_SEC`, `EPHEMERAL_WORKER_MAX_TOKENS`, `DR_WORKER_QUERY_VARIANTS_ENABLED`

**Validierung**

- `23 passed` — `tests/test_ephemeral_workers.py`, `tests/test_deep_research_query_workers.py`, `tests/test_deep_research_report_quality.py`, `tests/test_llm_budget_guard.py`
- Lean grün

---

### Ephemeral Workers — Phase 2: Semantic Dedupe Worker (2026-03-24)

**Ziel**

Semantische Merge-Vorschläge für inhaltlich nahezu gleiche Claims, als konservativer Zusatz zur deterministischen Dedupe. Die deterministische Basis bleibt autoritativ.

**Umgesetzt**

- Fensterbasierte Batch-Verarbeitung über `run_worker_batch(...)` — große Claim-Mengen werden in überlappende Fenster aufgeteilt
- `_semantic_claim_overlap_ok(...)` — Token-Coverage-Check ≥ 0.6 als Vorfilter
- `_semantic_merge_protected_terms_ok(...)` — Guard gegen fachlich unterschiedliche Protected Terms (z.B. `Kraft-Momenten-Sensor ≠ Drehmomentsensor`)
- `_filter_semantic_merge_candidates(...)` — Confidence-Gate ≥ 0.85, Pair-Deduplizierung, Cache-Key-Prüfung
- `_apply_semantic_merge_candidates(...)` — Union-Find mit Pfadkompression, Reihenfolge aus Original-Claim-Liste erhalten
- `_apply_cached_semantic_claim_dedupe(...)` — Signature-Check als Cache-Invalidierungs-Guard
- `_populate_semantic_claim_dedupe_cache(...)` — Hook nach Deep Dive, vor Synthese
- Metadaten unter `session.research_metadata["semantic_claim_dedupe"]`
- Env-Flags: `DR_WORKER_SEMANTIC_DEDUPE_ENABLED`, `DR_WORKER_SEMANTIC_DEDUPE_CONFIDENCE_THRESHOLD`, `DR_WORKER_SEMANTIC_DEDUPE_CHUNK_SIZE`, `DR_WORKER_SEMANTIC_DEDUPE_CHUNK_OVERLAP`

**Bekannte Einschränkung**

Signature in `_populate_semantic_claim_dedupe_cache` wird auf allen deterministischen Claims berechnet, in `_apply_cached_semantic_claim_dedupe` aber nur auf `verified_fact | legacy_claim`. Bei Sessions mit gemischten Claim-Typen kann der Cache konservativer als nötig invalidiert werden (kein Correctness-Bug, nur verpasste Merges). Vor produktiver Aktivierung patchen.

**Validierung**

- `34 passed`
- CrossHair grün (`tests/test_deep_research_semantic_dedupe_contracts.py`)
- Lean grün

---

### Ephemeral Workers — Phase 3: Conflict Scan Worker (2026-03-25)

**Ziel**

Strukturierte Analyse von Widersprüchen, Evidenzlücken und schwach abgesicherten Claims vor der finalen Synthese. Nur Metadaten — keine Mutation von Claims oder Evidences.

**Umgesetzt**

- `_claim_report_signal_score(...)` — Risk-gewichtetes Tuple-Sort für Input-Priorisierung
- `_build_conflict_scan_input(...)` — harte Input-Caps: 15 Claims, 8 conflicting_info, 6 open_questions; `notes` auf 200 Zeichen, `unknowns` auf 4 pro Claim begrenzt
- `_normalize_conflict_scan_payload(...)` — toleriert `null`-Listen, Confidence-Gate ≥ 0.83, Output-Caps: 6 Konflikte, 8 offene Fragen, 6 weak_evidence_flags, 6 report_notes
- `_get_conflict_scan_report_context(...)` — sicherer Leser des Caches für Report-Pfade
- `_populate_conflict_scan_cache(...)` — `skipped_no_material` wenn kein Material, harter Fallback bei Fehler
- `recommended_report_section` bewusst nicht implementiert (zu viel Layouter-Verantwortung für den Worker)
- Integration in akademischen Report: separate "Conflict-Scan-Hinweise"-Sektion
- Metadaten unter `session.research_metadata["conflict_scan_worker"]`
- Env-Flags: `DR_WORKER_CONFLICT_SCAN_ENABLED`, `DR_WORKER_CONFLICT_SCAN_CONFIDENCE_THRESHOLD`, `DR_WORKER_CONFLICT_SCAN_MODEL`, `DR_WORKER_CONFLICT_SCAN_MAX_TOKENS` (default 1200), `DR_WORKER_CONFLICT_SCAN_TIMEOUT_SEC` (default 25)

**Offener Punkt**

`_normalize_conflict_scan_payload` kappt `conflicts[:6]` in Reihenfolge des Modell-Outputs ohne Nachsortierung nach Confidence. Vor Phase-2-Erweiterung: absteigende Sortierung nach Confidence vor dem Cap ergänzen.

**Validierung**

- `45 passed`
- CrossHair grün (`tests/test_deep_research_conflict_scan_contracts.py`)
- Lean grün

---

### YouTube-Transcript-Fix (2026-03-25)

**Problemstellung**

- `tools/search_tool/tool.py` schnitt `full_text` aus Transkripten hart auf 8000 Zeichen ab.
- `youtube_researcher.py` holte nur einen gekappten String statt das vollständige Transcript-Payload.
- `_analyze_text(...)` arbeitete mit stumpfem 4000-Zeichen-Limit.
- Lange Videos (> 30 Min.) waren damit praktisch nicht analysierbar.

**Umgesetzt**

- `full_text` in `tool.py` wird nicht mehr abgeschnitten
- `_get_transcript_with_fallback(...)` holt das komplette Payload-Dict
- `_chunk_transcript_items(...)` — segmentbasierte Aufteilung mit Überlapp; passt Chunk-Größe dynamisch an wenn Material sonst zu viele Chunks erzeugen würde
- `_analyze_transcript_payload(...)` — zentraler Einstieg: 1 Chunk direkt analysieren, mehrere Chunks parallel analysieren + verdichten
- `_synthesize_chunk_analyses(...)` — LLM-Gesamtsynthese über Chunk-Ergebnisse, deterministisches `_merge_chunk_analyses` als Fallback ohne OpenRouter-Key

**Validierung**

- `25 passed` — `tests/test_search_tool_serpapi_youtube.py`, `tests/test_youtube_researcher_modes.py`, `tests/test_search_tool_youtube_contracts.py`
- CrossHair grün
- Lean grün

---

### Routing-Fix: Visual-Nemotron False Positives (2026-03-23)

**Problemstellung**

Normale Konversationstexte (z.B. über Predictive Maintenance) wurden fälschlicherweise zum Visual-Nemotron-Agenten geroutet, der sie als Browser-Navigationsbefehle interpretierte.

**Ursache**

`VISUAL_NEMOTRON_KEYWORDS` in `main_dispatcher.py` enthielt sehr generische deutsche Wörter: `dann`, `danach`, `anschließend`, `zuerst`, `unterhaltung`. Parallel dazu hatten `suche`, `formular`, `anmelden`, `login` als Einzelwörter in `_has_browser_ui_action` zu geringe Spezifität.

**Fix**

- `dann`, `danach`, `anschließend`, `zuerst`, `zuerst...dann`, `unterhaltung`, `cookie`, `formular`, `login`, `anmelden` aus `VISUAL_NEMOTRON_KEYWORDS` entfernt
- `suche`, `formular`, `anmelden`, `login` aus `_has_browser_ui_action` entfernt oder auf spezifische Phrasen (`formular ausfüllen`, `anmelden auf`) eingeschränkt
- Verbleibende Keywords sind ausnahmslos explizite Browser-Steuerungsphrsen

**Validierung**

- Manuell: alle Problem-Cases aus Screenshot-Kontext routen nicht mehr zu `visual_nemotron`

---

## 2026-03-26 bis 2026-03-27 — Goal-First Meta-Orchestrierung

### Problemstellung

Timus war in der Meta-Orchestrierung zu stark `recipe-first` und zu wenig `goal-first`.

Konkretes Symptom in dieser Session:

- Bei neuen Situationen wie `hole aktuelle Live-Daten und mache daraus eine Tabelle/Datei` hat Timus das Nutzerziel nicht sauber abstrahiert.
- Der richtige Ablauf `executor -> document` war fachlich vorhanden, wurde aber nicht verlässlich aus dem Ziel selbst abgeleitet.
- Dadurch musste die Kette mehrfach manuell nachgeschärft werden, obwohl ein vollwertiger Assistent solche neuen Kombinationen selbst erkennen sollte.

Zielbild dieser Arbeit:

- Timus soll zuerst verstehen, **was am Ende gebraucht wird**.
- Danach soll er die passende Agenten-/Tool-Kette ableiten.
- Bestehende Rezepte sollen als Sicherheitsnetz erhalten bleiben, aber nicht mehr die einzige Denkform sein.

### Phase 1 — Advisory Goal-First Layer

**Ziel**

Eine erste Ziel- und Fähigkeits-Schicht einziehen, ohne die bestehende Orchestrierung sofort hart umzubauen.

**Umgesetzt**

- Neues Zielmodell in [goal_spec.py](/home/fatih-ubuntu/dev/timus/orchestration/goal_spec.py)
  - `domain`
  - `freshness`
  - `evidence_level`
  - `output_mode`
  - `artifact_format`
  - `uses_location`
  - `delivery_required`
  - `goal_signature`
- Neuer Fähigkeitsgraph in [capability_graph.py](/home/fatih-ubuntu/dev/timus/orchestration/capability_graph.py)
  - bildet benötigte Fähigkeiten gegen vorhandene Agentenprofile ab
  - erkennt Lücken wie fehlende strukturierte Ausgabe- oder Delivery-Stufen
- Neuer beratender Planner in [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
  - berechnet empfohlene Ketten
  - bleibt in Phase 1 ausdrücklich nur advisory
- Integration in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `classify_meta_task(...)` liefert jetzt zusätzlich:
    - `goal_spec`
    - `capability_graph`
    - `adaptive_plan`
- Durchleitung bis in den Meta-Handoff:
  - [orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)
  - [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)

**Wirkung**

- Meta sieht jetzt nicht mehr nur `task_type` und `recipe_id`, sondern zusätzlich das eigentliche Zielmodell.
- Der Handoff enthält jetzt:
  - `goal_spec_json`
  - `capability_graph_json`
  - `adaptive_plan_json`

**Validierung**

- `52 passed`
- CrossHair grün
- Lean grün

**Commit**

- `a829f6a` — `Add goal-first advisory planning for meta orchestration`

**Live-Aktivierung**

- `timus-mcp` neu gestartet am **27. März 2026 um 00:33 CET**
- Health danach grün

### Phase 2 — Planner-First, Recipes-Fallback

**Ziel**

Die Planner-Schicht nicht nur anzeigen, sondern bei sicheren Fällen wirklich vor die Rezeptwahl setzen.

**Umgesetzt**

- Neue Safe-Adoption-Logik in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py):
  - `resolve_adaptive_plan_adoption(...)`
- Harte Guardrails für Planner-Adoption:
  - nur definierte sichere Task-Typen
  - `confidence >= 0.78`
  - maximale Kettenlänge `4`
  - Entry-Agent darf nicht kippen
  - Recipe-Hint muss auf aktuelles Rezept oder vorhandene Alternativen zeigen
  - Rezeptkette und Planner-Kette müssen übereinstimmen
- Dispatcher-Adoption in [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - sichere Planner-Empfehlungen werden vor dem Meta-Lauf übernommen
  - Ergebnis wird als `planner_resolution` im Handoff sichtbar gemacht
- Meta-Auswahl in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - `_select_initial_recipe_payload(...)` prüft jetzt zuerst den Planner
  - Strategy- und Learning-Fallbacks bleiben erhalten

**Wirkung**

- Bei sicheren Fällen kann Meta jetzt tatsächlich von einem Basisrezept auf eine passendere Kette umschalten.
- Beispielziel:
  - von `simple_live_lookup`
  - auf `simple_live_lookup_document`
  - also praktisch `meta -> executor -> document`
- Gleichzeitig bleibt die Sicherheitsarchitektur erhalten:
  - wenn der Planner unsicher ist, bleibt das bestehende Rezept aktiv

**Neue Handoff-Daten**

- `planner_resolution_json`

**Validierung**

- `33 passed`
- CrossHair grün
- Lean grün

**Commit**

- `88211ae` — `Adopt safe adaptive plans before recipe fallback`

**Live-Aktivierung**

- `timus-mcp` neu gestartet am **27. März 2026 um 12:20 CET**
- `Application startup complete` um **12:20:30 CET**
- Health grün um **12:20:32 CET**

### Phase 3 — Runtime Gap-Replanning nach Stage-Ergebnissen

**Ziel**

Timus soll nicht nur zu Beginn eine gute Kette wählen, sondern auch **während** eines laufenden Rezepts erkennen, wenn das Ziel noch nicht vollständig erfüllt ist.

Konkreter Ziel-Fall:

- Ein `research`- oder `executor`-Schritt liefert bereits verwertbares Material.
- Das Nutzerziel verlangt aber noch ein Artefakt oder eine Tabelle.
- Timus soll dann selbst erkennen: `document_output` fehlt noch und muss sicher nachgeschaltet werden.

**Umgesetzt**

- Neue Runtime-Gap-Erkennung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py):
  - `resolve_runtime_goal_gap_stage(...)`
- Die Runtime-Regel ist konservativ:
  - aktuell nur für fehlende `document_output`-Stufen
  - nur bei `artifact`-/`table`-Zielen
  - nur nach erfolgreicher vorheriger Stage
  - nur wenn verwertbares Material bereits vorhanden ist
  - keine Doppel-Insertion, wenn `document_output` schon im Rezept oder Verlauf enthalten ist
- Integration in den Meta-Lauf in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - nach erfolgreicher Stage wird geprüft, ob noch eine sichere Dokument-Stufe fehlt
  - falls ja, wird `document_output` zur Laufzeit eingefügt
  - die effektive Agentenkette wird für Telemetrie und Feedback mitgezogen
- Abschlussausgabe verfeinert:
  - saubere Dokument-Läufe geben direkt das Artefakt-Ergebnis zurück
  - Recovery-/Fehlerpfade behalten die ausführliche Rezeptzusammenfassung

**Wirkung**

- Timus kann jetzt innerhalb eines laufenden Rezepts Ziel-Lücken erkennen und schließen.
- Beispiel:
  - Ausgangsrezept: `meta -> research`
  - Ziel: `aktuelle LLM-Preise recherchieren und als txt speichern`
  - neuer Laufzeitpfad:
    - `research` liefert verwertbares Material
    - Meta erkennt fehlendes Artefakt
    - `document_output` wird sicher nachgeschaltet

**Validierung**

- `31 passed`
- CrossHair grün
- Lean grün

**Commit**

- `8b43e9b` — `Add runtime goal-gap replanning for document output`

**Status**

- Phase 3 ist fertig implementiert und committed.
- Live-Aktivierung ist zu diesem Stand noch nicht erfolgt.

### Phase 4 — Learned Chains + breiteres Runtime-Replanning (abgeschlossen)

**Ziel**

Timus soll nicht nur Ziele erkennen und sichere Ketten auswählen, sondern aus erfolgreichen Läufen lernen und weitere Ziel-Lücken selbstständig schließen.

Der Kernsprung dieser Phase:

- von statischer Ziel- und Fähigkeitsplanung
- hin zu erfahrungsbasierter Kettenpriorisierung und breiterem Runtime-Replanning

**Bisher umgesetzt**

- Neue Lernschicht in [adaptive_plan_memory.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_plan_memory.py)
  - persistiert Chain-Outcomes pro `goal_signature`
  - speichert empfohlene Kette, finale Kette, Erfolg/Misserfolg, Laufzeit und Runtime-Gap-Insertions
  - aggregiert daraus konservative Chain-Statistiken mit `learned_bias` und `learned_confidence`
- Planner-Anreicherung in [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
  - Candidate-Scores koennen jetzt durch gelernte positive oder negative Erfahrungswerte nachjustiert werden
  - Candidate-Payloads zeigen `learned_bias` und Evidenz
- Integration in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `classify_meta_task(...)` liest gelernte Chain-Statistiken fuer die aktuelle `goal_signature`
  - der Adaptive Planner bekommt diese Daten direkt in den Planungsaufruf
- Rueckschreiben in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - echte Rezeptlaeufe schreiben ihre Outcomes jetzt in den Lernspeicher zurueck
  - Runtime-Gap-Insertions wie `runtime_goal_gap_document` werden dabei explizit markiert
- Erweiterung der Runtime-Gap-Erkennung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `runtime_goal_gap_verification`
  - `runtime_goal_gap_delivery`
- Integration in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - `verification_output` wird vor spaeteren `document`-/`communication`-Stages eingefuegt
  - `communication_output` wird nach erfolgreicher Material- oder Artefakt-Erzeugung sicher nachgeschaltet
  - Communication-Handoffs tragen jetzt auch `attachment_path` und `source_material`
- Validierung

### 2026-03-27 — Wochenbeobachtung fuer Goal-First- und Self-Hardening-Livebetrieb

**Ziel**

Die neuen Autonomiepfade sollen nicht nur live laufen, sondern eine Woche lang strukturiert beobachtet und danach belastbar ausgewertet werden.

**Umgesetzt**

- Neue Beobachtungsschicht in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - strukturierter JSONL-Log unter `logs/autonomy_observation.jsonl`
  - Session-State unter `logs/autonomy_observation_state.json`
  - Start-/Fensterverwaltung fuer ein 7-Tage-Beobachtungsfenster
  - verdichtete Summary-Funktion fuer Planner-, Runtime-Gap- und Self-Hardening-Signale
- Neue Hooks in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - `meta_recipe_outcome`
  - `runtime_goal_gap_inserted`
- Neue Hooks in [self_hardening_runtime.py](/home/fatih-ubuntu/dev/timus/orchestration/self_hardening_runtime.py)
  - `self_hardening_runtime_event`
  - deckt dadurch auch `self_modify_started` / `self_modify_finished` sauber mit ab
- Neue Hilfsskripte:
  - [start_autonomy_observation.py](/home/fatih-ubuntu/dev/timus/scripts/start_autonomy_observation.py)
  - [evaluate_autonomy_observation.py](/home/fatih-ubuntu/dev/timus/scripts/evaluate_autonomy_observation.py)

**Wirkung**

- Wir muessen nach der Beobachtungswoche nicht mehr manuell Rohlogs auswerten.
- Die Auswertung kann jetzt direkt messen:
  - wie oft Planner-Adoptionen wirklich genutzt wurden
  - welche Runtime-Gaps eingefuegt wurden
  - wie erfolgreich Meta-Rezeptketten liefen
  - wie oft Self-Hardening und Self-Modify aktiv wurden

**Validierung**

- neue Unit-Tests fuer Beobachtungsspeicher und Summary
- Meta-Rezept-Test fuer Runtime-Gap-Observation
- Self-Hardening-Runtime-Test fuer Observation-Hook
- CrossHair auf den Summary-Vertrag
- Lean erweitert

**Beobachtungspunkt waehrend der Wochenbeobachtung**

- `user_reported_state_update` / `state_invalidation`
  - Beispiel:
    - Nutzer: `ich habe meinen handy standort aktualisiert`
    - Meta wiederholt trotzdem den alten Status `kein synchronisierter Handy-Standort`
  - Interpretation:
    - Meta erkennt die Aussage noch nicht als Zustandskorrektur gegen einen veralteten Tool-/Agenten-Output
  - Soll spaeter ausgewertet werden als:
    - Wie oft Nutzer einen geaenderten Zustand meldet
    - Wie oft Timus danach noch stale Resultate wiederholt
    - Wie oft stattdessen eine frische Revalidierung erfolgt
  - Geplanter spaeterer Ausbau:
    - `State Correction Handling`
    - Nutzerhinweis invalidiert den betroffenen Teilkontext
    - Meta erzwingt danach frischen Statuscheck statt normalem Follow-up-Rezept

### Nach der Beobachtungswoche — Plan fuer eine semantische Meta-Verstehensschicht

**Ausloeser**

Ein aktueller Fehlfall zeigt die naechste Reifegradgrenze von Timus klar:

- Anfrage: `ich moechte ein cafe eroeffnen welches land ist am besten geeignet`
- Falsches Verhalten:
  - Meta hat den Begriff `Cafe` zu stark als lokalen Places-/Maps-Hinweis gelesen
  - daraus wurde sinngemaess `location_local_search`
  - der aktive Standort wurde dadurch faelschlich priorisiert
- Eigentliches Ziel:
  - keine lokale Suche
  - sondern eine strategische Geschaefts- und Standortentscheidung

**Problemkern**

Meta arbeitet aktuell noch zu stark als:

- Task-Klassifikator
- Rezeptwaehler
- Heuristik-Orchestrator

und noch nicht stark genug als:

- Bedeutungs-Interpreter
- Intent-Modellierer
- Konfliktpruefer zwischen moeglichen Lesarten

**Zielbild**

Vor der Rezeptwahl soll eine neue Schicht eingefuehrt werden:

- `Meta Semantic Understanding Layer`

Diese Schicht soll nicht nur Keywords lesen, sondern die Anfrage in konkurrierende Lesarten zerlegen und semantisch priorisieren.

**Architekturplan**

1. `semantic_intent.py`
- neue Datei in `orchestration/`
- erzeugt 2-4 moegliche Lesarten einer Anfrage
- Beispiel:
  - `local_place_lookup`
  - `business_planning`
  - `country_comparison`
  - `knowledge_research`

2. `SemanticIntentSpec`
- strukturierte Darstellung der Bedeutung
- geplante Felder:
  - `primary_intent`
  - `secondary_intents`
  - `domain_object`
  - `decision_scope`
  - `freshness_need`
  - `location_relevance`
  - `artifact_need`
  - `delivery_need`
  - `evidence_need`
  - `competing_interpretations`
  - `rejection_reasons`

3. Konfliktregeln zwischen Lesarten
- Beispiele:
  - `country_comparison` widerspricht `location_local_search`
  - `business_planning` widerspricht `nearby_places`
  - `current_position_lookup` darf nicht aus einem blossen Branchenwort abgeleitet werden
- diese Konflikte muessen explizit modelliert werden statt nur implizit in Keywords zu stecken

4. Integration in `meta_orchestration.py`
- `classify_meta_task(...)` soll nicht mehr direkt aus Keywords auf `task_type` springen
- neuer Ablauf:
  - Query normalisieren
  - semantische Lesarten erzeugen
  - Konflikte bewerten
  - daraus `goal_spec` und `task_type` ableiten

5. `goal_spec.py` erweitern
- das Zielmodell soll spaeter nicht nur Task-Typen tragen, sondern schon die semantische Absicht reflektieren
- moegliche neue Felder:
  - `intent_family`
  - `decision_scope`
  - `location_relevance_confidence`

6. Adaptive Planner spaeter mitnutzen
- der Planner soll nicht nur `GoalSpec + CapabilityGraph` lesen
- sondern auch die semantische Hauptlesart und verworfene Alternativen sehen
- damit Timus spaeter sagen kann:
  - `Cafe` erkannt
  - aber `business_planning` gewinnt gegen `local_search`

7. Tests / Validierung
- neue Regressionen fuer typische Fehlklassen:
  - `ich moechte ein cafe eroeffnen welches land ist am besten geeignet`
  - `ich will ein restaurant gruenden wo waere der beste markt`
  - `welches land ist fuer eine baeckerei am attraktivsten`
  - weiterhin lokal korrekt:
    - `suche mir ein cafe in meiner naehe`
    - `wo bekomme ich gerade kaffee`
- dazu:
  - CrossHair-Contracts fuer Konfliktregeln
  - Lean-Invarianten fuer ausgeschlossene Fehlklassifikationen

**Rollout-Vorschlag**

Phase A
- nur advisory neben der bisherigen Klassifikation
- protokollieren, wenn semantische Lesart und heuristische Klassifikation auseinanderlaufen

Phase B
- semantic-first, heuristic-fallback

Phase C
- semantische Lesarten in Learned Chains und Runtime-Gaps rueckkoppeln

**Erfolgskriterium**

Timus soll bei mehrdeutigen Anfragen nicht mehr nur auf bekannte Rezepte springen, sondern die eigentliche Bedeutung priorisieren.

Das konkrete Minimalziel:

- `Cafe` in einer Gruendungs- oder Laendervergleichsfrage darf nie mehr automatisch zu `location_local_search` fuehren.
  - `26 passed` in der fokussierten Runtime-Gap-Suite
  - `48 passed` fuer den Phase-4-Lernsockel
  - CrossHair gruen
  - Lean gruen

**Erreichte Zielabdeckung**

- Lernspeicher fuer erfolgreiche und gescheiterte Agentenketten
- Planner-Anreicherung mit Erfahrungswissen
- Runtime-Gap `document_output`
- Runtime-Gap `delivery`
- Runtime-Gap `verification`

**Commits**

- `2831bde` — `Add learned chain memory for adaptive planning`
- `a5ec788` — `Complete adaptive runtime gap replanning`

**Status**

- Phase 4 ist vollständig implementiert, committed und nach `origin/main` gepusht.
- Live-Aktivierung ist zu diesem Stand noch nicht erfolgt.

**Geplante Dateien**

- Neue Datei [adaptive_plan_memory.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_plan_memory.py)
  - persistiert gelernte Ketten kompakt und deterministisch
- Erweiterung in [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
  - kombiniert statische Planner-Heuristik mit Erfahrungsdaten
- Erweiterung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - zusätzliche Runtime-Gap-Typen
  - sichere Adoptionslogik für gelernte Ketten
- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - schreibt Outcome-Signale nach Stage- und Gesamterfolg zurück
  - nutzt gelernte Ketten nur innerhalb harter Guardrails
- Kleiner Infrastruktur-Fix in [verify_pre_commit_lean.py](/home/fatih-ubuntu/dev/timus/scripts/verify_pre_commit_lean.py)
  - nutzt fuer `CiSpecs.lean` jetzt bevorzugt die lokal installierte Lean-Toolchain statt den `elan`-Wrapper
  - vermeidet unnoetige Download-/Timeout-Pfade in der lokalen Verifikation

**Guardrails**

- keine freie Rekursion
- maximale Kettenlänge bleibt begrenzt
- gelernte Ketten dürfen nur bekannte Agenten nutzen
- `research` bleibt ein teurer Spezialpfad und wird nicht aggressiv hochpriorisiert
- negative Lernsignale dürfen nur abwerten, nicht sofort alle Alternativen blockieren
- neue Runtime-Gap-Typen werden einzeln und konservativ aktiviert

**Implementierungsreihenfolge**

1. Lernspeicher für Ketten-Outcome
2. Planner-Priorisierung mit Erfahrungsdaten
3. Runtime-Gap `delivery`
4. Runtime-Gap `verification`
5. erweiterte Regressionen, Contracts und Lean-Invarianten

**Erfolgskriterium**

- Timus soll bei wiederkehrenden Zielmustern schneller zur funktionierenden Kette greifen
- Timus soll bekannte Fehlpfade seltener wiederholen
- Timus soll nach erfolgreichen Zwischenresultaten weitere sichere Ziel-Lücken selbst schließen

### Aktueller Stand

Timus ist nach dieser Session auf einem deutlich besseren Orchestrierungsniveau, aber noch nicht am Endziel.

**Jetzt live vorhanden**

- Goal-first-Zielmodell
- Capability-Mapping
- Advisory-Planung
- Sichere Planner-Adoption vor Rezept-Fallback
- Vollständige Meta-Handoff-Sichtbarkeit der neuen Planungsdaten
- Sichere Runtime-Lückenerkennung für `document`, `verification` und `delivery` ist implementiert, aber noch nicht live aktiviert

**Noch nicht fertig**

- optionale weitere Gap-Typen
  - z. B. `local context`
- breitere Nutzung außerhalb der aktuellen Meta-/Recipe-Pfade

### Relevante Dateien dieser Session

- [goal_spec.py](/home/fatih-ubuntu/dev/timus/orchestration/goal_spec.py)
- [capability_graph.py](/home/fatih-ubuntu/dev/timus/orchestration/capability_graph.py)
- [adaptive_plan_memory.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_plan_memory.py)
- [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [communication.py](/home/fatih-ubuntu/dev/timus/agent/agents/communication.py)
- [verify_pre_commit_lean.py](/home/fatih-ubuntu/dev/timus/scripts/verify_pre_commit_lean.py)
- [CiSpecs.lean](/home/fatih-ubuntu/dev/timus/lean/CiSpecs.lean)
- [test_adaptive_plan_memory.py](/home/fatih-ubuntu/dev/timus/tests/test_adaptive_plan_memory.py)
- [test_adaptive_plan_memory_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_adaptive_plan_memory_contracts.py)
- [test_runtime_goal_gap_replan.py](/home/fatih-ubuntu/dev/timus/tests/test_runtime_goal_gap_replan.py)
- [test_runtime_goal_gap_replan_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_runtime_goal_gap_replan_contracts.py)
- [test_meta_recipe_execution.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_recipe_execution.py)

### Nächster sinnvoller Schritt

Den jetzt gepushten Phase-3/Phase-4-Stand live schalten und beobachten:

- erweitertes Runtime-Replanning auf `timus-mcp` aktivieren
- echte Live-Fälle prüfen, ob `executor -> research`, `research -> document` und `document -> communication` stabil nachgezogen werden
- beobachten, ob gelernte Ketten bei wiederkehrenden `goal_signature`-Mustern schon sichtbar bevorzugt werden
- anschließend entscheiden, ob ein weiterer konservativer Gap-Typ wie `local context` sinnvoll ist

---

## 2026-03-29 — Meta-Ausbau Phase M1: Diagnosis Discipline

### Beobachtungsbasis

Die laufende Autonomy-Observation zeigt inzwischen stabil:

- Meta ist der Rettungsanker, wenn Dispatcher oder Spezialisten scheitern.
- Meta kann replannen und direkte Tool-Rescues ausführen.
- Meta ist aber noch zu unpräzise bei:
  - belegte Ursache vs. Hypothese
  - führende Diagnose vs. Nebenhypothese
  - developer-taugliche Anweisungen an andere Agenten
- Der Nutzer fungiert noch zu oft als Schiedsrichter zwischen `meta`, `system`, `reasoning`, `shell`.

Diese Phase zielt deshalb nicht auf neue Fähigkeiten, sondern auf sauberere Diagnose- und Delegationsdisziplin von Meta.

### Ziel

Meta soll Diagnosen anderer Agenten und eigene Beobachtungen strukturierter auswerten und daraus präzisere, belegbare Handlungsanweisungen ableiten.

Meta soll danach:

- Fakten und Vermutungen sauber trennen
- eine führende Diagnose auswählen
- unbelegte Behauptungen unterdrücken
- nur verifizierte Dateien und Ursachen in Developer-Tasks schreiben

### Scope

1. Diagnosis Record einführen

- neue strukturierte Diagnoseform, z. B. in [diagnosis_records.py](/home/fatih-ubuntu/dev/timus/orchestration/diagnosis_records.py)
- Felder:
  - `source_agent`
  - `claim`
  - `evidence_level`
  - `evidence_refs`
  - `confidence`
  - `actionability`
  - `verified_paths`
  - `verified_functions`

2. Lead Diagnosis Auswahl

- Meta soll konkurrierende Diagnosen ranken
- genau eine `lead_diagnosis` auswählen
- übrige Diagnosen als `supporting` oder `rejected` markieren
- keine Mischdiagnosen mehr aus teilweise widersprüchlichen Aussagen

3. Developer-Task Compiler härten

- Meta darf nur noch in Tasks schreiben:
  - verifizierte Dateien
  - verifizierte Funktionen
  - verifizierte Ursachen
  - konkrete gewünschte Änderung
- unbelegte Dateipfade oder falsche "BELEGT"-Behauptungen müssen unterdrückt werden

4. Belegsprache normalisieren

- `BELEGT` nur mit echten Evidenzreferenzen
- sonst:
  - `Plausible Hypothese`
  - `Noch zu verifizieren`
  - `Unbestätigt`

5. Beobachtung erweitern

- neue Meta-Metriken in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py):
  - `lead_diagnosis_selected`
  - `diagnosis_conflict_detected`
  - `developer_task_compiled`
  - `unverified_claim_suppressed`

### Geplante Dateien

- neue Datei [diagnosis_records.py](/home/fatih-ubuntu/dev/timus/orchestration/diagnosis_records.py)
- Erweiterung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- Erweiterung in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)

### Guardrails

- keine freie Konsensmaschine für alle Agenten in M1
- keine neue große semantische Intent-Schicht in M1
- keine automatische Umsetzung von Diagnose in Code-Patch in M1
- Fokus nur auf:
  - Diagnosequalität
  - Evidenzdisziplin
  - präziseren Delegationsaufträgen

### Implementierungsreihenfolge

1. Diagnosis Record Datentyp
2. Lead-Diagnosis-Ranking
3. Developer-Task-Compiler mit Verifikations-Gate
4. Observation-Metriken
5. Tests, Contracts, Lean

### Erfolgskriterium

- Meta soll keine falschen "BELEGT"-Aussagen mehr an Developer-Tasks durchreichen
- Meta soll bei konkurrierenden Diagnosen eine saubere führende Diagnose benennen
- Meta soll weniger Nutzerkorrekturen benötigen, um einen präzisen Task zu formulieren
- Die interne Delegation soll nachvollziehbarer und präziser werden

### M1-Implementierungsstand

**Umgesetzt**

- neue Diagnose-Schicht in [diagnosis_records.py](/home/fatih-ubuntu/dev/timus/orchestration/diagnosis_records.py)
  - `DiagnosisRecord`
  - `DiagnosisResolution`
  - `DeveloperTaskBrief`
  - Normalisierung von Evidenzstufen
  - Lead-Diagnosis-Auswahl
  - Developer-Task-Brief mit Suppression unverifizierter Claims
- neue Wrapper in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `build_meta_diagnosis_resolution(...)`
  - `compile_meta_developer_task_payload(...)`
- Integration in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Developer-Handoff wird jetzt mit Lead-Diagnose, verifizierten Pfaden/Funktionen und Suppression-Countern angereichert
  - komplexe Handoff-Werte werden stabil als JSON gerendert
  - neue Observation-Events fuer:
    - `lead_diagnosis_selected`
    - `diagnosis_conflict_detected`
    - `developer_task_compiled`
    - `unverified_claim_suppressed`
- Erweiterung in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neue Meta-Metriken fuer Diagnosequalitaet und Task-Kompilierung

**Validierung**

- `53 passed` in der fokussierten Pytest-Suite
- CrossHair gruen ueber [test_diagnosis_records_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_diagnosis_records_crosshair.py)
- Hypothesis enthalten in [test_diagnosis_records_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_diagnosis_records_contracts.py)
- Lean gruen

**Status**

- M1-Grundlage ist implementiert
- noch nicht live auf `timus-mcp` neu geladen
- naechster sinnvoller Schritt: echte Meta-zu-Developer-Handoffs produktiv beobachten

### Geplanter Folgeausbau: Meta Phase M2 — Root-Cause-First Task Emission

### Beobachtungsbasis

Die M1-Beobachtung zeigt inzwischen klar:

- Meta kann brauchbare Diagnosen liefern oder von `system`/`shell` uebernehmen
- Meta verliert bei der Taskableitung aber noch zu oft die Spur zum primaeren Root Cause
- Root Cause, Folgeeffekte, Monitoring-Ideen und Spaetmassnahmen werden noch vermischt
- dadurch entstehen Developer-Tasks, die plausibel klingen, aber nicht den eigentlichen Incident zuerst adressieren

### Ziel

Meta soll bei technischen Incidents zuerst genau **einen primaeren Fix-Task** emitten, der auf dem am besten belegten Root Cause basiert.

Folgeaufgaben wie:

- Monitoring
- Guardrails
- Alerting
- Cleanup
- Telemetrie

duerfen erst danach und getrennt als Folge-Tasks erscheinen.

### Scope

1. Root-Cause-First Resolution

- Meta soll aus mehreren Diagnosen eine `primary_fix_target` ableiten
- dieser muss enthalten:
  - primaere Ursache
  - primaere Datei(en)
  - primaere Funktion(en)
  - primaeren Aenderungstyp

2. Incident Task Split

- Tasks werden in Klassen getrennt:
  - `primary_fix`
  - `followup_monitoring`
  - `followup_hardening`
  - `followup_cleanup`
- fuer die erste Ausgabe an Developer/Shell ist nur `primary_fix` erlaubt

3. Root-Cause Gate vor Task-Emission

- kein Developer-Task, wenn diese Punkte fehlen:
  - belegte primaere Ursache
  - mindestens ein verifizierter Zielpfad
  - klarer Aenderungstyp
- wenn das Gate nicht erfuellt ist:
  - erst Verifikation
  - kein halb-präziser Task

4. Folgeaufgaben explizit abspalten

- wenn Monitoring oder Telemetrie sinnvoll sind, muessen sie als getrennte `followup_tasks` erscheinen
- sie duerfen nicht den primaeren Fix-Task verunreinigen

5. Observation erweitern

- neue Meta-Metriken:
  - `primary_fix_task_emitted`
  - `followup_task_deferred`
  - `root_cause_gate_blocked`
  - `task_mix_suppressed`

### Geplante Dateien

- neue Datei [root_cause_tasks.py](/home/fatih-ubuntu/dev/timus/orchestration/root_cause_tasks.py)
  - Datentypen fuer Primary/Followup-Tasks
- Erweiterung in [diagnosis_records.py](/home/fatih-ubuntu/dev/timus/orchestration/diagnosis_records.py)
  - Root-Cause-Selektion und Task-Split-Helfer
- Erweiterung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `compile_root_cause_task_payload(...)`
- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Developer-Handoff nur fuer `primary_fix`
  - Folgeaufgaben separat markieren
- Erweiterung in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neue M2-Metriken

### Guardrails

- genau ein primaerer Fix-Task pro Incident-Ausgabe
- Monitoring nie als primaerer Fix, wenn ein belegter Root Cause existiert
- kein Mischen von `primary_fix` und `followup_monitoring` in einem Task
- wenn Root Cause unklar bleibt:
  - `verification_needed`
  - kein ueberdehnter Fix-Task

### Implementierungsreihenfolge

1. Root-Cause-Task-Datentypen
2. Root-Cause-Gate
3. Primary-vs-Followup-Split
4. Meta-Handoff-Anpassung
5. Observation, Tests, Contracts, Lean

### Erfolgskriterium

- Meta emittiert bei technischen Incidents zuerst einen klaren `primary_fix`
- Monitoring/Alerting tauchen nur noch als getrennte Folgeaufgaben auf
- Nutzer muessen Meta seltener korrigieren, welcher Task der eigentliche erste Schritt ist
- die erste Taskausgabe wird fuer Laien nachvollziehbarer und fuer Developer umsetzbarer

### M2-Implementierungsstand

**Umgesetzt**

- neue Root-Cause-Schicht in [root_cause_tasks.py](/home/fatih-ubuntu/dev/timus/orchestration/root_cause_tasks.py)
  - `classify_change_focus(...)`
  - `RootCauseTask`
  - `RootCauseTaskPayload`
  - `build_root_cause_task_payload(...)`
- Erweiterung in [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
  - `compile_meta_developer_task_payload(...)` liefert jetzt zusaetzlich `root_cause_tasks`
- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Developer-Handoffs emitten jetzt entweder:
    - einen klaren `primary_fix`
    - oder einen geblockten `verification_needed`-Pfad
  - Follow-up-Aufgaben werden getrennt als `followup_tasks_json` bzw. `deferred_followup_tasks_json` ausgegeben
  - der eigentliche Developer-Task-Text wird auf den primaeren Fix oder die Verifikationsanweisung umgeschrieben
- Erweiterung in [autonomy_observation.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_observation.py)
  - neue M2-Metriken:
    - `primary_fix_task_emitted`
    - `followup_task_deferred`
    - `root_cause_gate_blocked`
    - `task_mix_suppressed`

**Validierung**

- `16 passed` in der fokussierten M2-Test-Suite
- CrossHair gruen ueber [test_root_cause_tasks_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_root_cause_tasks_crosshair.py)
- Hypothesis enthalten in [test_root_cause_tasks_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_root_cause_tasks_contracts.py)
- Lean gruen

**Status**

- M2 ist implementiert, aber noch nicht live auf `timus-mcp` neu geladen
- naechster sinnvoller Schritt: Neustart und gezielte Beobachtung echter Meta-Developer-Tasks auf `primary_fix` vs. `followup`

## M2.1 - system_diagnosis an Root-Cause-first anbinden

### Problem

- `M2` war technisch vorhanden, wurde aber im wichtigen Rezept `system_diagnosis` nicht genutzt
- Meta konnte Diagnosen liefern, emittierte bei Prompts wie
  - `erstelle daraus genau einen Primary-Fix-Task`
  - `wenn nicht belegt, gib verification needed aus`
  noch keinen echten `primary_fix`
- die Beobachtung zeigte deshalb trotz `M2` weiter:
  - `Lead-Diagnosen gewaehlt: 0`
  - `Developer-Tasks kompiliert: 0`
  - `Primary-Fix-Tasks emittiert: 0`

### Umsetzung

- Erweiterung in [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
  - Erkennung, ob eine `system_diagnosis`-Anfrage explizit einen Root-Cause-Task verlangt
  - Extraktion von Diagnose-Claims direkt aus dem erfolgreichen `system`-Stage-Ergebnis
  - Normalisierung von Datei- und Evidenzreferenzen aus freien Diagnose-Texten
  - Wiederverwendung des bestehenden `M1/M2`-Compilers auch fuer `system_diagnosis`
  - direkte Ausgabe von:
    - `Primary-Fix-Task`
    - oder `verification needed`
- kein zweiter Task-Compiler gebaut; `M2.1` ist bewusst nur die fehlende Verkabelung des vorhandenen Root-Cause-first-Pfads

### Validierung

- neue End-to-End-Abdeckung in [test_meta_recipe_execution.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_recipe_execution.py)
  - `system_diagnosis` emittiert jetzt bei belegter Vision-Root-Cause einen `Primary-Fix-Task`
  - `system_diagnosis` emittiert bei zu schwacher Ursache `verification needed`
- fokussierte Suite:
  - `40 passed`
- CrossHair gruen ueber [test_root_cause_tasks_crosshair.py](/home/fatih-ubuntu/dev/timus/tests/test_root_cause_tasks_crosshair.py)
- Lean gruen

### Status

- `M2.1` ist implementiert
- Neustart von `timus-mcp` fuer den neuen Stand steht noch aus
- naechster sinnvoller Schritt: Live-Test mit einem echten `system_diagnosis`-Prompt auf `Primary-Fix-Task` / `verification needed`

## Beobachtungspunkt - Vision/OCR Speicherdruck und OOM

### Live-Befund

- Am **29.03.2026 um 22:53:42 CEST** wurde `timus-mcp` vom OOM-Killer beendet
- der sichtbare Nutzerfehler war nur `Failed to fetch`
- `systemd` hat den Dienst danach automatisch neu gestartet

### Wahrscheinliche Ursache

- der problematische Hot-Path ist aktuell kein reiner GPU-Pfad
- [tool.py](/home/fatih-ubuntu/dev/timus/tools/florence2_tool/tool.py)
  - Florence-2 laeuft dort auf `cuda`, wenn verfuegbar
  - der zugehoerige PaddleOCR-Pfad wird dort aber hart auf `CPU` initialisiert
    - `use_gpu: False`
    - `device: "cpu"`
- die Logs zeigen genau diesen Mischbetrieb:
  - `Florence-2 Device: cuda`
  - direkt danach `PaddleOCR geladen (CPU)`
- dadurch entsteht ueber Zeit hoher kombinierter VRAM-/RAM-Druck statt eines sauberen, einheitlichen Device-Pfads

### Einordnung

- das Problem ist nicht nur `GPU wird spaeter nicht mehr erkannt`
- der aktuelle Florence/OCR-Pfad ist bereits heute architektonisch uneinheitlich
- zusaetzlich existieren weitere OCR-Zweige im System, was den Druck und die Debug-Komplexitaet erhoeht

### Nach der Beobachtungswoche angehen

1. Vision/OCR-Pfad vereinheitlichen
- kein CPU/GPU-Mischbetrieb im selben Hot-Path

2. Florence-2- und OCR-Lifecycle haerten
- aggressiveres Freigeben/Recyceln von Modellen und Caches
- keine unnötigen Mehrfachinitialisierungen unter Last

3. OCR-Backends konsolidieren
- klarer Primärpfad
- saubere Fallback-Regeln
- keine parallelen schweren OCR-Wege ohne Not

4. Observability erweitern
- Device-Wechsel
- CPU/GPU-Fallback
- Modellinitialisierungen
- Peak-Memory vor Vision-/OCR-Aufrufen

## Nach Beobachtungswoche - Dispatcher Semantic Upgrade + Meta/Dispatcher Buddy Loop

### Aktueller Befund

- der Dispatcher faellt zu oft mit `empty_decision` auf Meta zurueck
- besonders schlecht sind aktuell:
  - Umgangssprache
  - kurze Anschlussfragen
  - implizite Referenzen
  - Meta-Kommunikation wie
    - `du verstehst mich nicht`
    - `uebernehme Empfehlung 2`
    - `bist du ein funktionierendes ki system`
- Meta ist in vielen dieser Faelle semantisch staerker als der Dispatcher und muss den Lauf retten

### Prioritaet

- **Top-Prioritaet 1 nach der Beobachtungswoche**
  - `Dispatcher Semantic Upgrade for colloquial / follow-up / intent-aware routing`

### Zielbild

- Dispatcher und Meta sollen nicht nur strikt nacheinander arbeiten
- sie sollen als **Buddy-/Agenten-Team** zusammenwirken:
  - Dispatcher = schnelle Frontdoor-Semantik und Erstsortierung
  - Meta = tiefere Bedeutungspruefung, Replanning und Konfliktaufloesung
- bei Unsicherheit soll der Dispatcher nicht nur `empty_decision` liefern, sondern:
  - eine semantische Vorhypothese
  - erkannte Unsicherheit
  - moegliche Lesarten / Kandidaten
  an Meta uebergeben

### Gewuenschte Eigenschaften

1. Umgangssprache besser verstehen
- locker formulierte Anfragen
- unvollstaendige Sätze
- kurze Frustrations- oder Korrektur-Saetze

2. Follow-up-Verstaendnis
- Bezug auf vorherige Antwort
- Bezug auf `Empfehlung 2`, `das`, `so`, `nochmal`, `dieselbe Sache`

3. Intent-aware Routing
- nicht nur Keywords
- sondern Bedeutung, Ziel und Gespraechszustand

4. Buddy-Kommunikation zwischen Dispatcher und Meta
- Dispatcher liefert bei Unsicherheit strukturierte Voranalyse statt Leerausfall
- Meta kann diese Voranalyse uebernehmen, bestaetigen, korrigieren oder erweitern

5. Beobachtbare Qualitaet
- weniger `dispatcher_meta_fallback: empty_decision`
- weniger Nutzerhinweise wie `du verstehst mich nicht`
- weniger Meta-Rettung fuer triviale Frontdoor-Faelle

### Nach der Beobachtungswoche konkret angehen

1. Dispatcher-Prompt und Output-Schema fuer Umgangssprache/Follow-ups erweitern
2. Unsicherheitsausgabe statt Leerausfall
3. strukturierte Buddy-Handoff-Daten an Meta
4. gemeinsame Beobachtungsmetriken fuer Dispatcher + Meta
5. spaeter optional: kleiner semantischer Vorinterpretations-Worker nur fuer Frontdoor-Faelle

### Konkretes Zielbild des Buddy Loops

- Dispatcher und Meta arbeiten als gleichrangige Buddys
- Dispatcher bleibt der schnelle Erstleser
- Meta bleibt der tiefere Bedeutungspruefer
- Entscheidungen entstehen ueber ein Buddy-Protokoll, nicht ueber Rang

#### BuddyHypothesis

Jeder Buddy soll eine strukturierte Hypothese liefern mit:

- `intent`
- `goal`
- `confidence`
- `uncertainty`
- `candidate_routes`
- `risk_level`
- `needs_clarification`
- `reasoning_summary`

Optional:

- `followup_reference`
- `location_relevance`
- `freshness_requirement`
- `artifact_need`
- `delivery_need`
- `state_invalidation_signal`

#### Arbitration-Zustaende

- `aligned`
  - beide sehen dieselbe Richtung
- `soft_conflict`
  - aehnliche Bedeutung, aber unterschiedliche Konservativitaet
- `hard_conflict`
  - unterschiedliche Bedeutungslesarten
- `insufficient_signal`
  - beide unsicher

#### Entscheidungslogik

- `aligned` -> Fast-Path
- `soft_conflict` -> konservativere Route
- `hard_conflict` -> Rueckfrage oder Meta-konservativer Pfad
- `insufficient_signal` -> Rueckfrage statt Blindrouting

#### Guardrails

- max. 2 Buddy-Runden
- Fast-Path nur bei hoher Konfidenz + niedrigem Risiko
- bei Unsicherheit kein `empty_decision`, sondern strukturierte Vorhypothese
- bei Risiko nie blind am Dispatcher vorbeilaufen

#### Erfolgskriterium

- weniger `dispatcher_meta_fallback: empty_decision`
- weniger Meta-Rettung fuer triviale Frontdoor-Faelle
- bessere Umgangssprache
- bessere Follow-up-Verarbeitung
- weniger Nutzerkorrekturen wie `du verstehst mich nicht`

## Startplan ab 2026-04-01 - erste Ausbauwelle in 3 Phasen

### Phase A - Dispatcher Semantic Upgrade

Ziel:
- Umgangssprache, kurze Anschlussfragen und implizite Referenzen an der Frontdoor deutlich besser verstehen

Umfang:
- Dispatcher-Prompt und Output-Schema fuer colloquial/follow-up/meta-dialogische Anfragen erweitern
- `empty_decision` durch strukturiertere Unsicherheitsausgabe ersetzen
- bessere Follow-up-Aufloesung fuer kurze Anschlussfragen wie:
  - `kannst du sie reparieren`
  - `uebernehme Empfehlung 2`
  - `was machst du da das ist doch falsch`

Erfolg:
- deutlich weniger `dispatcher_meta_fallback: empty_decision`

### Phase B - Meta Root-Cause und Semantik nachschaerfen

Ziel:
- Meta soll Diagnosen sauberer priorisieren und in echte primaere Fix-Aufgaben uebersetzen

Umfang:
- `M2`/`M2.1` weiter schaerfen
- Ursachenzeilen aus `Ursache:` und `suspected_root_cause` haerter priorisieren
- Pfadtragende Claims vor allgemeinen Diagnosezeilen bevorzugen
- erstes echtes `primary_fix_task_emitted` erreichen
- semantische Fehlklassifikationen wie Business-/Strategiefragen vs. lokale Suche spaeter ueber eine fruehe Meaning-Layer reduzieren

Erfolg:
- weniger `verification needed` aus rein extraktiven Gruenden
- mindestens erste stabile primaere Fix-Tasks ohne Nutzer-Nachschleife

#### Bestaetigte Semantik-Fehlfaelle fuer Phase B

- `ich moechte ein cafe eroeffnen welches land ist am besten geeignet`
  - soll als Strategie-/Businessfrage verstanden werden
  - wurde in der Session mehrfach zu stark Richtung lokaler Suche gezogen
- `soll ich kaffee oder tee trinken was meinst du und was und wie koenntest du mich reich machen`
  - lief am **01.04.2026 20:48 CEST** direkt auf `meta`
  - wurde dort als `simple_live_lookup` / `general_lookup|live|light|answer|none|loc=0|deliver=0` behandelt
  - Ergebnis war eine stale Standortantwort statt einer kombinierten Praeferenz-/Lebensstrategie-Antwort
  - Beleg:
    - [2026-04-01_task_bc313161.jsonl](/home/fatih-ubuntu/dev/timus/logs/2026-04-01_task_bc313161.jsonl)
    - [autonomy_observation.jsonl](/home/fatih-ubuntu/dev/timus/logs/autonomy_observation.jsonl)
- `ich habe meinen handy standort aktualisiert du musst das registrieren`
  - ist kein normaler Maps-Follow-up, sondern ein `user_reported_state_update`
  - Meta braucht dafuer spaeter explizite State-Invalidation/Revalidation

### Phase C - Runtime-Haertung fuer MCP und Vision/OCR

Ziel:
- sichtbare Laufzeitprobleme reduzieren, die Timus fuer Nutzer wie Telegram, Canvas oder Live-Recherche unzuverlaessig wirken lassen

Umfang:
- `mcp_health`-Timeout-/Self-Healing-Pfad pruefen und haengen gebliebene Playbooks abbauen
- Vision/OCR-Hot-Path haerten
- Florence-2-/PaddleOCR-Mischpfad und Speicher-/Device-Lifecycle spaeter konsolidieren
- Antwortpfade beobachten, wenn Timus in Telegram denkt, aber nicht zurueckantwortet

Erfolg:
- weniger Health-Timeouts
- weniger haengende Recovery-/Self-Healing-Aufgaben
- stabilerer Antwortpfad bei laengeren oder schwereren Laeufen

## Noch fehlende Faelle / Daten fuer die zweite Welle

### 1. Buddy-Konfliktfaelle

Wir brauchen mehr reale Faelle, in denen Dispatcher und Meta dieselbe Anfrage unterschiedlich lesen wuerden:
- Umgangssprache
- Follow-ups
- implizite Referenzen
- Nutzerkorrekturen
- Meta-Kommunikation

Nutzen:
- Buddy-Loop spaeter auf echte Konfliktmuster statt nur Theorie zuschneiden

### 2. Mehr technische Incident-Faelle fuer Meta M2

Wir haben bisher erst sehr wenige echte Faelle, in denen:
- `lead_diagnosis_selected`
- `developer_task_compiled`
- `root_cause_gate_blocked`
oder spaeter
- `primary_fix_task_emitted`

sichtbar wurden.

Nutzen:
- Root-Cause-First-Tasking stabilisieren

### 3. Reale Self-Hardening-Pfade

Es fehlen noch echte Self-Hardening-/Self-Modify-Faelle fuer:
- `dispatcher empty_decision`
- `mcp_health`-Timeouts
- Vision/OCR-/Browser-Folgen
- stale state / Nutzerkorrekturen

Nutzen:
- Self-Hardening auf reale Live-Probleme statt auf zu enge Alt-Patterns anschliessen

### 4. Bessere Korrelation fuer Telegram-/Antwortausfaelle

Wir sehen bereits:
- `mcp_health`-Timeouts
- ausbleibende Antworten
- Self-Healing-Playbooks in der Queue

Es fehlen aber noch mehr klare Korrelationen zwischen:
- eingehender Anfrage
- laufenden Agenten/Tools
- Queue-/Health-Zustand
- ausbleibender Telegram-Antwort

Nutzen:
- Antwortpfad und Runtime-Blockaden spaeter gezielt haerten

### 5. Vision/OCR-Lastbild unter echter Nutzung

Es fehlen noch mehr belastbare Live-Faelle fuer:
- parallele Browser-/Vision-/OCR-Laeufe
- RAM-/VRAM-Spitzen
- CPU-/GPU-Fallbacks
- OOM-Vorlaeufer

Nutzen:
- Vision/OCR-Haertung spaeter nicht nur reaktiv, sondern systematisch angehen

## Fortschritt 2026-04-01 - Phase A gestartet

Phase A (Dispatcher Semantic Upgrade) ist im ersten konservativen Block umgesetzt.

- `main_dispatcher.py` priorisiert bei Follow-up-Kapseln jetzt semantisch `# CURRENT USER QUERY`
- kurze referenzielle Anschlussfragen wie `dann uebernimm die Empfehlung 2`, `koenntest du damit arbeiten`, `kannst du sie reparieren` werden konservativ frueh als `meta` erkannt statt spaeter in `empty_decision` zu kippen
- umgangssprachliche Selbststatus-/Selbstbild-Fragen wie `ok was stoert dich wie kann ich dir helfen`, `bist du anpassungsfaehig`, `bist du ein funktionierendes ki system` werden frueh als `executor` erkannt
- Nutzerkorrektur-/Beschwerdephaenomene wie `anscheinend verstehst du mich nicht` oder `was machst du da das ist doch falsch` werden frueh als `meta` behandelt
- ein enger Guard verhindert, dass harmlose Kurzfragen wie `soll ich kaffee oder tee trinken` durch die neue Frontdoor vorschnell auf `meta` gehoben werden

Absicherung:
- Dispatcher-Tests fuer die beobachteten Umgangssprache-Faelle erweitert
- neue Contract-/Hypothesis-Datei fuer Dispatcher-Semantik
- Lean `CiSpecs.lean` um zwei kleine Dispatcher-Invarianten erweitert

### Phase A.1 - triviale Umgangssprache entkernen

Die Beobachtung zeigt weiter ein Frontdoor-Problem bei sehr leichten Alltagsfragen wie:
- `was denkst du wird es morgen regnen`
- `kannst du mir sagen wie spaet es ist`
- `weisst du wann heute sonnenuntergang ist`

Darauf ist ein generischer Preparse-Block im Dispatcher angesetzt:
- umgangssprachliche Fragehuellen wie `was denkst du`, `meinst du`, `glaubst du`, `kannst du mir sagen`, `weisst du` werden vor dem Routing reduziert
- der Dispatcher arbeitet danach mit einer `NORMALIZED CORE QUERY`
- kurze triviale Kernfragen mit klarer Frageform und ohne komplexe Marker koennen konservativ direkt an `executor` gehen
- nicht-triviale Strategie-, Browser-, Research- oder Multi-Intent-Faelle bleiben weiter ausserhalb dieses Schnellpfads

## Fortschritt 2026-04-01 - Phase B Vorbereitung gestartet

Phase B laeuft jetzt als konservative Advisory-Vorbereitung an, noch ohne harte Rezept-Umbauten.

- `classify_meta_task(...)` markiert ab jetzt beobachtete semantische Konfliktmuster nur advisory:
  - `mixed_personal_preference_and_wealth_strategy`
  - `business_strategy_vs_local_lookup`
  - `user_reported_location_state_update`
- diese Marker aendern das Routing heute noch nicht hart, geben uns aber ab sofort sauberere Signale fuer:
  - spaetere Meaning-Layer vor der Rezeptwahl
  - State-Correction-Handling
  - besseres Mischen/Trennen von Lebenshilfe-, Strategie- und Lookup-Fragen
- neue Meta-Orchestration-Tests decken die bestaetigten Live-Faelle jetzt explizit ab

## Fortschritt 2026-04-01 - Phase B erster echter Schnitt

Der erste konservative Phase-B-Schnitt ist jetzt im Meta-Classifier drin.

- bestaetigte Semantik-Konfliktfaelle werden nicht mehr in bekannte Live-Lookup-Rezepte gezwungen
- stattdessen faellt Meta fuer diese Faelle bewusst auf einen rezeptlosen `single_lane` / `meta`-Dialogpfad zurueck
- konkret gilt das jetzt fuer:
  - `mixed_personal_preference_and_wealth_strategy`
  - `business_strategy_vs_local_lookup`
  - `user_reported_location_state_update`
- damit werden genau die beobachteten Fehlmuster konservativ unterbrochen:
  - `ich moechte ein cafe eroeffnen welches land ist am besten geeignet`
  - `soll ich kaffee oder tee trinken ... wie koenntest du mich reich machen`
  - `ich habe meinen handy standort aktualisiert du musst das registrieren`

Wichtig:
- das ist noch keine vollwertige Meaning-Layer
- aber es stoppt erste klar belegte Fehlpfade, bevor Meta sie wieder in `simple_live_lookup` oder lokale Rezeptpfade zwingt

## Spaetere Phase D - Assistive Action Workflows mit Approval Gate

Der Fall `reserviere mir ein hotel in portugal lissabon` zeigt eine eigene, spaetere Ausbauphase:

- Ziel ist nicht nur Suche oder Vergleich
- Ziel ist assistierte Handlung bis kurz vor den finalen Commit
- Timus soll aktiv mitdenken, vorbereiten und den Nutzer erst bei sensiblen/bindenden Schritten einbinden

### Zielbild

- Meta versteht `buche`, `reserviere`, `bestelle`, `beantrage`, `melde an` als assistierte Aktions-Workflows
- Visual-/Operator-Agent arbeitet aktiv bis kurz vor:
  - Zahlung
  - finalem Submit
  - rechtlich/finanziell bindendem Schritt
- Timus uebergibt dann sauber:
  - `Ich habe alles vorbereitet`
  - `Bitte hier Daten eingeben / Zahlung bestaetigen`

### Bausteine

1. Action Intent Understanding
- nicht nur `finden`
- sondern `vorbereiten und fast abschliessen`

2. Operator Readiness
- robustere UI-/Screen-Erkennung
- praezisere Navigation
- bessere Formularrobustheit

3. Approval Gate
- harter Stop vor Zahlung / finalem Commit

4. Preference Memory
- Budgets, Praeferenzen, wiederkehrende Nutzerwuensche merken

5. Session Persistence
- abgebrochene Flows spaeter wieder aufnehmen koennen

### Erfolgskriterium

- Timus schickt nicht nur einen Link
- sondern arbeitet aktiv bis zum letzten sicheren Schritt
- und zeigt damit echtes assistives Mitdenken statt nur Such-/Antwortlogik

## Fortschritt 2026-04-02 - Frontdoor/Reasoning Guard + Parse-Recovery Hardening

Die beobachteten Chat-Fehlfaelle vom 02.04.2026 haben drei konkrete Schutzmassnahmen ausgeloest:

- Frontdoor-Guard fuer persoenliche Strategie-/Lebensdialoge:
  - lange Ich-/Job-/Karriere-/Finanz-Kontexte gehen jetzt konservativ an `meta`
  - sie sollen nicht mehr allein wegen Woertern wie `architektur` oder `design` in `reasoning` kippen
- allgemeiner Evidenz-Guard fuer Architektur-/Review-Routen:
  - `reasoning` darf eine Architektur-/Review-Lesart nur noch bevorzugen, wenn technische Artefakte/Evidenz vorhanden sind
  - Beispiele fuer Evidenz: `code`, `datei`, `api`, `service`, `traceback`, `db`, `framework`
- zusaetzlicher Schutz im `ReasoningAgent` selbst:
  - falls ein persoenlicher Kontext trotzdem bei `reasoning` landet, wird `PROBLEM_TYP: Architektur-Review` ohne technische Evidenz unterdrueckt
- Parse-Recovery im `BaseAgent` gehaertet:
  - laengere, strukturierte Freitextantworten koennen bei `Kein JSON gefunden` jetzt als finale Antwort gerettet werden
  - dadurch soll ein guter erster Reply nicht mehr vom strikten JSON-Reparaturprompt zerstoert werden

Neue/erweiterte Tests:

- Dispatcher-Routing fuer:
  - persoenliche Strategie-/Jobwechsel-Kontexte
  - echte technische Architektur-Reviews
- Reasoning-Problemtyp-Guard
- Parse-Error-Salvage fuer gute Advisory-Antworten

Verifikation:

- fokussierte Pytest-Suite gruen (`46 passed`, `2 deselected`)
- Lean gruen
- CrossHair auf dem Dispatcher-Contract bleibt wegen der schweren `main_dispatcher`-Imports weiterhin instabil/langsam und liefert hier keinen verlaesslichen Abschluss

## Fortschritt 2026-04-02 - Phase B Follow-up-Kapsel-Fix

Ein weiterer echter Phase-B-Fehlfall aus dem Live-Chat ist jetzt abgesichert:

- beobachteter Fehler:
  - Follow-up wie `und wie kannst du mir dabei behilflich sein` wurde als `system_diagnosis` klassifiziert
  - alter Antworttext aus der Follow-up-Kapsel (`System stabil`, `YouTube-Videos`) wurde mitklassifiziert
- Ursache:
  - `extract_effective_meta_query(...)` konnte nur echte Mehrzeilen-Kapseln sauber auspacken
  - serialisierte / einzeilige Follow-up-Kapseln fielen auf den kompletten Rohtext zurueck
- Fix:
  - `extract_effective_meta_query(...)` versteht jetzt auch Ein-Zeilen-/serialisierte Kapseln
  - bei `# CURRENT USER QUERY` wird der Text nach dem Marker jetzt auch ohne Zeilenumbruch extrahiert
  - fuehrende Trenner und offensichtliche Serialisierungsreste werden abgeschnitten
- Wirkung:
  - alter Antworttext darf `site_kind`, `task_type` und Rezeptwahl nicht mehr aus der Bahn werfen
  - der aktuelle Nutzer-Follow-up wird isoliert klassifiziert

Tests:

- Ein-Zeilen-Follow-up fuer `extract_effective_meta_query(...)`
- Klassifikation mit altem `System stabil`-/`YouTube-Videos`-Text in derselben Kapsel

Verifikation:

- fokussierte Meta-Orchestration-Suite gruen (`31 passed`)
- CrossHair auf `tests/test_meta_semantic_review_contracts.py` gruen

## Fortschritt 2026-04-02 - Phase B Context Anchoring Layer (erster Schnitt)

Der Follow-up-Kapsel-Fix allein reicht nicht fuer laengere Themenverlaeufe. Deshalb gibt es jetzt einen ersten Context-Anchoring-Schnitt in der Meta-Klassifikation:

- neues Ziel:
  - kurze Anschlussfragen wie `und wie kannst du mir dabei behilflich sein`
  - sollen am aktiven Thema haengen bleiben
  - ohne alten Assistant-Text wieder in `system_diagnosis`, `youtube` oder andere Spezialpfade zu kippen

- Umsetzung:
  - `extract_meta_context_anchor(...)` zieht einen sauberen Themenanker aus der Follow-up-Kapsel
  - Prioritaet:
    1. `last_user`
    2. `recent_user_queries`
    3. `pending_followup_prompt`
    4. `topic_recall` (nur als Fallback)
  - `last_assistant` wird bewusst NICHT als Anker genutzt, um Trigger-Leaks aus alten Antworten zu vermeiden
  - `_should_apply_meta_context_anchor(...)` aktiviert den Anker nur bei kurzen, kontextabhaengigen Follow-ups
    - z. B. `dabei`, `damit`, `wie kannst du mir helfen`, `womit sollte ich anfangen`, `und was jetzt`

- Wirkung:
  - Meta klassifiziert die aktuelle Nutzerfrage weiterhin primär ueber `# CURRENT USER QUERY`
  - bei mehrdeutigen Kurz-Follow-ups wird zusaetzlich der letzte Nutzerkontext beruecksichtigt
  - daraus faellt der Fall konservativ auf `single_lane` / `meta` statt auf `executor` oder ein falsches Spezialrezept

Tests:

- Themenanker aus serialisierten Follow-up-Kapseln
- Karriere-/KI-Selbstaendigkeits-Follow-up bleibt auf `meta`
- alter Assistant-Text mit `System stabil` oder `YouTube-Videos` darf nicht mehr die Route bestimmen

Verifikation:

- fokussierte Meta-Orchestration-Suite gruen (`33 passed`)
- CrossHair auf `tests/test_meta_semantic_review_contracts.py` gruen

## Fortschritt 2026-04-02 - Phase B Active Topic State + komprimierte Follow-ups

Der erste Context-Anchoring-Schnitt reicht fuer laengere Themen noch nicht aus. Deshalb wurde die Meta-Klassifikation jetzt um einen kleinen userseitigen Dialogzustand erweitert:

- neues Ziel:
  - aktive Themen ueber mehrere Turns stabil halten
  - `open_goal` und einfache Nutzer-Constraints wiederverwenden
  - knappe Advisory-Follow-ups wie `KI-Consulting, KI-Tools 2 stunden budget 0` nicht mehr als inhaltsleeren Rest behandeln

- Umsetzung:
  - `extract_meta_dialog_state(...)` extrahiert jetzt:
    - `active_topic`
    - `open_goal`
    - `constraints`
    - `next_step`
    - `compressed_followup_parsed`
    - `active_topic_reused`
  - Themenquellen bleiben bewusst userseitig:
    - `context_anchor`
    - `last_user`
    - `recent_user_queries`
    - `pending_followup_prompt`
    - nur spaet als Fallback `topic_recall` / `session_summary`
  - alte Assistant-Texte werden weiterhin NICHT als Themenanker verwendet
  - kompakte Advisory-Eingaben mit Zeit-/Budget-Slots werden jetzt konservativ erkannt
    - z. B. `2 stunden`
    - `budget 0`
    - `kein finanzielles polster`
    - `ohne team`
  - wenn so ein komprimierter Advisory-Follow-up erkannt wird, faellt Meta konservativ auf `single_lane` / `meta` statt auf den generischen Executor-Default

- Wirkung:
  - Phase B haelt nicht nur den letzten Query-String sauber, sondern merkt sich jetzt auch einen kleinen aktiven Nutzerkontext
  - knappe Planungs-/Beratungs-Follow-ups koennen mit Themenanker + Constraints weiterlaufen
  - Brasilien-/Karriere-/KI-Selbstaendigkeits-Faelle bleiben stabiler auf dem eigentlichen Thema
  - Spezialpfade wie `system_diagnosis`, `location_local_search` oder `simple_live_lookup` werden jetzt wieder staerker an die AKTUELLE Nutzerfrage gebunden
  - ein alter Themenanker darf diese Spezialrouten nicht mehr allein ausloesen

Neue Tests:

- Dialog-State-Extraktion fuer Karriere-/KI-Selbstaendigkeits-Follow-up mit `2 stunden` + `budget 0`
- komprimierter Advisory-Follow-up `KI-Consulting, KI-Tools 2 stunden budget 0`
- Brasilien-/KI-Follow-up mit wiederverwendetem Aktivthema
- Orts-/Maps-Anker darf eine allgemeine Anschlussfrage nicht wieder in `location_local_search` ziehen
- neue Contract-Datei fuer `extract_meta_dialog_state(...)`

Verifikation:

- `python -m py_compile` gruen
- fokussierte Pytest-Suite gruen (`36 passed`)
- Lean gruen
- CrossHair auf `tests/test_meta_dialog_state_contracts.py` bleibt hier aktuell haengen und wird deshalb NICHT als falsches Gruen gewertet
