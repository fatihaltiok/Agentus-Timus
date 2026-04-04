---
name: google-calendar
description: Google Calendar Integration für Timus - Termine lesen, erstellen, aktualisieren und löschen via Google Calendar API. Benötigt OAuth2-Credentials.
version: 1.0.0
tags: calendar, google, oauth2
---

# Google Calendar Integration

## Quick Start

### Voraussetzungen

1. Google Cloud Console öffnen: https://console.cloud.google.com/
2. Projekt erstellen oder bestehendes nutzen
3. Google Calendar API aktivieren (APIs & Services → Library → "Google Calendar API" → Enable)
4. OAuth2-Credentials erstellen (APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app)
5. Client ID und Client Secret kopieren
6. credentials.json im scripts/ Ordner anlegen
7. oauth_flow.py ausführen für ersten Login

### Verwendung

Termine auflisten: action=list, days=7
Termin erstellen: action=create, title, start, end
Termin löschen: action=delete, event_id

## Setup-Status

action=status prüft: credentials_ok, token_ok, calendar_accessible
