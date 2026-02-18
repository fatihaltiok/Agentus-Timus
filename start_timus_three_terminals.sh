#!/usr/bin/env bash
set -euo pipefail

# Starts three separate terminals for:
# 1) MCP server
# 2) main_dispatcher
# 3) timus_hybrid_v2
#
# Optional environment variables:
# - PYTHON_BIN: python executable (default: python)
# - TIMUS_ACTIVATE_CMD: custom activation command (overrides auto-conda activation)
# - TIMUS_CONDA_ENV: conda env name for auto activation (default: timus)
# - MCP_URL: health check endpoint base (default: http://127.0.0.1:5000)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python}"
MCP_URL="${MCP_URL:-http://127.0.0.1:5000}"
TIMUS_ACTIVATE_CMD="${TIMUS_ACTIVATE_CMD:-}"
TIMUS_CONDA_ENV="${TIMUS_CONDA_ENV:-timus}"

if [[ ! -f "$REPO_ROOT/main_dispatcher.py" || ! -f "$REPO_ROOT/timus_hybrid_v2.py" ]]; then
  echo "ERROR: Script must be run from the Timus repository root."
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: Python binary not found: $PYTHON_BIN"
  exit 1
fi

# Auto-activate conda env (default: timus), unless custom activation command is provided.
if [[ -z "$TIMUS_ACTIVATE_CMD" ]]; then
  CONDA_SH=""
  if command -v conda >/dev/null 2>&1; then
    CONDA_BASE="$(conda info --base 2>/dev/null || true)"
    if [[ -n "${CONDA_BASE:-}" && -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
      CONDA_SH="$CONDA_BASE/etc/profile.d/conda.sh"
    fi
  fi

  if [[ -z "$CONDA_SH" && -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    CONDA_SH="$HOME/miniconda3/etc/profile.d/conda.sh"
  fi

  if [[ -z "$CONDA_SH" && -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
    CONDA_SH="$HOME/anaconda3/etc/profile.d/conda.sh"
  fi

  if [[ -z "$CONDA_SH" ]]; then
    echo "ERROR: Could not find conda activation script (conda.sh)."
    echo "Set TIMUS_ACTIVATE_CMD manually, e.g.:"
    echo "  TIMUS_ACTIVATE_CMD='source ~/miniconda3/etc/profile.d/conda.sh && conda activate $TIMUS_CONDA_ENV'"
    exit 1
  fi

  TIMUS_ACTIVATE_CMD="source $CONDA_SH && conda activate $TIMUS_CONDA_ENV"
fi

WAIT_MCP_CMD='for i in $(seq 1 60); do curl -fsS "'"$MCP_URL"'/health" >/dev/null 2>&1 && break; echo "[wait] MCP not ready yet... ($i/60)"; sleep 1; done'

build_full_cmd() {
  local run_cmd="$1"
  if [[ -n "$TIMUS_ACTIVATE_CMD" ]]; then
    printf '%s; cd "%s"; %s' "$TIMUS_ACTIVATE_CMD" "$REPO_ROOT" "$run_cmd"
  else
    printf 'cd "%s"; %s' "$REPO_ROOT" "$run_cmd"
  fi
}

open_in_terminal() {
  local title="$1"
  local cmd="$2"

  local full_cmd
  full_cmd="$(build_full_cmd "$cmd")"

  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title="$title" -- bash -lc "$full_cmd; exec bash" &
    return 0
  fi

  if command -v konsole >/dev/null 2>&1; then
    konsole --new-tab -p tabtitle="$title" -e bash -lc "$full_cmd; exec bash" &
    return 0
  fi

  if command -v xfce4-terminal >/dev/null 2>&1; then
    xfce4-terminal --title="$title" --command="bash -lc '$full_cmd; exec bash'" &
    return 0
  fi

  if command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -T "$title" -e bash -lc "$full_cmd; exec bash" &
    return 0
  fi

  if command -v xterm >/dev/null 2>&1; then
    xterm -T "$title" -e bash -lc "$full_cmd; exec bash" &
    return 0
  fi

  echo "ERROR: No supported terminal emulator found."
  echo "Install one of: gnome-terminal, konsole, xfce4-terminal, xterm"
  return 1
}

echo "Starting Timus in 3 terminals..."
echo "Repo: $REPO_ROOT"
echo "Python: $PYTHON_BIN"
echo "Conda env: $TIMUS_CONDA_ENV"
echo "Env activation: configured"

open_in_terminal "Timus MCP Server" "$PYTHON_BIN server/mcp_server.py"
sleep 0.5
open_in_terminal "Timus Main Dispatcher" "$WAIT_MCP_CMD; $PYTHON_BIN main_dispatcher.py"
sleep 0.5
open_in_terminal "Timus Hybrid v2" "$WAIT_MCP_CMD; $PYTHON_BIN timus_hybrid_v2.py"

echo "Done. Three terminal windows/tabs were launched."
