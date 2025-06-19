import logging
from typing import Dict
import psutil
from tools.system_monitor_tool import SystemMonitorTool

# Konfiguriere den Logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class SystemMonitorToolSkill:
    def __init__(self):
        self.tool = SystemMonitorTool()

    def run(self):
        logger.info("Starting System Monitor Tool Skill")
        self.tool.run()

if __name__ == "__main__":
    skill = SystemMonitorToolSkill()
    skill.run()

async def get_system_usage() -> Dict[str, float]:
    """
    Ruft die aktuelle CPU-Auslastung und die Speichernutzung in MB.
    
    Rückgabe:
        Dict[str, float]: Ein Wörterbuch mit den Schlüsseln 'cpu_usage' (in %), 'total_memory' (in MB), 'available_memory' (in MB), 'used_memory' (in MB).
    """
    try:
        # CPU-Auslastung in %
        cpu_usage = psutil.cpu_percent(interval=1)
        
        # Speichernutzung in MB
        memory_info = psutil.virtual_memory()
        total_memory = memory_info.total / (1024 * 1024)
        available_memory = memory_info.available / (1024 * 1024)
        used_memory = memory_info.used / (1024 * 1024)
        
        return {
            'cpu_usage': cpu_usage,
            'total_memory': total_memory,
            'available_memory': available_memory,
            'used_memory': used_memory
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Systemnututzung: {e}")
        raise

if __name__ == "__main__":
    import asyncio
    
    async def main():
        usage = await get_system_usage()
        print(usage)
    
    asyncio.run(main())
