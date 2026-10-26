# Smart QoS Manager — Development Plan

Ten phases. Each phase has a concrete exit criterion; a phase is done only when
its exit criterion is met in the actual environment, not when the code exists.

> Phase 1–2 are delivered in this initial commit. Phases 3+ are sequenced
> afterward. Nothing before Phase 5 modifies the host network; nothing before
> Phase 6 touches the radio or default route.

## Phase 1 — Inspect & plan  ✅ (this commit)

- Inspect host: OS, kernel, interfaces, Wi-Fi combos, privileges, tools.
- Produce docs: `HOST_ENVIRONMENT.md`, `ARCHITECTURE.md`, `SECURITY.md`,
  `NETWORK_SHAPING.md`, `API_SPEC.md`, `DEVELOPMENT_PLAN.md`,
  `PHASE_CHECKLIST.md`, `README.md`.
- **Exit:** documents committed; no code yet.

## Phase 2 — Project foundation  ✅ (this commit)

- Backend skeleton: FastAPI app factory, lifespan, config (`pydantic-settings`),
  structured logging with secret redaction, SQLAlchemy 2.0 engine + `init_db`,
  initial models, `/api/health` + `/api/system/info`.
- Frontend skeleton: Vite + React + TS + Tailwind, router, app shell with nav,
  Dashboard placeholder, typed API client + WebSocket client (reconnect), types
  mirroring backend schemas.
- Dev tooling: `scripts/env.sh` (no-dotfile PATH), `scripts/setup.sh`,
  `scripts/dev-start.sh` / `dev-stop.sh`, uv lockfile for backend, npm for frontend.
- **Exit:** `curl :8090/api/health` returns ok; the dashboard loads at :5173;
  the WebSocket connects (even if it only sends placeholders); backend tests pass.

## Phase 3 — Read-only monitoring  (next)

- `services/monitor.py`: 1 Hz `/proc/net/dev` polling, rate calc with reset
  handling, stale detection.
- `GET /api/network/interfaces`, `/api/network/status` (with a real internet
  probe), `/api/system/info`.
- `WS /ws/monitor` streams a real `MonitorSnapshot` (aggregate only this phase).
- Dashboard: stat cards, live traffic graph (Recharts), hotspot/upstream state.
- **Exit:** displayed speeds match `ip -s link` deltas within tolerance; no mock
  values anywhere. No privileged ops, no config changes.

## Phase 4 — Device discovery

- Combine DHCP leases, neighbor table, AP station info; dedupe to stable IDs.
- `GET /api/devices`, `GET /api/devices/{id}`, `PATCH` (rename).
- Per-device accounting from tc class stats (read-only this phase; classes
  created in Phase 5) — until then per-device shows "Unavailable" honestly.
- Device list UI, empty state, rename.
- **Exit:** a real connected client appears and is identified across IP changes.

## Phase 5 — QoS engine  (privileged, first network changes)

- `services/qos_state.py` + privileged helper `qos.apply`/`qos.clear`/`stats.read`.
- Upload + download HTB shaping with fw marks; priority classes; pause/resume
  via nft; atomic apply/verify/rollback; ownership markers; safe cleanup.
- `PUT /api/devices/{id}/qos`, QoS rule CRUD, Bandwidth Rules UI.
- **Network integration tests in namespaces**: verify rates are actually
  constrained (e.g. iperf3 through a veth pair with a 5 Mbps class must not exceed
  ~5 Mbps), per-device isolation, pause/resume, cleanup leaves nothing behind.
- **Exit:** shaping tests pass in namespaces; rates are real, not asserted.

## Phase 6 — Hotspot integration  (privileged, radio changes)

- Wireless capability detection, hotspot start/stop via `nmcli` through helper,
  upstream selection, channel pinning for topology 2 warnings, error handling,
  safe recovery, ip_forward toggle at start.
- `GET /api/hotspot/status`, `POST start/stop`. Hotspot Settings UI.
- **Exit:** a real phone can join the hotspot and reach the internet through the
  laptop; stopping restores prior state; no silent STA breakage.

## Phase 7 — Access control & policies

- Pause/resume (nft), priority controls, saved policies (balanced/gaming/
  streaming/save-bandwidth/custom), rule preview, revert, confirmation dialogs.
- **Exit:** pause blocks a real client's internet (verified), resume restores it;
  policy apply shows the diff and reverts cleanly.

## Phase 8 — Analytics

- Historical storage + downsampled buckets + retention; per-device history;
  usage charts; data export (secrets stripped). Traffic Analytics UI.
- **Exit:** history graphs for 5m/1h/24h/7d reflect real accumulated bytes; DB
  stays bounded under sustained run.

## Phase 9 — Security & packaging

- Auth/session/CSRF, rate limiting, audit logging, privilege-separation hardening.
- Root systemd unit for the helper; installer `smartqos-setup`; diagnostics page;
- production build + serve frontend from FastAPI; docs for install/upgrade/uninstall.
- **Exit:** unauth requests rejected; helper down → 503; `0.0.0.0` bind refused
  without a password; install is reproducible; diagnostics export has no secrets.

## Phase 10 — End-to-end verification

- Run all tests; manual hardware verification procedure (hotspot + phone + iperf
  shaping check); report unsupported features honestly.
- **Exit:** every Definition-of-Done item checked off or explicitly marked
  unsupported with a reason.

## Risk register (top items)

1. **Same-adapter concurrent STA+AP** — hardware supports same-channel only, and
   NM takes over the interface. Mitigation: recommend Ethernet upstream; warn and
   refuse to silently break STA. (HOST_ENVIRONMENT.md)
2. **Download shaping is egress-side** — enforces per-device ceilings but does
   not reclaim already-consumed upstream bandwidth. Disclosed in UI.
3. **Privileged ops need the user's sudo password** — agent cannot run them
   unattended. Mitigation: privileged helper started once by the user; all dev
   work through Phase 4 needs no privileges.
4. **Per-device accounting needs tc classes** — until Phase 5, per-device speed
   is honestly "Unavailable," never faked.
5. **IPv6** — shaped only where the hotspot actually routes it; otherwise
   disclosed as IPv4-only.
