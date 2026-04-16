#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALLER_SCRIPT="${SCRIPT_DIR}/install_timus_stack.sh"
HOST_SETUP_SCRIPT="${SCRIPT_DIR}/setup_timus_host.sh"
PRODUCTION_GATES_SCRIPT="${SCRIPT_DIR}/run_production_gates.py"
DOCTOR_SCRIPT="${SCRIPT_DIR}/timus_doctor.py"
GENERATED_SYSTEMD_DIR="${PROJECT_ROOT}/.generated/systemd"

QDRANT_SERVICE="qdrant.service"
MCP_SERVICE="timus-mcp.service"
DISPATCHER_SERVICE="timus-dispatcher.service"
STACK_TARGET="timus-stack.target"
QDRANT_READY_URL="http://127.0.0.1:6333/readyz"
MCP_HEALTH_URL="http://127.0.0.1:5000/health"
DISPATCHER_HEALTH_URL="http://127.0.0.1:5010/health"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[TIMUS]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[FEHLER]${NC} $*"; }

usage() {
    cat <<'EOF'
Nutzung:
  ./scripts/timusctl.sh up
  ./scripts/timusctl.sh down
  ./scripts/timusctl.sh restart
  ./scripts/timusctl.sh status
  ./scripts/timusctl.sh health
  ./scripts/timusctl.sh doctor [--json|--strict]
  ./scripts/timusctl.sh install [--no-start]
  ./scripts/timusctl.sh setup-host [--install]
  ./scripts/timusctl.sh logs [qdrant|mcp|dispatcher]

Befehle:
  up         Startet qdrant -> mcp -> dispatcher
  down       Stoppt dispatcher -> mcp -> qdrant
  restart    Neustart in sicherer Reihenfolge
  status     Zeigt kompakten Service-Status
  health     Prueft qdrant, mcp und production gates
  doctor     Gibt einen einheitlichen Diagnose- und Lifecycle-Report fuer den Stack aus
  install    Installiert/aktiviert den gesamten Stack; startet ihn standardmaessig direkt
  setup-host Rendert portable systemd-Units fuer diesen Host; mit --install direkt inklusive Installation
  logs       Folgt den Logs eines Dienstes oder allen dreien
EOF
}

check_noninteractive_sudo() {
    local service
    for service in "$QDRANT_SERVICE" "$MCP_SERVICE" "$DISPATCHER_SERVICE"; do
        if ! sudo -n systemctl status "$service" >/dev/null 2>&1; then
            err "Passwortloses sudo fuer $service nicht verfuegbar. Installiere scripts/sudoers_timus."
            exit 1
        fi
    done
}

stack_target_exists() {
    systemctl cat "$STACK_TARGET" >/dev/null 2>&1
}

wait_for_http() {
    local url="$1"
    local label="$2"
    local retries="${3:-15}"
    local wait_secs="${4:-2}"
    local attempt

    for attempt in $(seq 1 "$retries"); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            ok "$label antwortet"
            return 0
        fi
        sleep "$wait_secs"
    done

    err "$label antwortet nicht: $url"
    return 1
}

start_service() {
    local service="$1"
    log "Starte $service ..."
    sudo -n systemctl start "$service"
}

stop_service() {
    local service="$1"
    log "Stoppe $service ..."
    sudo -n systemctl stop "$service" || true
}

show_status() {
    log "=== Status ==="
    if stack_target_exists; then
        systemctl --no-pager --full status "$STACK_TARGET" | sed -n '1,8p' || true
        echo
    fi
    systemctl --no-pager --full status "$QDRANT_SERVICE" | sed -n '1,8p' || true
    echo
    systemctl --no-pager --full status "$MCP_SERVICE" | sed -n '1,8p' || true
    echo
    systemctl --no-pager --full status "$DISPATCHER_SERVICE" | sed -n '1,8p' || true
}

start_stack() {
    check_noninteractive_sudo
    if stack_target_exists; then
        log "Starte Stack-Target $STACK_TARGET ..."
        sudo -n systemctl start "$STACK_TARGET"
    else
        start_service "$QDRANT_SERVICE"
        start_service "$MCP_SERVICE"
        start_service "$DISPATCHER_SERVICE"
    fi
    wait_for_http "$QDRANT_READY_URL" "Qdrant" 20 2
    wait_for_http "$MCP_HEALTH_URL" "MCP" 20 2
    wait_for_http "$DISPATCHER_HEALTH_URL" "Dispatcher" 20 2
    sleep 2
    if systemctl is-active --quiet "$DISPATCHER_SERVICE"; then
        ok "Dispatcher laeuft"
    else
        err "Dispatcher konnte nicht gestartet werden"
        exit 1
    fi
    show_status
}

