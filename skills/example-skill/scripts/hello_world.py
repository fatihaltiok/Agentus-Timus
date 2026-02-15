#!/usr/bin/env python3
"""
Beispiel-Script für den example-skill.

Demonstriert wie Skills wiederverwendbaren Code enthalten können.
"""

import sys

def main():
    """Hauptfunktion"""
    print("👋 Hello from Example Skill!")
    print("This script is bundled with the skill and can be executed.")
    
    if len(sys.argv) > 1:
        name = sys.argv[1]
        print(f"Nice to meet you, {name}!")
    else:
        print("Usage: python hello_world.py [name]")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
