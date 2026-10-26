"""Device discovery parsing + combination logic."""
from __future__ import annotations

from app.services.device_discovery import (
    discover_clients,
    parse_iw_station_dump,
    parse_ip_neigh_json,
)

STATION_DUMP = """Station aa:bb:cc:dd:ee:ff (on testap)
	inactive time:	100 ms
	rx bytes:	1000000
	rx packets:	1234
	tx bytes:	2000000
	tx packets:	5678
	signal:  	-42 [-44, -46] dBm
	connected time:	3600 seconds
	rx bitrate:	300.0 MBit/s
Station 11:22:33:44:55:66 (on testap)
	inactive time:	200 ms
	rx bytes:	500
	tx bytes:	900
	signal:  	-60 [-62, -63] dBm
	connected time:	10 seconds
"""

NEIGH_JSON = [
    {"dst": "10.42.0.5", "dev": "testap", "lladdr": "aa:bb:cc:dd:ee:ff", "state": ["REACHABLE"]},
    {"dst": "fe80::1", "dev": "testap", "lladdr": "aa:bb:cc:dd:ee:ff", "state": ["STALE"]},
    {"dst": "10.42.0.9", "dev": "testap", "lladdr": "77:88:99:aa:bb:cc", "state": ["REACHABLE"]},
    {"dst": "10.42.0.99", "dev": "testap", "lladdr": "de:ad:be:ef:00:01", "state": ["STALE"]},
]


def test_parse_station_dump():
    stations = parse_iw_station_dump(STATION_DUMP)
    assert len(stations) == 2
    s0 = stations[0]
    assert s0.mac == "aa:bb:cc:dd:ee:ff"
    assert s0.rx_bytes == 1_000_000   # client -> AP (upload)
    assert s0.tx_bytes == 2_000_000   # AP -> client (download)
    assert s0.signal_dbm == -42
    assert s0.connected_time_s == 3600


def test_parse_ip_neigh():
    neigh = parse_ip_neigh_json(NEIGH_JSON)
    macs = [n.mac for n in neigh]
    assert "aa:bb:cc:dd:ee:ff" in macs
    ipv4 = next(n for n in neigh if n.ip == "10.42.0.5")
    assert ipv4.family == "inet"
    assert "REACHABLE" in ipv4.state


def test_discover_clients_combines_sources(monkeypatch):
    monkeypatch.setattr(
        "app.services.device_discovery._run",
        lambda args, timeout=5.0: STATION_DUMP if "station" in args else "",
    )
    monkeypatch.setattr(
        "app.services.device_discovery._run_json",
        lambda args, timeout=5.0: NEIGH_JSON,
    )

    clients = {c.mac: c for c in discover_clients("testap")}
    # Two stations + one REACHABLE neighbor-only fallback (77:88:99...).
    assert "aa:bb:cc:dd:ee:ff" in clients
    assert "11:22:33:44:55:66" in clients
    assert "77:88:99:aa:bb:cc" in clients
    # STALE-only neighbor (de:ad:be:ef:00:01) is NOT included (no false "connected").
    assert "de:ad:be:ef:00:01" not in clients

    c0 = clients["aa:bb:cc:dd:ee:ff"]
    assert c0.ip == "10.42.0.5"          # IP resolved from neighbor table by MAC
    assert c0.tx_bytes == 2_000_000     # download bytes
    assert c0.rx_bytes == 1_000_000     # upload bytes
    assert "ap_sta" in c0.sources and "neighbor" in c0.sources

    # Neighbor-only fallback has no station counters and is flagged neighbor-only.
    c3 = clients["77:88:99:aa:bb:cc"]
    assert c3.sources == ["neighbor"]
    assert c3.tx_bytes is None


def test_discover_clients_no_hotspot_returns_empty():
    assert discover_clients(None) == []


def test_ip_neigh_live_finds_gateway():
    # Integration: the host's default-route neighbor (the gateway) is present.
    from app.services.device_discovery import ip_neigh
    neigh = ip_neigh("eno1")
    ips = [n.ip for n in neigh]
    assert any(ip.startswith("192.168.") for ip in ips), ips
