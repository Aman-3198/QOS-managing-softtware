"""WebSocket router: streams monitor snapshots to dashboard clients.

One subscription per connection (no duplicate polling loops). The client may
send ``ping``; the server replies ``pong``. Dead connections are cleaned up.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])
log = logging.getLogger("smartqos.ws")


@router.websocket("/ws/monitor")
async def monitor_ws(websocket: WebSocket) -> None:
    # Auth (when a password is configured): require a valid session cookie.
    auth = getattr(websocket.app.state, "auth_service", None)
    if auth is not None and auth.has_password():
        token = websocket.cookies.get("sqm_session")
        if not auth.verify_session(token):
            await websocket.close(code=4401)
            return
    await websocket.accept()
    hub = websocket.app.state.monitor_hub
    queue = await hub.subscribe()

    async def sender() -> None:
        while True:
            snapshot = await queue.get()
            await websocket.send_text(snapshot.model_dump_json())

    async def reader() -> None:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")

    sender_task = asyncio.create_task(sender(), name="sqm-ws-sender")
    reader_task = asyncio.create_task(reader(), name="sqm-ws-reader")
    try:
        done, pending = await asyncio.wait(
            {sender_task, reader_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive
        log.debug("websocket error", exc_info=True)
    finally:
        hub.unsubscribe(queue)
        for t in (sender_task, reader_task):
            if not t.done():
                t.cancel()
