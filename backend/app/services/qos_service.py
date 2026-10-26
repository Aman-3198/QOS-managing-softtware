"""QoS service: validate a user request, build the full desired state from all
rules + live device IPs, ask the privileged helper to apply it, then persist the
result. On helper failure the rule is marked ``failed`` and the previous applied
state is preserved (the helper rolls back app-owned objects).

Pause/resume is represented as a QoSRule with ``paused=True`` (its device gets
nft drop rules and no tc class — traffic is dropped before shaping).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from ..config import settings
from ..core.exceptions import HelperUnavailableError, NotFoundError, ValidationError
from ..core.rate import validate_priority, validate_rate_mbps
from . import helper_client
from .audit_service import log as audit_log
from .device_service import DeviceService
from .network_info import NetworkContext
from .qos_state import DeviceRule

log = logging.getLogger("smartqos.qos")


class QoSService:
    def __init__(self, device_service: DeviceService, network_ctx: NetworkContext) -> None:
        self.devices = device_service
        self.net = network_ctx

    # ------------------------------------------------------------------ build
    def _build_rules_for_apply(self) -> list[DeviceRule]:
        from ..database import session_scope
        from ..models import DeviceIdentity, QoSRule

        rules: list[DeviceRule] = []
        with session_scope() as s:
            for qr in s.query(QoSRule).all():
                ident = s.get(DeviceIdentity, qr.device_id)
                if not ident or not ident.mac_last_seen:
                    continue
                client = self.devices._current.get(ident.mac_last_seen)
                ip = client.ip if client else None
                rules.append(DeviceRule(
                    device_id=qr.device_id, mac=ident.mac_last_seen, ip=ip,
                    dl_limit_mbps=qr.dl_limit_mbps, ul_limit_mbps=qr.ul_limit_mbps,
                    priority=qr.priority, enabled=qr.enabled, paused=qr.paused,
                ))
        return rules

    def _apply_desired(self) -> dict:
        rules = self._build_rules_for_apply()
        hs = self.net.hotspot()
        upstream = self.net.default_route_iface()
        hotspot = hs.hotspot_interface if hs.state == "started" else None
        request = {
            "upstream_iface": upstream,
            "hotspot_iface": hotspot,
            "parent_cap_mbps": settings.qos_parent_cap_mbps,
            "min_rate_mbps": settings.qos_min_rate_mbps,
            "rules": [asdict(r) for r in rules],
        }
        return helper_client.call("qos.apply", request)

    def _set_state(self, state: str, device_ids: set[str] | None = None) -> None:
        from ..database import session_scope
        from ..models import QoSRule

        with session_scope() as s:
            for qr in s.query(QoSRule).all():
                if device_ids is None or qr.device_id in device_ids:
                    qr.state = state
                    if state == "applied":
                        qr.applied_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------ API
    def set_device_qos(
        self, device_id: str, dl_limit_mbps: float | None, ul_limit_mbps: float | None,
        priority: str | None, enabled: bool,
    ) -> dict:
        dl = validate_rate_mbps(dl_limit_mbps, "dl_limit_mbps")
        ul = validate_rate_mbps(ul_limit_mbps, "ul_limit_mbps")
        prio = validate_priority(priority)
        from ..database import session_scope
        from ..models import QoSRule

        with session_scope() as s:
            qr = s.query(QoSRule).filter_by(device_id=device_id).first()
            if qr is None:
                qr = QoSRule(id=str(uuid.uuid4()), device_id=device_id, state="pending")
                s.add(qr)
            qr.dl_limit_mbps = dl
            qr.ul_limit_mbps = ul
            qr.priority = prio
            qr.enabled = enabled
            qr.state = "pending"

        try:
            self._apply_desired()
            self._set_state("applied")
            audit_log("user", "qos.update", target=device_id,
                      after={"dl_limit_mbps": dl, "ul_limit_mbps": ul, "priority": prio, "enabled": enabled})
            return {"state": "applied"}
        except (HelperUnavailableError, RuntimeError) as e:
            self._set_state("failed", {device_id})
            audit_log("user", "qos.update", target=device_id,
                      after={"dl_limit_mbps": dl, "ul_limit_mbps": ul, "priority": prio}, success=False)
            raise

    def set_paused(self, device_id: str, paused: bool) -> dict:
        from ..database import session_scope
        from ..models import QoSRule

        with session_scope() as s:
            qr = s.query(QoSRule).filter_by(device_id=device_id).first()
            if qr is None:
                if not paused:
                    return {"paused": False}     # nothing to resume
                qr = QoSRule(id=str(uuid.uuid4()), device_id=device_id, state="pending",
                             dl_limit_mbps=None, ul_limit_mbps=None, priority="normal")
                s.add(qr)
            qr.paused = paused
            qr.state = "pending"
        try:
            self._apply_desired()
            self._set_state("applied")
            return {"paused": paused}
        except (HelperUnavailableError, RuntimeError):
            self._set_state("failed", {device_id})
            raise

    def list_rules(self) -> list[dict]:
        from ..database import session_scope
        from ..models import QoSRule

        out: list[dict] = []
        with session_scope() as s:
            for qr in s.query(QoSRule).all():
                out.append({
                    "id": qr.id, "device_id": qr.device_id,
                    "dl_limit_mbps": qr.dl_limit_mbps,
                    "ul_limit_mbps": qr.ul_limit_mbps,
                    "priority": qr.priority, "enabled": qr.enabled,
                    "paused": qr.paused, "state": qr.state,
                    "applied_at": qr.applied_at.isoformat() if qr.applied_at else None,
                })
        return out

    def get_rule(self, rule_id: str) -> dict | None:
        from ..database import session_scope
        from ..models import QoSRule

        with session_scope() as s:
            qr = s.get(QoSRule, rule_id)
            if not qr:
                return None
            return {
                "id": qr.id, "device_id": qr.device_id,
                "dl_limit_mbps": qr.dl_limit_mbps,
                "ul_limit_mbps": qr.ul_limit_mbps,
                "priority": qr.priority, "enabled": qr.enabled,
                "paused": qr.paused, "state": qr.state,
                "applied_at": qr.applied_at.isoformat() if qr.applied_at else None,
            }

    def delete_rule(self, rule_id: str) -> bool:
        from ..database import session_scope
        from ..models import QoSRule

        device_id: str | None = None
        with session_scope() as s:
            qr = s.get(QoSRule, rule_id)
            if not qr:
                return False
            device_id = qr.device_id
            s.delete(qr)
        try:
            self._apply_desired()
            self._set_state("applied")
        except (HelperUnavailableError, RuntimeError):
            pass  # rule deleted from DB; helper may keep shaping until re-applied
        return True

    def clear_all(self) -> dict:
        return helper_client.call("qos.clear", {"interfaces": [
            self.net.default_route_iface(),
            (self.net.hotspot().hotspot_interface if self.net.hotspot().state == "started" else None),
        ]})
