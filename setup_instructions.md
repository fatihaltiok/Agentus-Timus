# Timus Setup-Anleitung

## 1. Ordnerstruktur erstellen

Lösche alle bestehenden Dateien und erstelle die folgende Struktur:

```bash
# Ins Projekt-Verzeichnis wechseln
cd /home/fatih-ubuntu/dev/timus

# Alte Dateien löschen (Backup erstellen falls gewünscht)
rm -rf agent/ server/ tools/ *.py *.log

# Neue Ordnerstruktur erstellen
mkdir -p agent
mkdir -p server
mkdir -p tools/browser_tool
mkdir -p tools/search_tool
mkdir -p tools/summarizer
mkdir -p tools/planner
```

## 2. Leere __init__.py Dateien erstellen

```bash
# __init__.py Dateien für Python-Pakete
touch tools/__init__.py
touch tools/browser_tool/__init__.py
touch tools/search_tool/__init__.py
touch tools/summarizer/__init__.py
touch tools/planner/__init__.py
```

## 3. Dateien kopieren

### Agent-Dateien (unverändert)
```bash
# agent/timus.py - Kopiere den Inhalt aus deiner timus.py
# agent/timus_react.py - Kopiere den Inhalt aus deiner timus_react.py
```

### Server-Datei
```bash
# server/mcp_server.py - Verwende die korrigierte Version aus dem Artifact
```

### Tool-Dateien

#### tools/universal_tool_caller.py
```bash
# Kopiere deine bestehende universal_tool_caller.py
```

#### tools/browser_tool/tool.py
```bash
# Kopiere deine bestehende browser_tool.py
```

#### tools/summarizer/tool.py
```bash
# Kopiere deine bestehende summarizer_tool.py
```

#### tools/planner/tool.py
```bash
# Kopiere deine bestehende planner_tool.py
```

#### tools/planner/planner_helpers.py
```bash
# Kopiere deine bestehende planner_helpers.py
```

#### tools/search_tool/tool.py
```bash
# Verwende die KORRIGIERTE Version aus dem Artifact "search_tool_fixed"
```

## 4. Konfiguration

### .env Datei erstellen
```bash
# Verwende das .env Template und fülle deine echten API-Keys ein
```

### requirements.txt
```bash
# Verwende die requirements.txt aus dem Artifact
```

## 5. Installation

```bash
# Virtual Environment erstellen (empfohlen)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Pakete installieren
pip install -r requirements.txt

# Playwright Browser installieren
playwright install chromium
```

## 6. DataForSEO Account einrichten

1. Gehe zu https://dataforseo.com/
2. Erstelle einen kostenlosen Account
3. Gehe zu deinem Dashboard
4. Notiere dir:
   - Email (als DATAFORSEO_USER)
   - Passwort (als DATAFORSEO_PASS)
5. Trage diese in die .env Datei ein

## 7. Server starten

```bash
# Ins server-Verzeichnis wechseln
cd server

# Server starten
python mcp_server.py
```

Der Server läuft auf http://127.0.0.1:5000

## 8. Agent testen

```bash
# In neuem Terminal, ins agent-Verzeichnis wechseln
cd agent

# Einfache Version testen
python timus.py

# Oder ReAct-Version testen
python timus_react.py
```

## 9. Troubleshooting

### Problem: Import-Fehler
```bash
# Stelle sicher, dass du im Projekt-Root bist
cd /home/fatih-ubuntu/dev/timus

# Python-Path prüfen
python -c "import sys; print(sys.path)"
```

### Problem: DataForSEO API-Fehler
```bash
# Test der API-Credentials
curl -u "your-email:your-password" \
  "https://api.dataforseo.com/v3/serp/google/organic/live/advanced" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '[{"keyword":"test","location_code":2276,"language_code":"de"}]'
```

### Problem: Browser-Tool funktioniert nicht
```bash
# Playwright Browser erneut installieren
playwright install chromium
```

## 10. Verbesserungen in der korrigierten Version

1. **Search Tool**: 
   - Korrekte DataForSEO API-Endpoints
   - Bessere Error-Behandlung
   - Deutsche Lokalisierung (location_code: 2276)

2. **Server**:
   - Bessere Import-Behandlung
   - Detaillierte Fehlerprotokollierung
   - Health-Check-Endpoint

3. **Ordnerstruktur**:
   - Saubere Paket-Struktur
   - Korrekte __init__.py Dateien
   - Bessere Modularität