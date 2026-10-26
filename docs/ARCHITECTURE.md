# Smart QoS Manager — Architecture

A real, host-running network-management application for Linux Mint 22.3
(Ubuntu 24.04). The dashboard is a browser SPA; the brain is a FastAPI backend
running **unprivileged**; the only root code is a tiny, allowlisted helper that
touches `tc`/`nft`/`nmcli`. See `HOST_ENVIRONMENT.md` for the concrete machine
this targets.

## Design goals

- **Real measurements, not mocks.** Every speed comes from `/proc/net/dev`,
  `tc` class stats, or interface counters.
- **Privilege separation by construction.** The web server never runs as root.
- **Never clobber the system.** Application-owned tc handles, nft
  tables/chains, and class IDs. No global flushes. Clean shutdown cleanup.
- **Discover, never assume.** Interface names, channels, capabilities, and
  upstream state are detected at runtime.
- **Honest limitations.** Unsupported configurations are detected and reported,
  not papered over.

## High-level components

```
                 +---------------------------------------------------+
 Browser (laptop | phone on hotspot)  -- HTTP/WS (localhost) -->
                 +---------------------------------------------------+
                                        |  127.0.0.1:8090  |
                                        v                  v
                          +------------------------------+      +-----------------+
                          |  Backend (FastAPI, unpriv.)   |      |  SQLite (data/) |
                          |  - REST API + WebSocket        |      |  settings, devs,|
                          |  - Monitoring engine (1 Hz)    |      |  qos rules,     |
                          |  - Device discovery            |      |  traffic samples,|
                          |  - QoS state builder           |      |  audit log       |
                          |  - Hotspot state machine        |      +-----------------+
                          +------------------------------+
                                 |  JSON allowlist RPC (Unix socket / localhost)
                                 v
                          +------------------------------+
                          |  Privileged Helper (root)     |
                          |  - start/stop hotspot (nmcli)  |
                          |  - apply/replace tc qdisc      |
                          |  - apply/replace nft rules     |
                          |  - set ip_forward / sysctls    |
                          |  - read tc/nft stats back      |
                          +------------------------------+
                                 |
                                 v
                          Linux kernel: wlp4s0 (AP), eno1 (upstream),
                          tc HTB + fq_codel, nftables forward/mangle
```

### A. Frontend — React + TypeScript + Vite + Tailwind

Pages: Dashboard, Connected Devices, Bandwidth Rules, Traffic Analytics,
Hotspot Settings, Network Diagnostics, Application Settings.

- `src/api/` — typed REST + WebSocket client (auto-reconnect, dedup polling).
- `src/pages/` — one file per page.
- `src/components/` — shared UI (cards, tables, graphs, modals, toasts).
- `src/hooks/` — `useMonitorSnapshot`, `useApi`, etc.
- `src/types/` — TypeScript mirrors of backend Pydantic schemas.
- Recharts for graphs, Lucide for icons, Tailwind for layout.

Dev: Vite dev server on `127.0.0.1:5173` proxying `/api` and `/ws` to the
backend. Prod: built to static files served by the FastAPI app (single origin,
no CORS exposure).

### B. Backend — FastAPI + Uvicorn (unprivileged, runs as `aman`)

Layout under `backend/app/`:

| Area | Responsibility |
|---|---|
| `main.py` | App factory, lifespan (start/stop monitor + helper client), mounts routers, serves built frontend. |
| `config.py` | `pydantic-settings` settings from env + `config/*.conf`. No secrets in env beyond a token file path. |
| `logging_config.py` | Structured logging, secret redaction filter, file + console. |
| `database.py` | SQLAlchemy 2.0 sync engine, `sessionmaker`, `Base`, `init_db()` (creates schema + runs migrations). |
| `models/` | ORM models (see Database section). |
| `schemas/` | Pydantic v2 request/response models (typed contract for the API). |
| `api/` | Routers: `health`, `system`, `network`, `hotspot`, `devices`, `qos`, `analytics`, `diagnostics`, `settings`, `ws`. |
| `services/` | Business logic: `monitor`, `discovery`, `qos_state`, `hotspot`, `diagnostics`, `helper_client`. |
| `core/` | `security` (auth/session/CSRF — Phase 9), `exceptions`, `constants`. |

The backend **only** reads system state directly (unprivileged). Anything that
modifies the system is delegated to the privileged helper through a typed
client. The backend builds the *desired* state, asks the helper to apply it,
verifies via read-back, then persists.

### C. Network Monitoring Engine (`services/monitor.py`)

A single async background task started in the FastAPI lifespan:

1. Every 1 s, read aggregate counters from `/proc/net/dev` for the hotspot and
   upstream interfaces (unprivileged).
2. Compute bit/s from `Δbytes * 8 / Δt`. Handle counter resets (interface
   restart/counter rollover) by detecting decreases and treating the sample as
   a reset, not a negative rate.
3. Per-device accounting (Phase 4+) from `tc` class stats via the helper, or
   marked "Unavailable" when not measurable.
4. Publish a `MonitorSnapshot` to an in-memory `asyncio` pub/sub; the WebSocket
   router streams it to clients. Persist a downsampled sample to SQLite at a
   configurable cadence (default every 5 s) to avoid unbounded writes.
5. Detect stale data (no counter movement for N seconds) and flag it.

