"""Network diagnostics: real read-only checks with pass/warning/fail/unknown +
suggested resolutions. Privileged checks (nft read) report unknown when the
unprivileged backend can't see them; the helper can run those later.

The export form omits all secrets/tokens/passwords (spec requirement).
"""
from __future__ import annotations

import os
import shutil
import subprocess

from ..core.constants import EXEC_PATHS
from . import helper_client
from .connectivity import ConnectivityProbe
from .network_info import NetworkContext


class DiagnosticsService:
    def __init__(self, network_ctx: NetworkContext, probe: ConnectivityProbe, device_service) -> None:
        self.net = network_ctx
        self.probe = probe
        self.devices = device_service

    def run(self) -> dict:
        checks = [
            self._check_tools(),
            self._check_interfaces(),
            self._check_ap_support(),
            self._check_default_route(),
            self._check_internet(),
            self._check_ip_forward(),
            self._check_tc(),
            self._check_firewall(),
            self._check_helper(),
            self._check_backend_not_root(),
            self._check_hotspot_clients(),
        ]
        return {"checks": checks}

    # --- individual checks ---
    def _ok(self, cid, name, detail="", suggestion=""): return {"id": cid, "name": name, "status": "pass", "detail": detail, "suggestion": suggestion}
    def _warn(self, cid, name, detail, suggestion=""): return {"id": cid, "name": name, "status": "warning", "detail": detail, "suggestion": suggestion}
    def _fail(self, cid, name, detail, suggestion=""): return {"id": cid, "name": "name", "status": "fail", "detail": detail, "suggestion": suggestion} if False else {"id": cid, "name": name, "status": "fail", "detail": detail, "suggestion": suggestion}
    def _unk(self, cid, name, detail, suggestion=""): return {"id": cid, "name": name, "status": "unknown", "detail": detail, "suggestion": suggestion}

    def _check_tools(self):
        missing = [n for n, p in EXEC_PATHS.items() if not shutil.which(p) and not os.path.exists(p)]
        if not missing:
            return self._ok("tools", "Required tools", "ip, tc, iw, nft, nmcli all present")
        return self._fail("tools", "Required tools", f"missing: {', '.join(missing)}", "install iproute2, iw, nftables, network-manager")

    def _check_interfaces(self):
        ifs = self.net.interfaces()
        names = [i["name"] for i in ifs]
        if "lo" in names and len(names) >= 2:
            return self._ok("interfaces", "Network interfaces", f"{len(names)} found: {', '.join(names)}")
        return self._fail("interfaces", "Network interfaces", "only loopback found", "check kernel/udev for interface enumeration")

    def _check_ap_support(self):
        ap = [i["name"] for i in self.net.interfaces() if (i.get("wifi") or {}).get("supports_ap")]
        if ap:
            return self._ok("ap_support", "Wireless AP support", f"AP-capable: {', '.join(ap)}")
        return self._warn("ap_support", "Wireless AP support", "no AP-capable Wi-Fi adapter", "use a Wi-Fi adapter + driver supporting AP mode")

    def _check_default_route(self):
        r = self.net.default_route()
        if r:
            return self._ok("default_route", "Default route", f"via {r.get('gateway')} dev {r.get('dev')}")
        return self._fail("default_route", "Default route", "no default route", "connect to an upstream network")

    def _check_internet(self):
        internet, latency = self.probe.check()
        if internet == "ok":
            return self._ok("internet", "Internet connectivity", f"reachable, {latency} ms")
        if internet == "limited":
            return self._warn("internet", "Internet connectivity", "DNS works but no TCP reachability", "check for a captive portal or filtering")
        if internet == "none":
            return self._fail("internet", "Internet connectivity", "DNS resolution failed", "check DNS / upstream link")
        return self._unk("internet", "Internet connectivity", "probe inconclusive")

    def _check_ip_forward(self):
        try:
            with open("/proc/sys/net/ipv4/ip_forward") as f:
                on = f.read().strip() == "1"
        except OSError:
            return self._unk("ip_forward", "IP forwarding", "could not read /proc/sys")
        if on:
            return self._ok("ip_forward", "IP forwarding", "net.ipv4.ip_forward = 1")
        return self._warn("ip_forward", "IP forwarding", "net.ipv4.ip_forward = 0", "enabling forwarding is required for a hotspot (done by the helper at hotspot start)")

    def _check_tc(self):
        iface = self.net.default_route_iface()
        if not iface:
            return self._warn("tc", "Traffic-control config", "no upstream interface")
        try:
            out = subprocess.run([EXEC_PATHS["tc"], "qdisc", "show", "dev", iface],
                                 capture_output=True, text=True, timeout=5, check=False).stdout
        except Exception:
            return self._unk("tc", "Traffic-control config", "tc read failed")
        if "htb" in out and "smartqos" not in out and "1:" in out:
            return self._ok("tc", "Traffic-control config", f"qdisc on {iface}: {out.strip()[:120]}")
        return self._warn("tc", "Traffic-control config", f"no app HTB qdisc on {iface}", "start the helper + apply a rule to enable shaping")

    def _check_firewall(self):
        # nft reads require CAP_NET_ADMIN; the unprivileged backend reports unknown.
        try:
            rc = subprocess.run([EXEC_PATHS["nft"], "list", "tables"],
                                capture_output=True, text=True, timeout=5, check=False)
            if rc.returncode == 0:
                has_sqm = "smartqos" in (rc.stdout or "")
                return self._ok("firewall", "Firewall (nftables)",
                                "smartqos table present" if has_sqm else "smartqos table not present (no shaping active)")
            return self._unk("firewall", "Firewall (nftables)", "nft read needs privileges; check via the helper")
        except Exception:
            return self._unk("firewall", "Firewall (nftables)", "nft unavailable")

    def _check_helper(self):
        return self._ok("helper", "Privileged helper", "reachable") if helper_client.is_available() else \
            self._warn("helper", "Privileged helper", "not running", "sudo bash privileged-helper/setup.sh then sudo python3 privileged-helper/helper.py")

    def _check_backend_not_root(self):
        return self._ok("backend_perms", "Backend permissions",
                        f"running unprivileged (uid={os.geteuid()})" if os.geteuid() != 0 else
                        "RUNNING AS ROOT (unexpected)") if os.geteuid() != 0 else \
            self._fail("backend_perms", "Backend permissions", "backend is running as root", "do not run the web backend as root; use the helper")

    def _check_hotspot_clients(self):
        n = len(self.devices.list_devices())
        hs = self.net.hotspot()
        if hs.state == "started":
            return self._ok("hotspot_clients", "Hotspot clients", f"{n} connected")
        return self._warn("hotspot_clients", "Hotspot clients", "hotspot not started", "start a hotspot to discover clients")
