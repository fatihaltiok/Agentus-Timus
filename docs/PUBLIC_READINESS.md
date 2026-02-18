# Public Readiness Checklist

Stand: 2026-02-18  
Repo: `fatihaltiok/Agentus-Timus`

## Ergebnis (Kurzfassung)
Status: **NOT READY for public**

Blocker:
- Versionierte Datei `env.txt` enthält reale API-Secrets.
- Secrets sind bereits in der Git-Historie vorhanden.

## Scan-Umfang
1. Working Tree Scan (tracked + untracked, ohne große Artefaktordner)
2. Git-Index/Tracked Files Check
3. History-Scan auf Secret-Muster

## Findings

### F1 (CRITICAL): Reale API-Keys in versionierter Datei
- Datei: `env.txt`
- Beispiele:
  - `OPENAI_API_KEY=sk-proj-...`
  - `INCEPTION_API_KEY=sk_...`
- Tracking-Status: `env.txt` ist versioniert (`git ls-files`)

### F2 (CRITICAL): Secret in Git-Historie
- Nachweis in Diff-Historie von `env.txt` vorhanden
- Betroffener Commit-Pfad: `git log -- env.txt` zeigt Einbringung in Historie

### F3 (INFO): Platzhalter in Doku
- `README.md` und einige Doku-Dateien enthalten Platzhalter (`sk-...`), keine klaren Live-Secrets

## Pflichtmaßnahmen vor Public-Switch

1. **Sofortige Rotation aller betroffenen Keys**
- OpenAI Key rotieren
- Inception Key rotieren
- Falls weitere Keys jemals im Repo waren: ebenfalls rotieren

2. **Secrets aus aktuellem Stand entfernen**
- `env.txt` aus Tracking nehmen oder löschen
- Nur Templates behalten (`.env.example`)

3. **Git-Historie bereinigen (Rewrite)**
- Empfohlen: `git filter-repo` oder BFG
- Danach Force-Push auf Remote

4. **Branch/Repo schützen**
- Secret-Scanning aktivieren
- Push-Protection aktivieren
- CI-Gates auf `main` required lassen

## Konkrete technische Schritte

### A) Sofort (Working Tree bereinigen)
```bash
# 1) Datei aus Git-Tracking entfernen (lokale Datei bleibt erhalten)
git rm --cached env.txt

# 2) Absichern, dass sie künftig ignoriert wird
echo "env.txt" >> .gitignore

# 3) Commit
git add .gitignore
git commit -m "security: stop tracking env.txt"
```

### B) Historie bereinigen (empfohlen)
```bash
# Voraussetzung: git-filter-repo installiert
# Entfernt env.txt aus der gesamten Historie
git filter-repo --path env.txt --invert-paths

# Danach neu zu GitHub pushen (Achtung: History Rewrite)
git push --force --all origin
git push --force --tags origin
```

### C) Nachkontrolle
```bash
# Tracked-Dateien prüfen
git ls-files | rg "env\.txt|\.env"

# Working Tree Secret-Scan
rg -n --hidden --glob '!.git/**' \
  "(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)" .

# History Scan (Ausschnitt)
git log --all -p --no-color | rg -n "(ghp_|github_pat_|sk-proj-|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)"
```

## Empfehlung
Public-Schaltung erst nach:
- Key-Rotation abgeschlossen
- `env.txt` aus Tracking entfernt
- History Rewrite durchgeführt
- Nachkontrolle ohne Secret-Treffer

