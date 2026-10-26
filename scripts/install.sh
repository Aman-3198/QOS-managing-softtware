#!/usr/bin/env bash
# scripts/install.sh — reproducible install for Linux Mint 22.3 / Ubuntu 24.04.
# Safe: does NOT start a hotspot, does NOT modify network settings, does NOT
# enable the systemd units automatically. Installs deps, builds the frontend,
# and sets up the privileged helper (the helper setup needs sudo; it will prompt).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/scripts/env.sh"

echo "=== 1. System dependencies (sudo) ==="
sudo apt-get update -qq
sudo apt-get install -y -qq iproute2 iw nftables network-manager \
    python3 python3-venv curl 2>/dev/null || true
# iperf3 is only needed for the namespace shaping test (optional).
sudo apt-get install -y -qq iperf3 2>/dev/null || echo "  (iperf3 optional, skipped)"

echo "=== 2. Dev toolchain (no sudo) ==="
# env.sh already puts node + uv on PATH; setup.sh below installs deps.

echo "=== 3. Backend + frontend deps ==="
bash "$REPO/scripts/setup.sh"

echo "=== 4. Build frontend (production) ==="
( cd "$REPO/frontend" && npm run build )

echo "=== 5. Privileged helper setup (sudo; one-time) ==="
sudo bash "$REPO/privileged-helper/setup.sh"

echo
echo "=== Optional: install systemd units ==="
echo "  sudo cp packaging/smartqos-*.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now smartqos-helper.service smartqos-backend.service"
echo
echo "=== Run in dev instead ==="
echo "  bash scripts/dev-start.sh   (dashboard at http://127.0.0.1:5173)"
echo "=== Run in production (single process, serves built SPA) ==="
echo "  bash scripts/prod-start.sh  (dashboard at http://127.0.0.1:8090)"
echo
echo "Nothing was started or network-changed by this installer."
