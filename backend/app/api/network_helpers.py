"""Small read-only helpers shared by network routers."""
from __future__ import annotations

_PROC_SYS_MAP = {
    "net.ipv4.ip_forward": "/proc/sys/net/ipv4/ip_forward",
    "net.ipv6.conf.all.forwarding": "/proc/sys/net/ipv6/conf/all/forwarding",
}


def read_sysctl_bool(name: str) -> bool:
    """Read a boolean sysctl via /proc/sys (unprivileged read)."""
    path = _PROC_SYS_MAP.get(name)
    if not path:
        return False
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() == "1"
    except OSError:
        return False
