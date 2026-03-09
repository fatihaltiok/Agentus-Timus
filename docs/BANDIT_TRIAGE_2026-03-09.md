# Bandit Triage 2026-03-09

Stand nach `python scripts/run_production_gates.py` am 9. Maerz 2026.

## Ziel

Den aktuellen Bandit-Bestand in echte P0-Risiken und bekannten Security-Debt zerlegen,
damit die Produktionshaertung in kleinen, nachvollziehbaren Phasen weitergeht.

## Bereits abgebaut in dieser Phase

- `md5`-Fingerprints fuer UI-/State-/Memory-Hashes ersetzt
- harter `/tmp`-Pfad im `ShellAgent` entfernt
- `sha1`-Dedup-/Event-Keys in Ambient/Replanning entfernt
- `shell=True` in [tools/application_launcher/tool.py](/home/fatih-ubuntu/dev/timus/tools/application_launcher/tool.py) entfernt
- `shell=True` in [tools/visual_browser_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/visual_browser_tool/tool.py) entfernt
- `shell=True` in [tools/shell_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/shell_tool/tool.py) entfernt
- `urllib.request.urlopen` in Self-Healing- und Restart-Health-Checks ersetzt
- stiller Ambient-Feedback-Bug gefixt: `AmbientSignal.signal_id`
- `B701` im PDF-Builder behoben (`autoescape`)
- `B108`-Temp-Pfade auf `tempfile.gettempdir()` umgestellt
- `B104` bei Webhook-/Canvas-Bind-Host gehaertet
- `B608` fuer Goal-/Task-Queue auf feste SQL-Zweige bzw. `json_each(?)` umgestellt
- `B314` im ArXiv-XML-Parser auf `defusedxml` umgestellt
- `B615` fuer YOLOS/TrOCR/Qwen-VL/SAM/CLIP/Florence auf gepinnte HuggingFace-Revisions umgestellt
- `B307` im Planner von `eval` auf engen AST-Auswerter umgestellt

## P0: verbleibende blocker im Gate
- keine `bandit`-Blocker mehr im aktuellen Gate-Lauf
- `security_pip_audit` ist nach Pinning und Upgrade der direkten Dependencies ebenfalls gruen

## P1: Restliche Security-Debts

## Betriebsbefund

- `bandit` ist jetzt als Gate nuetzlich, weil die einfachen Low-Hanging-Fruits entfernt sind.
- `bandit`-High-Funde sind insgesamt von `13` auf `0` gefallen.
- `security_bandit` ist im aktuellen Production-Gate-Lauf vollstaendig gruen.
- `security_pip_audit` ist nach Pinning und Upgrade von `python-multipart`, `aiohttp`, `urllib3`, `Pillow`, `transformers` und `sentencepiece` ebenfalls gruen.
- `pip check` ist nach Upgrade von `kubernetes`, `torchaudio`, Anpassung von `tokenizers` und Entfernung des ungetrackten Legacy-Pakets `moondream` ebenfalls sauber.
