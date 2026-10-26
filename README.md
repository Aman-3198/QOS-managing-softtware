# Smart QoS Manager

<div align="center">

![Smart QoS Manager](https://img.shields.io/badge/Smart_QoS_Manager-v0.1.0-3b82f6?style=for-the-badge&logo=wifi&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Linux_Mint_22.3-green?style=for-the-badge&logo=linux&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61dafb?style=for-the-badge&logo=react&logoColor=black)
![Tests](https://img.shields.io/badge/Tests-76_passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)

**A real, host-running network management application for Linux.**  
Start a Wi-Fi hotspot · Monitor live traffic · Enforce per-device bandwidth limits · Pause internet access · All from a browser dashboard.

[Quick Start](#quick-start) · [Architecture](#architecture) · [API](#api-reference) · [How It Works](#how-it-works) · [Manual Test](#manual-hardware-test)

</div>

---

## What It Does

Smart QoS Manager turns your Linux laptop into a managed Wi-Fi hotspot with a professional browser-based dashboard. Connect your phone, tablet, or any device — then control its bandwidth from the UI.

```
Your laptop
│
├── Wi-Fi card (wlp4s0)  ──►  Hotspot "SmartQoS"  ──►  Connected phones & devices
│                                                         └── Per-device speed limits (real tc HTB)
│                                                         └── Pause/Resume internet (real nftables)
│                                                         └── Live speed monitoring
└── Ethernet (eno1)  ──►  Internet upstream
```

### Key features

| Feature | How it works |
|---|---|
| **Live traffic graph** | `/proc/net/dev` counters, 1 Hz, real Mbps |
| **Per-device speed limits** | Linux `tc` HTB (Hierarchical Token Bucket) |
| **Pause/Resume internet** | `nftables` forward-hook drop rules |
| **Device discovery** | AP station dump + neighbor table + DHCP leases |
| **Hotspot start/stop** | NetworkManager via privileged helper |
| **Historical analytics** | SQLite downsampled samples, 5m/1h/24h/7d |
| **Network diagnostics** | Real system checks with pass/warn/fail |
| **QoS policies** | Balanced / Gaming / Streaming / Save Bandwidth |
| **Authentication** | PBKDF2 password, signed session cookie |
| **Audit log** | Every privileged action, secrets redacted |

> **Real, not simulated.** Speeds come from `/proc/net/dev`. Limits are real `tc` classes. Pause is real `nftables`. No mock data, no fake devices.

---

## Dashboard Preview

```
┌─────────────────────────────────────────────────────────────────┐
│  Q Smart QoS │ Hotspot: started · SmartQoS · Internet: ok 11ms  │
├──────────┬──────────────────────────────────────────────────────┤
│Dashboard │  TOTAL DOWNLOAD      TOTAL UPLOAD    CONNECTED       │
│Devices   │  ┌──────────┐        ┌──────────┐    ┌──────────┐   │
│Rules     │  │ 31.2 Mbps│        │ 1.4 Mbps │    │    2     │   │
│Analytics │  │ 1.7 MB   │        │ 45 MB    │    │ devices  │   │
│Hotspot   │  └──────────┘        └──────────┘    └──────────┘   │
│Diagnos.  │                                                       │
│Settings  │  Live Traffic ─────────────────────────── [30s 1m 5m]│
│          │  ↓Download  ↑Upload                                   │
│          │  ████▄▂▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▄▆  │
│          │                                                       │
│          │  Hotspot Status: started · SSID: SmartQoS            │
│          │  Gateway: 10.42.0.1 · Upstream: eno1 · Clients: 2    │
└──────────┴───────────────────────────────────────────────────────┘
```

---

## Architecture

The application is split into three privilege tiers. **The web server never runs as root.**

```
┌─────────────────────────────────────────────────────────────────┐
│   Browser (laptop or phone on the hotspot)                      │
│   React + TypeScript + Vite + Tailwind + Recharts               │
└─────────────────┬───────────────────────────────────────────────┘
                  │ HTTP / WebSocket (127.0.0.1:5173 dev, :8090 prod)
┌─────────────────▼───────────────────────────────────────────────┐
│   FastAPI Backend  (runs as user 'aman', UNPRIVILEGED)          │
│                                                                  │
│   ┌────────────┐  ┌──────────┐  ┌──────────────────────────┐   │
│   │ REST API   │  │WebSocket │  │   Services                │   │
│   │ 31 routes  │  │/ws/monitor│  │  Monitor (1Hz /proc)     │   │
│   └────────────┘  └──────────┘  │  Device Discovery        │   │
│                                  │  QoS Service             │   │
│   ┌─────────────────────────┐   │  Hotspot Service          │   │
│   │   SQLite Database       │   │  Analytics Service        │   │
│   │   8 tables, real data   │   │  Auth Service             │   │
│   └─────────────────────────┘   └──────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ JSON allowlist RPC (Unix socket)
                       │ Token auth, strict allowlist, no shell
┌──────────────────────▼──────────────────────────────────────────┐
│   Privileged Helper  (runs as root)                             │
│                                                                  │
│   Allowlist: qos.apply  qos.clear  stats.read  sysctl.set      │
│              hotspot.start  hotspot.stop  helper.restart        │
│                                                                  │
│   ┌─────────────┐  ┌──────────┐  ┌────────────────────────┐    │
│   │ tc HTB      │  │nftables  │  │ nmcli (NetworkManager) │    │
│   │ per-device  │  │ smartqos │  │ hotspot start/stop     │    │
│   │ classes     │  │ table    │  └────────────────────────┘    │
│   └─────────────┘  └──────────┘                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Why this design?

- The browser dashboard is a single-page app (React) talking to a local FastAPI server
- FastAPI runs as a normal user — it can read `/proc`, discover interfaces, serve the UI
- **All privileged operations** (tc, nftables, nmcli, sysctl) go through a tiny root helper
- The helper accepts only 7 named operations, validates every request with Pydantic, uses fixed executable paths with no shell interpolation
- A shared secret token (32 bytes, random, file-only) authenticates the backend to the helper

---

## How It Works

### Live Traffic Monitoring

```python
# Every 1 second — /proc/net/dev is the source of truth
counters = read_proc_net_dev()  # e.g. {"eno1": {"rx_bytes": 12345678, "tx_bytes": 456}}
dl_bps = (rx_now - rx_prev) * 8 / elapsed_seconds   # download = rx on upstream
ul_bps = (tx_now - tx_prev) * 8 / elapsed_seconds   # upload   = tx on upstream
# → pushed to all WebSocket clients instantly
```

The dashboard receives a `MonitorSnapshot` every second over WebSocket — no polling needed. Counter resets (interface restart) are detected and handled cleanly (rate becomes `None` for that interval, never negative).

### Per-Device Bandwidth Limiting

```
Device (10.42.0.5) → hotspot AP → laptop → internet

nftables mangle (prerouting):
  iifname "wlp4s0" ip saddr 10.42.0.5 → mark = 0x1010  (upload mark)
  (mark survives NAT so it's still 0x1010 when the packet leaves eno1)

tc HTB on eno1 (upload):
  root 1:
  └─ 1:1  rate=100Mbit ceil=100Mbit  (parent — aggregate cap)
     ├─ 1:10  rate=100kbit ceil=2000kbit prio=2  (Device — 2 Mbps upload limit)
     │   └─ fq_codel  (fair queuing, low latency)
     └─ 1:ff  (default — unclassified traffic)

tc fw filter on eno1:
  fw handle 1010 flowid 1:10   ← routes marked packets to device's class

tc HTB on wlp4s0 (download):
  Same structure — shapes traffic going TO the device
```

This is **real Linux traffic shaping** — not simulated. Setting a 5 Mbps limit creates an actual `class htb ... ceil 5000kbit` entry that the kernel enforces.

### Device Discovery

```python
# Three sources combined by MAC address
stations = iw dev wlp4s0 station dump   # AP → client counters (rx/tx bytes, signal)
neighbors = ip -j neigh show dev wlp4s0 # ARP table → MAC to IP mapping
leases    = parse_dnsmasq_leases()       # DHCP → hostname hint (root-only, Phase 5)

# Result: DiscoveredClient(mac, ip, tx_bytes, rx_bytes, signal_dbm, connected_time_s)
# Per-device download rate = AP tx bytes delta (AP→client)
# Per-device upload rate   = AP rx bytes delta (client→AP)
```

### Hotspot Management

Uses NetworkManager's built-in hotspot mode via `nmcli`. This means:
- Standard WPA2 security out of the box
- NM manages the DHCP server (dnsmasq)
- Works with the existing system NM configuration

```bash
# What the privileged helper runs when you click "Start Hotspot"
nmcli device wifi hotspot ifname wlp4s0 con-name smartqos-hotspot \
      ssid SmartQoS password "your-password"
```

### Wi-Fi Concurrent STA+AP — The Honest Answer

This laptop has a **MediaTek MT7921** Wi-Fi 6 adapter. The hardware supports concurrent STA+AP, but with `#channels <= 1` (both must share the same channel), AND NetworkManager repurposes `wlp4s0` for the hotspot — dropping the upstream Wi-Fi connection.

**Supported configuration:** Ethernet upstream (`eno1`) + Wi-Fi hotspot (`wlp4s0`) ✓  
**Not supported:** Wi-Fi upstream + Wi-Fi hotspot on the same adapter (NM takes over the interface)

---

## Technology Stack

### Frontend

| Technology | Version | Purpose |
|---|---|---|
| React | 18.3 | UI framework |
| TypeScript | 5.6 | Type safety |
| Vite | 5.4 | Build tool + dev server |
| Tailwind CSS | 3.4 | Utility-first styling |
| Recharts | 2.13 | Traffic graphs |
| Lucide React | 0.456 | Icons |
| React Router | 6.27 | Client-side routing |

### Backend

| Technology | Version | Purpose |
|---|---|---|
| Python | 3.12.3 | Runtime |
| FastAPI | 0.115 | REST API + WebSockets |
| Uvicorn | 0.33 | ASGI server |
| SQLAlchemy | 2.1 | ORM (sync, SQLite) |
| Pydantic v2 | 2.9 | Request/response validation |
| pydantic-settings | 2.6 | Environment config |
| uv | 0.13 | Package management |

### Linux Networking

| Tool | Purpose |
|---|---|
| `tc` (iproute2) | HTB traffic shaping, fq_codel queues |
| `nftables` (`nft`) | Packet marking, pause/resume drop rules |
| `iw` | Wi-Fi capabilities, AP station dump |
| `nmcli` | NetworkManager — hotspot lifecycle |
| `/proc/net/dev` | Interface byte counters (1 Hz monitoring) |

### Infrastructure

| Component | Details |
|---|---|
| Database | SQLite (`data/smartqos.db`) |
| Auth | PBKDF2-SHA256 + signed session cookies |
| IPC | Unix socket (`/run/smartqos/helper.sock`) |
| Token | `openssl rand -hex 32`, file-only, group-restricted |

---

## Project Structure

```
Qos/
│
├── README.md                    ← You are here
├── restart-helper.sh            ← One-command helper restart
│
├── backend/                     ← FastAPI application (unprivileged)
│   ├── pyproject.toml           ← Python deps (uv)
│   ├── app/
│   │   ├── main.py              ← App factory, lifespan, router mounting
│   │   ├── config.py            ← pydantic-settings (env vars SQM_*)
│   │   ├── database.py          ← SQLAlchemy engine, init_db, migrations
│   │   ├── logging_config.py    ← Structured logging + secret redaction
│   │   ├── models/              ← SQLAlchemy ORM models (8 tables)
│   │   ├── schemas/             ← Pydantic request/response models
│   │   ├── api/                 ← FastAPI routers
│   │   │   ├── health.py        ← GET /api/health
│   │   │   ├── system.py        ← GET /api/system/info
│   │   │   ├── network.py       ← GET /api/network/interfaces|status
│   │   │   ├── hotspot.py       ← GET/POST /api/hotspot/*
│   │   │   ├── devices.py       ← GET/PATCH/PUT/POST /api/devices/*
│   │   │   ├── qos.py           ← CRUD /api/qos/rules/*
│   │   │   ├── policies.py      ← /api/policies/*
│   │   │   ├── analytics.py     ← /api/analytics/history|summary|export
│   │   │   ├── diagnostics.py   ← GET /api/diagnostics
│   │   │   ├── settings.py      ← GET/PATCH /api/settings
│   │   │   ├── auth.py          ← /api/auth/login|logout|me|set-password
│   │   │   └── ws.py            ← WS /ws/monitor
│   │   ├── services/
│   │   │   ├── monitor.py       ← 1 Hz /proc/net/dev + WebSocket pub/sub
│   │   │   ├── network_info.py  ← Interface discovery (ip/iw/ethtool)
│   │   │   ├── connectivity.py  ← Internet probe (DNS + TCP)
│   │   │   ├── device_discovery.py  ← AP station + neighbor + DHCP
│   │   │   ├── device_service.py    ← Stable identity, per-device rates
│   │   │   ├── qos_service.py       ← Validate → build → apply → persist
│   │   │   ├── qos_state.py         ← Pure tc/nft command generation
│   │   │   ├── hotspot_service.py   ← Hotspot lifecycle + grant permission
│   │   │   ├── policy_service.py    ← QoS policy engine (4 built-ins)
│   │   │   ├── analytics_service.py ← History from SQLite samples
│   │   │   ├── diagnostics_service.py ← System checks
│   │   │   ├── settings_service.py  ← App settings CRUD
│   │   │   ├── auth_service.py      ← PBKDF2 + session tokens
│   │   │   ├── audit_service.py     ← Append-only audit log
│   │   │   └── helper_client.py     ← Unix socket client to root helper
│   │   └── core/
│   │       ├── constants.py     ← Fixed exe paths, priority map
│   │       ├── exceptions.py    ← SmartQoSError hierarchy
│   │       └── rate.py          ← Pure speed math (tested)
│   └── tests/                   ← 76 tests (pytest)
│       ├── test_health.py       ← API + WebSocket tests
│       ├── test_rate.py         ← Speed calculation math
│       ├── test_validation.py   ← Input validation
│       ├── test_database.py     ← ORM + migrations
│       ├── test_monitor.py      ← RateAccumulator (counter reset handling)
│       ├── test_network_info.py ← /proc/net/dev parsing, live interface check
│       ├── test_connectivity.py ← Probe classification (mocked sockets)
│       ├── test_device_discovery.py ← Station/neighbor parsing + combination
│       ├── test_device_service.py   ← Identity stability, per-device rates
│       ├── test_qos_state.py    ← tc/nft command generation
│       ├── test_qos_service.py  ← Orchestration (mocked helper)
│       └── test_qos_integration.py  ← Real namespaces (sudo, skipped otherwise)
│
├── frontend/                    ← React SPA
│   ├── package.json
│   ├── vite.config.ts           ← Dev proxy: /api + /ws → :8090
│   ├── tailwind.config.js
│   └── src/
│       ├── main.tsx             ← Entry point
│       ├── App.tsx              ← Router + auth guard
│       ├── index.css            ← Tailwind + component classes
│       ├── types/index.ts       ← TypeScript mirrors of backend schemas
│       ├── api/
│       │   ├── client.ts        ← Typed REST client (30+ methods)
│       │   └── ws.ts            ← WebSocket client (auto-reconnect)
│       ├── hooks/
│       │   ├── useMonitor.ts    ← WS consumer, rolling history buffer
│       ├── components/
│       │   ├── Layout.tsx       ← Sidebar + header + mobile nav
│       │   ├── StatCard.tsx     ← Metric card widget
│       │   ├── TrafficGraph.tsx ← Recharts area chart
│       │   └── ComingSoon.tsx   ← Phase placeholder
│       └── pages/
│           ├── Dashboard.tsx    ← Live stats + graph + hotspot toggle
│           ├── Devices.tsx      ← Device list + rename (live, 2s refresh)
│           ├── Rules.tsx        ← Bandwidth limits + priorities + policies
│           ├── Analytics.tsx    ← Historical charts + CSV export
│           ├── Hotspot.tsx      ← Start/stop + QR code + password
│           ├── Diagnostics.tsx  ← System health checks
│           ├── Settings.tsx     ← App settings + auth
│           └── Login.tsx        ← Password login
│
├── privileged-helper/
│   ├── helper.py                ← Root daemon (409 lines, 7 ops, no shell)
│   └── setup.sh                 ← One-time: token + socket dir (sudo)
│
├── scripts/
│   ├── env.sh                   ← PATH setup (Node + uv, no dotfiles)
│   ├── setup.sh                 ← One-time: uv sync + npm install
│   ├── dev-start.sh             ← Start backend + frontend
│   ├── dev-stop.sh              ← Stop both
│   ├── prod-start.sh            ← Start backend serving built SPA
│   ├── test.sh                  ← Run pytest
│   └── inspect-host.sh          ← Read-only host inspection
│
├── packaging/
│   ├── smartqos-backend.service ← systemd unit (user 'aman')
│   └── smartqos-helper.service  ← systemd unit (root)
│
├── docs/
│   ├── ARCHITECTURE.md          ← Full design + trade-offs
│   ├── SECURITY.md              ← Privilege model + threat model
│   ├── NETWORK_SHAPING.md       ← tc + nft design, honest limitations
│   ├── HOST_ENVIRONMENT.md      ← Machine-specific findings
│   ├── API_SPEC.md              ← All 31 endpoints documented
│   ├── DEVELOPMENT_PLAN.md      ← 10-phase plan
│   ├── PHASE_CHECKLIST.md       ← Progress tracker
│   ├── DEFINITION_OF_DONE.md    ← Honest status per spec item
│   └── MANUAL_TEST.md           ← Hardware verification procedure
│
└── data/
    └── smartqos.db              ← SQLite (gitignored)
```

---

## Database Schema

8 tables in SQLite (`data/smartqos.db`):

```sql
device_identity   -- Stable UUID per device, MAC as identity hint, label
device_session    -- Current/recent connection (IP, interface, paused state)
qos_rule          -- Per-device limits, priority, tc class id, applied state
network_config    -- Hotspot config (SSID, interfaces — NO password stored)
traffic_sample    -- Downsampled tx/rx for analytics (aggregate + per-device)
saved_policy      -- User-saved QoS policy snapshots
app_setting       -- Key/value settings (speed unit, retention, dashboard bind)
audit_event       -- Append-only log (actor, action, before/after, secrets redacted)
```

---

## API Reference

**Base URL:** `http://127.0.0.1:8090` (dev) or `http://127.0.0.1:8090` (prod serving SPA)  
**WebSocket:** `ws://127.0.0.1:5173/ws/monitor` (dev) or `ws://127.0.0.1:8090/ws/monitor` (prod)

### System
```
GET  /api/health              → { status, version, uptime_s, helper, db }
GET  /api/system/info         → { hostname, os, kernel, cpu_model, nm_version, ... }
```

### Network (read-only)
```
GET  /api/network/interfaces  → { interfaces: [InterfaceInfo] }
GET  /api/network/status      → { upstream: UpstreamStatus, ip_forward, ... }
```

### Hotspot
```
GET  /api/hotspot/status      → HotspotStatus
POST /api/hotspot/start       → { ssid, password, hotspot_interface, upstream_interface }
POST /api/hotspot/stop        → { state: "stopped" }
POST /api/hotspot/grant       → opens terminal to start helper (GUI only)
POST /api/hotspot/restart-helper → ask helper to re-exec with latest code
```

### Devices
```
GET    /api/devices                    → { devices: [DeviceInfo] }
GET    /api/devices/{id}               → DeviceInfo
PATCH  /api/devices/{id}               → { label }  → rename
PUT    /api/devices/{id}/qos           → { dl_limit_mbps, ul_limit_mbps, priority }
POST   /api/devices/{id}/pause         → drop internet at network layer
POST   /api/devices/{id}/resume        → restore internet
```

### QoS Rules & Policies
```
GET    /api/qos/rules          → { rules: [QoSRule] }
POST   /api/qos/rules          → create
PATCH  /api/qos/rules/{id}     → update
DELETE /api/qos/rules/{id}     → remove + reapply

GET    /api/policies                      → [balanced, gaming, streaming, save_bandwidth, ...]
GET    /api/policies/{name}/preview       → diff preview before applying
POST   /api/policies/{name}/apply         → apply + save revert snapshot
POST   /api/policies/revert               → restore previous config
POST   /api/policies/save                 → save current config as named policy
```

### Analytics
```
GET /api/analytics/history?range=5m|1h|24h|7d&scope=aggregate|device
GET /api/analytics/summary?range=...  → totals, peaks, per-device
GET /api/analytics/export?range=...   → CSV download (no secrets)
```

### Diagnostics, Settings, Auth
```
GET  /api/diagnostics          → 11 system checks (pass/warn/fail/unknown)
GET  /api/diagnostics/export   → plain text (no secrets)

GET    /api/settings           → all non-secret settings
PATCH  /api/settings           → update

GET  /api/auth/me              → { authenticated, has_password }
POST /api/auth/login           → { password } → sets HttpOnly cookie
POST /api/auth/logout          → clears cookie
POST /api/auth/set-password    → set/change dashboard password
```

### WebSocket

`WS /ws/monitor` — pushes a `MonitorSnapshot` every ~1 second:

```json
{
  "ts": "2026-10-25T21:10:00Z",
  "hotspot": { "state": "started", "ssid": "SmartQoS", "connected_count": 2 },
  "upstream": { "internet": "ok", "latency_ms": 11.2 },
  "aggregate": { "dl_bps": 31200000, "ul_bps": 1400000, "dl_bytes": 104857600 },
  "devices": [
    { "id": "uuid", "dl_bps": 28000000, "ul_bps": 900000, "state": "connected" }
  ],
  "warnings": []
}
```

---

## Quick Start

### Prerequisites

- Linux Mint 22.3 (Ubuntu 24.04 base)
- NetworkManager (`nmcli` present)
- System tools: `ip`, `tc`, `iw`, `nft`, `nmcli` — all standard on Ubuntu
- An Ethernet cable for internet upstream (recommended)

### 1. Install toolchain (no sudo)

```bash
# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js 22 LTS (into ~/.local/node)
VERSION=v22.23.4
curl -fsS -o /tmp/node.tar.xz \
  https://nodejs.org/dist/$VERSION/node-$VERSION-linux-x64.tar.xz
mkdir -p ~/.local/node && tar -xf /tmp/node.tar.xz -C ~/.local/node --strip-components=1

# Add to PATH for this session
export PATH="$HOME/.local/node/bin:$HOME/.local/bin:$PATH"
```

### 2. Set up the project

```bash
cd /home/aman/Documents/Qos

# Install Python + Node deps (no sudo)
bash scripts/setup.sh
```

### 3. Set up the privileged helper (sudo, one-time)

```bash
# Creates /run/smartqos/, /etc/smartqos/helper.token, /var/log/smartqos/
sudo bash privileged-helper/setup.sh
```

### 4. Start the privileged helper

```bash
# Keep this terminal open while using the app, or use the restart script:
sudo python3 -B privileged-helper/helper.py --user aman &
```

Or use the convenience script:
```bash
bash restart-helper.sh
```

### 5. Start the dashboard

```bash
bash scripts/dev-start.sh
```

Open **http://127.0.0.1:5173** — the dashboard is live.

### Stop everything

```bash
bash scripts/dev-stop.sh
sudo pkill -f "helper.py"
```

---

## Production Deployment

```bash
# Build the frontend
cd frontend && npm run build && cd ..

# Start backend (serves built SPA on port 8090)
bash scripts/prod-start.sh

# Or use systemd:
sudo cp packaging/smartqos-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smartqos-helper.service smartqos-backend.service
```

---

## Security Model

```
Internet user
     │
     ▼ HTTP (127.0.0.1:8090 — local only by default)
┌─────────────────────────────────────────────────────┐
│  FastAPI (uid=1000, no capabilities)                │
│  Cannot: run tc/nft, start hotspot, change sysctl   │
│  Can:    read /proc, serve UI, talk to helper socket │
└──────────────────┬──────────────────────────────────┘
                   │ Unix socket /run/smartqos/helper.sock
                   │ Token: HMAC compare_digest (constant time)
                   │ Mode: 0660, group: aman
┌──────────────────▼──────────────────────────────────┐
│  Privileged Helper (uid=0)                          │
│  Fixed exe paths: /usr/sbin/tc, /usr/bin/nmcli, ... │
│  No shell=True, no user input in commands           │
│  7 named ops, Pydantic-validated args               │
└─────────────────────────────────────────────────────┘
```

**Security properties:**
- Web server never runs as root
- Helper token: 32 random bytes, file `0640`, group-only readable
- Auth: PBKDF2-SHA256 (200k iterations), HttpOnly + SameSite=Strict cookie
- Rate limiting: 5 login attempts per 60 seconds per IP
- CORS: restricted to dashboard origin only
- Hotspot password: write-only, stored in NM keyring, never in our DB
- Logs: secret redaction filter scrubs `password`, `token`, `psk` fields
- Audit log: every privileged action recorded, secrets redacted before write
- Dashboard bind: `127.0.0.1` by default — must explicitly enable for phone access

---

## Testing

```bash
# Run all 76 tests (no sudo, isolated temp DBs)
bash scripts/test.sh

# Run a specific test file
bash scripts/test.sh tests/test_qos_state.py -v

# Network namespace integration test (proves real tc shaping works, needs sudo)
sudo apt install -y iperf3
sudo -E $HOME/.local/bin/uv run pytest backend/tests/test_qos_integration.py -s
```

### Test coverage

| Test file | What's tested |
|---|---|
| `test_rate.py` | Speed calculation, counter resets, units, overflow |
| `test_validation.py` | Rate bounds, priority values, error messages |
| `test_database.py` | ORM, migrations, relationships |
| `test_monitor.py` | RateAccumulator: resets, cumulative totals, first tick |
| `test_network_info.py` | /proc/net/dev parsing, live interface discovery |
| `test_connectivity.py` | DNS+TCP probe classification (mocked sockets) |
| `test_device_discovery.py` | Station dump parsing, neighbor combination, STALE filter |
| `test_device_service.py` | Identity stable across IP change, per-device rates |
| `test_qos_state.py` | tc/nft command generation, mark allocation, cleanup |
| `test_qos_service.py` | Helper failure → "failed" state, pause/resume |
| `test_health.py` | API responses, WebSocket snapshot, ping/pong |
| `test_qos_integration.py` | **Real tc in namespaces**: iperf through 5Mbit class |

---

## Known Limitations

These are documented facts, not bugs. See `docs/DEFINITION_OF_DONE.md` for the full honest accounting.

| Limitation | Details |
|---|---|
| **Concurrent STA+AP** | MT7921 supports same-channel only; NM repurposes the interface. Use Ethernet upstream. |
| **Helper restart** | The helper runs as root. Code updates require `bash restart-helper.sh` (sudo once). |
| **IPv6 shaping** | IPv4 marks/classes only. IPv6 traffic is unshaped (disclosed in the UI). |
| **DHCP hostnames** | `/var/lib/NetworkManager` is root-only. Hostnames need Phase 5 helper DHCP read. |
| **Download shaping** | Enforces per-device ceilings at AP→client leg; doesn't reclaim upstream bandwidth. |
| **No DPI** | "Gaming" / "Streaming" policies are scheduling preferences, not application identification. |

---

## Hardware Tested On

| Component | Value |
|---|---|
| Machine | HP Victus Gaming Laptop 15-fa0xxx |
| OS | Linux Mint 22.3 "Zena" (Ubuntu 24.04 noble base) |
| Kernel | 7.0.0-38-generic |
| CPU | 12th Gen Intel Core i5-12450H (12 cores) |
| RAM | 15 GB |
| Wi-Fi | MediaTek MT7921 (Wi-Fi 6, `mt7921e` driver) |
| Ethernet | Realtek RTL8111/8168 (`r8169` driver) |
| NetworkManager | 1.46.0 |

---

## Contributing / Development

### Environment variables

All settings use the `SQM_` prefix and are loaded by `pydantic-settings`:

```bash
SQM_BACKEND_PORT=8090
SQM_BACKEND_HOST=127.0.0.1
SQM_DATABASE_URL=sqlite:///data/smartqos.db
SQM_LOG_LEVEL=INFO
SQM_MONITOR_INTERVAL_S=1.0
SQM_HISTORY_SAMPLE_INTERVAL_S=5
SQM_QOS_PARENT_CAP_MBPS=100.0
SQM_DASHBOARD_BIND=127.0.0.1   # change to 0.0.0.0 + set a password for phone access
```

### Adding a new API endpoint

1. Add a router in `backend/app/api/`
2. Add the service logic in `backend/app/services/`
3. Mount the router in `backend/app/main.py`
4. Add the TypeScript method to `frontend/src/api/client.ts`
5. Write tests in `backend/tests/`

### Adding a privileged operation

1. Add an `op_<name>` function in `privileged-helper/helper.py`
2. Add it to `ALLOWED_OPS` and `DISPATCH`
3. Add the call in `backend/app/services/helper_client.py`
4. The helper must be restarted for it to take effect: `bash restart-helper.sh`

---

## License

Built as a personal network management tool for Linux Mint 22.3.  
All networking operations are local — no data leaves your machine.

---

<div align="center">

Made with ❤️ and real `tc` commands — no mock data was harmed in the making of this project.

**Dashboard:** `http://127.0.0.1:5173` · **API Docs:** `http://127.0.0.1:8090/api/docs`

</div>
