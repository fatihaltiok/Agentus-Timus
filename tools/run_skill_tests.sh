#!/usr/bin/env bash
# ----------------------------------------------------------------------
# Skript zum Ausführen von Lint, Tests, Coverage und Berichtenerstellung
# ----------------------------------------------------------------------
set -euo pipefail

# Prüfen, ob python3 verfügbar ist
if ! command -v python3 &>/dev/null; then
  echo "Fehler: python3 ist nicht installiert." >&2
  exit 1
fi

# Virtuelle Umgebung erstellen, falls nicht existent
if [ ! -d ".venv_tests" ]; then
  python3 -m venv .venv_tests
fi
source .venv_tests/bin/activate

# Abhängigkeiten installieren
pip install -r requirements-dev.txt

# Lint-Tools ausführen
echo "Running black check..."
black --check .

echo "Running flake8..."
flake8 .

# Tests mit Coverage
echo "Running pytest..."
pytest --junitxml=reports/tests.xml --cov=skills --cov-report=xml:reports/coverage.xml

# Fehler-Logs sammeln (falls vorhanden)
if [ -d "skills/logs" ]; then
  find skills/logs -type f -name "*.log" -exec cat {} \; > reports/error_logs.txt || true
fi

echo "Alle Tests und Lint checks erfolgreich."
exit 0