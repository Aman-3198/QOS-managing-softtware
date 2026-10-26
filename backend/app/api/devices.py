"""Devices API: list, get, and rename connected hotspot clients.

Device discovery is live (services/device_service). Per-device speeds come from
AP station counters when a hotspot is running; with no hotspot the list is empty
(honest empty state). Limits/priority read-back from DB (enforced in Phase 5).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..core.exceptions import NotFoundError
from ..schemas import DeviceInfo, DeviceList, DevicePatch

router = APIRouter(prefix="/devices", tags=["devices"])


def _service(request: Request):
    return request.app.state.device_service


@router.get("", response_model=DeviceList)
def list_devices(request: Request) -> DeviceList:
    return DeviceList(devices=_service(request).list_devices())


@router.get("/{device_id}", response_model=DeviceInfo)
def get_device(device_id: str, request: Request) -> DeviceInfo:
    d = _service(request).get_device(device_id)
    if d is None:
        raise NotFoundError(f"device {device_id} not found")
    return d


@router.patch("/{device_id}", response_model=DeviceInfo)
def patch_device(device_id: str, patch: DevicePatch, request: Request) -> DeviceInfo:
    if patch.label is not None and len(patch.label) > 128:
        raise HTTPException(status_code=400, detail="label too long")
    d = _service(request).rename_device(device_id, patch.label)
    if d is None:
        raise NotFoundError(f"device {device_id} not found")
    return d


# --- QoS / access control (Phase 5/7) -------------------------------------
class DeviceQoSBody(BaseModel):
    dl_limit_mbps: float | None = Field(default=None, ge=0, le=10000)
    ul_limit_mbps: float | None = Field(default=None, ge=0, le=10000)
    priority: str = "normal"
    enabled: bool = True


@router.put("/{device_id}/qos")
def set_device_qos(device_id: str, body: DeviceQoSBody, request: Request):
    return request.app.state.qos_service.set_device_qos(
        device_id, body.dl_limit_mbps, body.ul_limit_mbps, body.priority, body.enabled
    )


@router.post("/{device_id}/pause")
def pause_device(device_id: str, request: Request):
    return request.app.state.qos_service.set_paused(device_id, True)


@router.post("/{device_id}/resume")
def resume_device(device_id: str, request: Request):
    return request.app.state.qos_service.set_paused(device_id, False)
