# Smart QoS Manager — API Specification

Base URL (dev): `http://127.0.0.1:8090`. WebSocket: `ws://127.0.0.1:8090/ws/monitor`.

All request/response bodies are JSON, defined as Pydantic v2 models on the
backend and mirrored as TypeScript types in `frontend/src/types/`. Consistent
error envelope:

```json
{ "ok": false, "error": { "code": "invalid_input", "message": "rate must be > 0", "details": {} } }
```

Status codes: 200 success, 400 validation, 401 unauthenticated, 403 forbidden,
404 not found, 409 conflict (e.g. hotspot busy), 429 rate-limited, 503
privileged helper unavailable / operation failed and rolled back.

Phase mapping in `[brackets]` shows when each endpoint becomes functional.
Endpoints marked `[P2]` are live in this phase; others are stubbed with
typed empty/`Unavailable` responses so the frontend can be built ahead.

## System

### `GET /api/health` `[P2]`
Public. Liveness probe.
Response: `{ "status": "ok", "version": "0.1.0", "uptime_s": 12.4,
"helper": "reachable"|"unreachable"|"unknown", "db": "ok" }`

### `GET /api/system/info` `[P2]`
Response: `{ "hostname": "amans-victus", "os": "Linux Mint 22.3",
"kernel": "7.0.0-38-generic", "cpu_model": "...", "cpu_count": 8,
"mem_total_mb": 15928, "nm_version": "1.46.0" }`

## Network (read-only)

### `GET /api/network/interfaces` `[P3]`
Response: `InterfaceList { interfaces: [InterfaceInfo] }`
```
InterfaceInfo {
  name: str                     # e.g. "wlp4s0"
  type: "wifi"|"ethernet"|"loopback"|"other"
  driver: str | null
  state: "up"|"down"|"unavailable"
  link: bool
  mac: str | null
  addresses: [ {family, addr, prefix} ]
  gateway: str | null
  is_default_route: bool
  upstream_candidate: bool       # usable as upstream
  hotspot_candidate: bool         # AP-capable, usable as hotspot
  wifi: { phy, supports_ap: bool, supports_managed: bool,
          current_mode: "managed"|"ap"|null, channel: int|null,
          supports_concurrent_sta_ap: bool } | null
}
```

### `GET /api/network/status` `[P3]`
Response: `NetworkStatus { upstream: UpstreamStatus, hotspot_present: bool,
default_route: str|null, ip_forward_v4: bool, ip_forward_v6: bool }`
```
UpstreamStatus { interface: str|null, link: bool, has_ip: bool,
has_default_route: bool, internet: "ok"|"limited"|"none"|"unknown",
latency_ms: float|null }
```
`internet` is derived from an actual probe (e.g. a short HTTP/ICMP check),
never from "interface is UP."

## Hotspot

### `GET /api/hotspot/status` `[P6]`
Response: `HotspotStatus { state: "stopped"|"starting"|"started"|"stopping"|"error",
ssid: str|null, hotspot_interface: str|null, upstream_interface: str|null,
gateway_ip: str|null, security: "wpa2"|"wpa3"|"wpa2/wpa3"|null,
band: str|null, channel: int|null, connected_count: int,
last_error: str|null, started_at: str|null }`

### `POST /api/hotspot/start` `[P6]`
Request: `{ ssid: str, password: str, hotspot_interface: str,
upstream_interface: str, band?: "a"|"bg", channel?: int|null,
security?: "wpa2"|"wpa3"|"wpa2/wpa3" }`
Response: `HotspotStatus`. Validates interface candidates; refuses to reuse the
active STA adapter without explicit acknowledgment of the channel constraint.

### `POST /api/hotspot/stop` `[P6]`
Response: `HotspotStatus`. Removes only app-owned shaping/firewall; leaves the
NM hotspot connection profile configurable to keep or delete.

## Devices

### `GET /api/devices` `[P4]`
Response: `{ devices: [DeviceInfo] }`
```
DeviceInfo {
  id: str                       # stable internal id
  label: str
  ip: str|null
  mac: str|null
  state: "connected"|"disconnected"|"paused"
  connected_at: str|null, last_seen: str|null,
  dl_bps: float|null, ul_bps: float|null,
  dl_bytes: int, ul_bytes: int,
  dl_limit_mbps: float|null, ul_limit_mbps: float|null,
  priority: "low"|"normal"|"high"|"critical",
  paused: bool, sources: [str]   # ["dhcp","neighbor","ap_sta"]
}
```

