# Changelog Dev

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

**Status**

- Phase 3 ist in diesem Arbeitsstand fertig implementiert und wird mit dem zugehörigen Session-Commit eingecheckt.
- Live-Aktivierung ist zu diesem Stand noch nicht erfolgt.

### Phase 4 — Learned Chains + breiteres Runtime-Replanning (Start umgesetzt)

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
- Validierung
  - `48 passed`
  - CrossHair gruen
  - Lean gruen

**Geplanter Restumfang**

- Neue Lernschicht für erfolgreiche und gescheiterte Agentenketten
  - `goal_signature`
  - `recommended_chain`
  - `final_chain`
  - `success` oder `failure`
  - `runtime_gap_insertions`
  - `duration_ms`
  - `confidence`
- Planner-Anreicherung mit Erfahrungswissen
  - bekannte gute Ketten sollen künftig bevorzugt werden
  - bekannte schlechte Ketten sollen abgewertet werden
- Erweiterung der Runtime-Gap-Erkennung über `document_output` hinaus
  - zuerst `delivery`
  - danach `verification`
  - optional später `location_context`

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
- Sichere Runtime-Lückenerkennung für fehlende Dokument-Stufen ist implementiert, aber noch nicht live aktiviert

**Noch nicht fertig**

- breiteres Runtime-Replanning über weitere Gap-Typen
  - z. B. `delivery`, `verification`, `local context`
- gelernte Ketten als echte bevorzugte Standardpfade
- breitere Nutzung außerhalb der aktuellen Meta-/Recipe-Pfade

### Relevante Dateien dieser Session

- [goal_spec.py](/home/fatih-ubuntu/dev/timus/orchestration/goal_spec.py)
- [capability_graph.py](/home/fatih-ubuntu/dev/timus/orchestration/capability_graph.py)
- [adaptive_planner.py](/home/fatih-ubuntu/dev/timus/orchestration/adaptive_planner.py)
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)
- [CiSpecs.lean](/home/fatih-ubuntu/dev/timus/lean/CiSpecs.lean)
- [test_runtime_goal_gap_replan.py](/home/fatih-ubuntu/dev/timus/tests/test_runtime_goal_gap_replan.py)
- [test_runtime_goal_gap_replan_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_runtime_goal_gap_replan_contracts.py)

### Nächster sinnvoller Schritt

Phase 3 live schalten und danach Phase 4 beginnen:

- Runtime-Replanning auf `timus-mcp` aktivieren
- danach echte Live-Fälle prüfen, ob `research -> document` und später weitere Gap-Typen sauber nachgezogen werden
- anschließend Phase 4 mit Learned Chains und den ersten zusätzlichen Gap-Typen `delivery` und `verification` umsetzen
