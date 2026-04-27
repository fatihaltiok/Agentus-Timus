#!/usr/bin/env bash
set -euo pipefail

tracked_pyc="$(git ls-files '*.pyc')"
tracked_pycache="$(git ls-files | grep -E '(^|/)__pycache__/' || true)"

if [[ -n "$tracked_pyc" || -n "$tracked_pycache" ]]; then
  echo "Tracked Python cache artifacts found:" >&2
  if [[ -n "$tracked_pyc" ]]; then
    printf '%s\n' "$tracked_pyc" >&2
  fi
  if [[ -n "$tracked_pycache" ]]; then
    printf '%s\n' "$tracked_pycache" >&2
  fi
  exit 1
fi

echo "No tracked Python cache artifacts."
