"""Application configuration.

Settings are loaded from environment variables (prefix ``SQM_``) and an optional
``.env`` file. ``scripts/env.sh`` exports the runtime defaults; anything set
there overrides these. No secrets live in settings — the privileged helper
token is a file path, never a value here.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SQM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App identity ---
    app_name: str = "Smart QoS Manager"
    version: str = "0.1.0"

    # --- Server ---
    backend_host: str = "127.0.0.1"
    backend_port: int = 8090
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 5173
    # Default local-only binding. Set SQM_DASHBOARD_BIND=0.0.0.0 only with auth
    # (enforced in Phase 9) to allow phone access from the hotspot network.
    dashboard_bind: str = "127.0.0.1"

    # --- Database ---
    database_url: str = "sqlite:///data/smartqos.db"

    # --- Logging ---
    log_level: str = "INFO"
    log_dir: str = "logs"

    # --- Monitoring ---
    monitor_interval_s: float = 1.0
    history_sample_interval_s: int = 5
    history_retention_days: int = 30

    # --- Internet connectivity probe ---
    # Connects (DNS + TCP) to a hostname; "ok" if any target connects,
    # "limited" if DNS resolves but no TCP (captive/filtered), "none" if DNS
    # fails. We probe a hostname (not a raw IP) because some networks block
    # specific IPs while allowing the hostname-resolved address — a raw-IP
    # probe would falsely report "limited" on such networks.
    connectivity_host: str = "one.one.one.one"
    connectivity_fallbacks: list[str] = ["www.google.com"]
    connectivity_port: int = 443
    connectivity_timeout_s: float = 2.0
    connectivity_ttl_s: float = 10.0

    # --- CORS (dev) ---
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )

    # --- Privileged helper (Phase 5+) ---
    helper_socket: str = "/run/smartqos/helper.sock"
    helper_token_file: str = "/etc/smartqos/helper.token"

    # --- QoS engine (Phase 5) ---
    # Parent cap bounds the aggregate of all per-device classes on each shaped
    # interface (HTB parent class rate/ceil). Unlimited devices inherit this.
    qos_parent_cap_mbps: float = 100.0
    # Small uniform guaranteed minimum so HTB can lend/borrow; priority (prio)
    # does the scheduling work, not this rate.
    qos_min_rate_mbps: float = 0.1

    # --- Frontend static assets (prod) ---
    frontend_dist: str = "frontend/dist"

    # --- Ownership markers (NETWORK_SHAPING.md) ---
    nft_table: str = "smartqos"
    tc_root_handle: str = "1:"
    # Class handles 1:0x10 .. 1:0xFF, allocated centrally.
    tc_class_min: int = 0x10
    tc_class_max: int = 0xFF
    # fw marks: high nibble = ownership+direction, low = class.
    mark_up_base: int = 0x1000
    mark_down_base: int = 0x2000


settings = Settings()