stop_stack() {
    check_noninteractive_sudo
    if stack_target_exists; then
        log "Stoppe Stack-Target $STACK_TARGET ..."
        sudo -n systemctl stop "$STACK_TARGET" || true
    fi
    stop_service "$DISPATCHER_SERVICE"
    stop_service "$MCP_SERVICE"
    stop_service "$QDRANT_SERVICE"
    ok "Timus-Stack gestoppt"
}

restart_stack() {
    stop_stack
    sleep 1
    start_stack
}

show_health() {
    log "=== Health ==="
    if curl -fsS "$QDRANT_READY_URL" >/dev/null 2>&1; then
        ok "Qdrant ready"
    else
        warn "Qdrant nicht ready"
    fi

    if curl -fsS "$MCP_HEALTH_URL" >/dev/null 2>&1; then
        ok "MCP healthy"
    else
        warn "MCP health fehlgeschlagen"
    fi

    if curl -fsS "$DISPATCHER_HEALTH_URL" >/dev/null 2>&1; then
        ok "Dispatcher healthy"
    else
        warn "Dispatcher health fehlgeschlagen"
    fi

    python "$PRODUCTION_GATES_SCRIPT"
}

show_doctor() {
    local doctor_arg="${1:-}"
    if [[ -n "$doctor_arg" && "$doctor_arg" != "--json" && "$doctor_arg" != "--strict" ]]; then
        err "Unbekannte doctor-Option: $doctor_arg"
        usage
        exit 1
    fi
    python "$DOCTOR_SCRIPT" ${doctor_arg:+"$doctor_arg"}
}

install_stack() {
    local installer_args=(--enable --start)
    if [[ -d "$GENERATED_SYSTEMD_DIR" ]]; then
        installer_args=(--unit-dir "$GENERATED_SYSTEMD_DIR" --enable --start)
    fi
    if [[ "${ARG:-}" == "--no-start" ]]; then
        if [[ -d "$GENERATED_SYSTEMD_DIR" ]]; then
            installer_args=(--unit-dir "$GENERATED_SYSTEMD_DIR" --enable)
        else
            installer_args=(--enable)
        fi
    elif [[ -n "${ARG:-}" && "${ARG:-}" != "--start" ]]; then
        err "Unbekannte install-Option: ${ARG}"
        usage
        exit 1
    fi

    if [[ ! -x "$INSTALLER_SCRIPT" ]]; then
        err "Installer fehlt: $INSTALLER_SCRIPT"
        exit 1
    fi
    log "Installiere Timus-Stack ..."
    sudo "$INSTALLER_SCRIPT" "${installer_args[@]}"
    ok "Timus-Stack installiert"
}

setup_host() {
    local setup_args=()
    if [[ "${ARG:-}" == "--install" ]]; then
        setup_args=(--install --enable --start)
    elif [[ -n "${ARG:-}" ]]; then
        err "Unbekannte setup-host-Option: ${ARG}"
        usage
        exit 1
    fi

    if [[ ! -x "$HOST_SETUP_SCRIPT" ]]; then
        err "Host-Setup fehlt: $HOST_SETUP_SCRIPT"
        exit 1
    fi

    "$HOST_SETUP_SCRIPT" "${setup_args[@]}"
}

show_logs() {
    local target="${1:-all}"
    case "$target" in
        qdrant)
            journalctl -u "$QDRANT_SERVICE" -f
            ;;
        mcp)
            journalctl -u "$MCP_SERVICE" -f
            ;;
        dispatcher)
            journalctl -u "$DISPATCHER_SERVICE" -f
            ;;
        all)
            journalctl -u "$QDRANT_SERVICE" -u "$MCP_SERVICE" -u "$DISPATCHER_SERVICE" -f
            ;;
        *)
            err "Unbekannter log target: $target"
            usage
            exit 1
            ;;
    esac
}

COMMAND="${1:-status}"
ARG="${2:-}"

case "$COMMAND" in
    up)
        start_stack
        ;;
    down)
        stop_stack
        ;;
    restart)
        restart_stack
        ;;
    status)
        show_status
        ;;
    health)
        show_health
        ;;
    doctor)
        show_doctor "$ARG"
        ;;
    install)
        install_stack
        ;;
    setup-host)
        setup_host
        ;;
    logs)
        show_logs "$ARG"
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        err "Unbekannter Befehl: $COMMAND"
        usage
        exit 1
        ;;
esac
