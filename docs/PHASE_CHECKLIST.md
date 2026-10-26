# Smart QoS Manager — Phase Checklist

A copy of the checklist from `DEVELOPMENT_PLAN.md`, kept as a single ticklist
to track progress. Check off only when the *exit criterion* is met in the real
environment, not when code is merely written.

## Phase 1 — Inspect & plan
- [x] Inspect host: OS, kernel, interfaces, Wi-Fi combinations, privileges, tools
- [x] `docs/HOST_ENVIRONMENT.md`
- [x] `docs/ARCHITECTURE.md`
- [x] `docs/SECURITY.md`
- [x] `docs/NETWORK_SHAPING.md`
- [x] `docs/API_SPEC.md`
- [x] `docs/DEVELOPMENT_PLAN.md`
- [x] `docs/PHASE_CHECKLIST.md`
- [x] `README.md`

## Phase 2 — Project foundation
- [x] Dev toolchain installed (Node 22, uv) into `$HOME`, no sudo
- [x] `scripts/env.sh`, `scripts/setup.sh`, `scripts/dev-start.sh`, `scripts/dev-stop.sh`
- [x] Backend: FastAPI app factory + lifespan
- [x] Backend: config via pydantic-settings
- [x] Backend: structured logging with secret redaction
- [x] Backend: SQLAlchemy 2.0 engine + init_db + initial models
- [x] Backend: `GET /api/health`, `GET /api/system/info`
- [x] Backend: WebSocket route (placeholder snapshot for now)
- [x] Backend: pytest suite (health, speed calc, validation) passing
- [x] Frontend: Vite + React + TS + Tailwind scaffold
- [x] Frontend: router + app shell + nav + Dashboard placeholder
- [x] Frontend: typed API client + WebSocket client with reconnect
- [x] Frontend: types mirroring backend schemas
- [x] Verified: `curl :8090/api/health` ok; dashboard loads at :5173; WS connects
- [x] Documented exact dev launch steps in README

## Phase 3 — Read-only monitoring
- [x] `services/monitor.py`: 1 Hz `/proc/net/dev` polling
- [x] Rate calculation with counter-reset handling
- [x] Stale-data detection (frontend useMonitor, >5s)
- [x] `GET /api/network/interfaces` (real discovery)
- [x] `GET /api/network/status` (real internet probe)
- [x] `WS /ws/monitor` streams real aggregate snapshot
- [x] Dashboard: stat cards + live traffic graph
- [x] Verify displayed speeds match `ip -s link` deltas (31 Mbps avg / 76 Mbps peak, ratio 2.44 MATCH)

## Phase 4 — Device discovery
- [x] DHCP lease + neighbor + AP-sta discovery, deduped to stable IDs
- [x] `GET /api/devices`, `GET /api/devices/{id}`, `PATCH` rename
- [x] Per-device accounting from AP station counters (real speeds), or honest "Unavailable" when no station stats
- [x] Device list UI, empty state, rename
- [x] A client is identified across an IP change (unit-tested; live phone test needs a hotspot → Phase 6)

## Phase 5 — QoS engine
- [x] `services/qos_state.py` (pure builder + command generation, unit-tested) + privileged helper `qos.apply`/`qos.clear`
- [x] Upload shaping (HTB + fw marks on upstream egress)
- [x] Download shaping (HTB on hotspot egress)
- [x] Priority classes (4 levels), class-id/mark allocation
- [x] Pause/resume via nft (app-owned `inet smartqos` table)
- [x] Atomic apply / verify / rollback (helper rolls back app-owned objects on failure)
- [x] Ownership markers + safe cleanup (no global flush; only our table/qdisc)
- [x] `PUT /api/devices/{id}/qos`, QoS rule CRUD, pause/resume, Bandwidth Rules UI
- [x] Helper-down → 503 (graceful), bad input rejected (422/400), `paused` column migration
- [ ] Namespace throughput test RUN with sudo (written; skips without root — `sudo -E uv run pytest tests/test_qos_integration.py`). Logic is unit-tested; live rate-constraint proof needs your `sudo`.
- [ ] Per-device isolation / pause / cleanup namespace tests (written; run with sudo)
- [ ] Live shaping on real interfaces (needs `sudo bash privileged-helper/setup.sh` + `sudo python3 privileged-helper/helper.py` + a hotspot+client — Phase 6)

## Phase 6 — Hotspot integration
- [ ] Wireless capability detection + interface role detection
- [ ] Hotspot start/stop via nmcli through helper
- [ ] Upstream selection + internet probe
- [ ] Channel pinning + topology-2 warning (refuse silent STA break)
- [ ] ip_forward toggle at start, restore at stop
- [ ] `GET /api/hotspot/status`, `POST start/stop`, Hotspot Settings UI
- [ ] A real phone joins and reaches the internet

## Phase 7 — Access control & policies
- [ ] Pause/resume verified at network layer
- [ ] Priority controls
- [ ] Saved policies (balanced/gaming/streaming/save-bandwidth/custom)
- [ ] Rule preview + revert + confirmation dialogs

## Phase 8 — Analytics
- [ ] Downsampled bucket storage + retention
- [ ] Per-device history
- [ ] Usage charts + export (secrets stripped)
- [ ] DB stays bounded under sustained run

## Phase 9 — Security & packaging
- [ ] Auth/session/CSRF + rate limiting
- [ ] Audit logging (secrets redacted)
- [ ] Root systemd unit for the helper + installer `smartqos-setup`
- [ ] Diagnostics page (pass/warn/fail/unknown + suggestions)
- [ ] Production build served from FastAPI
- [ ] Unauth rejected; helper-down → 503; no-password → no `0.0.0.0`
- [ ] Diagnostics export has no secrets

## Phase 10 — End-to-end verification
- [ ] All automated tests pass
- [ ] Manual hardware verification procedure documented & run
- [ ] Each Definition-of-Done item checked or marked unsupported with reason
