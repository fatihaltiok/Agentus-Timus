#!/usr/bin/env python3
"""
Test-Script für Meta-Agent mit Visual Integration
"""
import asyncio
import sys
from pathlib import Path

# Pfad-Setup
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.meta_agent import run_meta_task_async
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s'
)

log = logging.getLogger("meta_test")


async def test_tool_discovery():
    """Test 1: Tool Discovery"""
    log.info("="*80)
    log.info("Test 1: Tool Discovery")
    log.info("="*80)

    from agent.meta_agent import get_available_tools

    tools = await get_available_tools()
    tool_lines = tools.splitlines()
    log.info(f"✅ Tools geladen: {len(tool_lines)} Zeilen")
    log.info(f"Preview:\n{tools[:500]}...")


async def test_visual_delegation():
    """Test 2: Visual Agent Delegation"""
    log.info("\n" + "="*80)
    log.info("Test 2: Visual Agent Delegation")
    log.info("="*80)

    task = "Liste alle verfügbaren Tools auf"

    result = await run_meta_task_async(task, max_steps=5)

    log.info("\n📋 META-AGENT ERGEBNIS:")
    log.info("="*80)
    log.info(result)
    log.info("="*80)


async def test_visual_task():
    """Test 3: Echte visuelle Aufgabe (nur wenn Server läuft)"""
    log.info("\n" + "="*80)
    log.info("Test 3: Visuelle Aufgabe (Optional)")
    log.info("="*80)

    # Einfache visuelle Aufgabe
    task = "Scanne den Bildschirm nach UI-Elementen"

    result = await run_meta_task_async(task, max_steps=3)

    log.info("\n📋 ERGEBNIS:")
    log.info(result)


async def main():
    """Haupt-Test-Routine"""
    log.info("🧪 Meta-Agent Integration Tests")
    log.info("="*80)

    try:
        # Test 1: Tool Discovery
        await test_tool_discovery()

        # Test 2: Visual Delegation
        await test_visual_delegation()

        # Test 3: Optional - Visuelle Aufgabe
        # await test_visual_task()

        log.info("\n✅ Alle Tests abgeschlossen!")

    except KeyboardInterrupt:
        log.info("\n⚠️ Tests abgebrochen")
    except Exception as e:
        log.error(f"❌ Fehler: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
