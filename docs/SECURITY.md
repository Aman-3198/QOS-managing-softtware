# Smart QoS Manager — Security Design

Network reconfiguration is privileged. This document defines how the app keeps
privileged operations narrow, authenticated, audited, and tamper-resistant.

## Threat model & boundaries

| Boundary | Trust level | Protection |
|---|---|---|
| Browser ↔ Backend | Semi-trusted (must authenticate) | TLS in prod, auth session, CSRF, input validation |
| Backend ↔ Privileged Helper | Trusted (same host, locked socket) | Unix socket, group-restricted, shared token, allowlist |
| Helper ↔ Kernel | Privileged (root) | Fixed exe paths, argument allowlists, no shell, timeouts |

The web backend is the **only** network-facing surface and it is unprivileged.
The helper has no network listener; it is reachable only via a filesystem Unix
socket with group + token auth. There is no path from the network to "arbitrary
root command."

## Privilege separation

- **Backend** runs as the normal user (`aman`). It can read `/proc`, run
  read-only `nmcli`/`ip`, and talk to the helper socket. It cannot apply tc/nft,
  start an AP, or change sysctls directly.
- **Privileged helper** runs as `root` (user starts it with `sudo` or a root
  systemd unit). It owns: starting/stopping the hotspot, applying app-owned
  `tc` and `nft` state, toggling `ip_forward`, reading privileged stats.
- The helper **never** exposes a generic "exec" operation. It exposes a fixed
  allowlist of named operations, each with a strict Pydantic request schema.
- Subprocess invocation uses **fixed absolute executable paths**
  (`/usr/sbin/tc`, `/usr/bin/nmcli`, …) with argument arrays — **never** a
  shell string. User-supplied values are validated and passed as discrete argv
  elements, never interpolated into a command. No `shell=True`. Ever.

### Helper communication channel

- Socket: `/run/smartqos/helper.sock`, ownership `root:smartqos`, mode `0660`.
- Token: `/etc/smartqos/helper.token`, ownership `root:smartqos`, mode `0640`,
  contents 32 bytes from `openssl rand -hex 32`, generated once at install.
- Every request: `{"op": "<allowlisted>", "token": "<hex>", "args": {...}}`.
- Helper validates the token (constant-time compare) and the op+args schema,
  then performs the operation and returns `{"ok": bool, "data": ..., "error": ...}`.
- The backend reads the token file as a member of the `smartqos` group; the
  dashboard process never has the token in memory longer than needed and never
  logs it. (The redaction filter below drops any string matching the token.)

## Authentication & authorization (Phase 9, design locked now)

- Dashboard access requires a login. Default credential is set at install time
  via an interactive `smartqos-setup` script that hashes a password (argon2 /
  bcrypt) into the DB; never stored in plaintext, never logged.
- Session: signed cookie (HMAC) with short TTL + sliding renewal; HttpOnly,
  SameSite=Strict, Secure in prod (TLS).
- CSRF: SameSite cookie + double-submit token for state-changing requests.
- Rate limiting: per-IP + per-account limits on `/auth/login`, hotspot start/stop,
  qos writes, pause/resume. Implemented via an in-memory token bucket (FastAPI
  middleware).
- Authorization: every state-changing endpoint checks an authenticated session.
  The health/`/api/health` endpoint is the only intentionally public one.
- Privileged actions additionally require the helper to be reachable; if it is
  down, the endpoint returns `503` with a clear "privileged helper not running"
  message rather than silently failing or running unprivileged fallbacks.

## Network exposure

- **Default bind: `127.0.0.1`.** The dashboard is reachable only from the laptop.
- **Phone access** from the hotspot network is opt-in: the user explicitly sets
  `SQM_DASHBOARD_BIND=0.0.0.0` (or the specific hotspot subnet) via settings, with
  a confirmation that auth is required and a strong password is set. The app
  refuses to bind `0.0.0.0` if no password is configured.
- CORS is restricted to the dashboard origin(s); never `*`.
- WebSocket requires the same authenticated session (cookie) and same origin.

## Input validation (defense in depth)

