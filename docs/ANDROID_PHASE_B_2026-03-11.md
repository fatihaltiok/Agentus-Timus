# Android Phase B

## Ziel

Phase B macht aus dem Phase-A-Grundgeruest einen ersten nutzbaren Voice-first-Chat-Client.

## Neu in Phase B

- gemeinsamer App-Session-State ueber `AppSessionViewModel`
- einfache Netzwerk-Schicht gegen Timus
- `/chat`-Anbindung
- `/chat/history`-Anbindung
- `/voice/status`-Anbindung
- `/voice/transcribe`-Upload fuer nativen Android-Audioinput
- `/voice/synthesize`-Abruf fuer Audioausgabe
- nativer Voice-Screen mit:
  - Mikrofon-Permission
  - Aufnahme starten/stoppen
  - Transkript nach Timus schicken
  - letzte Antwort als Audio anfordern
  - letzte Audioantwort lokal abspielen

## Wichtige Klassen

- `android/.../data/TimusRepository.kt`
- `android/.../data/NetworkTimusRepository.kt`
- `android/.../ui/AppSessionViewModel.kt`
- `android/.../ui/screens/ChatScreen.kt`
- `android/.../ui/screens/VoiceScreen.kt`

## Noch nicht Teil von Phase B

- Datei-Picker/Download in Android
- echte Admin-/Ops-Endpunktanbindung
- persistente sichere Credential-Speicherung
- SSE-Streaming / Live-Updates
- robustes Audio-Fokus-/Interrupt-Handling

## Wichtiger Hinweis

Im Terminal konnte kein echter Android-Build gefahren werden, weil lokal kein nutzbares Gradle/Android-SDK-Tooling verfuegbar ist. Der naechste praktische Schritt fuer diese Phase ist deshalb:

1. `android/` in Android Studio oeffnen
2. Gradle-Sync laufen lassen
3. auf dem Pixel oder Emulator starten
4. danach Compiler-/SDK-Probleme direkt im Projekt nachziehen
