# Android Phase A

## Ziel

Phase A legt das Android-Grundgeruest fuer Timus Mobile im Repo unter `android/` an.

Der Schnitt ist bewusst klein:

- Android-Studio-faehiges Projekt
- Kotlin + Jetpack Compose
- Login/Auth-Screen
- Bottom-Navigation
- Screens:
  - Home
  - Chat
  - Voice
  - Files
  - Admin
- zentrale Timus-Konfiguration mit `baseUrl`, `username`, `password`

## Noch nicht Teil von Phase A

- echte Voice-Aufnahme
- echte TTS-Wiedergabe
- Datei-Picker und Downloads
- Live-API-Anbindung
- Persistenz via DataStore / Encrypted Storage
- Push / Notifications

## Zweck

Phase A schafft die stabile Struktur, damit die naechsten Phasen nicht wieder UI, Architektur und API-Anbindung gleichzeitig vermischen.
