# engine.py (IMPROVED IMPLEMENTATION)

import logging
import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import time

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s')
log = logging.getLogger("TimusEngine")

class TimusEngine:
    """
    Der zentrale Engine für das Timus-System.
    Verwaltet den Lebenszyklus von Server und Dispatcher.
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.resolve()
        self.server_process: Optional[asyncio.subprocess.Process] = None
        self.dispatcher_process: Optional[asyncio.subprocess.Process] = None
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
        # Status-Tracking
        self.status = {
            "server": {"running": False, "pid": None, "health": "unknown"},
            "dispatcher": {"running": False, "pid": None, "ready": False}
        }
        
        log.info(f"🔧 Timus Engine initialisiert (Projekt-Root: {self.project_root})")

    async def start_server(self) -> bool:
        """Startet den MCP-Server."""
        server_script = self.project_root / "server" / "mcp_server.py"
        if not server_script.exists():
            log.error(f"❌ Server-Skript nicht gefunden: {server_script}")
            return False

        try:
            log.info("🚀 Starte MCP-Server...")
            self.server_process = await asyncio.create_subprocess_exec(
                sys.executable, str(server_script),
                cwd=str(self.project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            self.status["server"]["running"] = True
            self.status["server"]["pid"] = self.server_process.pid
            log.info(f"✅ MCP-Server gestartet (PID: {self.server_process.pid})")
            
            # Warte kurz, damit der Server hochfahren kann
            await asyncio.sleep(3)
            
            # Überprüfe Server-Gesundheit
            health_ok = await self.check_server_health()
            self.status["server"]["health"] = "healthy" if health_ok else "unhealthy"
            
            return health_ok
            
        except Exception as e:
            log.error(f"❌ Fehler beim Starten des Servers: {e}", exc_info=True)
            self.status["server"]["running"] = False
            return False

    async def check_server_health(self) -> bool:
        """Überprüft die Gesundheit des MCP-Servers."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://127.0.0.1:5000/health", timeout=5.0)
                if response.status_code == 200:
                    health_data = response.json()
                    log.info(f"✅ Server-Gesundheitscheck erfolgreich: {health_data.get('status', 'unknown')}")
                    return True
                else:
                    log.warning(f"⚠️ Server antwortet mit Status {response.status_code}")
                    return False
        except Exception as e:
            log.warning(f"⚠️ Server-Gesundheitscheck fehlgeschlagen: {e}")
            return False

    async def start_dispatcher(self) -> bool:
        """Startet den Main-Dispatcher."""
        dispatcher_script = self.project_root / "main_dispatcher_fixed.py"
        if not dispatcher_script.exists():
            log.error(f"❌ Dispatcher-Skript nicht gefunden: {dispatcher_script}")
            return False

        try:
            log.info("🧠 Starte Main-Dispatcher...")
            self.dispatcher_process = await asyncio.create_subprocess_exec(
                sys.executable, str(dispatcher_script),
                cwd=str(self.project_root),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            self.status["dispatcher"]["running"] = True
            self.status["dispatcher"]["pid"] = self.dispatcher_process.pid
            log.info(f"✅ Main-Dispatcher gestartet (PID: {self.dispatcher_process.pid})")
            
            return True
            
        except Exception as e:
            log.error(f"❌ Fehler beim Starten des Dispatchers: {e}", exc_info=True)
            self.status["dispatcher"]["running"] = False
            return False

    async def start(self) -> bool:
        """Startet das gesamte Timus-System."""
        log.info("="*60)
        log.info("🚀 TIMUS ENGINE - SYSTEMSTART")
        log.info("="*60)
        
        # Schritt 1: Server starten
        if not await self.start_server():
            log.error("❌ Server-Start fehlgeschlagen. Abbruch.")
            return False
        
        # Schritt 2: Kurz warten und dann Dispatcher starten
        await asyncio.sleep(2)
        
        if not await self.start_dispatcher():
            log.error("❌ Dispatcher-Start fehlgeschlagen. Stoppe Server.")
            await self.stop()
            return False
        
        self.is_running = True
        log.info("✅ Timus-System erfolgreich gestartet!")
        return True

    async def stop(self):
        """Stoppt das gesamte Timus-System ordnungsgemäß."""
        log.info("🛑 Stoppe Timus-System...")
        
        # Dispatcher stoppen
        if self.dispatcher_process and self.dispatcher_process.returncode is None:
            log.info("🛑 Stoppe Main-Dispatcher...")
            try:
                self.dispatcher_process.terminate()
                await asyncio.wait_for(self.dispatcher_process.wait(), timeout=5.0)
                log.info("✅ Main-Dispatcher gestoppt.")
            except asyncio.TimeoutError:
                log.warning("⚠️ Dispatcher-Timeout. Erzwinge Stopp...")
                self.dispatcher_process.kill()
                await self.dispatcher_process.wait()
        
        # Server stoppen
        if self.server_process and self.server_process.returncode is None:
            log.info("🛑 Stoppe MCP-Server...")
            try:
                self.server_process.terminate()
                await asyncio.wait_for(self.server_process.wait(), timeout=5.0)
                log.info("✅ MCP-Server gestoppt.")
            except asyncio.TimeoutError:
                log.warning("⚠️ Server-Timeout. Erzwinge Stopp...")
                self.server_process.kill()
                await self.server_process.wait()
        
        self.is_running = False
        self.shutdown_event.set()
        log.info("✅ Timus-System vollständig gestoppt.")

    def get_status(self) -> Dict[str, Any]:
        """Gibt den aktuellen System-Status zurück."""
        return {
            "engine_running": self.is_running,
            "components": self.status.copy(),
            "project_root": str(self.project_root)
        }

    async def monitor_system(self):
        """Überwacht das System und reagiert auf Probleme."""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Prüfe Server
                if self.server_process and self.server_process.returncode is not None:
                    log.error("❌ MCP-Server ist unerwartet gestoppt!")
                    self.status["server"]["running"] = False
                    
                # Prüfe Dispatcher
                if self.dispatcher_process and self.dispatcher_process.returncode is not None:
                    log.error("❌ Main-Dispatcher ist unerwartet gestoppt!")
                    self.status["dispatcher"]["running"] = False
                
                # Periodischer Health-Check
                if self.status["server"]["running"]:
                    health_ok = await self.check_server_health()
                    self.status["server"]["health"] = "healthy" if health_ok else "unhealthy"
                
                await asyncio.sleep(10)  # Alle 10 Sekunden prüfen
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"❌ Fehler im System-Monitor: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def run(self):
        """Haupteinstiegspunkt für die Engine."""
        # Signal-Handler für ordnungsgemäßes Herunterfahren
        def signal_handler(signum, frame):
            log.info(f"Signal {signum} empfangen. Starte Shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # System starten
            if not await self.start():
                log.error("❌ System-Start fehlgeschlagen.")
                return False
            
            # Monitoring starten
            monitor_task = asyncio.create_task(self.monitor_system())
            
            # Warten bis Shutdown-Signal
            await self.shutdown_event.wait()
            
            # Cleanup
            monitor_task.cancel()
            await self.stop()
            
            return True
            
        except Exception as e:
            log.error(f"❌ Kritischer Fehler in der Engine: {e}", exc_info=True)
            await self.stop()
            return False

# --- Einfache Befehlszeilen-Schnittstelle ---
async def main():
    """Hauptfunktion für Kommandozeilen-Start."""
    engine = TimusEngine()
    
    try:
        success = await engine.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log.info("👋 Herunterfahren durch Benutzer angefordert.")
        await engine.stop()
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())


