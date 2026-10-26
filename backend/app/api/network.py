"""Network API: real interface discovery and network status (read-only)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import (
    AddressInfo,
    InterfaceInfo,
    InterfaceList,
    NetworkStatus,
    UpstreamStatus,
    WifiInfo,
)
from .network_helpers import read_sysctl_bool

router = APIRouter(prefix="/network", tags=["network"])


def _to_iface(d: dict) -> InterfaceInfo:
    wifi = WifiInfo(**d["wifi"]) if d.get("wifi") else None
    return InterfaceInfo(
        name=d["name"],
        type=d["type"],
        driver=d.get("driver"),
        state=d.get("state"),
        link=d.get("link", False),
        mac=d.get("mac"),
        addresses=[AddressInfo(**a) for a in d.get("addresses", [])],
        gateway=d.get("gateway"),
        is_default_route=d.get("is_default_route", False),
        upstream_candidate=d.get("upstream_candidate", False),
        hotspot_candidate=d.get("hotspot_candidate", False),
        wifi=wifi,
    )


@router.get("/interfaces", response_model=InterfaceList)
def list_interfaces(request: Request) -> InterfaceList:
    ctx = request.app.state.network_ctx
    return InterfaceList(interfaces=[_to_iface(d) for d in ctx.interfaces()])


@router.get("/status", response_model=NetworkStatus)
def network_status(request: Request) -> NetworkStatus:
    ctx = request.app.state.network_ctx
    probe = request.app.state.connectivity_probe

    route = ctx.default_route()
    upstream_iface = route.get("dev") if route else None
    default_route_str = (
        f"default via {route['gateway']} dev {route['dev']}"
        if route and route.get("gateway")
        else (f"default dev {route['dev']}" if route else None)
    )

    # Find the upstream interface entry for link/has_ip.
    ifaces = {i["name"]: i for i in ctx.interfaces()}
    up = ifaces.get(upstream_iface) if upstream_iface else None
    has_ip = any(a["addr"] for a in (up or {}).get("addresses", []))

    internet, latency_ms = probe.check()
    hs = ctx.hotspot()

    return NetworkStatus(
        upstream=UpstreamStatus(
            interface=upstream_iface,
            link=bool(up.get("link")) if up else False,
            has_ip=bool(has_ip),
            has_default_route=route is not None,
            internet=internet,
            latency_ms=latency_ms,
        ),
        hotspot_present=hs.state == "started",
        default_route=default_route_str,
        ip_forward_v4=read_sysctl_bool("net.ipv4.ip_forward"),
        ip_forward_v6=read_sysctl_bool("net.ipv6.conf.all.forwarding"),
    )
