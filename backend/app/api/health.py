"""Health endpoint — the one intentionally public endpoint."""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from sqlalchemy import text

from .. import __version__
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    started = getattr(request.app.state, "started_at", None) or time.time()
    # DB reachability check (cheap; uses existing engine).
    db_state = "ok"
    try:
        from ..database import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_state = "error"

    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_s=round(time.time() - started, 2),
        helper=_helper_state(),
        db=db_state,
    )


def _helper_state() -> str:
    try:
        from ..services import helper_client

        return "reachable" if helper_client.is_available() else "unreachable"
    except Exception:
        return "unreachable"
