import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.getcwd())

# Setup basic logging
logging.basicConfig(level=logging.INFO)

print("--- Verifying Tool Imports ---")

try:
    print("Importing tools.ocr_tool.tool...")
    import tools.ocr_tool.tool
    print("✅ tools.ocr_tool.tool imported successfully.")
except Exception as e:
    print(f"❌ Failed to import tools.ocr_tool.tool: {e}")

try:
    print("Importing tools.text_finder_tool.tool...")
    import tools.text_finder_tool.tool
    print("✅ tools.text_finder_tool.tool imported successfully.")
except Exception as e:
    print(f"❌ Failed to import tools.text_finder_tool.tool: {e}")

print("--- Verification Complete ---")
