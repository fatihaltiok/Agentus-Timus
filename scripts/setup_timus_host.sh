#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE_DIR="${PROJECT_ROOT}/systemd/templates"
INSTALL_SCRIPT="${SCRIPT_DIR}/install_timus_stack.sh"
CONFIG_FILE="${TIMUS_STACK_SETUP_ENV_FILE:-${SCRIPT_DIR}/timus_stack_host.env}"
OUTPUT_DIR="${TIMUS_STACK_OUTPUT_DIR:-${PROJECT_ROOT}/.generated/systemd}"
NONINTERACTIVE="${TIMUS_STACK_NONINTERACTIVE:-0}"
INSTALL_AFTER_RENDER=false
ENABLE_STACK=false
START_STACK=false

usage() {
  cat <<'EOF'
Nutzung:
  ./scripts/setup_timus_host.sh
  ./scripts/setup_timus_host.sh --install --enable --start
  ./scripts/setup_timus_host.sh --non-interactive

Beschreibung:
  Fragt einfache Host-Werte ab, rendert daraus portable systemd-Units
  und kann den Timus-Stack danach direkt installieren.

Optionen:
  --install           installiert die gerenderten Units nach dem Rendern
  --enable            aktiviert timus-stack.target beim Boot
  --start             startet timus-stack.target direkt nach der Installation
  --non-interactive   verwendet Defaults/Umgebungswerte ohne Rueckfragen
  --config PATH       alternativer Pfad fuer die Host-Konfigurationsdatei
  --output-dir PATH   alternatives Ziel fuer gerenderte Units
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      INSTALL_AFTER_RENDER=true
      ;;
    --enable)
      ENABLE_STACK=true
      ;;
    --start)
      START_STACK=true
      ;;
    --non-interactive)
      NONINTERACTIVE=1
      ;;
    --config)
      CONFIG_FILE="${2:?Fehlender Wert fuer --config}"
      shift
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?Fehlender Wert fuer --output-dir}"
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

if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

