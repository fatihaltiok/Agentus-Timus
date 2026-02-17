# Log: Problemstellung und Maßnahmen (Timus)

Datum: 2026-02-17  
Projekt: Timus  
Branch: `main`

## 1. Kontext
Dieser Log dokumentiert die identifizierten Probleme aus Laufzeit-Logs/Tests sowie die umgesetzten und empfohlenen Maßnahmen zur Stabilisierung von Routing, Memory-Verhalten und Ausführungspfaden.

Zielbild: Ein dynamisches, persistentes, kontextsensitives Gedächtnis mit robuster Agenten-Orchestrierung, nachvollziehbarer Telemetrie und reproduzierbaren Quality-Gates.

## 2. Problemstellung (beobachtet)

### 2.1 Routing/Dispatcher
- Leere Dispatcher-Antworten führten wiederholt zu Fallback auf `executor`.
- Konsequenz: Recall-lastige Fragen ("was haben wir eben gesucht") wurden nicht konsistent im passenden Pfad behandelt.

### 2.2 Memory-Verhalten
- Abrufe waren zeitweise inkonsistent: direkt nach erfolgreicher Aufgabe war Recall nicht immer treffsicher.
- Session-Kontinuität war nicht durchgängig robust (Queries mit Kontrollzeichen, wechselnde Laufzeitpfade).
- Eindruck beim Nutzer: Kontext „geht verloren“, obwohl Events persistiert wurden.

### 2.3 Tool-/Ausführungsebene
- ActionPlan-Pfade schlugen teilweise fehl (z. B. `Tippen fehlgeschlagen`), danach degradiert auf regulären Flow.
- Wiederholte Tool-Loops (`get_text`, `get_page_content`) erhöhten Latenz und verschlechterten Ergebnisqualität.
- Externe Seiten (z. B. eBay Challenge/Bot-Page) verhinderten verifizierbare Extraktion.

### 2.4 Reflection/LLM-Client-Kompatibilität
- Fehlerbild: `'MultiProviderClient' object has no attribute 'chat'`.
- Ursache: Reflection-Pfad erwartete OpenAI-kompatiblen Raw-Client, erhielt aber Multiprovider-Wrapper.

### 2.5 Signalqualität in Antworten
- Teilweise unpräzise/fehlgeleitete Antworten bei eigentlich einfachem Kontextrückbezug.
- Parse-Fehler (`Kein JSON gefunden`) führten zu zusätzlichen Iterationen und sinkender Antwortqualität.

## 3. Root-Cause-Analyse

1. **Dualität der Memory-Pfade (historisch):** Kernlogik und Adapter lagen nicht immer sauber in einer Ownership-Linie.
2. **Nicht deterministische Recall-Abkürzungen:** Wenn Toolwahl/Agentenpfad variierte, war die Recall-Qualität nicht konstant.
3. **Session-/Input-Hygiene:** Kontrollzeichen und uneinheitliche Session-Verkettung störten semantische Wiederauffindbarkeit.
4. **Provider-Abstraktion nicht überall konsistent:** Reflection nutzte an einer Stelle nicht die gleiche Client-Auflösung wie der Rest.
5. **Web-Automation-Realität:** Anti-Bot/Challenge-Seiten verursachen harte Grenzen für automatische Vollverifikation.

## 4. Umgesetzte Maßnahmen

## 4.1 Architektur und Memory-Stabilisierung (Milestones 0-6)
- Kanonischer Memory-Kern auf `memory/memory_system.py` festgelegt.
- Deterministisches Interaction-Logging pro Runde zentral in Dispatcher-Runpfad etabliert.
- Working-Memory-Layer mit Budget und Prompt-Injektion eingebaut.
- Dynamische Relevanz/Decay implementiert (kurzzeit- und langzeitgewichtete Scores).
- Runtime-Telemetrie + Memory-Snapshot als Metadaten pro Interaktion ergänzt.
- Quality-Gates + E2E-Readiness-Checks erweitert und automatisiert.

Relevante Dateien:
- `memory/memory_system.py`
- `agent/base_agent.py`
- `main_dispatcher.py`
- `tests/test_milestone5_quality_gates.py`
- `tests/test_milestone6_e2e_readiness.py`
- `verify_milestone6.py`

## 4.2 Recall-Robustheit und Session-Kontinuität
- Unified Recall eingeführt (episodische Interaktionen + semantische Treffer).
- Session-gebundene Priorisierung und Kontinuitätslogik ergänzt.
- Query-Sanitizing (Kontrollzeichen entfernen) integriert.
- Unresolved-first Heuristik für "offene Anliegen" implementiert.

