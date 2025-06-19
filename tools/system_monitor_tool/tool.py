import logging
import psutil

class SystemMonitorTool:
    def get_system_usage(self):
        try:
            # Get CPU usage percentage
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # Get memory usage details
            memory_info = psutil.virtual_memory()
            memory_usage = memory_info.percent
            
            # Get disk usage details
            disk_info = psutil.disk_usage('/')
            disk_usage = disk_info.percent
            
            return {
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'disk_usage': disk_usage
            }
        except Exception as e:
            print(f"An error occurred: {e}")
            return None
        logging.info("System Monitor Tool is running")
