"""Pydantic v2 request/response schemas (the typed API contract).

These are mirrored as TypeScript types in ``frontend/src/types/``. Keep field
names and shapes in sync when changing them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    ok: bool = False
    error: ErrorDetail

    class ErrorDetail(BaseModel):
        code: str
        message: str
        details: dict = Field(default_factory=dict)


class OkResponse(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------------------
# Health & system
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    uptime_s: float
    helper: Literal["reachable", "unreachable", "unknown"]
    db: Literal["ok", "error"]


class SystemInfo(BaseModel):
    hostname: str | None = None
    os: str | None = None
    os_codename: str | None = None
    kernel: str | None = None
    arch: str | None = None
    cpu_model: str | None = None
    cpu_count: int | None = None
    mem_total_mb: int | None = None
    nm_version: str | None = None
    python_version: str | None = None


# ---------------------------------------------------------------------------
# Network (stubs filled in Phase 3)
# ---------------------------------------------------------------------------
class AddressInfo(BaseModel):
    family: str
    addr: str
    prefix: int | None = None


class WifiInfo(BaseModel):
    phy: str | None = None
    supports_ap: bool = False
    supports_managed: bool = False
    current_mode: str | None = None  # "managed" | "ap" | "monitor" | ...
    channel: int | None = None
    ssid: str | None = None
    # Concurrent STA+AP support (HOST_ENVIRONMENT.md). When True, channels_constraint
    # reports the #channels limit (e.g. 1 => must share the upstream channel).
    supports_concurrent_sta_ap: bool = False
    channels_constraint: int | None = None


class InterfaceInfo(BaseModel):
    name: str
    type: str | None = None
    driver: str | None = None
    state: str | None = None
    link: bool = False
    mac: str | None = None
    addresses: list[AddressInfo] = Field(default_factory=list)
    gateway: str | None = None
    is_default_route: bool = False
    upstream_candidate: bool = False
    hotspot_candidate: bool = False
    wifi: WifiInfo | None = None


class InterfaceList(BaseModel):
    interfaces: list[InterfaceInfo] = Field(default_factory=list)


class UpstreamStatus(BaseModel):
    interface: str | None = None
    link: bool = False
    has_ip: bool = False
    has_default_route: bool = False
    internet: Literal["ok", "limited", "none", "unknown"] = "unknown"
    latency_ms: float | None = None


class NetworkStatus(BaseModel):
    upstream: UpstreamStatus
    hotspot_present: bool = False
    default_route: str | None = None
    ip_forward_v4: bool = False
    ip_forward_v6: bool = False


# ---------------------------------------------------------------------------
# Hotspot (stub until Phase 6)
# ---------------------------------------------------------------------------
class HotspotStatus(BaseModel):
    state: Literal["stopped", "starting", "started", "stopping", "error"] = "stopped"
    ssid: str | None = None
    hotspot_interface: str | None = None
    upstream_interface: str | None = None
    gateway_ip: str | None = None
    security: str | None = None
    band: str | None = None
    channel: int | None = None
    connected_count: int = 0
    last_error: str | None = None
    started_at: datetime | None = None


class HotspotStartRequest(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=8, max_length=63)
    hotspot_interface: str
    upstream_interface: str
    band: str | None = None
    channel: int | None = None
    security: str | None = "wpa2"


# ---------------------------------------------------------------------------
# Devices (stub until Phase 4)
# ---------------------------------------------------------------------------
class DeviceInfo(BaseModel):
    id: str
    label: str | None = None
    ip: str | None = None
    mac: str | None = None
    state: Literal["connected", "disconnected", "paused", "unknown"] = "unknown"
    connected_at: datetime | None = None
    last_seen: datetime | None = None
    dl_bps: float | None = None
    ul_bps: float | None = None
    dl_bytes: int = 0
    ul_bytes: int = 0
    dl_limit_mbps: float | None = None
    ul_limit_mbps: float | None = None
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    paused: bool = False
    sources: list[str] = Field(default_factory=list)
    # Wi-Fi/AP enrichment (from iw station dump).
    hostname: str | None = None
    signal_dbm: int | None = None
    connected_time_s: int | None = None


class DeviceList(BaseModel):
    devices: list[DeviceInfo] = Field(default_factory=list)


class DevicePatch(BaseModel):
    label: str | None = Field(default=None, max_length=128)


# ---------------------------------------------------------------------------
# QoS
# ---------------------------------------------------------------------------
class QoSRuleSet(BaseModel):
    dl_limit_mbps: float | None = Field(default=None, ge=0, le=10000)
    ul_limit_mbps: float | None = Field(default=None, ge=0, le=10000)
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    enabled: bool = True


class QoSRule(QoSRuleSet):
    id: str
    device_id: str
    class_id: int | None = None
    state: Literal["applied", "pending", "failed"] = "pending"
    applied_at: datetime | None = None


class QoSRuleList(BaseModel):
    rules: list[QoSRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Analytics (stub until Phase 8)
# ---------------------------------------------------------------------------
class TrafficPoint(BaseModel):
    ts: datetime
    dl_bps: float | None = None
    ul_bps: float | None = None
    dl_bytes: int = 0
    ul_bytes: int = 0


class TrafficHistory(BaseModel):
    scope: str
    samples: list[TrafficPoint] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# WebSocket snapshot
# ---------------------------------------------------------------------------
class AggregateTraffic(BaseModel):
    dl_bps: float | None = None
    ul_bps: float | None = None
    dl_bytes: int = 0
    ul_bytes: int = 0


class DeviceSnapshot(BaseModel):
    id: str
    dl_bps: float | None = None
    ul_bps: float | None = None
    dl_bytes: int = 0
    ul_bytes: int = 0
    state: Literal["connected", "disconnected", "paused", "unknown"] = "unknown"
    paused: bool = False


class QoSSnapshot(BaseModel):
    device_id: str
    state: Literal["applied", "pending", "failed"] = "pending"


class UpstreamSnapshot(BaseModel):
    internet: Literal["ok", "limited", "none", "unknown"] = "unknown"
    latency_ms: float | None = None


class MonitorSnapshot(BaseModel):
    ts: datetime
    hotspot: HotspotStatus
    upstream: UpstreamSnapshot
    aggregate: AggregateTraffic
    devices: list[DeviceSnapshot] = Field(default_factory=list)
    qos: list[QoSSnapshot] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
