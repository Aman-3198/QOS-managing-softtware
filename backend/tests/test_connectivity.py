"""Connectivity probe classification (mocked sockets, no real network)."""
from __future__ import annotations

import socket

from app.services.connectivity import ConnectivityProbe


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _make_probe(monkeypatch, dns_ok, connect_ok, latency_ms=5.0):
    probe = ConnectivityProbe(
        host="example.test", fallback_hosts=[], port=443,
        timeout_s=0.2, ttl_s=0.0,
    )

    def fake_create_connection(addr, timeout=None, **k):
        if connect_ok:
            return _FakeConn()
        # DNS resolution failure vs connect failure are distinguished by the
        # exception type: gaierror => DNS failed; other OSError => resolved.
        if dns_ok:
            raise OSError("connect refused")
        raise socket.gaierror("dns fail")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    return probe


def test_ok_when_dns_and_tcp_succeed(monkeypatch):
    probe = _make_probe(monkeypatch, dns_ok=True, connect_ok=True)
    internet, latency = probe.check()
    assert internet == "ok"
    assert latency is not None and latency >= 0


def test_limited_when_dns_ok_but_tcp_fails(monkeypatch):
    probe = _make_probe(monkeypatch, dns_ok=True, connect_ok=False)
    internet, latency = probe.check()
    assert internet == "limited"
    assert latency is None


def test_none_when_dns_fails(monkeypatch):
    probe = _make_probe(monkeypatch, dns_ok=False, connect_ok=False)
    internet, latency = probe.check()
    assert internet == "none"
    assert latency is None


def test_fallback_target_recovers(monkeypatch):
    # Primary target's TCP fails (DNS ok) but fallback connects => "ok".
    calls: list[str] = []

    def fake_create_connection(addr, timeout=None, **k):
        calls.append(addr[0])
        if addr[0] == "primary.test":
            raise OSError("refused")
        return _FakeConn()

    probe = ConnectivityProbe(
        host="primary.test", fallback_hosts=["backup.test"], port=443,
        timeout_s=0.2, ttl_s=0.0,
    )
    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    internet, latency = probe.check()
    assert internet == "ok"
    assert calls == ["primary.test", "backup.test"]


def test_result_is_cached(monkeypatch):
    # ttl_s=60 so the second call must not re-probe.
    probe = ConnectivityProbe(
        host="example.test", fallback_hosts=[], port=443,
        timeout_s=0.2, ttl_s=60.0,
    )
    calls = {"n": 0}

    def fake_create_connection(addr, timeout=None, **k):
        calls["n"] += 1
        return _FakeConn()

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    probe.check()
    probe.check()
    assert calls["n"] == 1  # cached: only one connect across two calls
