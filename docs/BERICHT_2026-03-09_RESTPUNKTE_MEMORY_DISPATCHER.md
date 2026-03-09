# Bericht 2026-03-09: Restpunkte Memory + Dispatcher

## Ausgangslage

Nach `P4.1` bis `P4.3` blieben zwei bekannte Restpunkte offen:

1. alte `md5`-Fingerprints in [memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py)
2. ein bekannter Pytest-Teardown-Haenger bei gezielten Dispatcher-Tests

## 1. Memory-Fingerprints gehaertet

### Umsetzung

- [memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py)
  - Session-IDs jetzt als kurze opaque `uuid4`-IDs statt `md5(timestamp)`
  - stabile Non-Security-Keys jetzt ueber `blake2b`-basierte Helfer
- [stable_hash.py](/home/fatih-ubuntu/dev/timus/utils/stable_hash.py)
  - bestehende stabile Digest-Helfer weiterverwendet
- [test_memory_hybrid_v2.py](/home/fatih-ubuntu/dev/timus/tests/test_memory_hybrid_v2.py)
  - neue Checks fuer opaque Session-ID
  - neue Checks fuer stabile Explicit-Note-Keys

### Ergebnis

Der gezielte `bandit`-Scan auf:

- [memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [chroma_runtime.py](/home/fatih-ubuntu/dev/timus/utils/chroma_runtime.py)

lief gruen.

## 2. Dispatcher-Teardown-Haenger behoben

### Ursache

Der nackte `main_dispatcher`-Import war nicht der eigentliche Haenger. Die relevante Beobachtung war:

- nach `_call_dispatcher_llm(...)` blieb im Testpfad ein nicht-daemon `asyncio_0`-Thread stehen
- genau dieser Thread fuehrte dazu, dass gezielte Pytest-Laeufe zwar fachlich fertig waren, aber nicht sauber beendeten

### Umsetzung

- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  - neuer Helper `_should_inline_dispatcher_sync_call()`
  - neuer Helper `_run_dispatcher_sync_call(...)`
  - unter Pytest bzw. mit explizitem Inline-Flag laufen synchrone Provider-Calls jetzt inline statt ueber `asyncio.to_thread(...)`
  - Produktionspfad bleibt sonst unveraendert bei Thread-Offloading
- [test_dispatcher_provider_selection.py](/home/fatih-ubuntu/dev/timus/tests/test_dispatcher_provider_selection.py)
  - neuer Test fuer den Inline-Testpfad

### Ergebnis

Der bisher problematische gezielte Lauf:

- Dispatcher-Feedback-Bias
- Fallback auf `meta`
- Verbose-Dispatcher-Extraktion
- `reasoning_content`-Fallback

lief jetzt mit:

- `6 passed`
- `EXIT:0`

Zusatzprobe:

- vor dem Call: nur `MainThread` + OTel-Daemon-Threads
- nach dem Call: kein `asyncio_0`-Thread mehr
- Prozess beendet sauber

## Verifikation

- `python -m py_compile` auf den geaenderten Dateien: gruen
- `pytest -q tests/test_memory_hybrid_v2.py -k 'session_id_is_opaque_short_uuid or explicit_note_uses_stable_digest_for_explicit_note or store_with_embedding_no_chromadb or sync_from_markdown'`
  - `3 passed`
- gezielte Dispatcher-Tests:
  - `6 passed`
  - `EXIT:0`
- `python -m crosshair check tests/test_stable_hash_contracts.py --analysis_kind=deal`
  - gruen
- `lean lean/CiSpecs.lean`
  - gruen
- `python scripts/run_production_gates.py`
  - `READY | total=4 passed=4 failed=0 skipped=0 blocking_failed=0`

## Fazit

Beide bekannten Restpunkte aus dem letzten Produktionsschnitt sind damit geschlossen:

- keine `md5`-Fingerprints mehr im relevanten `memory_system`-Pfad
- kein bekannter Dispatcher-Pytest-Teardown-Haenger mehr im gezielten Problemfall
