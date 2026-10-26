"""Device discovery for the hotspot (read-only, unprivileged).

Combines three sources and dedupes to per-device records keyed by MAC:
- ``iw dev <iface> station dump`` — authoritative "connected" set for a Wi-Fi AP,
  with per-station rx/tx byte counters (real per-device accounting) + signal +
  connected time.
- ``ip -j neigh show dev <iface>`` — resolves a station's MAC to its current IP.
- DHCP leases — hostname hint; the lease files under /var/lib/NetworkManager are
  root-only, so hostnames come from the privileged helper in Phase 5 (until then
  hostname is None, honestly).

Per-device speed source (documented in NETWORK_SHASING.md and section 8):
  client download (internet -> client) = AP tx bytes to that station.
  client upload   (client -> internet) = AP rx bytes from that station.
These are AP-side counters and are independent of the upstream aggregate
(/proc/net/dev); they are NOT summed with it (no double counting).

We never infer a device is connected from a stale neighbor entry. A device is
"connected" only if it appears in the station dump (or has a REACHABLE neighbor
entry, used only as a robustness fallback when station dump misses a client).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .network_info import _IP, _IW, _run, _run_json

log = logging.getLogger("smartqos.discovery")

_MAC_RE = re.compile(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")


# ---------------------------------------------------------------------------
# Source parsers
# ---------------------------------------------------------------------------
@dataclass
class StationInfo:
    mac: str
    iface: str
    rx_bytes: int | None = None      # client -> AP (upload)
    tx_bytes: int | None = None      # AP -> client (download)
    signal_dbm: int | None = None
    connected_time_s: int | None = None
    inactive_ms: int | None = None


def parse_iw_station_dump(text: str) -> list[StationInfo]:
    """Parse `iw dev <iface> station dump` text into StationInfo list."""
    stations: list[StationInfo] = []
    cur: StationInfo | None = None
    for line in text.splitlines():
        m = re.match(r"Station\s+([0-9a-fA-F:]{17})\s+\(on\s+(\S+)\)", line)
        if m:
            if cur is not None:
                stations.append(cur)
            cur = StationInfo(mac=m.group(1).lower(), iface=m.group(2))
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("rx bytes:"):
            cur.rx_bytes = _first_int(s)
        elif s.startswith("tx bytes:"):
            cur.tx_bytes = _first_int(s)
        elif s.startswith("signal:"):
            # Format: "signal:\t-17 [-18, -23] dBm" — capture the first number.
            mm = re.search(r"signal:\s*(-?\d+)", s)
            cur.signal_dbm = int(mm.group(1)) if mm else None
        elif s.startswith("connected time:"):
            mm = re.search(r"(\d+)\s*seconds", s)
            cur.connected_time_s = int(mm.group(1)) if mm else None
        elif s.startswith("inactive time:"):
            mm = re.search(r"(\d+)\s*ms", s)
            cur.inactive_ms = int(mm.group(1)) if mm else None
    if cur is not None:
        stations.append(cur)
    return stations


@dataclass
class NeighborInfo:
    ip: str
    mac: str
    family: str  # "inet" | "inet6"
    state: list[str] = field(default_factory=list)


def parse_ip_neigh_json(data: list[dict]) -> list[NeighborInfo]:
    """Parse `ip -j neigh show` JSON entries into NeighborInfo list."""
    out: list[NeighborInfo] = []
    for e in data or []:
        mac = (e.get("lladdr") or "").lower()
        if not mac:
            continue
        ip = e.get("dst")
        if not ip:
            continue
        out.append(NeighborInfo(
            ip=ip, mac=mac,
            family="inet6" if ":" in ip else "inet",
            state=list(e.get("state") or []),
        ))
    return out


def ip_neigh(iface: str) -> list[NeighborInfo]:
    data = _run_json([_IP, "-j", "neigh", "show", "dev", iface])
    return parse_ip_neigh_json(data or [])


# ---------------------------------------------------------------------------
# DHCP leases (best-effort; root-only under NetworkManager -> Phase 5 helper)
# ---------------------------------------------------------------------------
_LEASE_PATHS = [
    "/var/lib/NetworkManager/dnsmasq-*.leases",
    "/var/lib/misc/dnsmasq.leases",
    "/var/lib/dnsmasq/dnsmasq.leases",
]


def parse_dnsmasq_leases() -> dict[str, dict]:
    """Return {mac: {ip, hostname, ts}} from readable dnsmasq lease files.

    Best-effort: files under /var/lib/NetworkManager are root-only on this host,
    so this returns {} when unreadable. Hostnames then come from the Phase 5
    privileged helper. We never fabricate a hostname.
    """
    import glob

    by_mac: dict[str, dict] = {}
    for pattern in _LEASE_PATHS:
        for path in glob.glob(pattern):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        # dnsmasq lease format: <ts> <mac> <ip> <hostname> <clientid>
                        parts = line.split()
                        if len(parts) >= 4:
                            mac = parts[1].lower()
                            if _MAC_RE.fullmatch(mac):
                                by_mac[mac] = {
                                    "ip": parts[2],
                                    "hostname": parts[3] if parts[3] != "*" else None,
                                    "ts": parts[0],
                                }
            except (OSError, PermissionError):
                continue
    return by_mac


# ---------------------------------------------------------------------------
# Combined discovery
# ---------------------------------------------------------------------------
@dataclass
class DiscoveredClient:
    mac: str
    ip: str | None = None
    ip6: str | None = None
    hostname: str | None = None
    signal_dbm: int | None = None
    connected_time_s: int | None = None
    rx_bytes: int | None = None      # client -> AP (upload)
    tx_bytes: int | None = None      # AP -> client (download)
    inactive_ms: int | None = None
    sources: list[str] = field(default_factory=list)


def discover_clients(hotspot_iface: str | None) -> list[DiscoveredClient]:
    """Discover currently-connected hotspot clients.

    Returns [] when there is no hotspot interface. A client is "connected" if
    it is in the AP station dump; REACHABLE neighbor entries not in the station
    dump are included only as a robustness fallback (sources=["neighbor"]).
    """
    if not hotspot_iface:
        return []
    stations = parse_iw_station_dump(_run([_IW, "dev", hotspot_iface, "station", "dump"]) or "")
    neigh = ip_neigh(hotspot_iface)
    leases = parse_dnsmasq_leases()

    neigh_by_mac: dict[str, list[NeighborInfo]] = {}
    for n in neigh:
        neigh_by_mac.setdefault(n.mac, []).append(n)

    clients: list[DiscoveredClient] = []
    seen_macs: set[str] = set()

    for st in stations:
        mac = st.mac
        seen_macs.add(mac)
        ip4 = next((n.ip for n in neigh_by_mac.get(mac, []) if n.family == "inet"), None)
        ip6 = next((n.ip for n in neigh_by_mac.get(mac, []) if n.family == "inet6"), None)
        lease = leases.get(mac)
        sources = ["ap_sta"]
        if ip4 is not None:
            sources.append("neighbor")
        if lease is not None:
            sources.append("dhcp")
        clients.append(DiscoveredClient(
            mac=mac, ip=ip4, ip6=ip6,
            hostname=(lease or {}).get("hostname"),
            signal_dbm=st.signal_dbm,
            connected_time_s=st.connected_time_s,
            rx_bytes=st.rx_bytes, tx_bytes=st.tx_bytes,
            inactive_ms=st.inactive_ms,
            sources=sources,
        ))

    # Robustness fallback: REACHABLE neighbors not reported by station dump.
    for mac, entries in neigh_by_mac.items():
        if mac in seen_macs:
            continue
        if not any("REACHABLE" in n.state for n in entries):
            continue
        ip4 = next((n.ip for n in entries if n.family == "inet"), None)
        lease = leases.get(mac)
        sources = ["neighbor"]
        if lease is not None:
            sources.append("dhcp")
        clients.append(DiscoveredClient(
            mac=mac, ip=ip4, hostname=(lease or {}).get("hostname"),
            sources=sources,
        ))

    return clients


def _first_int(s: str) -> int | None:
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None
