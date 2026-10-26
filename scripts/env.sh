#!/usr/bin/env bash
# scripts/env.sh
#
# Self-contained PATH/environment setup for Smart QoS Manager development.
# Sourced by the dev scripts so we never modify the user's shell dotfiles.
#
# Usage:  source scripts/env.sh
#
# This script is idempotent: it only PREPENDS entries that are not already
# on PATH, so it is safe to source multiple times.
#
# Toolchain locations (all in $HOME, no sudo required):
#   - Node.js 22 LTS  -> $HOME/.local/node/bin
#   - uv (Python)     -> $HOME/.local/bin
#   - System tools (ip, tc, iw, nmcli, nft) -> /usr/sbin, /usr/bin

set -euo pipefail

# Resolve the project root from this script's location.
SQM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export SQM_ROOT

# --- PATH setup --------------------------------------------------------------
_prepend_path() {
  local dir="$1"
  case ":${PATH:-}:" in
    *":${dir}:"*) ;;            # already present
    *) PATH="${dir}:${PATH:-}" ;;
  esac
}

_prepend_path "${HOME}/.local/node/bin"   # node, npm, npx
_prepend_path "${HOME}/.local/bin"        # uv, uvx
_prepend_path "/usr/sbin"                  # ip, tc, iw, nft, ethtool
_prepend_path "/usr/bin"                   # nmcli, ss, openssl
export PATH

# --- Project layout ----------------------------------------------------------
export SQM_BACKEND_DIR="${SQM_ROOT}/backend"
export SQM_FRONTEND_DIR="${SQM_ROOT}/frontend"
export SQM_DATA_DIR="${SQM_ROOT}/data"
export SQM_LOG_DIR="${SQM_ROOT}/logs"
export SQM_CONFIG_DIR="${SQM_ROOT}/config"

# Database file (SQLite). Created on first run by the backend.
export SQM_DB_PATH="${SQM_DATA_DIR}/smartqos.db"
export SQM_DATABASE_URL="sqlite:///${SQM_DB_PATH}"

# Backend dev server.
export SQM_BACKEND_HOST="${SQM_BACKEND_HOST:-127.0.0.1}"
export SQM_BACKEND_PORT="${SQM_BACKEND_PORT:-8090}"
export SQM_BACKEND_URL="http://${SQM_BACKEND_HOST}:${SQM_BACKEND_PORT}"

# Frontend dev server (Vite).
export SQM_FRONTEND_HOST="${SQM_FRONTEND_HOST:-127.0.0.1}"
export SQM_FRONTEND_PORT="${SQM_FRONTEND_PORT:-5173}"
export SQM_FRONTEND_URL="http://${SQM_FRONTEND_HOST}:${SQM_FRONTEND_PORT}"

# By default, the dashboard is only reachable from the local machine.
# Set SQM_DASHBOARD_BIND=0.0.0.0 only when you deliberately want phone access
# from the hotspot network (Phase 6+). The app never exposes secrets in status.
export SQM_DASHBOARD_BIND="${SQM_DASHBOARD_BIND:-127.0.0.1}"

# Create runtime dirs (best effort, non-fatal).
mkdir -p "${SQM_DATA_DIR}" "${SQM_LOG_DIR}" "${SQM_CONFIG_DIR}" 2>/dev/null || true

# Sanity check: warn (do not fail) if core toolchain is missing.
_check() { command -v "$1" >/dev/null 2>&1 || echo "env.sh: WARNING: '$1' not found on PATH"; }
_check node
_check npm
_check uv
_check python3
_check nmcli
_check ip
_check tc
_check iw
_check nft
