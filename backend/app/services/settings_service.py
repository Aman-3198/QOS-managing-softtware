"""Application settings (non-secret key/value in app_setting)."""
from __future__ import annotations

DEFAULTS = {
    "speed_unit": "Mbps",
    "data_unit": "auto",
    "history_retention_days": "30",
    "dashboard_bind": "127.0.0.1",
}


class SettingsService:
    def get_all(self) -> dict:
        from ..database import session_scope
        from ..models import AppSetting

        out = dict(DEFAULTS)
        try:
            with session_scope() as s:
                for row in s.query(AppSetting).all():
                    out[row.key] = row.value
        except Exception:
            pass
        return out

    def update(self, changes: dict) -> dict:
        from ..database import session_scope
        from ..models import AppSetting
        from datetime import datetime, timezone

        allowed = set(DEFAULTS.keys())
        with session_scope() as s:
            for k, v in changes.items():
                if k not in allowed:
                    continue
                row = s.query(AppSetting).filter_by(key=k).first()
                if row is None:
                    s.add(AppSetting(key=k, value=str(v), updated_at=datetime.now(timezone.utc)))
                else:
                    row.value = str(v)
        return self.get_all()
