#!/usr/bin/env python3
"""
Setup-Skript für Qwen2.5-VL Integration in Timus.

Dieses Skript:
1. Prüft System-Voraussetzungen (CUDA, VRAM)
2. Installiert benötigte Packages
3. Konfiguriert Umgebungsvariablen
4. Testet die Engine

Benutzung:
    python setup_qwen_vl.py
    
ODER mit HuggingFace Token (für Model-Download):
    HF_TOKEN=dein_token python setup_qwen_vl.py
"""

import os
import sys
import subprocess
from pathlib import Path

# Colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def print_step(step: str):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}🔧 {step}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

def print_success(msg: str):
    print(f"{GREEN}✅ {msg}{RESET}")

def print_warning(msg: str):
    print(f"{YELLOW}⚠️  {msg}{RESET}")

def print_error(msg: str):
    print(f"{RED}❌ {msg}{RESET}")

def check_python_version():
    """Prüft Python Version"""
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        print_success(f"Python {version.major}.{version.minor}.{version.micro} OK")
        return True
    else:
        print_error(f"Python 3.9+ erforderlich, du hast {version.major}.{version.minor}")
        return False

def check_cuda():
    """Prüft CUDA Verfügbarkeit"""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
            print_success(f"CUDA verfügbar: {gpu_name}")
            print_success(f"VRAM: {gpu_memory:.1f} GB")
            
            if gpu_memory < 16:
                print_warning("Empfohlen: Mindestens 16 GB VRAM für 7B Modell")
            
            return True, gpu_memory
        else:
            print_error("CUDA nicht verfügbar! GPU-Treiber prüfen.")
            return False, 0
    except ImportError:
        print_error("PyTorch nicht installiert!")
        return False, 0

def install_requirements():
    """Installiert benötigte Packages"""
    packages = [
        "transformers>=4.40.0",
        "accelerate>=0.25.0",
        "qwen-vl-utils",
        "torchvision",
    ]
    
    print_step("Installiere Packages...")
    
    for package in packages:
        print(f"📦 {package}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", package],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print_success(f"{package} installiert")
        else:
            print_error(f"Fehler bei {package}: {result.stderr}")
            return False
    
    return True

def configure_env():
    """Konfiguriert Umgebungsvariablen"""
    print_step("Konfiguration")
    
    env_file = Path(__file__).parent / ".env"
    
    # Frage Benutzer
    print("Wähle das Modell:")
    print("  1. Qwen2.5-VL-3B-Instruct (schneller, weniger VRAM)")
    print("  2. Qwen2.5-VL-7B-Instruct (bessere Qualität)")
    
    choice = input("\nAuswahl (1 oder 2) [1]: ").strip() or "1"
    
    if choice == "2":
        model = "Qwen/Qwen2.5-VL-7B-Instruct"
        print_success("7B Modell ausgewählt")
    else:
        model = "Qwen/Qwen2.5-VL-3B-Instruct"
        print_success("3B Modell ausgewählt")
    
    # Lese existierende .env
    env_vars = {}
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    env_vars[key] = value
    
    # Update Qwen-VL Variablen
    env_vars["QWEN_VL_ENABLED"] = "1"
    env_vars["QWEN_VL_MODEL"] = model
    env_vars["QWEN_VL_DEVICE"] = "auto"
    env_vars["QWEN_VL_MAX_TOKENS"] = "512"
    env_vars["QWEN_VL_SCREENSHOT_SIZE"] = "1920,1080"
    
    # HuggingFace Token (optional)
    hf_token = os.getenv("HF_TOKEN", "")
    if hf_token:
        env_vars["HF_TOKEN"] = hf_token
        print_success("HF_TOKEN gesetzt")
    else:
        print_warning("Kein HF_TOKEN gesetzt (optional, für private Modelle)")
    
    # Schreibe .env
    with open(env_file, "w") as f:
        f.write("# Qwen2.5-VL Konfiguration\n")
        f.write(f"QWEN_VL_ENABLED={env_vars['QWEN_VL_ENABLED']}\n")
        f.write(f"QWEN_VL_MODEL={env_vars['QWEN_VL_MODEL']}\n")
        f.write(f"QWEN_VL_DEVICE={env_vars['QWEN_VL_DEVICE']}\n")
        f.write(f"QWEN_VL_MAX_TOKENS={env_vars['QWEN_VL_MAX_TOKENS']}\n")
        f.write(f"QWEN_VL_SCREENSHOT_SIZE={env_vars['QWEN_VL_SCREENSHOT_SIZE']}\n")
        if hf_token:
            f.write(f"HF_TOKEN={hf_token}\n")
    
    print_success(f".env aktualisiert: {env_file}")
    return True

def test_engine():
    """Testet die Engine"""
    print_step("Teste Qwen-VL Engine...")
    
    try:
        # Füge Projekt zu Path hinzu
        project_root = Path(__file__).parent
        sys.path.insert(0, str(project_root))
        
        from tools.engines.qwen_vl_engine import qwen_vl_engine_instance
        
        print("🚀 Initialisiere Engine (erster Start lädt Modell)...")
        qwen_vl_engine_instance.initialize()
        
        if qwen_vl_engine_instance.is_initialized():
            print_success("Engine erfolgreich initialisiert!")
            
            info = qwen_vl_engine_instance.get_model_info()
            print(f"\n📊 Modell-Info:")
            print(f"   Modell: {info['model_name']}")
            print(f"   Device: {info['device']}")
            if 'gpu_name' in info:
                print(f"   GPU: {info['gpu_name']}")
                print(f"   VRAM: {info.get('vram_used_gb', 0):.1f} / {info.get('vram_total_gb', 0):.1f} GB")
            
            return True
        else:
            print_error("Engine Initialisierung fehlgeschlagen!")
            return False
            
    except Exception as e:
        print_error(f"Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Haupt-Funktion"""
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Qwen2.5-VL Setup für Timus{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    print("\nDieses Skript richtet Qwen2.5-VL für deine RTX 3090 ein.")
    
    # Schritte
    checks = [
        ("Python Version", check_python_version),
        ("CUDA / GPU", check_cuda),
        ("Packages installieren", install_requirements),
        ("Konfiguration", configure_env),
        ("Engine Test", test_engine),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            if isinstance(result, tuple):
                result = result[0]
            results.append((name, result))
        except Exception as e:
            print_error(f"{name} fehlgeschlagen: {e}")
            results.append((name, False))
    
    # Zusammenfassung
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  ZUSAMMENFASSUNG{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    
    for name, success in results:
        status = f"{GREEN}✅ OK{RESET}" if success else f"{RED}❌ FEHLER{RESET}"
        print(f"  {name:<30} {status}")
    
    all_ok = all(r[1] for r in results)
    
    if all_ok:
        print(f"\n{GREEN}{BOLD}✅ Setup erfolgreich abgeschlossen!{RESET}")
        print(f"\nNächste Schritte:")
        print(f"  1. Starte den MCP-Server: python server/mcp_server.py")
        print(f"  2. Teste das Tool: python agent/qwen_visual_agent.py --url https://google.com --task 'Suche nach KI'")
        print(f"  3. Oder nutze das MCP-Tool: qwen_web_automation")
    else:
        print(f"\n{RED}{BOLD}❌ Setup nicht vollständig. Bitte prüfe die Fehler oben.{RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
