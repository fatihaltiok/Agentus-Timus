#!/usr/bin/env bash

set -euo pipefail

QDRANT_SERVICE="qdrant.service"
MCP_SERVICE="timus-mcp.service"
DISPATCHER_SERVICE="timus-dispatcher.service"
QDRANT_READY_URL="http://127.0.0.1:6333/readyz"
MCP_HEALTH_URL="http://127.0.0.1:5000/health"

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
  ./scripts/timusctl.sh logs [qdrant|mcp|dispatcher]

Befehle:
  up         Startet qdrant -> mcp -> dispatcher
  down       Stoppt dispatcher -> mcp -> qdrant
  restart    Neustart in sicherer Reihenfolge
  status     Zeigt kompakten Service-Status
  health     Prueft qdrant, mcp und production gates
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
    systemctl --no-pager --full status "$QDRANT_SERVICE" | sed -n '1,8p' || true
    echo
    systemctl --no-pager --full status "$MCP_SERVICE" | sed -n '1,8p' || true
    echo
    systemctl --no-pager --full status "$DISPATCHER_SERVICE" | sed -n '1,8p' || true
}

start_stack() {
    check_noninteractive_sudo
    start_service "$QDRANT_SERVICE"
    wait_for_http "$QDRANT_READY_URL" "Qdrant" 20 2
    start_service "$MCP_SERVICE"
    wait_for_http "$MCP_HEALTH_URL" "MCP" 20 2
    start_service "$DISPATCHER_SERVICE"
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

    python scripts/run_production_gates.py
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
