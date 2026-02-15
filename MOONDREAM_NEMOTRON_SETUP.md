# Moondream + Nemotron Pipeline Setup

## Problem gelöst

Das Skript `moondream_nemotron_pipeline.py` löst das Problem, dass Moondream Webseiten nicht zuverlässig erkennt, indem es:

1. **Moondream** nur für visuelle Analyse nutzt (Textbeschreibung)
2. **Nemotron** für strukturierte JSON-Konvertierung nutzt
3. **Automatisch mehrere Ports** versucht (2020, 2021, 2022)

## Port-Konfiguration

### Standard-Ports für Moondream Station

- **Port 2020**: Standard Moondream Station Port
- **Port 2021**: Alternativer Port (häufig im Projekt verwendet)
- **Port 2022**: Fallback Port

### Moondream Station auf Port 2020 starten

```bash
# Methode 1: Direkt mit Port-Parameter
moondream-station --port 2020

# Methode 2: Mit vollständiger Konfiguration
moondream-station --host 0.0.0.0 --port 2020 --model moondream

# Methode 3: Über Umgebungsvariable
export MOONDREAM_PORT=2020
moondream-station
```

### Port in .env konfigurieren (optional)

Füge in `.env` hinzu:

```bash
MOONDREAM_API_BASE=http://localhost:2020/v1
```

Das Skript versucht automatisch:
1. Die Umgebungsvariable `MOONDREAM_API_BASE`
2. Port 2020 (Standard)
3. Port 2021 (Fallback)
4. Port 2022 (Fallback)

## Installation

```bash
# Python-Packages installieren
pip install openai pillow

# Umgebungsvariable setzen
export OPENROUTER_API_KEY='sk-or-...'
```

## Verwendung

```bash
# Mit Default-Screenshot (test_project/screenshot.png)
python3 moondream_nemotron_pipeline.py

# Mit eigenem Screenshot
python3 moondream_nemotron_pipeline.py /pfad/zum/screenshot.png
```

## Ausgabe

Das Skript erstellt eine `.json`-Datei neben dem Original-Screenshot mit strukturierten Daten:

```json
{
  "page_title": "Beispiel Webseite",
  "main_heading": "Willkommen",
  "sections": [
    {
      "type": "header",
      "heading": "Navigation",
      "links": [
        {"text": "Home", "url": "/"},
        {"text": "Über uns", "url": "/about"}
      ]
    }
  ],
  "detected_elements_summary": {
    "buttons": 5,
    "links": 12,
    "forms": 1
  }
}
```

## Troubleshooting

### "Moondream Station nicht erreichbar"

1. Prüfe ob Moondream Station läuft:
   ```bash
   ps aux | grep moondream
   ```

2. Prüfe welcher Port aktiv ist:
   ```bash
   netstat -tuln | grep 202
   # oder
   ss -tuln | grep 202
   ```

3. Starte Moondream Station auf dem richtigen Port:
   ```bash
   moondream-station --port 2020
   ```

### "OPENROUTER_API_KEY nicht gesetzt"

Setze die Umgebungsvariable:

```bash
export OPENROUTER_API_KEY='sk-or-...'
```

Oder füge sie zu `.env` hinzu.

## Features

- ✅ Automatische Port-Erkennung (2020, 2021, 2022)
- ✅ Umgebungsvariable `MOONDREAM_API_BASE` Support
- ✅ Robuste Fehlerbehandlung
- ✅ Strict JSON Schema für Nemotron
- ✅ Temperature = 0.0 (deterministische Ausgabe)
- ✅ Progress-Anzeige
- ✅ Automatische Speicherung als `.json`
