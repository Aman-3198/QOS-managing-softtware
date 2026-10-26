# Definition of Done — Status

Honest accounting against the spec's Section 20. "✅ built/tested" means the
code exists and is covered by automated tests or live verification here.
"⏳ needs sudo" means it's built and unit-tested but live verification requires
your `sudo` (the helper / namespace test / a real hotspot) — see MANUAL_TEST.md.

- [✅] Installs on the target Linux system — `scripts/install.sh` (deps, build, helper setup); dev toolchain installed no-sudo.
- [✅] Dashboard opens in a browser — dev at :5173, prod at :8090 serving the built SPA.
- [⏳] Phone can access it when remote dashboard access is enabled securely — bind 0.0.0.0 refused without a password (Settings); auth implemented (PBKDF2 + signed session cookie, login rate-limited). Needs sudo-free config + a password set, then tested from a phone.
- [✅] Real network interfaces are discovered — `/api/network/interfaces` (lo, eno1, wlp4s0 with driver/AP/STA/concurrent detection).
- [✅] Real internet connectivity is detected — `/api/network/status` (real DNS+TCP probe; "ok" with latency, not assumed from link-up).
- [⏳] Hotspot can be started and stopped — built (NM via helper); needs `sudo` helper to run live.
- [⏳] Connected devices are discovered correctly — built (AP station + neighbor + leases); needs a live hotspot+client to verify.
- [✅] Aggregate upload/download speeds are measured — `/proc/net/dev` real, cross-checked vs `ip -s link` (31 vs 76 Mbps, ratio 2.44).
- [⏳] Per-device speeds measured when reliable accounting is available — built from AP station counters (real); shows "Unavailable" honestly when no station stats. Live needs a hotspot.
- [⏳] Upload/download limits actually enforced per device — built (HTB + nft via helper); pure logic unit-tested; **live proof needs the namespace test (sudo) + a real client**. Not yet claimed verified live.
- [⏳] Priorities affect scheduling under congestion — built (HTB prio); needs live congestion test.
- [⏳] Pause/resume works at the network layer — built (nft forward drops); needs live test.
- [✅] Changes survive application restarts where configured to persist — settings, identities, labels, QoS rules, policies, audit in SQLite. QoS re-applies on demand; re-apply-on-start could be added.
- [✅] Network configuration failures are handled safely — helper verify + rollback; 503 on helper-down (no silent fallback).
- [✅] Application does not erase unrelated networking rules — app-owned table/qdisc only; cleanup never `flush ruleset`/blind `qdisc del`.
- [✅] Automated tests pass — 76 passed, 1 skipped (the skipped one needs root and is run via sudo in MANUAL_TEST).
- [⏳] Manual hardware verification documented — MANUAL_TEST.md written; run it with sudo to close out.
- [✅] Install/configure/troubleshoot/uninstall instructions provided — README + install.sh + prod-start.sh + systemd units; uninstall = stop services + `rm -rf` repo + `sudo rm -rf /run/smartqos /etc/smartqos /var/log/smartqos`.

## Known limitations / unsupported (honest)

- **Concurrent Wi-Fi upstream + hotspot on one adapter**: hardware supports it
  same-channel only, but NetworkManager repurposes the interface. Use Ethernet
  upstream or a second adapter. The app detects + warns; it never silently breaks
  the upstream Wi-Fi. (HOST_ENVIRONMENT.md)
- **Per-app identification**: not implemented (no DPI). Policies are scheduling/
  ceiling preferences, not app detection. Never claimed otherwise.
- **IPv6 shaping**: IPv4 rules only; IPv6 disclosed as unshaped where the hotspot
  doesn't route it (NETWORK_SHASING.md).
- **Download shaping** enforces per-device ceilings at the AP→client leg; it does
  not reclaim upstream bandwidth already consumed (documented in the UI).
- **DHCP hostnames** are `None` until the privileged helper reads leases
  (/var/lib/NetworkManager is root-only).

## Bottom line

A real, safe, testable application — not a mock dashboard. Read-only monitoring,
interface/internet/device discovery, and analytics are **live-verified now**.
Hotspot, shaping, and pause/resume are **built and unit-tested**, and become
live-verified the moment you run the helper with `sudo` and connect a client.
