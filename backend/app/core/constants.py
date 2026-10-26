"""Fixed constants and validated executable paths.

Privileged and system-interacting code must use these fixed paths and never
interpolate user input into a command string (see SECURITY.md). Existence is
validated lazily; callers check ``is_available()`` before invoking.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass

# --- Fixed executable paths (never overridden by user input) ---
EXEC_PATHS: dict[str, str] = {
    "ip": "/usr/sbin/ip",
    "tc": "/usr/sbin/tc",
    "iw": "/usr/sbin/iw",
    "nft": "/usr/sbin/nft",
    "nmcli": "/usr/bin/nmcli",
    "ethtool": "/usr/sbin/ethtool",
    "dnsmasq": "/usr/sbin/dnsmasq",
    "hostapd": "/usr/sbin/hostapd",
    "openssl": "/usr/bin/openssl",
    "ss": "/usr/bin/ss",
}


@dataclass(frozen=True)
class ExecInfo:
    name: str
    path: str

    def is_available(self) -> bool:
        return shutil.which(self.path) is not None or __import__("os").path.exists(self.path)


def exec_info(name: str) -> ExecInfo:
    """Return a validated ExecInfo for a known executable name."""
    if name not in EXEC_PATHS:
        raise KeyError(f"unknown executable: {name!r}")
    return ExecInfo(name=name, path=EXEC_PATHS[name])


# --- Priority mapping (NETWORK_SHAPING.md) ---
# HTB prio: lower borrows first. Priority is a scheduling preference, NOT a
# bandwidth guarantee.
PRIORITY_TO_PRIO: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
}
PRIORITY_LEVELS = tuple(PRIORITY_TO_PRIO.keys())

# --- Validation bounds ---
MAX_RATE_MBPS = 10_000.0  # hard ceiling on any single rate (10 Gbps)
