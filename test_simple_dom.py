#!/usr/bin/env python3
"""
Simple Direct Test - DOM Methods without MCP
"""

import asyncio
import logging

# Direct imports
from tools.browser_tool.tool import open_url, get_page_content, type_text, click_by_selector
from tools.browser_controller.dom_parser import DOMParser

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def main():
    log.info("🚀 Simple DOM Test - Direct Function Calls")

    # Step 1: Open Google
    log.info("\n=== STEP 1: Open Google ===")
    open_result = await open_url("https://www.google.com")
    # Result is Right(SuccessResult({data})) - extract via _value.result
    open_data = open_result._value.result if hasattr(open_result, '_value') else open_result
    if isinstance(open_data, dict) and 'url' in open_data:
        log.info(f"✅ Opened: {open_data.get('url')}")
    else:
        log.error(f"❌ Open failed: {open_result}")
        return

    await asyncio.sleep(2)

    # Step 2: Get Page Content
    log.info("\n=== STEP 2: Get Page Content ===")
    content_result = await get_page_content()
    content_data = content_result._value.result if hasattr(content_result, '_value') else content_result
    if isinstance(content_data, dict) and 'html' in content_data:
        html = content_data.get('html', '')
        log.info(f"✅ HTML: {len(html)} characters")

        # Step 3: Parse DOM
        log.info("\n=== STEP 3: Parse DOM ===")
        parser = DOMParser()
        parser.parse(html)
        log.info(f"✅ Found {len(parser.elements)} interactive elements")

        # Find search field
        search_fields = [el for el in parser.elements if el.tag == 'textarea' and el.role == 'combobox']
        if search_fields:
            search_field = search_fields[0]
            log.info(f"✅ Search field: {search_field.selector}")

            # Step 4: Type text
            log.info("\n=== STEP 4: Type Text ===")
            query = "Anthropic Claude AI"
            type_result = await type_text(search_field.selector, query)
            type_data = type_result._value.result if hasattr(type_result, '_value') else type_result
            if isinstance(type_data, dict) and 'status' in type_data:
                log.info(f"✅ Typed: '{query}'")
                log.info(f"   Status: {type_data.get('status')}")
                log.info(f"   Message: {type_data.get('message')}")
            else:
                log.error(f"❌ Type failed: {type_result}")
        else:
            log.error("❌ Search field not found")
    else:
        log.error(f"❌ Get content failed: {content_result}")

    log.info("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
