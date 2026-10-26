"""Smart QoS policies (Section 11).

Policies are scheduling/ceiling preferences applied over the user's existing
per-device rules. We do NOT claim application identification (no DPI) — each
policy clearly states what it changes. Apply snapshots the current rules for
revert; revert restores them.

Built-ins:
- balanced:        keep user-configured limits and priorities (no change).
- gaming:           raise configured devices to high scheduling priority.
- streaming:        raise configured devices to high scheduling priority.
- save_bandwidth:   halve configured per-device ceilings (stricter caps).
- custom:           a user-saved named snapshot of rules.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from ..core.exceptions import NotFoundError, ValidationError
from .qos_service import QoSService

log = logging.getLogger("smartqos.policy")

BUILTINS = {
    "balanced": "Keep user-configured limits and priorities.",
    "gaming": "Raise configured devices to HIGH scheduling priority (preference, not a latency guarantee).",
    "streaming": "Raise configured devices to HIGH scheduling priority.",
    "save_bandwidth": "Halve configured per-device ceilings (stricter caps).",
}


class PolicyService:
    def __init__(self, qos_service: QoSService) -> None:
        self.qos = qos_service
        self._revert_snapshot: dict[str, dict] | None = None  # device_id -> rule fields

    def list_policies(self) -> list[dict]:
        out = [{"name": k, "description": v, "builtin": True} for k, v in BUILTINS.items()]
        from ..database import session_scope
        from ..models import SavedPolicy
        try:
            with session_scope() as s:
                for p in s.query(SavedPolicy).all():
                    out.append({"name": p.name, "description": p.description, "builtin": False})
        except Exception:
            pass
        return out

    def _current_rules(self) -> list[dict]:
        from ..database import session_scope
        from ..models import QoSRule

        with session_scope() as s:
            return [{
                "device_id": qr.device_id, "dl_limit_mbps": qr.dl_limit_mbps,
                "ul_limit_mbps": qr.ul_limit_mbps, "priority": qr.priority,
                "enabled": qr.enabled, "paused": qr.paused,
            } for qr in s.query(QoSRule).all()]

    def _transform(self, name: str, rules: list[dict]) -> list[dict]:
        out = [dict(r) for r in rules]
        if name == "balanced":
            return out
        if name in ("gaming", "streaming"):
            for r in out:
                r["priority"] = "high"
            return out
        if name == "save_bandwidth":
            for r in out:
                if r["dl_limit_mbps"]:
                    r["dl_limit_mbps"] = round(r["dl_limit_mbps"] / 2, 2)
                if r["ul_limit_mbps"]:
                    r["ul_limit_mbps"] = round(r["ul_limit_mbps"] / 2, 2)
            return out
        # custom: leave as-is (the saved snapshot is applied directly)
        return out

    def preview(self, name: str) -> dict:
        current = self._current_rules()
        if name not in BUILTINS:
            # custom: load saved rules
            saved = self._load_custom(name)
            if saved is None:
                raise NotFoundError(f"policy {name} not found")
            return {"policy": name, "current": current, "after": saved,
                    "diff": _diff(current, saved)}
        after = self._transform(name, current)
        return {"policy": name, "current": current, "after": after, "diff": _diff(current, after)}

    def apply(self, name: str) -> dict:
        current = self._current_rules()
        self._revert_snapshot = {r["device_id"]: r for r in current}
        if name not in BUILTINS:
            after = self._load_custom(name)
            if after is None:
                raise NotFoundError(f"policy {name} not found")
        else:
            after = self._transform(name, current)
        self._write_rules(after)
        try:
            self.qos._apply_desired()
        except Exception:
            # rollback DB to snapshot
            self._write_rules(list(self._revert_snapshot.values()))
            raise
        return {"applied": name, "changed": _diff(current, after)}

    def revert(self) -> dict:
        if not self._revert_snapshot:
            raise ValidationError("no policy to revert (no snapshot)")
        current = self._current_rules()
        self._write_rules(list(self._revert_snapshot.values()))
        try:
            self.qos._apply_desired()
        except Exception:
            self._write_rules(current)
            raise
        return {"reverted_to": self._revert_snapshot}

    def save_custom(self, name: str, description: str | None) -> dict:
        rules = self._current_rules()
        from ..database import session_scope
        from ..models import SavedPolicy
        with session_scope() as s:
            row = s.query(SavedPolicy).filter_by(name=name).first()
            if row is None:
                import uuid
                row = SavedPolicy(id=str(uuid.uuid4()), name=name, description=description,
                                  rules_json=json.dumps(rules), is_builtin=False)
                s.add(row)
            else:
                row.rules_json = json.dumps(rules)
                row.description = description
        return {"saved": name, "rules": len(rules)}

    # --- helpers ---
    def _load_custom(self, name: str) -> list[dict] | None:
        from ..database import session_scope
        from ..models import SavedPolicy
        with session_scope() as s:
            row = s.query(SavedPolicy).filter_by(name=name).first()
            if not row:
                return None
            return json.loads(row.rules_json)

    def _write_rules(self, rules: list[dict]) -> None:
        from ..database import session_scope
        from ..models import QoSRule
        with session_scope() as s:
            existing = {qr.device_id: qr for qr in s.query(QoSRule).all()}
            seen: set[str] = set()
            for r in rules:
                did = r["device_id"]
                seen.add(did)
                qr = existing.get(did)
                if qr is None:
                    import uuid
                    qr = QoSRule(id=str(uuid.uuid4()), device_id=did, state="pending")
                    s.add(qr)
                qr.dl_limit_mbps = r.get("dl_limit_mbps")
                qr.ul_limit_mbps = r.get("ul_limit_mbps")
                qr.priority = r.get("priority", "normal")
                qr.enabled = r.get("enabled", True)
                qr.paused = r.get("paused", False)
            for did, qr in existing.items():
                if did not in seen:
                    s.delete(qr)


def _diff(current: list[dict], after: list[dict]) -> list[dict]:
    cmap = {r["device_id"]: r for r in current}
    amap = {r["device_id"]: r for r in after}
    changes = []
    for did, a in amap.items():
        c = cmap.get(did, {})
        diffs = {k: (c.get(k), a.get(k)) for k in ("dl_limit_mbps", "ul_limit_mbps", "priority")
                 if c.get(k) != a.get(k)}
        if diffs or not c:
            changes.append({"device_id": did, "changes": diffs})
    for did in cmap:
        if did not in amap:
            changes.append({"device_id": did, "removed": True})
    return changes
