#!/usr/bin/env bash
# scripts/prod-start.sh — run the backend serving the built SPA (no Vite).
# Requires: frontend/dist (run `npm run build` in frontend/ first) + the helper
# running for privileged features.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

[ -d "$SQM_FRONTEND_DIR/dist" ] || { echo "Build the frontend first: (cd frontend && npm run build)"; exit 1; }
[ -d "$SQM_BACKEND_DIR/.venv" ] || { echo "Run scripts/setup.sh first"; exit 1; }

echo "Serving dashboard at http://${SQM_BACKEND_HOST}:${SQM_BACKEND_PORT} (Ctrl-C to stop)"
( cd "$SQM_BACKEND_DIR" && PYTHONPATH="$SQM_BACKEND_DIR" exec uv run uvicorn app.main:app \
    --host "$SQM_BACKEND_HOST" --port "$SQM_BACKEND_PORT" )
