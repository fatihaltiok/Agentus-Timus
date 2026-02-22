#!/usr/bin/env python3
"""
timus_terminal.py — Interaktiver Terminal-Client für Timus

Läuft PARALLEL zum systemd-Service (timus-dispatcher).
Startet KEINE neuen Services (kein Telegram-Bot, kein Runner, kein Monitor).
Verbindet sich einfach mit dem laufenden MCP-Server auf Port 5000.

Verwendung:
    python timus_terminal.py
    # oder direkt ausführbar nach: chmod +x timus_terminal.py
    ./timus_terminal.py
"""

import asyncio
import logging
import os
import re
import sys
import textwrap
import uuid
from pathlib import Path

# Projektpfad
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env", override=True)

logging.basicConfig(
    level=logging.WARNING,  # Nur Warnungen/Fehler — kein Info-Spam im Terminal
    format="%(levelname)-7s | %(name)s | %(message)s",
)

from main_dispatcher import (
    fetch_tool_descriptions_from_server,
    run_agent,
    get_agent_decision,
    _sanitize_user_query,
)


def _print_tasks() -> None:
    """Zeigt alle Tasks aus der SQLite-Queue an."""
    try:
        from orchestration.task_queue import get_queue
        tasks = get_queue().get_all(limit=20)
        if not tasks:
            print("   Keine Tasks vorhanden.")
            return
        stats = get_queue().stats()
        print(f"\n   Queue: {stats}")
        print(f"\n   {'ID':8} {'Prio':8} {'Status':12} {'Agent':14} Beschreibung")
        print("   " + "─" * 72)
        prio_names = {0: "CRITICAL", 1: "HIGH", 2: "NORMAL", 3: "LOW"}
        icons = {"pending": "⏳", "in_progress": "🔄", "completed": "✅",
                 "failed": "❌", "cancelled": "🚫"}
        for t in tasks:
            tid    = t.get("id", "?")[:8]
            status = t.get("status", "?")
            prio   = prio_names.get(t.get("priority", 2), "?")
            agent  = (t.get("target_agent") or "auto")[:12]
            desc   = t.get("description", "")[:42]
            icon   = icons.get(status, "•")
            print(f"   {tid:8} {prio:8} {icon} {status:10} {agent:14} {desc}")
    except Exception as e:
        print(f"   Fehler beim Lesen: {e}")


async def cli_loop(tools_desc: str) -> None:
    """Interaktive Terminal-Schleife."""
    session_id = f"term_{uuid.uuid4().hex[:8]}"

    print("\n" + "═" * 62)
    print("🖥️  TIMUS TERMINAL-CLIENT")
    print("═" * 62)
    print(f"   Session : {session_id}")
    print(f"   MCP     : Port 5000 (laufender Service)")
    print()
    print("   Beispiele:")
    print("   • 'asyncio vs threading?'   → REASONING")
    print("   • 'Recherchiere KI-Trends'  → RESEARCH")
    print("   • 'Öffne Firefox'           → VISUAL")
    print("   • 'Wie spät ist es?'        → EXECUTOR")
    print("   • '/tasks'                  → Queue anzeigen")
    print("   • '/new'                    → neue Session")
    print("   • 'exit'                    → beenden")
    print("─" * 62 + "\n")

    while True:
        try:
            q = await asyncio.to_thread(input, "\033[32mDu> \033[0m")
            q_clean = _sanitize_user_query(q)
            if not q_clean:
                continue

            if q_clean.lower() in {"exit", "quit", "q", "beenden"}:
                print("👋 Tschüss!")
                break

            if q_clean.lower() in {"/new", "new session", "neue session", "reset session"}:
                session_id = f"term_{uuid.uuid4().hex[:8]}"
                print(f"   ♻️  Neue Session: {session_id}")
                continue

            if q_clean.lower() in {"/tasks", "tasks"}:
                _print_tasks()
                continue

            print("   🤔 Timus denkt...")
            agent = await get_agent_decision(q_clean)
            print(f"   📌 Agent: {agent.upper()}")

            result = await run_agent(
                agent_name=agent,
                query=q_clean,
                tools_description=tools_desc,
                session_id=session_id,
            )

            if result:
                print()

        except (KeyboardInterrupt, EOFError):
            print("\n👋 Tschüss!")
            break
        except Exception as e:
            print(f"   ❌ Fehler: {e}")


async def main() -> None:
    print("⏳ Verbinde mit MCP-Server (Port 5000)...")
    tools_desc = await fetch_tool_descriptions_from_server(max_wait=30)
    if not tools_desc:
        print("❌ MCP-Server nicht erreichbar.")
        print("   Läuft timus-mcp.service?  →  sudo systemctl status timus-mcp")
        sys.exit(1)
    print("✅ MCP-Server verbunden.\n")
    await cli_loop(tools_desc)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
