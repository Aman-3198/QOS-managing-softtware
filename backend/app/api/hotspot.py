"""Hotspot API: status, start, stop. Privileged ops go through the helper."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import HotspotStartRequest, HotspotStatus

router = APIRouter(prefix="/hotspot", tags=["hotspot"])


@router.get("/status", response_model=HotspotStatus)
def hotspot_status(request: Request) -> HotspotStatus:
    return request.app.state.hotspot_service.status()


@router.post("/start")
def hotspot_start(body: HotspotStartRequest, request: Request) -> dict:
    return request.app.state.hotspot_service.start(
        ssid=body.ssid, password=body.password,
        hotspot_interface=body.hotspot_interface,
        upstream_interface=body.upstream_interface,
        band=body.band, channel=body.channel, security=body.security,
    )


@router.post("/stop")
def hotspot_stop(request: Request) -> dict:
    return request.app.state.hotspot_service.stop()


@router.post("/grant")
def hotspot_grant(request: Request) -> dict:
    """Open a terminal to start the privileged helper (user types sudo password).
    The terminal auto-closes once the helper is up."""
    return request.app.state.hotspot_service.grant_permission()


@router.post("/restart-helper")
def restart_helper(request: Request) -> dict:
    """Ask the running helper to re-exec itself with the latest code on disk.
    Works without any user interaction — the helper re-execs via os.execv."""
    from ..services import helper_client
    return helper_client.restart()
