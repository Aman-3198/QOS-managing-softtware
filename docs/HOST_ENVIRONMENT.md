# Host Environment — Findings & Constraints

Captured by inspecting the actual target machine on the first run.
These are **facts about this host**, not assumptions. Design decisions in the
other documents derive from here. Re-run `scripts/inspect-host.sh` (Phase 3) to
refresh.

## Operating system

| Property | Value |
|---|---|
| Distribution | Linux Mint 22.3 "Zena" (Ubuntu 24.04 / noble base) |
| Kernel | `7.0.0-38-generic` (x86_64) |
| Hardware | HP Victus by HP Gaming Laptop 15-fa0xxx |
| NetworkManager | `nmcli` tool, version `1.46.0` |
| Python | `3.12.3` (system) |

## Network interfaces (actual, observed)

```
DEVICE          TYPE      STATE                   CONNECTION
wlp4s0          wifi      connected               ATK
eno1            ethernet  unavailable (no link)   --
lo              loopback  connected (externally)  lo
p2p-dev-wlp4s0  wifi-p2p  disconnected            --
```

| Interface | Driver / chip | Link | Address | Notes |
|---|---|---|---|---|
| `wlp4s0` | `mt7921e` (MediaTek MT7921, Wi-Fi 6 / 802.11ax) | UP | `a8:41:f4:15:09:79` | Currently a **managed** (client) STA connected to SSID `ATK` on **channel 12 (2467 MHz, 40 MHz)**, IP `192.168.1.6/24`, default route via `192.168.1.1`. |
| `eno1` | `r8169` (Realtek RTL8111/8168) | DOWN (no carrier) | `2c:58:b9:2e:87:d4` | Ethernet port. No cable connected. **Preferred upstream** when a cable is attached. |
| `lo` | — | UP | — | Loopback. |

There is **no** fixed interface name assumption. The app discovers interfaces at
runtime. Names like `wlp4s0`/`eno1` appear only because that is what this machine
happens to expose; the code never hard-codes them.

## Wi-Fi AP capability (the key concurrent-AP question)

`iw list` reports the MT7921 supports interface modes:
`managed, AP, AP/VLAN, monitor, P2P-client, P2P-GO, P2P-device`.

The decisive field is **valid interface combinations**:

```
* #{ managed, P2P-client } <= 2, #{ P2P-GO } <= 1, #{ P2P-device } <= 1,
  total <= 3, #channels <= 2
* #{ managed, P2P-client } <= 2, #{ AP } <= 1, #{ P2P-device } <= 1,
  total <= 3, #channels <= 1
```

### What this means (the honest answer)

- **Concurrent STA + AP is supported** by the hardware: one `managed` interface
  (upstream Wi-Fi) + one `AP` interface (the hotspot) can coexist on this single
  adapter.
- **Hard constraint: `#channels <= 1`.** Both radios must share a single channel.
  If the upstream Wi-Fi (`ATK`) is on channel 12, the hotspot **must also be on
  channel 12**. There is no second independent radio.
- Practical consequences:
  - NetworkManager's `nmcli device wifi hotspot` picks a channel (often 1/6/11).
    For concurrent operation the hotspot must be **pinned to the same channel as
    the active STA connection** (set `802-11-wireless.band` and
    `802-11-wireless.channel` on the hotspot connection profile).
  - If the upstream AP changes channel, the hotspot must follow or fail
    gracefully. The app detects the active STA channel and constrains the
    hotspot profile to it.
  - 40 MHz operation on the shared channel is at the mercy of the upstream BSS;
    expect 20 MHz to be the reliable setting.
- **Driver behavior**: `mt7921e` in mainline kernels is generally reliable for
  STA+AP same-channel. We do not assume it is bug-free; the diagnostics page
  verifies actual activation rather than trusting the combination string.

### Recommended topology

1. **Ethernet upstream** (`eno1`) + Wi-Fi hotspot (`wlp4s0`) — most reliable,
   full channel freedom, no upstream Wi-Fi disruption. Requires a cable.
2. **Wi-Fi upstream + Wi-Fi hotspot on the same adapter** — works only with the
   same-channel constraint above. Acceptable for a portable demo but not a
   stable always-on setup. The app supports this but warns clearly.
3. A **second USB Wi-Fi adapter** for the hotspot removes the constraint; out of
   scope for the initial build but the architecture allows it.

The app **never silently breaks the existing `ATK` Wi-Fi connection**. Starting a
hotspot on `wlp4s0` while `ATK` is active is only attempted in topology 2, and
only after the user confirms, with the channel constraint enforced.

## Privileges (critical for the privileged-helper design)

```
user:  aman   uid=1000  groups: ..., sudo, ...
sudo:  PASSWORD REQUIRED  (NOT passwordless)
```

- The logged-in user is in the `sudo` group, but `sudo` prompts for a password.
- **Implication:** automated/agent runs in this environment **cannot** execute
  privileged commands (`tc`, `nft`, `ip_forward` changes, starting an AP that
  reconfigures the radio, etc.) without the user typing a password.
- **Design consequence:** all privileged work lives in a **separate, narrowly
  scoped privileged helper** that runs as root. The unprivileged web app never
  needs root. The helper is started by the user (with `sudo`) or installed as a
  root-owned systemd unit the user enables once. The web app talks to it over a
  locked-down local socket with a strict allowlist of operations.
- For Phase 1–4 (inspection + read-only monitoring), **no privileges are
  required** — everything reads `/proc`, `nmcli` (status), `ip` (read-only),
  which an unprivileged user can do.

## Kernel networking state

| Setting | Value | Needed for |
|---|---|---|
| `net.ipv4.ip_forward` | `0` (OFF) | Must be `1` for hotspot routing (privileged, Phase 6) |
| `net.ipv6.conf.all.forwarding` | `0` (OFF) | Same for IPv6 (privileged, Phase 6) |

The app **does not** enable forwarding automatically; it is a deliberate,
user-approved hotspot start action performed by the privileged helper.

## Available system tools

Present: `nft`, `tc`, `iw`, `ip`, `nmcli`, `dnsmasq`, `hostapd`, `iptables`,
`ss`, `openssl`, `python3` (3.12.3, has `venv` module), `git`.

Missing (installed into `$HOME`, no sudo): `node`/`npm` (Node 22 LTS via
nodejs.org tarball), `uv` (Astral). Missing system CLIs that we **do not**
require for Phase 1–2: `jq`, `sqlite3` (we use Python's `sqlite3` module),
`pip3`/`ensurepip` (we use `uv` instead).

## Interface counter source for monitoring

`/proc/net/dev` exposes byte/packet counters per interface (`lo`, `eno1`,
`wlp4s0`). This is the primary **aggregate** throughput source for Phase 3
(unprivileged, ~1 Hz polling). Per-device accounting in later phases uses `tc`
class stats (privileged) with `/proc/net/dev` as the cross-check.

## Unresolved / to-verify at runtime

These are deliberately **not** assumed and will be verified by the diagnostics
page when the relevant phase runs:

- Whether `mt7921e` actually activates a same-channel STA+AP pair without
  dropping the STA connection (topology 2). Verified only on a real start.
- Whether NetworkManager 1.46 honors a pinned `band`+`channel` on the hotspot
  profile while the STA is active. Verified before offering topology 2.
- Whether upstream internet is reachable (cable present for `eno1`, or
  upstream AP reachable for `wlp4s0`). Checked live, never assumed from
  interface-UP state.
