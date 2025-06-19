import os
import platform
import psutil

def get_system_info():
    """
    Ruft allgemeine Systeminformationen ab.
    
    Rückgabe:
        dict: Ein Wörterbuch, das den Betriebssystemnamen, die Version und den Hostnamen enthält.
    """
    try:
        system_info = {
            'system': platform.system(),
            'version': platform.version(),
            'node': platform.node()
        }
        return system_info
    except Exception as e:
        print(f"Fehler beim Abrufen von Systeminformationen: {e}")
        return {}

def get_cpu_usage():
    """
    Ruft die aktuelle CPU-Auslastung des Systems ab.
    
    Rückgabe:
        float: Die CPU-Auslastung in Prozent.
    """
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        return cpu_usage
    except Exception as e:
        print(f"Fehler beim Abrufen der CPU-Auslastung: {e}")
        return None

def get_memory_usage():
    """
    Ruft die aktuelle Speicherauslastung des Systems ab.
    
    Rückgabe:
        dict: Ein Wörterbuch, das die Gesamtmenge, freie Menge und genutzte Menge des Speichers in MB enthält.
    """
    try:
        memory_info = psutil.virtual_memory()
        memory_usage = {
            'total': memory_info.total / (1024 ** 2),
            'available': memory_info.available / (1024 ** 2),
            'used': memory_info.used / (1024 ** 2)
        }
        return memory_usage
    except Exception as e:
        print(f"Fehler beim Abrufen der Speicherauslastung: {e}")
        return {}

def display_system_status():
    """
    Zeigt die aktuelle Systemstatusinformationen an.
    """
    system_info = get_system_info()
    cpu_usage = get_cpu_usage()
    memory_usage = get_memory_usage()
    
    if system_info and cpu_usage is not None and memory_usage:
        print(f"System: {system_info['system']}, Version: {system_info['version']}, Node: {system_info['node']}")
        print(f"CPU-Auslastung: {cpu_usage}%")
        print(f"Speicher: Gesamt: {memory_usage['total']:.2f} MB, Frei: {memory_usage['available']:.2f} MB, Genutzt: {memory_usage['used']:.2f} MB")
    else:
        print("Fehler beim Abrufen der Systemstatusinformationen.")

if __name__ == "__main__":
    display_system_status()
