# Bericht: Kontext-Intelligenz & CI-Fix — 15.03.2026

**Datum:** 15.03.2026
**Scope:** Problem 2 (Referenz-Fortsetzung), Problem 4 (Self-Proposal Blindness), CI-Gate-Fix
**Status:** ✅ Abgeschlossen — 62/62 Tests grün · Lean 83 Theoreme · CI-Gate behoben

---

## Ausgangslage

Nach Abschluss der Selbstdiagnose-Gate-Implementierung (Evidence-Gate mit `[BELEGT]`/`[TEILWEISE BELEGT]`/`[NICHT BELEGT]`) wurden drei weitere Gesprächsprobleme aus realen Chat-Verläufen analysiert und priorisiert:

| Problem | Symptom | Priorität |
|---|---|---|
| P1 | YouTube-Query nicht bereinigt ("kurz rein...") | Hoch — bereits in letzter Session gefixt |
| P2 | Referenz-Pronomen verlieren Topic-Kontext ("damit", "das gleiche") | Hoch |
| P3 | Multilingualer YouTube-Suche (DE+EN parallel) | Hoch — bereits in letzter Session gefixt |
| P4 | Self-Proposal Blindness ("ja schau mal danach" → Meta fragt nach) | Hoch |

Diese Session behandelt P2, P4 sowie einen pre-existierenden CI-Dauerausfall.

---

## Problem 2 — Referenz-Fortsetzung (Reference Continuation)

### Problem

Nutzer bezieht sich mit einem Referenz-Pronomen auf eine vorangegangene Antwort:

```
Timus: "Auf YouTube habe ich zu 'KI Agenten' diese Videos gefunden: ..."
User:  "mach damit eine YouTube-Suche"
```

Das Wort "damit" trägt keine Topic-Information. `_match_assistant_reply_points()` findet keine
passenden Tokens → `topic_recall` bleibt leer → Executor sucht "trending deutschland" statt
"KI Agenten".

### Root Cause

`_match_assistant_reply_points()` benötigt Topic-Tokens aus der Query um Treffer zu finden.
Bei reinen Referenz-Queries ("damit", "das gleiche") gibt es keine Token → kein Match.

### Fix

**`server/mcp_server.py`:**
- `_REFERENCE_CONTINUATION_PATTERNS`: erkennt "damit", "das gleiche", "dieselbe", "genau das" etc.
- `_is_reference_continuation(query)`: Prüft ob Query nur ein Referenz-Pronomen ist (max. 12 Wörter)
- `_build_followup_capsule()`: Wenn Referenz erkannt UND kein `matched_reply_points` → `inherited_topic_recall` direkt aus `_extract_assistant_reply_points(last_assistant)` befüllen
- `_augment_query_with_followup_capsule()`: `inherited_topic_recall` als Fallback für `topic_recall` (P2)

**`agent/agents/executor.py`:**
- `_run_youtube_light_research()`: Wenn `search_query == "trending deutschland"` oder ≤ 2 Wörter UND `topic_recall` im Task-Text vorhanden → Recall-Thema als Such-Query verwenden

### Ergebnis

```
User: "mach damit eine youtube suche"
→ inherited_topic_recall: ["Auf YouTube habe ich zu 'KI Agenten' diese Videos gefunden: ..."]
→ search_query: "ki agenten"  (statt "trending deutschland")
```

---

## Problem 4 — Self-Proposal Blindness

### Problem

Meta bietet eine Aktion an und der Nutzer stimmt zu — aber Meta fragt erneut nach statt zu handeln:

```
Timus: "Ich könnte auch nach aktuellen YouTube-Videos zu KI Agenten suchen. Willst du das?"
User:  "ja schau mal danach"
→ Meta: "Was genau möchtest du suchen?"  ← FALSCH
```

### Root Cause

Keine persistente Speicherung des Angebots. Beim nächsten Turn ist die angebotene Aktion
vergessen — "ja schau mal danach" wird als leere Anfrage behandelt und zum LLM geschickt,
der für Klärung fragt statt auszuführen.

### Fix (strukturierte ProposalMetadata)

Der User hat explizit angemerkt: kein Regex auf Freitext, sondern strukturierte Metadaten.

**`server/mcp_server.py`:**

1. `_PROPOSAL_TRIGGER_PATTERNS`: Erkennt Angebotssätze ("soll ich", "ich kann", "ich könnte", "willst du")
2. `_extract_proposal_metadata(text)`: Extrahiert `{kind, target, suggested_query, raw_sentence}` aus dem letzten Angebotsatz der Assistenten-Antwort
   - `kind`: `youtube_search` / `web_search` / `generic_action`
   - `suggested_query`: extrahiertes Topic, bereinigt von Verb-Residuen
3. `_store_proposal_in_capsule(session_id, proposal)`: Speichert `last_proposed_action` in der Session-Kapsel (JSON-Datei auf Disk)
4. `_is_affirmation(query)`: Erkennt kurze Zustimmungen ("ja", "ok", "schau mal danach", "klingt gut", "auf jeden fall") — max. 8 Wörter
5. `_augment_query_with_followup_capsule()`: Bei Affirmation + gespeichertem Angebot → `# RESOLVED_PROPOSAL`-Block statt normalem Follow-up-Context
6. Routing: `RESOLVED_PROPOSAL` → `executor` direkt (youtube_search/web_search), Proposal einmalig konsumiert (gelöscht nach Nutzung)

