#!/usr/bin/env bash
# Double-click this file or run: bash restart-helper.sh
# Kills the old helper and starts the new one. Needs your sudo password once.
set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Stopping old helper..."
sudo pkill -f "privileged-helper/helper.py" 2>/dev/null || true
sleep 1
echo "Removing old pycache..."
sudo rm -rf "$REPO/privileged-helper/__pycache__"
echo "Starting new helper..."
sudo python3 -B "$REPO/privileged-helper/helper.py" --user aman &
HELPER_PID=$!
echo "Waiting for socket..."
for i in $(seq 1 20); do
  sleep 1
  if [ -S /run/smartqos/helper.sock ]; then
    echo "Helper is up! (PID $HELPER_PID)"
    echo "You can close this terminal."
    exit 0
  fi
done
echo "ERROR: Helper did not start. Check /var/log/smartqos/helper.out"
exit 1
