"""Audit log writer. Append-only events with secret redaction (no password /
token fields are ever recorded). Best-effort: a DB error never breaks the
calling operation."""
from __future__ import annotations

import json
from datetime import datetime, timezone

_SECRET_KEYS = {"password", "psk", "secret", "token"}


def _redact(obj: dict | None) -> str | None:
    if obj is None:
        return None
    clean = {k: ("[REDACTED]" if k.lower() in _SECRET_KEYS else v) for k, v in obj.items()}
    return json.dumps(clean, default=str)


def log(actor: str | None, action: str, target: str | None = None,
        before: dict | None = None, after: dict | None = None, success: bool = True) -> None:
    from ..database import session_scope
    from ..models import AuditEvent
    try:
        with session_scope() as s:
            s.add(AuditEvent(
                actor=actor, action=action, target=target,
                before_json=_redact(before), after_json=_redact(after),
                success=success, ts=datetime.now(timezone.utc),
            ))
    except Exception:
        # Audit must never break the operation it records.
        pass
