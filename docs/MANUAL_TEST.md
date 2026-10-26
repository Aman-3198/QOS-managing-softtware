# Manual Hardware Verification Procedure

Automated tests cover the pure logic (76 pass, 1 skipped). Live verification of
privileged operations requires `sudo` (your password) and physical devices.
Run these to confirm the app works end-to-end on real hardware.

## Prerequisites

```bash
cd /home/aman/Documents/Qos
sudo apt install -y iperf3                 # for the shaping throughput test
sudo bash privileged-helper/setup.sh      # one-time: token + socket dir
sudo python3 privileged-helper/helper.py   # start the privileged helper (foreground)
```
In another terminal: `bash scripts/dev-start.sh`, open http://127.0.0.1:5173.

## 1. Shaping actually constrains throughput (namespace, no hotspot needed)

```bash
cd /home/aman/Documents/Qos/backend
sudo -E $HOME/.local/bin/uv run pytest tests/test_qos_integration.py -s
```
Expect: an unshaped baseline > 20 Mbps, then a 5 Mbit HTB class measures 3–8 Mbps,
and cleanup restores throughput. If this passes, HTB shaping is real on this kernel.

## 2. Start the hotspot + connect a phone

- Dashboard → Hotspot Settings: enter SSID + password (≥8), pick hotspot
  interface `wlp4s0`, upstream `eno1` (Ethernet), Start.
  - With the helper running this should return "started"; `/api/hotspot/status`
    flips to `started` with a gateway IP on the new AP interface.
- On a phone, join the SSID with the password. Browse — it should have internet.

## 3. Device discovery is real

- Dashboard → Connected Devices: the phone appears with its IP, MAC, signal,
  and live per-device speeds (from AP station counters). Rename it.
- Confirm `/api/devices` lists it with `sources: ["ap_sta","neighbor"]`.

## 4. Per-device bandwidth limit is enforced

- Dashboard → Bandwidth Rules: set the phone's download to 5 Mbps, Apply.
- On the phone, run a speed test or iperf3 against a public server; throughput
  should cap around 5 Mbps (download). Verify with the helper's tc read-back:
  `sudo tc class show dev <upstream>` shows `1:<id>` with `ceil 5000Kbit`.
- Set upload to 2 Mbps; upload a file; should cap around 2 Mbps.

## 5. Pause / resume

- Bandwidth Rules → Pause on the phone. The phone loses internet but stays
  connected to the Wi-Fi; the dashboard remains reachable from the laptop.
- Resume restores internet.

## 6. Priority under congestion

- Connect two phones, give one HIGH priority and a 10 Mbps cap, the other LOW
  with 10 Mbps. Saturate the link; the HIGH device should get scheduling
  preference (more of the shared bandwidth) while both stay under their ceilings.

## 7. Diagnostics + analytics

- Dashboard → Network Diagnostics: all checks pass/known; the helper check is
  "reachable".
- Dashboard → Traffic Analytics: real history graph and per-device usage.

## 8. Cleanup / non-destructiveness

- Stop the hotspot. Run `sudo tc qdisc show dev <upstream>` — our HTB qdisc is
  removed; `sudo nft list tables` shows no `smartqos` table. No unrelated rules
  were touched.
