#!/usr/bin/env python3
"""
Debug-Viewer für VisualNemotronAgent v4.

Zeigt gespeicherte Screenshots und GPT-4 Analysen an.
"""

import os
import sys
from pathlib import Path
from PIL import Image

DEBUG_DIR = Path("/tmp/v4_debug")


def list_debug_files():
    """Listet alle Debug-Dateien auf."""
    if not DEBUG_DIR.exists():
        print("❌ Keine Debug-Dateien gefunden.")
        print(f"   Verzeichnis {DEBUG_DIR} existiert nicht.")
        return
    
    screenshots = sorted(DEBUG_DIR.glob("screenshot_*.png"))
    analyses = sorted(DEBUG_DIR.glob("analysis_*.txt"))
    
    print(f"\n📁 Debug-Verzeichnis: {DEBUG_DIR}")
    print(f"   Screenshots: {len(screenshots)}")
    print(f"   Analysen: {len(analyses)}")
    print()
    
    if not screenshots:
        print("❌ Keine Screenshots vorhanden.")
        return
    
    print("📸 Screenshots & Analysen:")
    print("-" * 60)
    
    for i, ss in enumerate(screenshots, 1):
        ts = ss.stem.replace("screenshot_", "")
        analysis_file = DEBUG_DIR / f"analysis_{ts}.txt"
        
        print(f"\n{i}. Screenshot: {ss.name}")
        
        # Bild-Info
        try:
            with Image.open(ss) as img:
                print(f"   Größe: {img.size[0]}x{img.size[1]} Pixel")
        except:
            pass
        
        # Analyse anzeigen
        if analysis_file.exists():
            content = analysis_file.read_text()
            lines = content.split('\n')
            
            # Extrahiere Task und Analysis
            task = ""
            analysis = ""
            for line in lines:
                if line.startswith("Task:"):
                    task = line.replace("Task:", "").strip()
                elif line.startswith("GPT-4 Analysis:"):
                    analysis = '\n'.join(lines[lines.index(line)+1:])
            
            print(f"   Task: {task[:60]}{'...' if len(task) > 60 else ''}")
            print(f"   Analyse: {analysis[:100].replace(chr(10), ' ')}{'...' if len(analysis) > 100 else ''}")
        else:
            print("   ⚠️ Keine Analyse-Datei")


def view_last_screenshot():
    """Öffnet den letzten Screenshot."""
    if not DEBUG_DIR.exists():
        print("❌ Keine Debug-Dateien.")
        return
    
    screenshots = sorted(DEBUG_DIR.glob("screenshot_*.png"))
    if not screenshots:
        print("❌ Keine Screenshots.")
        return
    
    last = screenshots[-1]
    print(f"📸 Öffne: {last}")
    
    # Versuche zu öffnen
    try:
        import subprocess
        subprocess.run(["xdg-open", str(last)], check=True)
    except:
        print(f"   Bild: {last}")
        print("   (xdg-open nicht verfügbar)")


def view_last_analysis():
    """Zeigt die letzte Analyse im Detail."""
    if not DEBUG_DIR.exists():
        print("❌ Keine Debug-Dateien.")
        return
    
    analyses = sorted(DEBUG_DIR.glob("analysis_*.txt"))
    if not analyses:
        print("❌ Keine Analysen.")
        return
    
    last = analyses[-1]
    print(f"\n📝 Letzte Analyse: {last.name}")
    print("=" * 60)
    content = last.read_text()
    print(content)


def clear_debug():
    """Löscht alle Debug-Dateien."""
    if not DEBUG_DIR.exists():
        return
    
    files = list(DEBUG_DIR.glob("*"))
    for f in files:
        f.unlink()
    
    print(f"✅ {len(files)} Dateien gelöscht.")


def main():
    if len(sys.argv) < 2:
        print("""
VisualNemotronAgent v4 - Debug Viewer

Verwendung:
  python tools/v4_debug_viewer.py list      # Liste alle Screenshots/Analysen
  python tools/v4_debug_viewer.py view      # Zeige letzten Screenshot
  python tools/v4_debug_viewer.py analysis  # Zeige letzte Analyse im Detail
  python tools/v4_debug_viewer.py clear     # Lösche alle Debug-Dateien
        """)
        return
    
    cmd = sys.argv[1]
    
    if cmd == "list":
        list_debug_files()
    elif cmd == "view":
        view_last_screenshot()
    elif cmd == "analysis":
        view_last_analysis()
    elif cmd == "clear":
        clear_debug()
    else:
        print(f"❌ Unbekannter Befehl: {cmd}")


if __name__ == "__main__":
    main()
