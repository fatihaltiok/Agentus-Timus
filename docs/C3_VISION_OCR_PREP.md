# C3 Vorbereitung - Vision/OCR Hot Path

Stand: 2026-04-05

Diese Datei bereitet C3 vor, ohne bereits in den Vision/OCR-Laufzeitpfad einzugreifen.

## Ziel

C3 soll den Vision/OCR-Hot-Path von Timus berechenbarer und robuster machen:

- weniger OOM- und Timeout-Risiko
- klarer Primärpfad statt impliziter CPU/GPU-Mischpfade
- nachvollziehbare Device-, Memory- und Fallback-Telemetrie
- stabilere Laufzeit für UI-/Vision-gestützte Aufgaben

## Bekannte Ausgangslage

Der auslösende Befund aus Phase C:

- `timus-mcp` wurde unter Last beendet
- Florence-2 lief auf `cuda`
- PaddleOCR lief gleichzeitig auf `cpu`
- damit entstand ein gemischter Hot-Path mit Druck auf VRAM und RAM

## C3 Arbeitsreihenfolge

1. Vision-/OCR-Inventur

- alle aktiven Pfade erfassen, die Florence-2, PaddleOCR, Qwen-VL oder OCR-Engine nutzen
- pro Pfad festhalten:
  - Einstiegspunkt
  - Modell/Engine
  - Device
  - Fallback-Verhalten
  - erwartete Last

2. Primärpfad und Fallback-Regeln definieren

- festlegen, wann Florence-2 primär ist
- festlegen, wann OCR allein reicht
- festlegen, wann ein CPU-Fallback erlaubt ist
- keine stillen Mischpfade mehr ohne explizite Regel

3. Telemetrie-Hookpoints vorbereiten

- vor Modellinitialisierung
- vor Inferenz
- nach Inferenz
- bei Device-Wechsel
- bei Fallback
- bei Timeout/OOM/Runtime-Fehler

4. Repro- und Testmatrix festziehen

- kleiner Screenshot
- großer Screenshot
- OCR-lastiger Fall
- UI-Detektionsfall
- gemischter Vision+OCR-Fall
- Degradationsfall ohne GPU

## Messwerte, die C3 sichtbar machen soll

- gewähltes Device
- Modellname / Engine
- Initialisierungsdauer
- Inferenzdauer
- Fallback-Grund
- geschätzte Bildgröße / Inputgröße
- OOM-/Timeout-/Runtime-Fehlerklasse

## Nicht Teil der Vorbereitung

Diese Datei startet C3 bewusst noch nicht:

- keine Änderung an Florence-2-Initialisierung
- keine Änderung an PaddleOCR-Konfiguration
- keine neuen Runtime-Guards im Code
- keine neuen Device-Switches

## Fertig für Start, wenn

- alle relevanten Hot-Paths inventarisiert sind
- die Ziel-Telemetrie klar definiert ist
- die Testmatrix für C3 steht
- klar ist, welcher Pfad zuerst gehärtet wird
