#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/restart_timus.sh
#
# Timus Neustart — MCP-Server + Dispatcher
#
# Nutzung:
#   ./scripts/restart_timus.sh            # Vollständiger Neustart
#   ./scripts/restart_timus.sh mcp        # Nur MCP-Server
#   ./scripts/restart_timus.sh dispatcher # Nur Dispatcher
#   ./scripts/restart_timus.sh status     # Nur Status anzeigen
#
# Voraussetzung für autonomen Restart (ohne Passwort):
#   sudo cp scripts/sudoers_timus /etc/sudoers.d/timus-restart
#   sudo chmod 440 /etc/sudoers.d/timus-restart
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

MCP_SERVICE="timus-mcp.service"
DISPATCHER_SERVICE="timus-dispatcher.service"
MCP_HEALTH_URL="http://127.0.0.1:5000/health"
MODE="${1:-full}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[TIMUS]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[FEHLER]${NC} $*"; }

check_health() {
    local retries=8
    local wait=3
    log "Warte auf MCP Health-Check (max ${retries}x ${wait}s)..."
    for i in $(seq 1 $retries); do
        if curl -sf "$MCP_HEALTH_URL" >/dev/null 2>&1; then
            ok "MCP-Server antwortet nach ${i}x ${wait}s"
            return 0
        fi
        echo -n "  Versuch $i/$retries..."
        sleep $wait
    done
    err "MCP-Server antwortet nicht nach $((retries * wait))s"
    return 1
}

check_noninteractive_sudo() {
    if ! sudo -n /usr/bin/systemctl status "$MCP_SERVICE" >/dev/null 2>&1; then
        err "Passwortloses sudo fuer $MCP_SERVICE nicht verfuegbar. Installiere scripts/sudoers_timus."
        exit 1
    fi
    if ! sudo -n /usr/bin/systemctl status "$DISPATCHER_SERVICE" >/dev/null 2>&1; then
        err "Passwortloses sudo fuer $DISPATCHER_SERVICE nicht verfuegbar. Installiere scripts/sudoers_timus."
        exit 1
    fi
}

show_status() {
    echo ""
    log "=== Service-Status ==="
    systemctl status "$MCP_SERVICE" --no-pager -l 2>&1 | head -12 || true
    echo ""
    systemctl status "$DISPATCHER_SERVICE" --no-pager -l 2>&1 | head -12 || true
    echo ""
    log "=== Letzte Logs (MCP) ==="
    journalctl -u "$MCP_SERVICE" -n 20 --no-pager 2>&1 | tail -20 || true
}

restart_mcp() {
    log "Stoppe $MCP_SERVICE..."
    sudo -n systemctl stop "$MCP_SERVICE" 2>/dev/null || true
    sleep 1
    log "Starte $MCP_SERVICE..."
    sudo -n systemctl start "$MCP_SERVICE"
    check_health && ok "MCP-Server läuft" || { err "MCP-Start fehlgeschlagen"; show_status; exit 1; }
}

restart_dispatcher() {
    log "Stoppe $DISPATCHER_SERVICE..."
    sudo -n systemctl stop "$DISPATCHER_SERVICE" 2>/dev/null || true
    sleep 1
    log "Starte $DISPATCHER_SERVICE..."
    sudo -n systemctl start "$DISPATCHER_SERVICE"
    sleep 3
    if systemctl is-active --quiet "$DISPATCHER_SERVICE"; then
        ok "Dispatcher läuft"
    else
        err "Dispatcher-Start fehlgeschlagen"
        journalctl -u "$DISPATCHER_SERVICE" -n 30 --no-pager 2>&1 | tail -30
        exit 1
    fi
}

echo ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "  Timus Neustart  (Modus: $MODE)"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

check_noninteractive_sudo

case "$MODE" in
    full)
        log "Stoppe Dispatcher zuerst (hängt von MCP ab)..."
        sudo -n systemctl stop "$DISPATCHER_SERVICE" 2>/dev/null || true
        sleep 1
        restart_mcp
        restart_dispatcher
        ok "━━━ Timus vollständig neugestartet ━━━"
        ;;
    mcp)
        restart_mcp
        warn "Dispatcher wurde NICHT neugestartet — ggf. manuell: $0 dispatcher"
        ;;
    dispatcher)
        restart_dispatcher
        ;;
    status)
        show_status
        ;;
    *)
        err "Unbekannter Modus: $MODE"
        echo "Nutzung: $0 [full|mcp|dispatcher|status]"
        exit 1
        ;;
esac

show_status
