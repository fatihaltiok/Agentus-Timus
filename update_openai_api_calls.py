#!/usr/bin/env python3
"""
OpenAI API Call Updater
=======================

Updates all Python files to use the new OpenAI API compatibility helper.

Changes:
1. Adds import: from utils.openai_compat import prepare_openai_params
2. Wraps all client.chat.completions.create() calls with prepare_openai_params()

Usage:
    python3 update_openai_api_calls.py --dry-run  # Preview changes
    python3 update_openai_api_calls.py            # Apply changes
"""

import os
import re
import sys
from pathlib import Path
import argparse


# Files to update (found via grep)
FILES_TO_UPDATE = [
    # Agent files
    "agent/timus_consolidated.py",
    "agent/developer_agent_v2.py",
    "agent/developer_agent.py",
    "agent/creative_agent.py",
    "agent/deep_research_agent.py",
    "agent/reasoning_agent.py",

    # Tool files
    "tools/deep_research/tool.py",
    "tools/decision_verifier/tool.py",
    "tools/report_generator/tool.py",
    "tools/summarizer/tool.py",
    "tools/memory_tool/tool.py",
    "tools/curator_tool/tool.py",
    "tools/annotator_tool/tool.py",
    "tools/creative_tool/tool.py",
    "tools/fact_corroborator/tool.py",
    "tools/visual_click_tool/tool.py",
    "tools/maintenance_tool/tool.py",
    "tools/developer_tool/tool.py",

    # Root files
    "test_apis.py",
    "check_keys.py",
    "memory/memory_system.py",
]

# Files already updated (skip these)
ALREADY_UPDATED = [
    "agent/timus_react.py",
    "agent/task_agent.py",
    "main_dispatcher.py",
]


def has_utils_import(content: str) -> bool:
    """Check if file already imports utils.openai_compat."""
    return "from utils.openai_compat import" in content


def add_utils_import(content: str) -> str:
    """Add the import statement after openai import."""
    # Find the line with "from openai import" or "import openai"
    lines = content.split('\n')

    for i, line in enumerate(lines):
        if re.match(r'^\s*from openai import', line) or re.match(r'^\s*import openai', line):
            # Insert after this line
            lines.insert(i + 1, "from utils.openai_compat import prepare_openai_params")
            return '\n'.join(lines)

    # If no openai import found, add at top after other imports
    for i, line in enumerate(lines):
        if line.strip() and not line.strip().startswith('#') and not line.strip().startswith('"""'):
            if 'import' in line:
                continue
            else:
                # Found first non-import line, insert before
                lines.insert(i, "from utils.openai_compat import prepare_openai_params")
                return '\n'.join(lines)

    return content


def wrap_api_call(match: re.Match) -> str:
    """Wrap a chat.completions.create call with prepare_openai_params."""
    indent = match.group(1)
    client = match.group(2)
    rest = match.group(3)

    # Parse the parameters
    # This is a simple approach - might need refinement for complex cases

    # Check if already wrapped
    if 'prepare_openai_params' in rest:
        return match.group(0)  # Already wrapped

    # Extract model, messages, and other params
    # Pattern: model="...", messages=[...], ...

    # Simple case: all on one line with **kwargs
    if '**kwargs' in rest or '**api_params' in rest or '**params' in rest:
        # Already using parameter dict, likely needs manual review
        return match.group(0)

    # Try to wrap simple cases
    # Pattern: create(model="...", messages=[...], temperature=..., max_tokens=...)
    if 'model=' in rest and 'messages=' in rest:
        # Wrap the parameters
        wrapped = f"{indent}{client}.chat.completions.create(**prepare_openai_params({{{rest}}})"
        return wrapped

    return match.group(0)  # Skip complex cases


def update_file(filepath: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Update a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()

        modified = original
        changes = []

        # Step 1: Add import if missing
        if not has_utils_import(modified):
            modified = add_utils_import(modified)
            changes.append("Added import: from utils.openai_compat import prepare_openai_params")

        # Step 2: Find and report all chat.completions.create calls
        # We'll do this manually for now since wrapping is complex
        pattern = r'([ \t]*)([\w.]+)\.chat\.completions\.create\('
        matches = list(re.finditer(pattern, modified))

        if matches:
            changes.append(f"Found {len(matches)} chat.completions.create() calls - needs manual wrapping")

        # Write back if changed
        if modified != original:
            if not dry_run:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(modified)
                return True, f"✅ Updated: {filepath}\n   " + "\n   ".join(changes)
            else:
                return True, f"🔍 Would update: {filepath}\n   " + "\n   ".join(changes)
        else:
            return False, f"⏭️  No changes: {filepath}"

    except Exception as e:
        return False, f"❌ Error processing {filepath}: {e}"


def main():
    parser = argparse.ArgumentParser(description="Update OpenAI API calls")
    parser.add_argument('--dry-run', action='store_true', help="Preview changes without modifying files")
    args = parser.parse_args()

    print("OpenAI API Call Updater")
    print("=" * 60)
    print(f"Mode: {'DRY RUN (preview only)' if args.dry_run else 'LIVE (will modify files)'}")
    print()

    project_root = Path(__file__).parent

    updated_count = 0
    skipped_count = 0
    error_count = 0

    # Update files
    for rel_path in FILES_TO_UPDATE:
        if rel_path in ALREADY_UPDATED:
            print(f"⏭️  Skipped (already done): {rel_path}")
            skipped_count += 1
            continue

        filepath = project_root / rel_path

        if not filepath.exists():
            print(f"⚠️  File not found: {filepath}")
            error_count += 1
            continue

        changed, message = update_file(filepath, dry_run=args.dry_run)
        print(message)

        if changed:
            updated_count += 1

    print()
    print("=" * 60)
    print(f"Summary:")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Errors:  {error_count}")

    if args.dry_run:
        print()
        print("This was a DRY RUN. Run without --dry-run to apply changes.")
    else:
        print()
        print("✅ Import statements added. Review the files and manually wrap")
        print("   chat.completions.create() calls with prepare_openai_params().")
        print()
        print("Example:")
        print("  # Before:")
        print("  resp = client.chat.completions.create(model='gpt-5', messages=[...], max_tokens=1000)")
        print()
        print("  # After:")
        print("  params = prepare_openai_params({")
        print("      'model': 'gpt-5',")
        print("      'messages': [...],")
        print("      'max_tokens': 1000")
        print("  })")
        print("  resp = client.chat.completions.create(**params)")


if __name__ == "__main__":
    main()
