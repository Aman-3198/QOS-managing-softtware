"""Database init + basic CRUD smoke test (isolated temp DB)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.database import init_db, session_scope
from app.models import AppSetting, AuditEvent, DeviceIdentity, QoSRule


def test_init_db_creates_tables(tmp_db_path):
    init_db(f"sqlite:///{tmp_db_path}")
    # A second init should be idempotent.
    init_db(f"sqlite:///{tmp_db_path}")


def test_crud_app_setting(tmp_db_path):
    init_db(f"sqlite:///{tmp_db_path}")
    with session_scope() as s:
        s.add(AppSetting(key="units", value="Mbps", updated_at=datetime.now(timezone.utc)))
        s.commit() if False else None  # session_scope commits; just add
    with session_scope() as s:
        row = s.query(AppSetting).filter_by(key="units").first()
        assert row is not None
        assert row.value == "Mbps"


def test_device_and_qos_rule_relationship(tmp_db_path):
    init_db(f"sqlite:///{tmp_db_path}")
    dev_id = str(uuid.uuid4())
    rule_id = str(uuid.uuid4())
    with session_scope() as s:
        s.add(DeviceIdentity(id=dev_id, label="My Phone"))
        s.add(
            QoSRule(
                id=rule_id,
                device_id=dev_id,
                dl_limit_mbps=5.0,
                ul_limit_mbps=1.0,
                priority="high",
                enabled=True,
                state="pending",
            )
        )
    with session_scope() as s:
        dev = s.get(DeviceIdentity, dev_id)
        assert dev is not None
        assert dev.qos_rule is not None
        assert dev.qos_rule.dl_limit_mbps == 5.0
        assert dev.qos_rule.priority == "high"


def test_audit_event_append(tmp_db_path):
    init_db(f"sqlite:///{tmp_db_path}")
    with session_scope() as s:
        s.add(AuditEvent(actor="user", action="qos.update", target="dev-1", success=True))
    with session_scope() as s:
        rows = s.query(AuditEvent).all()
        assert len(rows) == 1
        assert rows[0].action == "qos.update"
