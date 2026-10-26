"""Analytics API: history, summary, CSV export."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/history")
def history(request: Request, range: str = "1h", scope: str = "aggregate", device_id: str | None = None):
    return request.app.state.analytics_service.history(range, scope, device_id)


@router.get("/summary")
def summary(request: Request, range: str = "1h"):
    return request.app.state.analytics_service.summary(range)


@router.get("/export", response_class=PlainTextResponse)
def export(request: Request, range: str = "1h"):
    # Traffic counters only; the spec requires exports to omit secrets/tokens.
    csv_text = request.app.state.analytics_service.export_csv(range)
    return PlainTextResponse(csv_text, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=smartqos-export.csv"})
