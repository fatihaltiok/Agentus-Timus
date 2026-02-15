#!/bin/bash
#
# Qwen-VL MCP Server Starter
# Startet den Server im Hintergrund mit screen oder direkt
#

PROJECT_DIR="/home/fatih-ubuntu/dev/timus"
LOG_FILE="$PROJECT_DIR/timus_server.log"
PID_FILE="$PROJECT_DIR/timus_server.pid"

# Farben
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

show_help() {
    echo "Qwen-VL MCP Server Starter"
    echo ""
    echo "Verwendung: $0 [OPTION]"
    echo ""
    echo "Optionen:"
    echo "  start       Server im Hintergrund starten (screen)"
    echo "  start-fg    Server im Vordergrund starten"
    echo "  stop        Server stoppen"
    echo "  restart     Server neu starten"
    echo "  status      Status prüfen"
    echo "  logs        Logs anzeigen (tail -f)"
    echo "  cache       HuggingFace Cache-Info anzeigen"
    echo "  help        Diese Hilfe"
    echo ""
    echo "Beispiele:"
    echo "  $0 start      # Startet im Hintergrund"
    echo "  $0 logs       # Zeigt Live-Logs"
    echo "  $0 status     # Prüft ob Server läuft"
}

start_server() {
    # Prüfe ob bereits läuft
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo -e "${YELLOW}Server läuft bereits (PID: $(cat $PID_FILE))${NC}"
        echo "Nutze: $0 logs    für Logs"
        echo "Nutze: $0 stop    zum Beenden"
        return 1
    fi
    
    cd "$PROJECT_DIR"
    
    # Lade .env
    if [ -f ".env" ]; then
        export $(grep -v '^#' .env | xargs)
    fi
    
    echo -e "${GREEN}🚀 Starte MCP Server mit Qwen-VL...${NC}"
    echo "   Modell: $QWEN_VL_MODEL"
    echo "   Log: $LOG_FILE"
    
    # Starte mit screen (ermöglicht Reconnect mit: screen -r timus)
    if command -v screen &> /dev/null; then
        screen -dmS timus bash -c "cd $PROJECT_DIR && python server/mcp_server.py > $LOG_FILE 2>&1; echo \$! > $PID_FILE"
        echo -e "${GREEN}✅ Server gestartet in screen session 'timus'${NC}"
        echo "   Verbinden: screen -r timus"
        echo "   Trennen:  Ctrl+A, dann D"
    else
        # Fallback: Direkt im Hintergrund
        nohup python server/mcp_server.py > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo -e "${GREEN}✅ Server gestartet (PID: $!)${NC}"
    fi
    
    echo ""
    echo -e "${YELLOW}⏳ Warte auf Modell-Ladung... (30-60 Sekunden)${NC}"
    sleep 5
    
    # Zeige Initialisierungs-Status
    if grep -q "Qwen-VL Engine erfolgreich initialisiert" "$LOG_FILE" 2>/dev/null; then
        echo -e "${GREEN}✅ Qwen-VL Engine bereit!${NC}"
    else
        echo -e "${YELLOW}⏳ Modell wird noch geladen...${NC}"
        echo "   Nutze: $0 logs    zum Beobachten"
    fi
}

start_foreground() {
    cd "$PROJECT_DIR"
    
    if [ -f ".env" ]; then
        export $(grep -v '^#' .env | xargs)
    fi
    
    echo -e "${GREEN}🚀 Starte MCP Server im Vordergrund...${NC}"
    echo "   Modell: $QWEN_VL_MODEL"
    echo "   Ctrl+C zum Beenden"
    echo ""
    
    python server/mcp_server.py
}

stop_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "${YELLOW}🛑 Stoppe Server (PID: $PID)...${NC}"
            kill "$PID"
            rm -f "$PID_FILE"
            
            # Stoppe auch screen session falls vorhanden
            screen -S timus -X quit 2>/dev/null
            
            echo -e "${GREEN}✅ Server gestoppt${NC}"
        else
            echo -e "${RED}Server nicht aktiv (veraltete PID-Datei)${NC}"
            rm -f "$PID_FILE"
        fi
    else
        echo -e "${RED}Keine PID-Datei gefunden${NC}"
        
        # Versuche screen session zu stoppen
        if screen -list | grep -q "timus"; then
            screen -S timus -X quit
            echo -e "${GREEN}✅ Screen session 'timus' gestoppt${NC}"
        fi
    fi
}

show_status() {
    echo -e "${GREEN}=== Timus MCP Server Status ===${NC}"
    echo ""
    
    # Prüfe Prozess
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "Status: ${GREEN}LÄUFT${NC} (PID: $PID)"
        else
            echo -e "Status: ${RED}NICHT LÄUFT${NC} (veraltete PID)"
        fi
    else
        echo -e "Status: ${RED}NICHT LÄUFT${NC}"
    fi
    
    # Prüfe screen
    if screen -list | grep -q "timus"; then
        echo -e "Screen: ${GREEN}AKTIV${NC} (screen -r timus)"
    else
        echo -e "Screen: ${RED}INAKTIV${NC}"
    fi
    
    # Qwen-VL Status aus Logs
    if [ -f "$LOG_FILE" ]; then
        if grep -q "Qwen-VL Engine erfolgreich initialisiert" "$LOG_FILE"; then
            echo -e "Qwen-VL: ${GREEN}INITIALISIERT${NC}"
        elif grep -q "Lade Qwen2.5-VL Modell" "$LOG_FILE"; then
            echo -e "Qwen-VL: ${YELLOW}LÄDT...${NC}"
        else
            echo -e "Qwen-VL: ${RED}NICHT GELADEN${NC}"
        fi
        
        # Zeige letzte Zeilen
        echo ""
        echo -e "${GREEN}Letzte Log-Einträge:${NC}"
        tail -3 "$LOG_FILE"
    fi
}

show_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo -e "${GREEN}=== Server Logs (Ctrl+C zum Beenden) ===${NC}"
        tail -f "$LOG_FILE"
    else
        echo -e "${RED}Log-Datei nicht gefunden: $LOG_FILE${NC}"
    fi
}

show_cache() {
    CACHE_DIR="$HOME/.cache/huggingface/hub"
    
    echo -e "${GREEN}=== HuggingFace Cache ===${NC}"
    echo "Cache-Verzeichnis: $CACHE_DIR"
    echo ""
    
    if [ -d "$CACHE_DIR" ]; then
        echo "Gecachte Modelle:"
        ls -lh "$CACHE_DIR" | grep "models--" | awk '{printf "  %-40s %s\n", $9, $5}'
        
        echo ""
        echo "Qwen-Modelle:"
        du -sh "$CACHE_DIR"/models--Qwen--Qwen2* 2>/dev/null || echo "  Keine Qwen-Modelle gefunden"
        
        echo ""
        echo -e "${YELLOW}Gesamt-Cache-Größe:${NC}"
        du -sh "$CACHE_DIR" 2>/dev/null || echo "  Unbekannt"
        
        echo ""
        echo "Cache wird automatisch verwendet - kein erneuter Download nötig!"
    else
        echo -e "${RED}Cache-Verzeichnis nicht gefunden${NC}"
    fi
}

# Haupt-Logik
case "${1:-help}" in
    start)
        start_server
        ;;
    start-fg)
        start_foreground
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        sleep 2
        start_server
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    cache)
        show_cache
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unbekannte Option: $1${NC}"
        show_help
        exit 1
        ;;
esac
