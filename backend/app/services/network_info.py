"""Read-only network information: interface discovery, /proc/net/dev counters,
default route, Wi-Fi capabilities, and hotspot (AP) detection.

Everything here is unprivileged (reads /proc, `ip -j`, `iw`, `ethtool -i`).
No state is modified. Parsing is defensive: if a command or field is missing we
return None/unknown rather than raising, so the dashboard degrades gracefully.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from ..core.constants import EXEC_PATHS

log = logging.getLogger("smartqos.netinfo")

_IP = EXEC_PATHS["ip"]
_IW = EXEC_PATHS["iw"]
_ETHTOOL = EXEC_PATHS["ethtool"]


# ---------------------------------------------------------------------------
# Low-level command helpers
# ---------------------------------------------------------------------------
def _run(args: list[str], timeout: float = 5.0) -> str | None:
    """Run a fixed-path command, return stdout (text) or None on failure."""
    try:
        if not os.path.exists(args[0]):
            return None
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.stdout if proc.returncode == 0 else (proc.stdout or None)
    except (subprocess.SubprocessError, OSError):
        return None


def _run_json(args: list[str], timeout: float = 5.0) -> list[dict] | None:
    out = _run(args, timeout)
    if not out:
        return None
    try:
        data = json.loads(out)
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# /proc/net/dev — primary aggregate throughput source (unprivileged, ~1 Hz)
# ---------------------------------------------------------------------------
def parse_proc_net_dev(text: str) -> dict[str, dict[str, int]]:
    """Parse the contents of /proc/net/dev into {iface: {rx_bytes, ...}}."""
    counters: dict[str, dict[str, int]] = {}
    lines = text.splitlines()
    for line in lines[2:]:  # first two lines are headers
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        parts = rest.split()
        if len(parts) < 16:
            continue
        counters[name] = {
            "rx_bytes": int(parts[0]),
            "rx_packets": int(parts[1]),
            "rx_errs": int(parts[2]),
            "rx_drop": int(parts[3]),
            "tx_bytes": int(parts[8]),
            "tx_packets": int(parts[9]),
            "tx_errs": int(parts[10]),
            "tx_drop": int(parts[11]),
        }
    return counters


def read_proc_net_dev() -> dict[str, dict[str, int]]:
    """Parse /proc/net/dev into {iface: {rx_bytes, tx_bytes, rx_packets, ...}}."""
    try:
        with open("/proc/net/dev", encoding="utf-8") as f:
            return parse_proc_net_dev(f.read())
    except OSError:
        return {}


# ---------------------------------------------------------------------------
# iproute2 JSON: links, addresses, default route
# ---------------------------------------------------------------------------
def _ip_link_dump() -> list[dict]:
    return _run_json([_IP, "-j", "-d", "link", "show"]) or []


def _ip_addr_dump() -> list[dict]:
    return _run_json([_IP, "-j", "addr", "show"]) or []


def default_route() -> dict | None:
    routes = _run_json([_IP, "-j", "route", "show", "default"])
    if not routes:
        return None
    # Pick the first default route (lowest metric among those is typical order).
    return routes[0]


def default_route_iface() -> str | None:
    r = default_route()
    return r.get("dev") if r else None


# ---------------------------------------------------------------------------
# iw: wireless interfaces + phy capabilities
# ---------------------------------------------------------------------------
def _parse_iw_dev() -> dict[str, dict]:
    """Parse `iw dev` into {iface: {phy, type, ssid, channel, addr}}."""
    out = _run([_IW, "dev"])
    info: dict[str, dict] = {}
    if not out:
        return info
    cur_phy: str | None = None
    cur_iface: str | None = None
    for line in out.splitlines():
        m = re.match(r"phy#(\d+)", line)
        if m:
            cur_phy = "phy" + m.group(1)
            continue
        m = re.match(r"\s*Interface\s+(\S+)", line)
        if m:
            cur_iface = m.group(1)
            info[cur_iface] = {"phy": cur_phy}
            continue
        if cur_iface is None or cur_iface not in info:
            continue
        s = line.strip()
        if s.startswith("type "):
            info[cur_iface]["type"] = s.split(None, 1)[1]
        elif s.startswith("ssid "):
            info[cur_iface]["ssid"] = s.split(None, 1)[1]
        elif s.startswith("channel "):
            mc = re.match(r"channel\s+(\d+)", s)
            if mc:
                info[cur_iface]["channel"] = int(mc.group(1))
    return info


def _parse_iw_list_caps() -> dict:
    """Parse `iw list` for supported modes + interface combinations.

    Returns {"modes": set[str], "combinations": [str], "supports_ap": bool,
             "supports_managed": bool, "supports_concurrent_sta_ap": bool,
             "channels_constraint": int|None}. Best-effort; never raises.
    """
    out = _run([_IW, "list"])
    caps: dict[str, Any] = {
        "modes": set(),
        "combinations": [],
        "supports_ap": False,
        "supports_managed": False,
        "supports_concurrent_sta_ap": False,
        "channels_constraint": None,
    }
    if not out:
        return caps
    section: str | None = None
    cur_combo: str = ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped == "Supported interface modes:":
            section = "modes"
            continue
        if stripped.startswith("valid interface combinations:"):
            section = "combos"
            continue
        if section == "modes":
            # Modes block: lines indented two tabs; a one-tab line ends the block.
            if line.startswith("\t\t") and stripped.startswith("* "):
                caps["modes"].add(stripped[2:].strip())
            elif not line.startswith("\t\t"):
                section = None
            continue
        if section == "combos":
            # Combination lines are indented two tabs and may WRAP across
            # multiple physical lines. Join continuations; the block ends at a
            # one-tab line (e.g. "HT Capability overrides:").
            if line.startswith("\t\t"):
                if stripped.startswith("* "):
                    if cur_combo:
                        caps["combinations"].append(cur_combo)
                    cur_combo = stripped[2:].strip()
                elif cur_combo:
                    cur_combo += " " + stripped
            else:
                if cur_combo:
                    caps["combinations"].append(cur_combo)
                    cur_combo = ""
                section = None
    if cur_combo and section == "combos":
        caps["combinations"].append(cur_combo)
    caps["supports_ap"] = "AP" in caps["modes"]
    caps["supports_managed"] = "managed" in caps["modes"]
    # Concurrent STA+AP: any combination line mentioning both managed and AP.
    for combo in caps["combinations"]:
        if "managed" in combo and "AP" in combo:
            caps["supports_concurrent_sta_ap"] = True
            mc = re.search(r"#channels\s*<=\s*(\d+)", combo)
            if mc:
                caps["channels_constraint"] = int(mc.group(1))
            break
    return caps


# ---------------------------------------------------------------------------
# ethtool driver
# ---------------------------------------------------------------------------
def _driver(iface: str) -> str | None:
    out = _run([_ETHTOOL, "-i", iface], timeout=3.0)
    if not out:
        return None
    for line in out.splitlines():
        if line.startswith("driver:"):
            return line.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# Hotspot (AP) detection — real: an active AP interface means a hotspot is up.
# Full lifecycle (start/stop) is Phase 6; this only *observes* current state.
# ---------------------------------------------------------------------------
@dataclass
class HotspotObservation:
    state: str = "stopped"  # "started" if an AP interface is active, else "stopped"
    hotspot_interface: str | None = None
    ssid: str | None = None
    channel: int | None = None


def detect_hotspot() -> HotspotObservation:
    wifi = _parse_iw_dev()
    for iface, info in wifi.items():
        if info.get("type") == "AP":
            return HotspotObservation(
                state="started",
                hotspot_interface=iface,
                ssid=info.get("ssid"),
                channel=info.get("channel"),
            )
    return HotspotObservation(state="stopped")


# ---------------------------------------------------------------------------
# NetworkContext — cached gather of interfaces + default route + hotspot,
# shared by the monitor (1 Hz) and the /api/network endpoints.
# ---------------------------------------------------------------------------
@dataclass
class NetworkContext:
    interfaces_ttl: float = 5.0
    route_ttl: float = 3.0
    hotspot_ttl: float = 5.0

    _ifaces_cache: list[dict] = field(default_factory=list)
    _ifaces_ts: float = 0.0
    _route_cache: dict | None = None
    _route_ts: float = 0.0
    _hs_cache: HotspotObservation = field(default_factory=lambda: HotspotObservation())
    _hs_ts: float = 0.0
    _wifi_ifaces: dict[str, dict] = field(default_factory=dict)
    _wifi_caps: dict = field(default_factory=lambda: _parse_iw_list_caps())
    _wifi_ts: float = 0.0

    def _refresh_wifi(self, now: float) -> None:
        if now - self._wifi_ts > self.hotspot_ttl:
            self._wifi_ifaces = _parse_iw_dev()
            self._wifi_caps = _parse_iw_list_caps()
            self._wifi_ts = now

    def default_route(self) -> dict | None:
        now = time.monotonic()
        if now - self._route_ts > self.route_ttl:
            self._route_cache = default_route()
            self._route_ts = now
        return self._route_cache

    def default_route_iface(self) -> str | None:
        r = self.default_route()
        return r.get("dev") if r else None

    def hotspot(self) -> HotspotObservation:
        now = time.monotonic()
        if now - self._hs_ts > self.hotspot_ttl:
            self._hs_cache = detect_hotspot()
            self._hs_ts = now
        return self._hs_cache

    def interfaces(self) -> list[dict]:
        """Return a list of interface dicts (the raw gather), cached."""
        now = time.monotonic()
        if now - self._ifaces_ts > self.interfaces_ttl:
            self._refresh_wifi(now)
            self._ifaces_cache = self._gather_interfaces()
            self._ifaces_ts = now
        return self._ifaces_cache

    def _gather_interfaces(self) -> list[dict]:
        links = {l["ifname"]: l for l in _ip_link_dump() if "ifname" in l}
        addrs = {a["ifname"]: a for a in _ip_addr_dump() if "ifname" in a}
        dr_iface = self.default_route_iface()
        gw = None
        dr = default_route()
        if dr:
            gw = dr.get("gateway")
        result: list[dict] = []
        for name, link in links.items():
            link_type = link.get("link_type", "unknown")
            is_wifi = name in self._wifi_ifaces
            if link_type == "loopback":
                iftype = "loopback"
            elif is_wifi:
                iftype = "wifi"
            elif link_type == "ether":
                iftype = "ethernet"
            else:
                iftype = "other"
            flags = link.get("flags", []) or []
            operstate = link.get("operstate") or ""
            up = "UP" in flags
            # `carrier` may be True/False, or null/absent (common for wifi, which
            # does not report carrier). null/absent => infer from operstate +
            # the LOWER_UP flag. operstate is uppercase from `ip` (UP/DOWN).
            carrier = link.get("carrier")
            if carrier is True:
                link_up = True
            elif carrier is False:
                link_up = False
            else:
                link_up = operstate.lower() in ("up", "unknown") and "LOWER_UP" in flags
            # Addresses
            addr_list = (addrs.get(name) or {}).get("addr_info") or []
            addresses = [
                {"family": a.get("family", ""), "addr": a.get("local"),
                 "prefix": a.get("prefixlen")}
                for a in addr_list if a.get("local")
            ]
            has_ip = any(a["family"] in ("inet", "inet6") and a["addr"] for a in addresses)

            wifi_info = None
            if is_wifi:
                w = self._wifi_ifaces[name]
                wifi_info = {
                    "phy": w.get("phy"),
                    "supports_ap": self._wifi_caps.get("supports_ap", False),
                    "supports_managed": self._wifi_caps.get("supports_managed", False),
                    "current_mode": w.get("type"),
                    "channel": w.get("channel"),
                    "ssid": w.get("ssid"),
                    "supports_concurrent_sta_ap": self._wifi_caps.get("supports_concurrent_sta_ap", False),
                    "channels_constraint": self._wifi_caps.get("channels_constraint"),
                }

            # Candidates:
            # upstream_candidate: a connected wifi (managed) or an ethernet with link.
            upstream_candidate = (
                (iftype == "wifi" and w_current_mode(wifi_info) == "managed") if is_wifi
                else (iftype == "ethernet" and link_up)
            ) if iftype in ("wifi", "ethernet") else False
            hotspot_candidate = bool(is_wifi and wifi_info and wifi_info["supports_ap"])

            result.append({
                "name": name,
                "type": iftype,
                "driver": _driver(name),
                "state": operstate or ("up" if up else "down"),
                "link": link_up,
                "mac": link.get("address"),
                "addresses": addresses,
                "gateway": gw if name == dr_iface else None,
                "is_default_route": name == dr_iface,
                "upstream_candidate": upstream_candidate,
                "hotspot_candidate": hotspot_candidate,
                "wifi": wifi_info,
            })
        return result


def w_current_mode(wifi_info: dict | None) -> str | None:
    return wifi_info.get("current_mode") if wifi_info else None
