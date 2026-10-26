#!/usr/bin/env bash
# scripts/inspect-host.sh — read-only host re-inspection (Phase 1 source data).
# Never modifies the system. Safe to run anytime.
set -uo pipefail

echo "=== OS / kernel ==="
cat /etc/os-release 2>/dev/null | grep -E "^(NAME|VERSION|UBUNTU_CODENAME)=" || true
uname -sr
python3 --version 2>&1

echo
echo "=== Network interfaces ==="
ip -br addr show 2>/dev/null || true

echo
echo "=== Default route ==="
ip route show default 2>/dev/null || true

echo
echo "=== NetworkManager ==="
nmcli --version 2>/dev/null | head -1 || echo "nmcli not found"
nmcli device status 2>/dev/null || true

echo
echo "=== Wi-Fi adapter / combinations ==="
iw dev 2>&1 | sed -n '1,20p' || true
echo "--- valid interface combinations ---"
iw list 2>&1 | grep -A6 "valid interface combinations" || true

echo
echo "=== Driver ==="
for w in $(iw dev 2>/dev/null | awk '/Interface/{print $2}'); do
  echo "[$w]"; ethtool -i "$w" 2>/dev/null | grep -E "driver|firmware" || true
done

echo
echo "=== Tools present ==="
for t in ip tc iw nft nmcli dnsmasq hostapd ethtool openssl python3; do
  printf "%-10s " "$t"; command -v "$t" 2>/dev/null || echo "MISSING"
done

echo
echo "=== Forwarding / counters ==="
sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding 2>/dev/null || true
echo "(counter source: /proc/net/dev)"