The monitor is the single source of truth for "what to display." No component
fabricates numbers.

### D. QoS Engine (`services/qos_state.py`)

Translates user rules into a desired Linux `tc` + `nft` configuration. It does
**not** run `tc` itself. It:

1. Holds the current authoritative rule set (from DB + live overrides).
2. Allocates stable class IDs and filter handles (see NETWORK_SHAPING.md).
3. Produces an idempotent desired-state document (qdisc tree, classes, filters,
   nft rules) tagged with the app's ownership marker.
4. Sends the diff to the privileged helper to apply.
5. Reads back `tc`/`nft` stats to verify, then marks the rule applied or rolls
   back (helper removes app-owned handles, then re-applies the previous known-good
   state).

### E. Privileged Helper (`privileged-helper/`, root-owned)

A small Python service run as root (started by the user with `sudo`, or a
root systemd unit). It listens on a Unix domain socket
(`/run/smartqos/helper.sock`, `root:smartqos`, mode `0660`) and accepts JSON
requests authenticated by a shared token (`/etc/smartqos/helper.token`,
`root:smartqos`, mode `0640`, generated at install time with `openssl rand`).

Allowlist of operations (everything else returns 403):
- `hotspot.start` / `hotspot.stop` (nmcli, with channel pinning for topology 2)
- `qos.apply` (replace app-owned qdisc + classes + filters)
- `qos.clear` (remove only app-owned tc/nft objects)
- `device.pause` / `device.resume` (insert/remove app-owned nft rules)
- `sysctl.set` (limited to `net.ipv4.ip_forward`, `net.ipv6.conf.all.forwarding`)
- `stats.read` (read tc class + qdisc stats, nft counters)

Every request is validated with Pydantic, every subprocess call uses **fixed
executable paths** with **argument allowlists** (no shell, no interpolation of
user input into a command string), and every call has a timeout. See
`SECURITY.md`.

The helper is **not** an RPC shell. There is no "run command" operation.

### F. Database — SQLite (`data/smartqos.db`)

Schema (SQLAlchemy 2.0 models, migrations via Alembic-style version table):

| Table | Purpose |
|---|---|
| `device_identity` | Stable internal ID, MAC (last seen), label, first_seen, vendor guess. MAC is identity *hint*, not the key. |
| `device_session` | A current/recent connection: device_identity_id, ip, mac, iface, connected_at, last_seen, paused. |
| `qos_rule` | device_identity_id, dl_rate_mbps, ul_rate_mbps, priority, enabled, burst cfg. |
| `network_config` | hotspot/upstream interface selection, SSID, security mode (no password stored here — see Security). |
| `traffic_sample` | timestamp, scope (aggregate/device), dl_bytes, ul_bytes, dl_bps, ul_bps. Downsampled. |
| `saved_policy` | name, description, serialized rule deltas. |
| `app_setting` | key/value settings. |
| `audit_event` | timestamp, actor, action, target, before/after (secrets redacted), success. |

Retention: raw 1 Hz samples are kept short-term; aggregated 1-min buckets are
kept for the configurable history window (default 30 days). Historical graphs
read buckets, not raw samples.

## Data flow examples

**Live dashboard update:** browser opens `WS /ws/monitor` → backend's monitor
task already pushes `MonitorSnapshot` every 1 s → WebSocket router forwards it
→ React updates cards/graph. No polling loop, no fabricated data.

**Set a download limit:** user enters 5 Mbps → `PUT /api/devices/{id}/qos` →
backend validates (positive, ≤ interface capacity) → `qos_state` computes new
desired tc state for that device's class → helper `qos.apply` → backend
read-back verifies the class ceil → persists `qos_rule` + writes `audit_event`
→ returns success. On helper failure, the rule stays "pending" and the previous
applied state is preserved (rollback inside helper).

**Pause a device:** `POST /api/devices/{id}/pause` → backend resolves the
device's current IPs → helper `device.pause` inserts an app-owned nft rule
forwarding `iifname <hotspot> ip saddr <ip>` to drop (keeping the gateway's
management IP reachable) → verified → state saved. If the IP changes (new DHCP
lease), a lease-change hook re-applies the rule for the new IP.

## Security boundaries (summary; full in SECURITY.md)

- Web app: unprivileged, bound to `127.0.0.1` by default. Auth required (Phase 9).
- Helper: root, Unix-socket only, token-auth, strict allowlist, no shell.
- No secret is returned in any status response. Hotspot password is write-only
  (set at configure time, stored salted/derived or in NM keyring, never echoed).
- CORS restricted to the dashboard origin; WebSocket same-origin + auth.

## What is explicitly NOT in scope / deferred

- Per-application DPI (we do not claim to identify apps).
- Wi-Fi password plaintext reveal beyond an explicit authorized action.
- IPv6 shaping is best-effort; where incomplete we disclose it (NETWORK_SHAPING.md).
- Containerization (host networking needs direct kernel access).

## Phased rollout (see DEVELOPMENT_PLAN.md)

Phase 1 docs → Phase 2 foundation (this phase) → Phase 3 read-only monitoring →
Phase 4 device discovery → Phase 5 QoS engine (+ namespace tests) → Phase 6
hotspot → Phase 7 access control/policies → Phase 8 analytics → Phase 9
security/packaging → Phase 10 end-to-end verification.
