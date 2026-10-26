"""Device service: stable identity across IP change, per-device rates, rename."""
from __future__ import annotations

from app.services.device_discovery import DiscoveredClient
from app.services.device_service import DeviceService
from app.services.network_info import HotspotObservation, NetworkContext


def _client(mac, ip, tx, rx, hostname=None):
    return DiscoveredClient(
        mac=mac, ip=ip, hostname=hostname, tx_bytes=tx, rx_bytes=rx,
        signal_dbm=-50, connected_time_s=120, sources=["ap_sta", "neighbor"],
    )


def _make_service(monkeypatch, clients_per_call, hotspot_on=True):
    net = NetworkContext()
    monkeypatch.setattr(
        net, "hotspot",
        lambda: HotspotObservation(
            state="started" if hotspot_on else "stopped",
            hotspot_interface="testap" if hotspot_on else None,
        ),
    )
    # Replace the live discovery with our controlled sequence of client lists.
    calls = {"i": 0}

    def fake_discover(iface):
        i = calls["i"]
        calls["i"] += 1
        return clients_per_call[min(i, len(clients_per_call) - 1)]

    monkeypatch.setattr("app.services.device_service.discover_clients", fake_discover)
    return DeviceService(net), calls


def test_no_hotspot_returns_empty(monkeypatch, db_ready):
    svc, _ = _make_service(monkeypatch, [[]], hotspot_on=False)
    svc.tick()
    assert svc.list_devices() == []


def test_per_device_rates_from_station_stats(monkeypatch, db_ready):
    # Two ticks: download = AP->client (tx delta); upload = client->AP (rx delta).
    clients = [
        [_client("aa:bb:cc:dd:ee:ff", "10.42.0.5", tx=1_000_000, rx=500_000)],
        [_client("aa:bb:cc:dd:ee:ff", "10.42.0.5", tx=2_000_000, rx=600_000)],
    ]
    svc, _ = _make_service(monkeypatch, clients)
    svc.tick()                              # baseline (no rate yet)
    snaps = svc.tick()                      # 1,000,000 tx bytes in ~0s -> rate computed
    assert len(snaps) == 1
    # Download rate from tx delta (AP -> client). Exact bps depends on dt (~0),
    # so just assert it's a non-negative number (real, not None/fabricated).
    assert snaps[0].dl_bps is not None and snaps[0].dl_bps >= 0
    assert snaps[0].ul_bps is not None and snaps[0].ul_bps >= 0
    devs = svc.list_devices()
    assert devs[0].dl_bytes == 1_000_000     # accumulated tx delta
    assert devs[0].ul_bytes == 100_000       # accumulated rx delta


def test_identity_stable_across_ip_change(monkeypatch, db_ready):
    # Same MAC, IP changes (new DHCP lease): identity + label must persist.
    clients = [
        [_client("aa:bb:cc:dd:ee:ff", "10.42.0.5", tx=0, rx=0, hostname="phone")],
        [_client("aa:bb:cc:dd:ee:ff", "10.42.0.9", tx=10, rx=10)],  # IP changed
    ]
    svc, _ = _make_service(monkeypatch, clients)
    svc.tick()
    first = svc.list_devices()[0]
    device_id = first.id
    assert first.ip == "10.42.0.5"

    # Rename using the stable id, then change the IP.
    renamed = svc.rename_device(device_id, "My Phone")
    assert renamed is not None and renamed.label == "My Phone"

    svc.tick()  # IP now 10.42.0.9
    second = svc.list_devices()[0]
    assert second.id == device_id          # SAME identity despite IP change
    assert second.ip == "10.42.0.9"
    assert second.label == "My Phone"        # label persisted


def test_disconnected_client_pruned(monkeypatch, db_ready):
    clients = [
        [_client("aa:bb:cc:dd:ee:ff", "10.42.0.5", tx=0, rx=0)],
        [],  # client disconnected
    ]
    svc, _ = _make_service(monkeypatch, clients)
    svc.tick()
    assert len(svc.list_devices()) == 1
    svc.tick()
    assert svc.list_devices() == []          # disconnected client removed


def test_get_device_unknown_returns_none(monkeypatch, db_ready):
    svc, _ = _make_service(monkeypatch, [[]], hotspot_on=False)
    assert svc.get_device("nope") is None
    assert svc.rename_device("nope", "x") is None
