"""ORM models (SQLAlchemy 2.0).

Identity: ``DeviceIdentity`` is the stable internal identity. The hotspot
client IP is *not* an identity — it can change. MAC is a hint used to recover
the same identity across IP changes (with MAC randomization caveats, handled in
Phase 4). The Wi-Fi / hotspot password is intentionally NOT stored here (see
SECURITY.md); it lives only in the NetworkManager connection profile.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeviceIdentity(Base):
    __tablename__ = "device_identity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Last-seen MAC; hint, not authoritative (randomization possible).
    mac_last_seen: Mapped[str | None] = mapped_column(String(17), index=True, nullable=True)
    vendor_guess: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    sessions: Mapped[list["DeviceSession"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    qos_rule: Mapped["QoSRule | None"] = relationship(back_populates="device", cascade="all, delete-orphan", uselist=False)


class DeviceSession(Base):
    """A current/recent connection of a device to the hotspot."""

    __tablename__ = "device_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("device_identity.id"), index=True)
    ip: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    mac: Mapped[str | None] = mapped_column(String(17), nullable=True)
    iface: Mapped[str | None] = mapped_column(String(32), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    # Cumulative counters (best-effort; see monitoring design).
    dl_bytes: Mapped[int] = mapped_column(Integer, default=0)
    ul_bytes: Mapped[int] = mapped_column(Integer, default=0)

    device: Mapped["DeviceIdentity"] = relationship(back_populates="sessions")


class QoSRule(Base):
    __tablename__ = "qos_rule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("device_identity.id"), index=True)
    dl_limit_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    ul_limit_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    # Ownership handles (NETWORK_SHAPING.md) — allocated centrally.
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mark_up: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mark_down: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # state: applied | pending | failed
    state: Mapped[str] = mapped_column(String(16), default="pending")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    device: Mapped["DeviceIdentity"] = relationship(back_populates="qos_rule")


class NetworkConfig(Base):
    """Hotspot / upstream configuration. NO password stored here."""

    __tablename__ = "network_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotspot_interface: Mapped[str | None] = mapped_column(String(32), nullable=True)
    upstream_interface: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ssid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    security: Mapped[str | None] = mapped_column(String(16), nullable=True)
    band: Mapped[str | None] = mapped_column(String(4), nullable=True)
    channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gateway_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class TrafficSample(Base):
    """Downsampled traffic samples (aggregate or per-device)."""

    __tablename__ = "traffic_sample"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    # scope: "aggregate" | "device"
    scope: Mapped[str] = mapped_column(String(16), default="aggregate", index=True)
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    iface: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dl_bytes: Mapped[int] = mapped_column(Integer, default=0)
    ul_bytes: Mapped[int] = mapped_column(Integer, default=0)
    dl_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    ul_bps: Mapped[float | None] = mapped_column(Float, nullable=True)


class SavedPolicy(Base):
    __tablename__ = "saved_policy"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Serialized rule deltas (JSON text). Secrets never stored.
    rules_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class AuditEvent(Base):
    """Append-only audit log. Secrets redacted before write (SECURITY.md)."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
