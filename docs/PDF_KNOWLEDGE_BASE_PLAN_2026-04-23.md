# PDF Knowledge Base Plan

Stand: 2026-04-23

## Problem

Timus kann heute PDFs teilweise nutzen, aber noch nicht als saubere,
persistent zitierbare Quellenbasis.

Vorhandene Bausteine:

- Upload-Infrastruktur in [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- PDF-Text-Extraktion von URL in [tool.py](/home/fatih-ubuntu/dev/timus/tools/document_parser/tool.py)
- Qdrant-basierter semantischer Speicher fuer Chat in [conversation_qdrant.py](/home/fatih-ubuntu/dev/timus/server/conversation_qdrant.py)

Was fehlt:

- ingestierbare PDF-Quellen aus Uploads und lokalen Dateien
- persistente Chunk-Speicherung als eigene Dokument-Collection
- Retrieval nur aus diesen PDF-Chunks
- harter Zitationsvertrag mit Datei, Seite und Chunk
- klare Trennung zwischen:
  - Dokumentinhalt
  - Chat-Memory
  - freier Modellantwort

## Ziel

Timus soll PDFs als echte Quellen verwalten koennen:

1. PDF annehmen
2. Text plus Seitenstruktur extrahieren
3. in zitierbare Chunks zerlegen
4. persistent speichern
5. spaeter retrieval-basiert nutzen
6. Antworten mit exakter Quellenangabe belegen

Beispiel:

- Nutzer gibt Timus eine PDF
- Timus legt sie in die PDF-Quellenbasis ab
- Nutzer fragt spaeter:
  - `Was sagt das Papier zu X?`
  - `Zitiere die Stelle zu Y`
  - `Nutze das Dokument als Quelle fuer diese Einordnung`

## Nicht-Ziele

Nicht Teil dieses Blocks:

- allgemeine Web-Recherche
- freies Halluzinations-zentriertes Zusammenfassen ohne Retrieval
- vollstaendiges Wissensgraph-System
- unbearbeitete Volltextspeicherung ohne Seiten-/Chunk-Metadaten

## Kernprinzip

Nicht:

- PDF nur einmal lesen
- alles in freiem Prompt-Kontext verschwimmen lassen
- spaeter aus unscharfer Erinnerung antworten

Sondern:

1. Quelle registrieren
2. Inhalt strukturiert extrahieren
3. Chunk mit Metadaten persistieren
4. Retrieval nur ueber diese Chunks
5. Antwort an Evidenz binden
6. Zitat nur aus echten Treffer-Chunks erzeugen

## Nutzerfaelle

Pflichtfaelle:

- `Lege diese PDF als Quelle ab`
- `Nutze diese PDF kuenftig als Wissensquelle`
- `Was sagt die PDF zu Thema X?`
- `Zitiere mir die relevante Passage`
- `Welche Stellen in der PDF stuetzen diese Aussage?`
- `Fasse die PDF zusammen, aber nur mit Quellenbezug`

## Architektur

### 1. Source Registry

Jede PDF bekommt einen stabilen Quelleneintrag:

- `source_id`
- `filename`
- `original_path` oder `upload_path`
- `source_kind`
  - `upload`
  - `local_file`
  - `url`
- `sha256`
- `page_count`
- `ingest_status`
- `created_at`

Dieser Registry-Eintrag ist die Bruecke zwischen Dateisystem, Chunk-Store und
spaeterer Antwort.

### 2. Extraction Layer

Die bestehende URL-Extraktion in [tool.py](/home/fatih-ubuntu/dev/timus/tools/document_parser/tool.py)
wird zu einer allgemeineren PDF-Extraktionsschicht erweitert:

- Upload-/lokale Datei einlesen
- seitenweiser Text
- robuste Fehlerisolierung wie heute
- Rueckgabe nicht nur `full_text`, sondern auch:
  - `pages`
  - `page_number`
  - `page_text`

### 3. Chunking Layer

Die Extraktion wird in semantisch nutzbare Chunks zerlegt.

Jeder Chunk bekommt:

- `source_id`
- `filename`
- `page_start`
- `page_end`
- `chunk_index`
- `chunk_text`
- `token_count`
- optional:
  - `section_title`
  - `heading_path`

Anforderung:

- keine Chunks ohne Seitenbezug
- keine Chunks ohne Rueckverweis auf `source_id`

### 4. Storage Layer

Die PDF-Chunks duerfen nicht in den normalen Chat-Store laufen.

Stattdessen:

- eigene Qdrant-Collection fuer PDF-Wissen
- getrennt von [conversation_qdrant.py](/home/fatih-ubuntu/dev/timus/server/conversation_qdrant.py)
- separates Retrieval-Budget
- separates Metadata-Schema

Beispiel:

- `timus_pdf_sources`
- `timus_pdf_chunks`

### 5. Retrieval Layer

Neue Retrieval-Regeln:

- nur Quellen aus der PDF-Collection
- optional source-scoped:
  - nur eine bestimmte PDF
  - oder mehrere explizit zugelassene PDFs
- Treffer muessen strukturiert zurueckkommen:
  - `source_id`
  - `filename`
  - `page_start`
  - `page_end`
  - `chunk_text`
  - `score`

### 6. Citation Contract

Timus darf bei PDF-Quellenantworten nicht frei paraphrasierend erfinden.

Pflichtvertrag:

- jede belegte Aussage muss auf mindestens einen echten Chunk zeigen
- direktes Zitat nur aus dem Treffer-Chunk
- Quellenformat mindestens:
  - Dateiname
  - Seite oder Seitenbereich
  - optional Chunk-ID

Beispiel:

- `Quelle: paper.pdf, S. 14`
- `Quelle: paper.pdf, S. 14-15, Chunk 08`

Wenn keine belastbare Evidenz vorliegt:

- nicht raten
- explizit sagen, dass die PDF-Stelle nicht sicher belegt wurde

## Interaktionsmodi

Die PDF-Quellenbasis muss zum bestehenden Modusmodell passen:

- `think_partner`
  - keine ungefragte Ingestion
  - PDF nur als benannte Quelle diskutieren
- `inspect`
  - PDF lesen, pruefen, zitieren, zusammenfassen
  - keine ungefragte Umstrukturierung
- `assist`
  - PDF ingestieren, Collection aufbauen, Quellenbasis pflegen

## Umsetzung in Slices

### PKB1. Source Registry und Upload-Bindung

Ziel:

- aus Uploads/lokalen PDFs echte Quellenobjekte machen

Umfang:

- Registry-Modell fuer PDF-Quellen
- Bindung an `data/uploads`
- Hashing und Deduplikation
- Metadatenpersistenz

Erfolg:

- Timus kann sagen:
  - welche PDF bekannt ist
  - ob sie schon ingestiert wurde

### PKB2. Extraktion und seitenweiser Output

Ziel:

- PDF nicht mehr nur als Volltext behandeln

Umfang:

- bestehende Parser-Schicht erweitern
- seitenweiser Output
- robuste Fehlerbehandlung

Erfolg:

- pro PDF liegen Seitenmetadaten sauber vor

### PKB3. Chunking und Qdrant-Storage

Ziel:

- zitierbare, semantisch abfragbare PDF-Chunks speichern

Umfang:

- Chunker
- dedizierte PDF-Qdrant-Collection
- Metadatenvertrag

Erfolg:

- PDF-Inhalt ist persistent und retrieval-faehig

### PKB4. Retrieval Tool und Quellenantworten

Ziel:

- Timus kann spaeter wirklich auf PDF-Chunks zugreifen

Umfang:

- neues Retrieval-Tool fuer PDF-Quellen
- source-scoped Query
- Trefferformat fuer Meta/Research

Erfolg:

- `Was sagt die PDF zu X?` liefert echte Treffer statt freie Erinnerung

### PKB5. Citation Guard

Ziel:

- nur evidenzgebundene PDF-Antworten

Umfang:

- Zitationsvertrag vor Final Answer
- Quote-Guard
- Antworten ohne Evidenz werden blockiert oder als ungesichert markiert

Erfolg:

- Timus zitiert keine nicht vorhandenen PDF-Stellen

### PKB6. Nutzerpfade und Live-Gates

Ziel:

- echter End-to-End-Pfad statt nur interne Bausteine

Pflichtfaelle:

- PDF hochladen und ingestieren
- spaeter `Nutze diese PDF als Quelle`
- spaeter `Zitiere die Passage zu X`
- spaeter `Fasse nur auf Basis dieser PDF zusammen`

Erfolg:

- PDF-Wissenspfad ist nicht nur intern vorhanden, sondern fuer den Nutzer stabil

## Qualitaetsregeln

Pflichtregeln:

- kein Chat-Memory als Ersatz fuer PDF-Evidenz
- keine Zitate ohne Seitenbezug
- keine PDF-Antworten aus bloßer Modellvermutung
- keine Vermischung von:
  - Quelle
  - Zusammenfassung
  - Interpretation

## Offene Architekturentscheidung

Noch sauber zu entscheiden:

- eine Collection fuer alle PDFs plus `source_id`-Filter
- oder getrennte Collections pro Quelle/Projekt

Aktuelle Empfehlung:

- eine dedizierte PDF-Chunk-Collection
- plus harter `source_id`- und Session-/Projekt-Filter

Das ist einfacher zu betreiben und spaeter leichter evaluiertbar.

## Erfolgskriterium

Timus gilt in diesem Block erst dann als fertig, wenn folgendes robust geht:

1. Nutzer gibt eine PDF
2. Timus ingestiert sie persistent
3. Nutzer fragt spaeter nach einer Aussage aus dieser PDF
4. Timus liefert eine evidenzgebundene Antwort
5. die Quelle ist mit Datei und Seite nachvollziehbar
