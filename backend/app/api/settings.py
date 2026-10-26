"""Application settings API (non-secret)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    speed_unit: str | None = None
    data_unit: str | None = None
    history_retention_days: int | None = None
    dashboard_bind: str | None = None


@router.get("")
def get_settings(request: Request):
    return request.app.state.settings_service.get_all()


@router.patch("")
def patch_settings(body: SettingsPatch, request: Request):
    return request.app.state.settings_service.update(body.model_dump(exclude_none=True))
