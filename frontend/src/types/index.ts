// TypeScript mirrors of the backend Pydantic schemas (see backend/app/schemas).
// Keep these in sync when changing the backend contract.

export type Priority = "low" | "normal" | "high" | "critical";
export type QoSState = "applied" | "pending" | "failed";
export type DeviceState = "connected" | "disconnected" | "paused" | "unknown";
export type InternetState = "ok" | "limited" | "none" | "unknown";
export type HotspotState =
  | "stopped"
  | "starting"
  | "started"
  | "stopping"
  | "error";

export interface HealthResponse {
  status: "ok" | "degraded" | "down";
  version: string;
  uptime_s: number;
  helper: "reachable" | "unreachable" | "unknown";
  db: "ok" | "error";
}

export interface SystemInfo {
  hostname: string | null;
  os: string | null;
  os_codename: string | null;
  kernel: string | null;
  arch: string | null;
  cpu_model: string | null;
  cpu_count: number | null;
  mem_total_mb: number | null;
  nm_version: string | null;
  python_version: string | null;
}

export interface HotspotStatus {
  state: HotspotState;
  ssid: string | null;
  hotspot_interface: string | null;
  upstream_interface: string | null;
  gateway_ip: string | null;
  security: string | null;
  band: string | null;
  channel: number | null;
  connected_count: number;
  last_error: string | null;
  started_at: string | null;
}

export interface WifiInfo {
  supports_ap: boolean;
  supports_managed: boolean;
  current_mode: string | null;
  channel: number | null;
  ssid: string | null;
  supports_concurrent_sta_ap: boolean;
  channels_constraint: number | null;
}

export interface InterfaceInfo {
  name: string;
  type: string;
  state: string | null;
  link: boolean;
  is_default_route: boolean;
  upstream_candidate: boolean;
  hotspot_candidate: boolean;
  wifi: WifiInfo | null;
}

export interface HistoryPoint {
  ts: string;
  dl_bps: number | null;
  ul_bps: number | null;
  dl_bytes: number;
  ul_bytes: number;
}

export interface UpstreamSnapshot {
  internet: InternetState;
  latency_ms: number | null;
}

export interface AggregateTraffic {
  dl_bps: number | null;
  ul_bps: number | null;
  dl_bytes: number;
  ul_bytes: number;
}

export interface DeviceSnapshot {
  id: string;
  dl_bps: number | null;
  ul_bps: number | null;
  dl_bytes: number;
  ul_bytes: number;
  state: DeviceState;
  paused: boolean;
}

export interface DeviceInfo {
  id: string;
  label: string | null;
  ip: string | null;
  mac: string | null;
  state: DeviceState;
  connected_at: string | null;
  last_seen: string | null;
  dl_bps: number | null;
  ul_bps: number | null;
  dl_bytes: number;
  ul_bytes: number;
  dl_limit_mbps: number | null;
  ul_limit_mbps: number | null;
  priority: Priority;
  paused: boolean;
  sources: string[];
  hostname: string | null;
  signal_dbm: number | null;
  connected_time_s: number | null;
}

export type QoSSnapshot = {
  device_id: string;
  state: QoSState;
}

export type WsStatus = "connecting" | "open" | "closed";

export interface MonitorSnapshot {
  ts: string;
  hotspot: HotspotStatus;
  upstream: UpstreamSnapshot;
  aggregate: AggregateTraffic;
  devices: DeviceSnapshot[];
  qos: QoSSnapshot[];
  warnings: string[];
}

export interface ApiError {
  ok: false;
  error: { code: string; message: string; details?: Record<string, unknown> };
}
