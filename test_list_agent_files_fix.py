#!/usr/bin/env python3
"""Test-Script für list_agent_files Parameter-Fix."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agent.developer_agent_v2 import run_developer_task

print("🧪 Testing list_agent_files Parameter-Fix")
print("=" * 60)
print()
print("Test: Einfache Funktion erstellen")
print("Erwartung: Keine 'Invalid params' Fehler mehr")
print()
print("-" * 60)

# Simple task to trigger list_agent_files
result = run_developer_task(
    "Erstelle eine Funktion square(n) die eine Zahl quadriert",
    dest_folder="test_project",
    max_steps=10
)

print()
print("=" * 60)
print("📊 ERGEBNIS:")
print("=" * 60)
print(result)
print()

# Check if file was created
output_file = Path("test_project/square.py")
if output_file.exists():
    print("✅ Datei wurde erstellt:", output_file)
    print()
    print("Inhalt:")
    print("-" * 60)
    print(output_file.read_text())
else:
    print("⚠️ Datei wurde nicht erstellt")