_default_python() {
  if [[ -n "${TIMUS_PYTHON:-}" && -x "${TIMUS_PYTHON}" ]]; then
    printf '%s\n' "${TIMUS_PYTHON}"
    return 0
  fi
  if [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
    printf '%s\n' "${CONDA_PREFIX}/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  printf '/usr/bin/python3\n'
}

TIMUS_SYSTEM_USER="${TIMUS_SYSTEM_USER:-$(id -un)}"
TIMUS_PROJECT_ROOT="${TIMUS_PROJECT_ROOT:-${PROJECT_ROOT}}"
TIMUS_PYTHON="${TIMUS_PYTHON:-$(_default_python)}"
TIMUS_DISPLAY="${TIMUS_DISPLAY:-${DISPLAY:-:0}}"
TIMUS_XAUTHORITY="${TIMUS_XAUTHORITY:-${XAUTHORITY:-/home/${TIMUS_SYSTEM_USER}/.Xauthority}}"
TIMUS_PYTHON_UVICORN="${TIMUS_PYTHON_UVICORN:-${TIMUS_PYTHON%/python}/uvicorn}"

prompt_value() {
  local var_name="$1"
  local label="$2"
  local default_value="$3"
  local current_value="${!var_name:-$default_value}"
  if [[ "${NONINTERACTIVE}" == "1" || ! -t 0 ]]; then
    printf -v "$var_name" '%s' "$current_value"
    return 0
  fi
  local answer=""
  read -r -p "${label} [${current_value}]: " answer
  if [[ -n "${answer}" ]]; then
    printf -v "$var_name" '%s' "$answer"
  else
    printf -v "$var_name" '%s' "$current_value"
  fi
}

prompt_value TIMUS_SYSTEM_USER "System-Benutzer fuer die Dienste" "${TIMUS_SYSTEM_USER}"
prompt_value TIMUS_PROJECT_ROOT "Projektpfad von Timus" "${TIMUS_PROJECT_ROOT}"
prompt_value TIMUS_PYTHON "Python-Pfad fuer Timus" "${TIMUS_PYTHON}"
prompt_value TIMUS_PYTHON_UVICORN "uvicorn-Pfad fuer Timus MCP" "${TIMUS_PYTHON_UVICORN}"
prompt_value TIMUS_DISPLAY "DISPLAY fuer visuelle Tools" "${TIMUS_DISPLAY}"
prompt_value TIMUS_XAUTHORITY "XAUTHORITY-Datei" "${TIMUS_XAUTHORITY}"

if [[ ! -d "${TIMUS_PROJECT_ROOT}" ]]; then
  echo "Projektpfad existiert nicht: ${TIMUS_PROJECT_ROOT}" >&2
  exit 1
fi

if [[ ! -x "${TIMUS_PYTHON}" ]]; then
  echo "Python-Pfad ist nicht ausfuehrbar: ${TIMUS_PYTHON}" >&2
  exit 1
fi

if [[ ! -x "${TIMUS_PYTHON_UVICORN}" ]]; then
  echo "uvicorn-Pfad ist nicht ausfuehrbar: ${TIMUS_PYTHON_UVICORN}" >&2
  exit 1
fi

if [[ ! -x "${TIMUS_PROJECT_ROOT}/scripts/start_qdrant_server.sh" ]]; then
  echo "Qdrant-Startskript fehlt oder ist nicht ausfuehrbar: ${TIMUS_PROJECT_ROOT}/scripts/start_qdrant_server.sh" >&2
  exit 1
fi

escape_sed() {
  printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

render_template() {
  local src="$1"
  local dst="$2"
  sed \
    -e "s/__TIMUS_SYSTEM_USER__/$(escape_sed "${TIMUS_SYSTEM_USER}")/g" \
    -e "s/__TIMUS_PROJECT_ROOT__/$(escape_sed "${TIMUS_PROJECT_ROOT}")/g" \
    -e "s/__TIMUS_PYTHON__/$(escape_sed "${TIMUS_PYTHON}")/g" \
    -e "s/__TIMUS_PYTHON_UVICORN__/$(escape_sed "${TIMUS_PYTHON_UVICORN}")/g" \
    -e "s/__TIMUS_DISPLAY__/$(escape_sed "${TIMUS_DISPLAY}")/g" \
    -e "s/__TIMUS_XAUTHORITY__/$(escape_sed "${TIMUS_XAUTHORITY}")/g" \
    "${src}" > "${dst}"
}

mkdir -p "${OUTPUT_DIR}"

render_template "${TEMPLATE_DIR}/qdrant.service.in" "${OUTPUT_DIR}/qdrant.service"
render_template "${TEMPLATE_DIR}/timus-mcp.service.in" "${OUTPUT_DIR}/timus-mcp.service"
render_template "${TEMPLATE_DIR}/timus-dispatcher.service.in" "${OUTPUT_DIR}/timus-dispatcher.service"
render_template "${TEMPLATE_DIR}/timus-stack.target.in" "${OUTPUT_DIR}/timus-stack.target"

cat > "${CONFIG_FILE}" <<EOF
TIMUS_SYSTEM_USER=${TIMUS_SYSTEM_USER}
TIMUS_PROJECT_ROOT=${TIMUS_PROJECT_ROOT}
TIMUS_PYTHON=${TIMUS_PYTHON}
TIMUS_PYTHON_UVICORN=${TIMUS_PYTHON_UVICORN}
TIMUS_DISPLAY=${TIMUS_DISPLAY}
TIMUS_XAUTHORITY=${TIMUS_XAUTHORITY}
EOF

echo "Host-Konfiguration gespeichert: ${CONFIG_FILE}"
echo "Gerenderte systemd-Units: ${OUTPUT_DIR}"

if [[ "${INSTALL_AFTER_RENDER}" == "true" ]]; then
  install_args=(--unit-dir "${OUTPUT_DIR}")
  if [[ "${ENABLE_STACK}" == "true" ]]; then
    install_args+=(--enable)
  fi
  if [[ "${START_STACK}" == "true" ]]; then
    install_args+=(--start)
  fi
  if [[ "${EUID}" -eq 0 ]]; then
    "${INSTALL_SCRIPT}" "${install_args[@]}"
  else
    sudo "${INSTALL_SCRIPT}" "${install_args[@]}"
  fi
fi
