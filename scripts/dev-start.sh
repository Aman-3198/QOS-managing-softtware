#!/usr/bin/env bash
# scripts/dev-start.sh — start the backend (uvicorn) + frontend (Vite) in the
# background. Logs go to logs/*.log, PIDs to logs/*.pid. No networking config
# is changed. Stop with scripts/dev-stop.sh.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

# --- Pre-flight: deps must be installed ---
if [ ! -d "$SQM_BACKEND_DIR/.venv" ]; then
  echo "ERROR: backend venv missing. Run: bash scripts/setup.sh"; exit 1
fi
if [ ! -d "$SQM_FRONTEND_DIR/node_modules" ]; then
  echo "ERROR: frontend deps missing. Run: bash scripts/setup.sh"; exit 1
fi

# --- Stop anything already running ---
bash "$SQM_ROOT/scripts/dev-stop.sh" >/dev/null 2>&1 || true

echo "Starting backend  -> $SQM_BACKEND_URL  (logs: $SQM_LOG_DIR/backend.log)"
# PYTHONPATH ensures the `app` package is importable regardless of uvicorn's
# sys.path behavior. Env vars (SQM_*) from env.sh configure the app.
(
  cd "$SQM_BACKEND_DIR"
  PYTHONPATH="$SQM_BACKEND_DIR" exec uv run uvicorn app.main:app \
    --host "$SQM_BACKEND_HOST" --port "$SQM_BACKEND_PORT" --no-access-log
) >"$SQM_LOG_DIR/backend.log" 2>&1 &
echo $! >"$SQM_LOG_DIR/backend.pid"

echo "Starting frontend -> $SQM_FRONTEND_URL  (logs: $SQM_LOG_DIR/frontend.log)"
(
  cd "$SQM_FRONTEND_DIR"
  exec npm run dev -- --host "$SQM_FRONTEND_HOST" --port "$SQM_FRONTEND_PORT"
) >"$SQM_LOG_DIR/frontend.log" 2>&1 &
echo $! >"$SQM_LOG_DIR/frontend.pid"

# --- Brief readiness check ---
sleep 2
ok=true
if curl -fsS "$SQM_BACKEND_URL/api/health" >/dev/null 2>&1; then
  echo "  backend health: OK"
else
  echo "  backend not ready yet (see $SQM_LOG_DIR/backend.log)"; ok=false
fi
if curl -fsS "$SQM_FRONTEND_URL" >/dev/null 2>&1; then
  echo "  frontend: OK"
else
  echo "  frontend not ready yet (see $SQM_LOG_DIR/frontend.log)"; ok=false
fi

echo
echo "Dashboard: $SQM_FRONTEND_URL"
echo "API docs:  $SQM_BACKEND_URL/api/docs"
echo "Stop with: bash scripts/dev-stop.sh"
$ok || exit 0
