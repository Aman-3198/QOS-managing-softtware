"""Policies API: list, preview (dry-run), apply, revert, save custom."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..core.exceptions import NotFoundError

router = APIRouter(prefix="/policies", tags=["policies"])


class SaveBody(BaseModel):
    name: str
    description: str | None = None


@router.get("")
def list_policies(request: Request):
    return {"policies": request.app.state.policy_service.list_policies()}


@router.get("/{name}/preview")
def preview_policy(name: str, request: Request):
    return request.app.state.policy_service.preview(name)


@router.post("/{name}/apply")
def apply_policy(name: str, request: Request):
    return request.app.state.policy_service.apply(name)


@router.post("/revert")
def revert_policy(request: Request):
    return request.app.state.policy_service.revert()


@router.post("/save")
def save_policy(body: SaveBody, request: Request):
    return request.app.state.policy_service.save_custom(body.name, body.description)