### `GET /api/devices/{id}` `[P4]`
Response: `DeviceInfo`.

### `PATCH /api/devices/{id}` `[P4]`
Request: `{ label?: str }`. Response: `DeviceInfo`.

### `GET /api/devices/{id}/traffic?range=5m|1h|24h|7d` `[P8]`
Response: `{ samples: [ {ts, dl_bps, ul_bps, dl_bytes, ul_bytes} ] }`.

### `PUT /api/devices/{id}/qos` `[P5]`
Request: `{ dl_limit_mbps: float|null, ul_limit_mbps: float|null,
priority: "low"|"normal"|"high"|"critical", enabled: bool }`
Validated: limits `>0` and `<=10000`; builds desired tc state; applies via helper;
verify; persist. Response: `DeviceInfo` with updated limits + `qos_state:
"applied"|"pending"|"failed"`.

### `POST /api/devices/{id}/pause` `[P7]`
Response: `DeviceInfo` with `paused: true`.

### `POST /api/devices/{id}/resume` `[P7]`
Response: `DeviceInfo` with `paused: false`.

## QoS rules

### `GET /api/qos/rules` `[P5]`
Response: `{ rules: [QoSRule] }`.

### `POST /api/qos/rules` `[P5]`
Body: a `QoSRule` without `id`. Response: created `QoSRule`.

### `PATCH /api/qos/rules/{rule_id}` `[P5]` / `DELETE /api/qos/rules/{rule_id}` `[P5]`

```
QoSRule { id: str, device_id: str, dl_limit_mbps: float|null,
ul_limit_mbps: float|null, priority: ..., enabled: bool,
class_id: int|null, state: "applied"|"pending"|"failed", applied_at: str|null }
```

## Policies

### `GET /api/policies` `[P7]` / `POST /api/policies` `[P7]` / `POST /api/policies/{name}/apply` `[P7]` / `POST /api/policies/revert` `[P7]`
Built-ins: `balanced`, `gaming`, `streaming`, `save_bandwidth`, plus user
`custom`. Apply returns the diff preview before committing if `?dry_run=true`.

## Analytics

### `GET /api/analytics/summary` `[P8]`
Response: `{ window: "5m|1h|24h|7d", total_dl_bytes, total_ul_bytes,
peak_dl_bps, peak_ul_bps, per_device: [ {id, dl_bytes, ul_bytes, peak_dl_bps} ] }`

### `GET /api/analytics/history?range=5m|1h|24h|7d&scope=aggregate|device:{id}` `[P8]`
Response: `{ samples: [ {ts, dl_bps, ul_bps} ] }`. Reads downsampled buckets.

## Diagnostics

### `GET /api/diagnostics` `[P9]`
Response: `{ checks: [DiagnosticCheck] }`
```
DiagnosticCheck { id, name, status: "pass"|"warning"|"fail"|"unknown",
detail, suggestion }
```
Covers: interface status, AP support, internet, default route, ip_forward,
firewall, DHCP, hotspot clients, tc config, tc counters, helper perms,
required tools. The export (`?format=export`) omits all secrets/tokens.

## Settings & auth

### `GET /api/settings` `[P9]` / `PATCH /api/settings` `[P9]`
Non-secret settings only (units, retention, dashboard bind). Secret fields are
write-only and never returned.

### `POST /api/auth/login` `[P9]` / `POST /api/auth/logout` `[P9]`
Login sets a signed HttpOnly SameSite cookie; rate-limited.

## WebSocket

### `WS /ws/monitor` `[P3]`
On connect the server sends the latest snapshot immediately, then pushes ~1 Hz:
```
MonitorSnapshot {
  ts: str,
  hotspot: HotspotStatus (summary),
  upstream: { internet, latency_ms },
  aggregate: { dl_bps, ul_bps, dl_bytes, ul_bytes },
  devices: [ { id, dl_bps, ul_bps, dl_bytes, ul_bytes, state, paused } ],
  qos: [ { device_id, state } ],
  warnings: [str]        # e.g. "stale data", "helper unreachable", "ipv6 not routed"
}
```
Client sends a `ping` periodically; server replies `pong` and closes dead
connections. Reconnect with backoff is handled client-side.

## Security notes

- All `POST`/`PUT`/`PATCH`/`DELETE` require an authenticated session (Phase 9)
  and, for network-changing ops, a reachable privileged helper (503 otherwise).
- No endpoint returns a secret (password, token, psk). `GET /api/hotspot/status`
  never includes the password.
- Input is validated server-side; the helper re-validates independently.
