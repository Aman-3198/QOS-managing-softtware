"""QoS service orchestration with the helper mocked (no root needed)."""
from __future__ import annotations

from app.services.qos_service import QoSService
from app.services.device_service import DeviceService
from app.services.network_info import HotspotObservation, NetworkContext
from app.core.exceptions import ValidationError


def _svc(monkeypatch, hotspot_on=True):
    net = NetworkContext()
    monkeypatch.setattr(net, "hotspot", lambda: HotspotObservation(
        state="started" if hotspot_on else "stopped",
        hotspot_interface="testap" if hotspot_on else None,
    ))
    monkeypatch.setattr(net, "default_route_iface", lambda: "eno1")
    dev = DeviceService(net)
    return QoSService(dev, net), dev, net


def test_set_device_qos_validates_and_applies(monkeypatch, db_ready):
    svc, dev, net = _svc(monkeypatch)
    # Seed a connected device + identity so apply has an IP.
    from app.services.device_discovery import DiscoveredClient
    dev._current["aa:bb:cc:dd:ee:ff"] = DiscoveredClient(
        mac="aa:bb:cc:dd:ee:ff", ip="10.42.0.5", tx_bytes=0, rx_bytes=0, sources=["ap_sta"])
    from app.services.device_service import DeviceService as DS
    # create the identity the service will look up
    import uuid
    from app.database import session_scope
    from app.models import DeviceIdentity
    did = str(uuid.uuid4())
    with session_scope() as s:
        s.add(DeviceIdentity(id=did, mac_last_seen="aa:bb:cc:dd:ee:ff", label="phone"))

    applied = {}
    def fake_call(op, args):
        applied["op"] = op
        applied["args"] = args
        return {"classes": len(args.get("rules", []))}
    monkeypatch.setattr("app.services.qos_service.helper_client.call", fake_call)

    res = svc.set_device_qos(did, dl_limit_mbps=5.0, ul_limit_mbps=2.0, priority="high", enabled=True)
    assert res["state"] == "applied"
    assert applied["op"] == "qos.apply"
    # The helper received the device's rule with its current IP.
    rules = applied["args"]["rules"]
    assert len(rules) == 1
    assert rules[0]["ip"] == "10.42.0.5"
    assert rules[0]["dl_limit_mbps"] == 5.0
    # Rule persisted as applied.
    rlz = svc.list_rules()
    assert rlz and rlz[0]["state"] == "applied" and rlz[0]["priority"] == "high"


def test_invalid_rate_rejected(monkeypatch, db_ready):
    svc, dev, net = _svc(monkeypatch)
    import uuid
    did = str(uuid.uuid4())
    import pytest
    with pytest.raises(ValidationError):
        svc.set_device_qos(did, dl_limit_mbps=0, ul_limit_mbps=None, priority="normal", enabled=True)


def test_helper_failure_marks_rule_failed(monkeypatch, db_ready):
    svc, dev, net = _svc(monkeypatch)
    import uuid
    from app.database import session_scope
    from app.models import DeviceIdentity
    did = str(uuid.uuid4())
    with session_scope() as s:
        s.add(DeviceIdentity(id=did, mac_last_seen="aa:bb:cc:dd:ee:ff"))
    from app.services.device_discovery import DiscoveredClient
    dev._current["aa:bb:cc:dd:ee:ff"] = DiscoveredClient(mac="aa:bb:cc:dd:ee:ff", ip="10.42.0.5", sources=["ap_sta"])

    def boom(op, args):
        raise RuntimeError("helper down")
    monkeypatch.setattr("app.services.qos_service.helper_client.call", boom)
    import pytest
    with pytest.raises(RuntimeError):
        svc.set_device_qos(did, 5.0, 2.0, "normal", True)
    # Rule persisted as failed.
    rlz = svc.list_rules()
    assert rlz and rlz[0]["state"] == "failed"


def test_pause_resume(monkeypatch, db_ready):
    svc, dev, net = _svc(monkeypatch)
    import uuid
    from app.database import session_scope
    from app.models import DeviceIdentity
    did = str(uuid.uuid4())
    with session_scope() as s:
        s.add(DeviceIdentity(id=did, mac_last_seen="aa:bb:cc:dd:ee:ff"))
    from app.services.device_discovery import DiscoveredClient
    dev._current["aa:bb:cc:dd:ee:ff"] = DiscoveredClient(mac="aa:bb:cc:dd:ee:ff", ip="10.42.0.5", sources=["ap_sta"])

    monkeypatch.setattr("app.services.qos_service.helper_client.call", lambda op, a: {"ok": True})
    svc.set_paused(did, True)
    rlz = svc.list_rules()
    assert rlz and rlz[0]["paused"] is True
    svc.set_paused(did, False)
    assert svc.list_rules()[0]["paused"] is False


def test_delete_rule_reapplies(monkeypatch, db_ready):
    svc, dev, net = _svc(monkeypatch)
    import uuid
    from app.database import session_scope
    from app.models import DeviceIdentity
    did = str(uuid.uuid4())
    with session_scope() as s:
        s.add(DeviceIdentity(id=did, mac_last_seen="aa:bb:cc:dd:ee:ff"))
    from app.services.device_discovery import DiscoveredClient
    dev._current["aa:bb:cc:dd:ee:ff"] = DiscoveredClient(mac="aa:bb:cc:dd:ee:ff", ip="10.42.0.5", sources=["ap_sta"])
    monkeypatch.setattr("app.services.qos_service.helper_client.call", lambda op, a: {"ok": True})
    svc.set_device_qos(did, 5.0, 2.0, "normal", True)
    rid = svc.list_rules()[0]["id"]
    assert svc.delete_rule(rid) is True
    assert svc.list_rules() == []
