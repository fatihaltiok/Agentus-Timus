#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/fatihaltiok/Agentus-Timus.git"
DIR="Agentus-Timus"

echo "==> Timus installer"

# Prerequisites
for cmd in git docker curl; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: '$cmd' is required but not installed." >&2
    exit 1
  fi
done

if ! docker compose version &>/dev/null && ! docker-compose version &>/dev/null; then
  echo "Error: 'docker compose' (v2) or 'docker-compose' is required." >&2
  exit 1
fi

# Clone or update
if [ -d "$DIR/.git" ]; then
  echo "==> Updating existing clone in $DIR"
  git -C "$DIR" pull --ff-only
else
  echo "==> Cloning $REPO"
  git clone "$REPO" "$DIR"
fi

cd "$DIR"

# .env setup
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "==> .env created from .env.example"
  echo "    Fill in your API keys before starting:"
  echo "    $PWD/.env"
  echo ""
fi

# Start
echo "==> Starting Qdrant + Timus via Docker Compose"
docker compose up -d --build

echo ""
echo "==> Done. Waiting for health check..."
sleep 8

STATUS=$(curl -sf http://127.0.0.1:5000/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "starting")
echo "    Health: $STATUS"
echo ""
echo "    MCP API : http://127.0.0.1:5000"
echo "    Health  : http://127.0.0.1:5000/health"
echo ""
echo "    To follow logs : docker compose logs -f timus"
echo "    To stop        : docker compose down"
