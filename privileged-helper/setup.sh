#!/usr/bin/env bash
# privileged-helper/setup.sh — one-time setup of the privileged helper (run with sudo).
# Creates the socket dir, the shared auth token, and the log dir. Non-destructive
# (does not start the helper, does not touch networking).
#
#   sudo bash privileged-helper/setup.sh
set -euo pipefail

DASH_USER="${SUDO_USER:-$USER}"
RUN_DIR="/run/smartqos"
ETC_DIR="/etc/smartqos"
LOG_DIR="/var/log/smartqos"
TOKEN="$ETC_DIR/helper.token"

echo "Dashboard user (for socket/token group access): $DASH_USER"

install -d -m 0770 -o root -g "$DASH_USER" "$RUN_DIR"
install -d -m 0755 -o root -g root "$ETC_DIR"
install -d -m 0755 -o root -g root "$LOG_DIR"

if [ ! -f "$TOKEN" ]; then
  umask 077
  openssl rand -hex 32 > "$TOKEN"
  echo "Generated token at $TOKEN"
fi
chown root:"$DASH_USER" "$TOKEN"
chmod 0640 "$TOKEN"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo
echo "Setup complete. Start the helper (keeps running in foreground; Ctrl-C to stop):"
echo "  sudo python3 $REPO/privileged-helper/helper.py --user $DASH_USER"
echo
echo "To run in the background, redirect output, e.g.:"
echo "  sudo nohup python3 $REPO/privileged-helper/helper.py --user $DASH_USER > /var/log/smartqos/helper.out 2>&1 &"
