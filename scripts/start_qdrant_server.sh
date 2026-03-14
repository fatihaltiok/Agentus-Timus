#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/fatih-ubuntu/dev/timus"
TIMUS_PYTHON="/home/fatih-ubuntu/miniconda3/envs/timus/bin/python"
DEFAULT_STORAGE="/media/fatih-ubuntu/WD6000/timus/qdrant_server/storage"
DEFAULT_SNAPSHOTS="/media/fatih-ubuntu/WD6000/timus/qdrant_server/snapshots"

if [[ -x "${TIMUS_PYTHON}" && -f "${PROJECT_ROOT}/.env" ]]; then
  while IFS='=' read -r key value; do
    [[ -z "${key}" ]] && continue
    export "${key}=${value}"
  done < <(
    "${TIMUS_PYTHON}" - <<'PY'
from dotenv import dotenv_values
from pathlib import Path

env_path = Path("/home/fatih-ubuntu/dev/timus/.env")
values = dotenv_values(env_path)
for key in (
    "QDRANT_API_KEY",
    "QDRANT_BIN",
    "QDRANT_SERVER_HOST",
    "QDRANT_SERVER_HTTP_PORT",
    "QDRANT_SERVER_GRPC_PORT",
    "QDRANT_SERVER_STORAGE_PATH",
    "QDRANT_SERVER_SNAPSHOTS_PATH",
):
    value = values.get(key)
    if value:
        print(f"{key}={value}")
PY
  )
fi

export QDRANT__SERVICE__HOST="${QDRANT_SERVER_HOST:-127.0.0.1}"
export QDRANT__SERVICE__HTTP_PORT="${QDRANT_SERVER_HTTP_PORT:-6333}"
export QDRANT__SERVICE__GRPC_PORT="${QDRANT_SERVER_GRPC_PORT:-6334}"
export QDRANT__STORAGE__STORAGE_PATH="${QDRANT_SERVER_STORAGE_PATH:-$DEFAULT_STORAGE}"
export QDRANT__STORAGE__SNAPSHOTS_PATH="${QDRANT_SERVER_SNAPSHOTS_PATH:-$DEFAULT_SNAPSHOTS}"

if [[ -n "${QDRANT_API_KEY:-}" ]]; then
  export QDRANT__SERVICE__API_KEY="${QDRANT_API_KEY}"
fi

mkdir -p "${QDRANT__STORAGE__STORAGE_PATH}" "${QDRANT__STORAGE__SNAPSHOTS_PATH}"

QDRANT_BIN="${QDRANT_BIN:-}"
if [[ -z "${QDRANT_BIN}" ]]; then
  if command -v qdrant >/dev/null 2>&1; then
    QDRANT_BIN="$(command -v qdrant)"
  elif [[ -x "/usr/local/bin/qdrant" ]]; then
    QDRANT_BIN="/usr/local/bin/qdrant"
  elif [[ -x "/usr/bin/qdrant" ]]; then
    QDRANT_BIN="/usr/bin/qdrant"
  else
    echo "qdrant binary not found; install Qdrant server or set QDRANT_BIN" >&2
    exit 1
  fi
fi

exec "${QDRANT_BIN}"
