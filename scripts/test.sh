#!/usr/bin/env bash
# scripts/test.sh — run the backend pytest suite (no sudo, isolated temp DBs).
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

if [ ! -d "$SQM_BACKEND_DIR/.venv" ]; then
  echo "ERROR: backend venv missing. Run: bash scripts/setup.sh"; exit 1
fi

echo "=== Backend tests ==="
( cd "$SQM_BACKEND_DIR" && PYTHONPATH="$SQM_BACKEND_DIR" exec uv run pytest "$@" )
