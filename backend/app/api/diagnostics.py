"""Diagnostics API. Export form omits secrets (only check results)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("")
def diagnostics(request: Request):
    return request.app.state.diagnostics_service.run()


@router.get("/export", response_class=PlainTextResponse)
def export(request: Request):
    result = request.app.state.diagnostics_service.run()
    lines = ["# Smart QoS Manager diagnostics export (no secrets)", ""]
    for c in result["checks"]:
        lines.append(f"{c['status'].upper()}\t{c['name']}\t{c['detail']}")
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain",
                             headers={"Content-Disposition": "attachment; filename=smartqos-diagnostics.txt"})
