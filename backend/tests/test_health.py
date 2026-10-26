"""Health, system info, and WebSocket smoke tests."""
from __future__ import annotations


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["helper"] in ("reachable", "unreachable", "unknown")
    assert isinstance(body["uptime_s"], (int, float))
    assert body["uptime_s"] >= 0


def test_api_root(client):
    r = client.get("/api")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "version" in body


def test_system_info(client):
    r = client.get("/api/system/info")
    assert r.status_code == 200
    body = r.json()
    # On a real Linux host these must be populated (not None/empty).
    assert body["hostname"]
    assert body["kernel"]
    assert body["os"]
    assert body["cpu_count"] and body["cpu_count"] > 0
    assert body["mem_total_mb"] and body["mem_total_mb"] > 0
    # NetworkManager is present on this host.
    assert body["nm_version"]


def test_websocket_sends_real_snapshot(client):
    with client.websocket_connect("/ws/monitor") as ws:
        data = ws.receive_json()
    assert data["ts"]
    # Real aggregate rate: a number (>=0) once a prior sample exists, or None on
    # the very first tick. Either is honest — never negative or fabricated.
    dl = data["aggregate"]["dl_bps"]
    assert dl is None or (isinstance(dl, (int, float)) and dl >= 0)
    # No AP is expected during tests on the host.
    assert data["hotspot"]["state"] in ("stopped", "started")
    assert data["upstream"]["internet"] in ("ok", "limited", "none", "unknown")
    assert isinstance(data["warnings"], list)


def test_websocket_ping_pong(client):
    with client.websocket_connect("/ws/monitor") as ws:
        ws.send_text("ping")
        # The monitor may interleave snapshots before the pong arrives.
        seen_pong = False
        for _ in range(10):
            msg = ws.receive_text()
            if msg == "pong":
                seen_pong = True
                break
        assert seen_pong