**`agent/agents/executor.py`:**

7. `_recover_resolved_proposal(task_text)`: Parst `RESOLVED_PROPOSAL`-Block (kind, suggested_query)
8. `run()`: Bei `youtube_search`-Proposal → synthetischer Handoff → `_run_youtube_light_research()` ohne LLM-Runde

### Ergebnis

```
Timus: "... Soll ich auch nach YouTube-Videos zu KI Agenten suchen?"
→ last_proposed_action gespeichert: {kind: youtube_search, suggested_query: "ki agenten"}

User:  "ja schau mal danach"
→ _is_affirmation() = True + last_proposed_action vorhanden
→ RESOLVED_PROPOSAL injiziert
→ Executor startet YouTube-Suche "ki agenten" direkt
→ Proposal aus Kapsel gelöscht (einmalig)
```

---

## Weitere Verbesserungen

### EN-Query-Cleanup

Problem 3 (Multilingual) hatte noch deutsches Filler-Residuum in der übersetzten EN-Query:

```
Vorher: "ki agenten neue entwicklungen im bereich ki"
→ EN:   "AI agents AI neue developments im bereich AI"  ← dt. Residuum

Nachher:
→ EN:   "AI agents AI developments AI"  ← sauber
```

Fix: `_YOUTUBE_EN_FILLER_TOKENS` — filtert dt. Wörter die nicht übersetzt wurden ("neue", "bereich", "im" etc.)

### Dedup-Fix

`_run_youtube_light_research()` deduplizierte nur per `video_id`. Mock-Daten in Tests
haben keine `video_id` → alle Items wurden verworfen → `combined_results` leer →
"Suche fehlgeschlagen" obwohl Mock korrekte Daten lieferte.

Fix: `_dedup_add()` — Items ohne `video_id` werden per Titel dedupliziert.

---

## CI-Gate-Fix

### Problem

Alle Commits seit mehreren Wochen scheiterten am CI-Gate `production_smoke`:

```
ModuleNotFoundError: No module named 'telegram'
in tests/test_telegram_feedback_gateway.py
```

### Ursache

`python-telegram-bot==21.9` stand in `requirements.txt` aber **nicht** in `requirements-ci.txt`.
Der CI installiert ausschließlich `requirements-ci.txt`.

### Fix

`python-telegram-bot==21.9` zu `requirements-ci.txt` ergänzt.

```
Vorher: 3/4 Gates passed, 1 blocking failure
Nachher: 4/4 Gates passed
```

---

## Tests & Verifikation

### Neue Tests (`tests/test_reference_and_proposal.py`)

| Klasse | Tests | Inhalt |
|---|---|---|
| `TestIsReferenceContinuation` | 7 | damit, das gleiche, dieselbe, Längen-Guard |
| `TestIsAffirmation` | 12 | ja, ok, schau mal danach, Negationen, Längen-Guard |
| `TestExtractProposalMetadata` | 7 | youtube_zu, youtube_auf, generic, kein Angebot |
| `TestRecoverResolvedProposal` | 5 | Parser, fehlende Felder, leer |
| `TestYoutubeTranslateQuery` | 4 | ki→AI, kein dt. Filler, Englisch unbeschädigt |

**Gesamt: 35 neue Tests · 62 gesamt grün**

### Lean 4 (neue Theoreme)

| Theorem | Inhalt |
|---|---|
| Th.80 | reference_continuation_max_words_bound — max. 12 Wörter |
| Th.81 | affirmation_max_words_bound — max. 8 Wörter |
| Th.82 | proposal_query_length_bound — Query ≤ 200 Zeichen |
| Th.83 | resolved_proposal_youtube_routes_to_executor |

**Gesamt: 83 Theoreme · 0 Fehler · 0 Warnungen**

---

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `server/mcp_server.py` | P2+P4: 6 neue Funktionen, Routing-Logik, Proposal-Hook |
| `agent/agents/executor.py` | P2+P4: RESOLVED_PROPOSAL-Parser, topic_recall-Fallback, EN-Filler, Dedup-Fix |
| `lean/CiSpecs.lean` | 4 neue Theoreme (Th.80–83) |
| `requirements-ci.txt` | python-telegram-bot==21.9 ergänzt |
| `tests/test_reference_and_proposal.py` | NEU — 35 Tests |

---

## Commits

| SHA | Beschreibung |
|---|---|
| `f3ffe9f` | fix(context): P2 reference-continuation + P4 self-proposal resolution |
| `497c5ed` | fix(ci): add python-telegram-bot to requirements-ci.txt |

---

## Systemstatus nach Session

- **Timus Version:** v4.12
- **CI-Gates:** 4/4 passed (erstmals seit Wochen)
- **Lean-Theoreme:** 83 (Th.1–83)
- **Test-Suite:** 62+ Tests grün
- **Offene Punkte:** keine (alle 4 Kontext-Probleme P1–P4 behoben)
