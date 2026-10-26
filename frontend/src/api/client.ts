// Typed REST client. Same-origin in dev (Vite proxies /api to the backend);
// in prod the FastAPI app serves the built SPA so /api is same-origin too.
import type { DeviceInfo, HealthResponse, HistoryPoint, HotspotStatus, InterfaceInfo, Priority, SystemInfo } from "../types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = (body && (body as { error?: { message?: string } }).error) || {};
    throw new Error(err.message || `HTTP ${res.status}`);
  }
  return body as T;
}

export interface DeviceListResponse { devices: DeviceInfo[] }
export interface QosRuleRow {
  id: string; device_id: string; dl_limit_mbps: number | null; ul_limit_mbps: number | null;
  priority: Priority; enabled: boolean; paused: boolean; state: string; applied_at: string | null;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  systemInfo: () => request<SystemInfo>("/system/info"),
  interfaces: () => request<{ interfaces: InterfaceInfo[] }>("/network/interfaces"),
  devices: () => request<DeviceListResponse>("/devices"),
  patchDevice: (id: string, label: string | null) =>
    request<DeviceInfo>(`/devices/${id}`, { method: "PATCH", body: JSON.stringify({ label }) }),
  setDeviceQos: (id: string, dl: number | null, ul: number | null, priority: Priority, enabled: boolean) =>
    request<{ state: string }>(`/devices/${id}/qos`, { method: "PUT", body: JSON.stringify({ dl_limit_mbps: dl, ul_limit_mbps: ul, priority, enabled }) }),
  pauseDevice: (id: string) => request<{ paused: boolean }>(`/devices/${id}/pause`, { method: "POST" }),
  resumeDevice: (id: string) => request<{ paused: boolean }>(`/devices/${id}/resume`, { method: "POST" }),
  deleteRule: (id: string) => request<{ ok: boolean }>(`/qos/rules/${id}`, { method: "DELETE" }),
  qosRules: () => request<{ rules: QosRuleRow[] }>("/qos/rules"),

  hotspotStatus: () => request<HotspotStatus>("/hotspot/status"),
  startHotspot: (b: { ssid: string; password: string; hotspot_interface: string; upstream_interface: string; band?: string; channel?: number | null; security?: string }) =>
    request<{ state: string; warnings?: string[] }>("/hotspot/start", { method: "POST", body: JSON.stringify(b) }),
  stopHotspot: () => request<{ state: string }>("/hotspot/stop", { method: "POST" }),
  grantHotspot: () => request<{ ok: boolean; already?: boolean; terminal?: string; message?: string }>("/hotspot/grant", { method: "POST" }),
  restartHelper: () => request<{ ok: boolean; restarted?: boolean; error?: string }>("/hotspot/restart-helper", { method: "POST" }),

  policies: () => request<{ policies: { name: string; description: string; builtin: boolean }[] }>("/policies"),
  previewPolicy: (name: string) => request<{ policy: string; current: unknown[]; after: unknown[]; diff: { device_id: string; changes?: Record<string, unknown>; removed?: boolean }[] }>(`/policies/${encodeURIComponent(name)}/preview`),
  applyPolicy: (name: string) => request<{ applied: string; changed: unknown[] }>(`/policies/${encodeURIComponent(name)}/apply`, { method: "POST" }),
  revertPolicy: () => request<{ reverted_to: unknown }>("/policies/revert", { method: "POST" }),
  savePolicy: (name: string, description?: string) => request<{ saved: string }>(`/policies/save`, { method: "POST", body: JSON.stringify({ name, description }) }),

  analyticsHistory: (range: string, scope = "aggregate") => request<{ range: string; samples: HistoryPoint[] }>(`/analytics/history?range=${range}&scope=${scope}`),
  analyticsSummary: (range: string) => request<{ window: string; total_dl_bytes: number; total_ul_bytes: number; peak_dl_bps: number; peak_ul_bps: number; per_device: { id: string; dl_bytes: number; ul_bytes: number; peak_dl_bps: number }[] }>(`/analytics/summary?range=${range}`),

  diagnostics: () => request<{ checks: { id: string; name: string; status: string; detail: string; suggestion: string }[] }>("/diagnostics"),

  settings: () => request<Record<string, string>>("/settings"),
  patchSettings: (b: Record<string, unknown>) => request<Record<string, string>>("/settings", { method: "PATCH", body: JSON.stringify(b) }),

  authMe: () => request<{ authenticated: boolean; has_password: boolean }>("/auth/me"),
  login: (password: string) => request<{ ok: boolean }>("/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  setPassword: (password: string) => request<{ ok: boolean }>("/auth/set-password", { method: "POST", body: JSON.stringify({ password }) }),
};