- All API inputs are Pydantic models with strict constraints: rates are `> 0` and
  `<= 10_000` Mbps, priorities in `{low,normal,high,critical}`, IDs are typed
  UUIDs/ints, SSIDs length-bounded, interface names matched against the
  discovered-interface allowlist (not free text).
- The helper re-validates every request independently of the backend (the
  backend is unprivileged and must not be blindly trusted by the root helper).
- No integer overflow in rate→tc-unit conversion; units documented in
  NETWORK_SHAPING.md.
- Path traversal is structurally impossible: there is no "filename" or "path"
  user input anywhere in the system.

## Secret handling

- **Hotspot password:** write-only. At configure time it is passed once to the
  helper, which writes it into the NetworkManager connection profile (NM stores
  it in its own `/etc/NetworkManager/system-connections/` file, root-readable).
  It is **never** stored in our DB or returned by any GET. A "reveal" action
  (if implemented) requires re-auth and reads from NM directly, never from our DB.
- **Helper token:** file-only, group-restricted, never logged, redacted by the
  log filter.
- **Login password:** stored only as a salted hash in the DB.
- **Audit log:** every state change writes an `audit_event` with before/after,
  but a redaction pass scrubs `password`, `token`, `secret`, `psk` fields.

## Subprocess & command safety

- Fixed executable paths, defined once in `core/constants.py`, validated to exist
  and be non-symlink-to-world-writable at startup.
- Argument allowlist per operation (e.g. `qos.apply` only accepts a pre-built
  tc-spec object, not free strings).
- `subprocess.run(..., shell=False, timeout=N, capture_output=True)`. Every
  system command has a timeout (default 10 s; hotspot start 30 s).
- Output is parsed defensively; unexpected output is an error, not ignored.
- `nmcli` is preferred over parsing `/etc/NetworkManager` files directly; when we
  must touch NM, we go through `nmcli`/D-Bus, not raw file writes.

## Safe teardown & ownership (no collateral damage)

- All app-owned objects carry a marker: nft table `smartqos` (dedicated table),
  chain names prefixed `sqm_`, tc handles allocated from a reserved range,
  qdisc marked with an `fwmark`-independent `tc` comment where supported.
- `qos.clear` / shutdown removes **only** objects whose name/handle matches the
  app's allocation scheme. We **never** run `tc qdisc del dev <iface> root`
  blindly or `nft flush ruleset`. Removal is per-handle / per-chain.
- On helper startup, it reconciles: removes orphaned app-owned objects whose
  corresponding DB rule no longer exists (healing), without touching anything
  else.

## Audit logging

`audit_event(actor, action, target_id, before_json, after_json, success, ts)`.
Covers: hotspot start/stop, qos create/update/delete, pause/resume, priority,
policy apply/revert, settings change, login/logout, helper start/stop.
Secrets redacted before write. Append-only (no UPDATE/DELETE in normal use).

## Logging hygiene

- Structured logs to `logs/smartqos.log` (rotated) + console in dev.
- A redaction filter scrubs: the helper token, any field literally named
  `password`/`psk`/`secret`/`token`, and NM connection `802-11-wireless-security`
  keys.
- Log levels: DEBUG in dev, INFO in prod. Sensitive detail is DEBUG-only and
  still redacted.

## Failure modes that must NOT silently degrade security

- Helper down → state-changing endpoints return 503, never fall back to running
  privileged ops from the unprivileged backend.
- Token file missing/unreadable → backend refuses to attempt privileged ops
  (returns 503), does not guess.
- Auth misconfigured (no password set) → `0.0.0.0` bind is refused.
- A `tc`/`nft` apply partially fails → helper rolls back to the prior
  known-good app-owned state and reports failure; the DB rule stays "pending",
  not "applied".

## What we explicitly do not do

- No arbitrary command execution endpoint. No `shell=True`. No `eval`.
- No storing hotspot passwords in our DB or logs.
- No exposing the dashboard to all interfaces without auth + explicit opt-in.
- No flushing system firewall or tc rules.
- No automatically switching the default route or enabling IP forwarding outside
  an explicit, user-approved hotspot start.
