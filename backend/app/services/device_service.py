"""Device service: combines live discovery with stable identities, per-device
rate accumulation, and DB persistence of identities/labels/sessions.

Identity model (see models/__init__.py): a stable internal UUID keyed by MAC.
MAC is an *identity hint*, not the key — MAC randomization means a device may
present a new MAC and appear as a new device (a disclosed limitation; we never
guess). The hotspot client IP is NOT an identity; it can change across DHCP
leases, and the same MAC keeps the same identity + label.

Per-device rates come from AP station counters (device_discovery), not tc
classes (those arrive in Phase 5 for shaping). These are real, independent
measurements — never summed with the upstream aggregate (no double counting).
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from ..core.rate import compute_bps
from ..schemas import DeviceInfo, DeviceSnapshot
from .device_discovery import DiscoveredClient, discover_clients
from .network_info import NetworkContext

log = logging.getLogger("smartqos.devices")

_DB_UPSERT_INTERVAL_S = 5.0


class DeviceService:
    def __init__(self, network_ctx: NetworkContext) -> None:
        self.net = network_ctx
        # mac -> per-device rate state
        self._acc: dict[str, dict] = {}
        # mac -> latest DiscoveredClient
        self._current: dict[str, DiscoveredClient] = {}
        self._last_db_ts: float = 0.0
        self._last_sample_ts: float = 0.0
        self._mac_to_id: dict[str, str] = {}

    # ------------------------------------------------------------------ tick
    def tick(self) -> list[DeviceSnapshot]:
        """Called by the monitor each second. Updates accumulators + returns
        the minimal per-device snapshot for the WebSocket stream."""
        hs = self.net.hotspot()
        iface = hs.hotspot_interface if hs.state == "started" else None
        clients = discover_clients(iface)
        now = time.monotonic()
        live_macs: set[str] = set()
        snapshots: list[DeviceSnapshot] = []

        for c in clients:
            mac = c.mac
            live_macs.add(mac)
            self._current[mac] = c
            self._update_acc(mac, c.tx_bytes, c.rx_bytes, now)
            acc = self._acc[mac]
            snapshots.append(DeviceSnapshot(
                id=mac,  # transient id for the snapshot; the API resolves to the DB id
                dl_bps=acc.get("dl_bps"),
                ul_bps=acc.get("ul_bps"),
                dl_bytes=acc.get("dl_total", 0),
                ul_bytes=acc.get("ul_total", 0),
                state="connected",
                paused=False,  # pause is Phase 7
            ))

        # Prune accumulators for clients that have disconnected.
        for mac in list(self._acc.keys()):
            if mac not in live_macs:
                self._acc.pop(mac, None)
        for mac in list(self._current.keys()):
            if mac not in live_macs:
                self._current.pop(mac, None)

        # Throttled DB upsert of identities + sessions.
        if now - self._last_db_ts >= _DB_UPSERT_INTERVAL_S:
            self._last_db_ts = now
            self._upsert_db(iface, clients)

        # Throttled per-device sample persistence (Phase 8 analytics source).
        if now - self._last_sample_ts >= _DB_UPSERT_INTERVAL_S:
            self._last_sample_ts = now
            self._persist_device_samples(iface)

        return snapshots

    def _persist_device_samples(self, iface: str | None) -> None:
        try:
            from ..database import session_scope
            from ..models import DeviceIdentity, TrafficSample

            with session_scope() as s:
                for mac, c in self._current.items():
                    dev_id = self._mac_to_id.get(mac)
                    if dev_id is None:
                        ident = s.query(DeviceIdentity).filter_by(mac_last_seen=mac).first()
                        if ident is None:
                            continue
                        dev_id = ident.id
                        self._mac_to_id[mac] = dev_id
                    acc = self._acc.get(mac, {})
                    s.add(TrafficSample(
                        scope="device", scope_id=dev_id, iface=iface,
                        dl_bytes=acc.get("dl_total", 0), ul_bytes=acc.get("ul_total", 0),
                        dl_bps=acc.get("dl_bps"), ul_bps=acc.get("ul_bps"),
                    ))
        except Exception:
            log.debug("device sample persist failed", exc_info=True)

    def _update_acc(self, mac: str, tx_bytes: int | None, rx_bytes: int | None, ts: float) -> None:
        st = self._acc.setdefault(mac, {"dl_total": 0, "ul_total": 0, "dl_bps": None, "ul_bps": None})
        prev_tx = st.get("last_tx")
        prev_rx = st.get("last_rx")
        prev_ts = st.get("last_ts")
        st["last_tx"] = tx_bytes
        st["last_rx"] = rx_bytes
        st["last_ts"] = ts
        if prev_ts is None or prev_tx is None or prev_rx is None or tx_bytes is None or rx_bytes is None:
            st["dl_bps"] = None
            st["ul_bps"] = None
            return
        dt = ts - prev_ts
        # download = AP -> client (tx); upload = client -> AP (rx)
        st["dl_bps"] = compute_bps(prev_tx, tx_bytes, dt)
        st["ul_bps"] = compute_bps(prev_rx, rx_bytes, dt)
        dl_d = tx_bytes - prev_tx
        ul_d = rx_bytes - prev_rx
        if dl_d > 0:
            st["dl_total"] += dl_d
        if ul_d > 0:
            st["ul_total"] += ul_d

    # ------------------------------------------------------------------ DB
    def _upsert_db(self, iface: str | None, clients: list[DiscoveredClient]) -> None:
        try:
            from ..database import session_scope
            from ..models import DeviceIdentity, DeviceSession

            now = datetime.now(timezone.utc)
            with session_scope() as s:
                for c in clients:
                    ident = s.query(DeviceIdentity).filter_by(mac_last_seen=c.mac).first()
                    if ident is None:
                        ident = DeviceIdentity(
                            id=str(uuid.uuid4()),
                            mac_last_seen=c.mac,
                            label=c.hostname,
                            first_seen=now,
                            last_seen=now,
                        )
                        s.add(ident)
                        s.flush()
                        sess = DeviceSession(
                            device_id=ident.id, ip=c.ip, mac=c.mac, iface=iface,
                            connected_at=now, last_seen=now, paused=False,
                            dl_bytes=0, ul_bytes=0,
                        )
                        s.add(sess)
                    else:
                        ident.last_seen = now
                        sess = s.query(DeviceSession).filter_by(device_id=ident.id).first()
                        if sess is None:
                            sess = DeviceSession(
                                device_id=ident.id, ip=c.ip, mac=c.mac, iface=iface,
                                connected_at=now, last_seen=now, paused=False,
                                dl_bytes=0, ul_bytes=0,
                            )
                            s.add(sess)
                        else:
                            # Reconnected: if it was idle, refresh connected_at.
                            sess.ip = c.ip
                            sess.mac = c.mac
                            sess.iface = iface
                            sess.last_seen = now
        except Exception:
            log.debug("device db upsert failed", exc_info=True)

    # ------------------------------------------------------------------ API
    def list_devices(self) -> list[DeviceInfo]:
        """Full DeviceInfo for currently-connected clients, enriched from DB
        (label, qos limits, priority, identity id)."""
        from ..database import session_scope
        from ..models import DeviceIdentity, QoSRule

        out: list[DeviceInfo] = []
        if not self._current:
            return out
        try:
            with session_scope() as s:
                for mac, c in self._current.items():
                    ident = s.query(DeviceIdentity).filter_by(mac_last_seen=mac).first()
                    device_id = ident.id if ident else mac
                    label = ident.label if ident else None
                    rule = (
                        s.query(QoSRule).filter_by(device_id=device_id).first()
                        if ident else None
                    )
                    acc = self._acc.get(mac, {})
                    connected_at = None
                    last_seen = None
                    if ident:
                        from ..models import DeviceSession
                        ds = s.query(DeviceSession).filter_by(device_id=ident.id).first()
                        if ds:
                            connected_at = ds.connected_at
                            last_seen = ds.last_seen
                    out.append(DeviceInfo(
                        id=device_id,
                        label=label,
                        ip=c.ip,
                        mac=c.mac,
                        state="connected",
                        connected_at=connected_at,
                        last_seen=last_seen,
                        dl_bps=acc.get("dl_bps"),
                        ul_bps=acc.get("ul_bps"),
                        dl_bytes=acc.get("dl_total", 0),
                        ul_bytes=acc.get("ul_total", 0),
                        dl_limit_mbps=rule.dl_limit_mbps if rule else None,
                        ul_limit_mbps=rule.ul_limit_mbps if rule else None,
                        priority=rule.priority if rule else "normal",
                        paused=False,
                        sources=c.sources,
                        hostname=c.hostname,
                        signal_dbm=c.signal_dbm,
                        connected_time_s=c.connected_time_s,
                    ))
        except Exception:
            log.debug("list_devices failed", exc_info=True)
        return out

    def get_device(self, device_id: str) -> DeviceInfo | None:
        for d in self.list_devices():
            if d.id == device_id:
                return d
        return None

    def rename_device(self, device_id: str, label: str | None) -> DeviceInfo | None:
        from ..database import session_scope
        from ..models import DeviceIdentity

        try:
            with session_scope() as s:
                ident = s.get(DeviceIdentity, device_id)
                if ident is None:
                    return None
                ident.label = label
        except Exception:
            log.debug("rename_device failed", exc_info=True)
            return None
        return self.get_device(device_id)
