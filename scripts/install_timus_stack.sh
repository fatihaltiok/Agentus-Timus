#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
UNIT_DIR="${TIMUS_STACK_UNITS_DIR:-${PROJECT_ROOT}}"
UNITS=(
  "qdrant.service"
  "timus-mcp.service"
  "timus-dispatcher.service"
  "timus-stack.target"
)
ENABLE_STACK=false
START_STACK=false

usage() {
  cat <<'EOF'
Nutzung:
  sudo ./scripts/install_timus_stack.sh [--enable] [--start]
  sudo ./scripts/install_timus_stack.sh [--unit-dir PATH] [--enable] [--start]

Optionen:
  --unit-dir PATH  alternative Quelle fuer die Unit-Dateien
  --enable   aktiviert timus-stack.target fuer den Boot
  --start    startet timus-stack.target direkt nach der Installation

Installiert:
  - qdrant.service
  - timus-mcp.service
  - timus-dispatcher.service
  - timus-stack.target
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable)
      ENABLE_STACK=true
      ;;
    --start)
      START_STACK=true
      ;;
    --unit-dir)
      UNIT_DIR="${2:?Fehlender Wert fuer --unit-dir}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unbekannte Option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte mit sudo/root ausfuehren." >&2
  exit 1
fi

install -d "${SYSTEMD_DIR}"

for unit in "${UNITS[@]}"; do
  src="${UNIT_DIR}/${unit}"
  dst="${SYSTEMD_DIR}/${unit}"
  if [[ ! -f "${src}" ]]; then
    echo "Fehlende Unit-Datei: ${src}" >&2
    exit 1
  fi
  install -m 0644 "${src}" "${dst}"
  echo "Installiert: ${dst}"
done

systemctl daemon-reload

# Nur das Stack-Target aktivieren; die Services werden darueber gestartet.
systemctl disable qdrant.service timus-mcp.service timus-dispatcher.service >/dev/null 2>&1 || true

if [[ "${ENABLE_STACK}" == "true" ]]; then
  systemctl enable timus-stack.target
  echo "Aktiviert: timus-stack.target"
fi

if [[ "${START_STACK}" == "true" ]]; then
  systemctl start timus-stack.target
  echo "Gestartet: timus-stack.target"
fi

echo "Timus-Stack-Installation abgeschlossen."
