"""QoS rules API: CRUD. The privileged helper applies each change; on helper
failure the endpoint returns 503 (not a silent fallback).
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..core.exceptions import NotFoundError
from ..schemas import QoSRuleList

router = APIRouter(prefix="/qos", tags=["qos"])


class RuleCreate(BaseModel):
    device_id: str
    dl_limit_mbps: float | None = Field(default=None, ge=0, le=10000)
    ul_limit_mbps: float | None = Field(default=None, ge=0, le=10000)
    priority: str = "normal"
    enabled: bool = True


class RuleUpdate(BaseModel):
    dl_limit_mbps: float | None = Field(default=None, ge=0, le=10000)
    ul_limit_mbps: float | None = Field(default=None, ge=0, le=10000)
    priority: str | None = None
    enabled: bool | None = None


@router.get("/rules", response_model=QoSRuleList)
def list_rules(request: Request):
    rules = request.app.state.qos_service.list_rules()
    # QoSRuleList expects QoSRule items; emit as a plain dict list for the model.
    return {"rules": rules}


@router.post("/rules")
def create_rule(body: RuleCreate, request: Request):
    return request.app.state.qos_service.set_device_qos(
        body.device_id, body.dl_limit_mbps, body.ul_limit_mbps, body.priority, body.enabled
    )


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdate, request: Request):
    existing = request.app.state.qos_service.get_rule(rule_id)
    if not existing:
        raise NotFoundError(f"rule {rule_id} not found")
    return request.app.state.qos_service.set_device_qos(
        existing["device_id"],
        body.dl_limit_mbps if body.dl_limit_mbps is not None else existing["dl_limit_mbps"],
        body.ul_limit_mbps if body.ul_limit_mbps is not None else existing["ul_limit_mbps"],
        body.priority or existing["priority"],
        body.enabled if body.enabled is not None else existing["enabled"],
    )


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str, request: Request):
    if not request.app.state.qos_service.delete_rule(rule_id):
        raise NotFoundError(f"rule {rule_id} not found")
    return {"ok": True}