## 4.3 Reflection-Fix (Provider-Kompatibilität)
- Reflection-Engine auf kompatible Chat-Client-Auflösung erweitert.
- Multiprovider-Objekte werden nun sauber auf OpenAI-kompatiblen `.chat.completions` Client aufgelöst.
- LLM-Call im Reflexionspfad thread-safe asynchronisiert.

Relevante Dateien:
- `memory/reflection_engine.py`

## 4.4 Embedding-Provider-Härtung
- Embedding-Funktion auf provider-agnostische Factory umgestellt.
- Reduziert harte Kopplung an einzelne Provider in Server-Initialisierung.

Relevante Dateien:
- `server/mcp_server.py`
- `utils/embedding_provider.py`

## 5. Commit- und Release-Historie (relevant)
- `ff308ba` - release: finalize memory stabilization milestones 1-6
- `c499c89` - docs: update README with milestone6 status and repo structure
- `e19ff8b` - feat(status): add live agent/tool runtime indicator
- `99f1ebe` - feat(memory): finalize milestones 2-6 dynamic context and rollout gates
- `f4c40c2` - fix(reflection): support multiprovider chat client + embedding provider

## 6. Wirkung (aktueller Stand)

### Positiv
- Deterministische Persistenz ist durchgängig im zentralen Runpfad verankert.
- Memory-Kontext wird zuverlässig in Agent-Prompts injiziert.
- Runtime-Statusanzeige (Agent/Tool aktiv) verbessert Transparenz deutlich.
- Reflection-Crash durch Multiprovider-Inkompatibilität adressiert.

### Noch nicht vollständig gelöst
- Dispatcher erzeugt teilweise weiterhin leere Klassifikationsantworten.
- Bei Anti-Bot-Webseiten bleibt Vollautomatisierung begrenzt.
- Parse-Fehler in Tool-JSON-Antworten können weiterhin Iterationsbudget verbrauchen.

## 7. Offene Risiken
- **R1 Dispatcher-Empty-Response:** Falscher Agentpfad möglich.
- **R2 Tool-Loop-Degeneration:** Mehrfach gleiche Toolaufrufe trotz geringer Zusatzinformation.
- **R3 Web-Challenge-Barrieren:** Datenqualität hängt von zugänglichen Quellen ab.
- **R4 Memory-Noise:** Schlechte Antworten könnten als negative Muster persistiert werden, wenn Filter zu permissiv sind.

## 8. Konkrete Folgemaßnahmen (priorisiert)

1. **Dispatcher-Hardening (P0)**
- Strict Output Contract (Enum + JSON-Schema + Retry mit kleinem Prompt).
- Bei leerer Antwort: deterministischer Keyword-/Intent-Klassifikator vor Executor-Fallback.

2. **Recall-Policy-Hardening (P0)**
- Bei Fragen wie "was haben wir eben gesucht" zuerst deterministischen Session-Recap verwenden.
- Danach erst semantischen Recall ergänzen.

3. **Loop-Control v2 (P1)**
- Tool-sequenzbasierten Guard einführen (nicht nur identische Call-Signatur).
- Früher Plan-Rewrite bei zweitem gleichartigen Fehlschlag.

4. **Web-Extraction-Fallbacks (P1)**
- Bei Challenge-Detection automatisch auf alternative Quellen wechseln (Preisvergleich/Marktplatzmix).
- Antwort explizit als "Snippet-basiert" oder "verifiziert" markieren.

5. **Memory-Qualitätsfilter (P1)**
- Nur high-confidence Ergebnisse in langfristige Muster überführen.
- Fehlantworten mit geringer Priorität/tagging als "unsicher" speichern.

6. **Beobachtbarkeit (P2)**
- KPI-Dashboard: recall_hit_rate, dispatcher_empty_rate, parse_error_rate, loop_skip_rate, fallback_rate.
- Alerting-Schwellen für Regressionen definieren.

## 9. Abnahmekriterien (für nächsten Stabilitätszyklus)
- Dispatcher-Empty-Rate < 2% über 200 Requests.
- Recall-Fragen mit Sessionbezug: >= 90% korrekt in den letzten 5 Interaktionen.
- Parse-Error-Folgen: max. 1 Zusatziteration im Median.
- Loop-Skip-Rate: < 5% bei Web-Recherche-Tasks.
- Jede Runde besitzt persistiertes Event inkl. Status + Metadaten.

## 10. Ablage / Referenzen
- `docs/MEMORY_ARCHITECTURE.md`
- `docs/MILESTONE6_RUNBOOK.md`
- `docs/RELEASE_NOTES_MILESTONE6.md`
- `docs/SESSION_LOG_2026-02-17_MILESTONES_0_TO_6.md`

