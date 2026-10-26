#!/usr/bin/env bash
# scripts/setup.sh — one-time dev environment setup (no sudo).
# Creates the Python venv (via uv) and installs frontend deps (via npm).
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

echo "=== Toolchain check ==="
command -v node >/dev/null || { echo "ERROR: node not on PATH. Source scripts/env.sh first or install Node 22 LTS to ~/.local/node."; exit 1; }
command -v npm  >/dev/null || { echo "ERROR: npm not on PATH."; exit 1; }
command -v uv   >/dev/null || { echo "ERROR: uv not on PATH. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
echo "node $(node --version)  npm $(npm --version)  uv $(uv --version)"

echo "=== Backend: uv sync (creates .venv + uv.lock) ==="
( cd "$SQM_BACKEND_DIR" && uv sync )

echo "=== Frontend: npm install ==="
if [ -f "$SQM_FRONTEND_DIR/package.json" ]; then
  ( cd "$SQM_FRONTEND_DIR" && npm install )
else
  echo "  frontend/package.json not found; skipping frontend."
fi

echo
echo "Setup complete. Start the dev environment with:"
echo "  bash scripts/dev-start.sh"
