"""Hotspot lifecycle: start/stop via NetworkManager through the privileged helper.

The backend never runs nmcli itself (it's unprivileged). It validates the request
against live interface capabilities, asks the helper to apply, and persists the
(non-secret) config. The hotspot password is NEVER stored in our DB — it goes
only to the helper, which passes it to NetworkManager once.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone

from ..core.exceptions import HelperUnavailableError, SmartQoSError, ValidationError
from ..schemas import HotspotStatus
from . import helper_client
from .audit_service import log as audit_log
from .network_info import NetworkContext

log = logging.getLogger("smartqos.hotspot")

# Terminal emulators tried in order; each is invoked to run the fixed bootstrap.
_TERMINALS = [
    ("x-terminal-emulator", ["-e", "bash", "/tmp/sqm-grant.sh"]),
    ("gnome-terminal", ["--", "bash", "/tmp/sqm-grant.sh"]),
    ("xterm", ["-e", "bash", "/tmp/sqm-grant.sh"]),
    ("mate-terminal", ["-e", "bash", "/tmp/sqm-grant.sh"]),
    ("xfce4-terminal", ["-e", "bash", "/tmp/sqm-grant.sh"]),
    ("konsole", ["-e", "bash", "/tmp/sqm-grant.sh"]),
]


def _write_bootstrap(repo: str) -> None:
    """Write the terminal bootstrap. Single sudo call, -B flag, clears cache."""
    helper_py = os.path.join(repo, "privileged-helper", "helper.py")
    setup_sh  = os.path.join(repo, "privileged-helper", "setup.sh")
    pycache   = os.path.join(repo, "privileged-helper", "__pycache__")
    log_file  = "/var/log/smartqos/helper.out"
    log_dir   = "/var/log/smartqos"

    lines = [
        "#!/usr/bin/env bash",
        "# Smart QoS Manager — privileged helper bootstrap",
        "echo '=== Smart QoS Manager: Grant Permission ==='",
        "echo 'Enter your sudo password when prompted.'",
        "echo ''",
        "",
        "# Single sudo session: setup + clear cache + start helper",
        f"sudo bash << 'SUDO_BLOCK'",
        f"set -e",
        f"mkdir -p {log_dir!r}",
        f"if [ ! -f /etc/smartqos/helper.token ]; then",
        f"  echo 'Running first-time setup...'",
        f"  bash {setup_sh!r}",
        f"fi",
        f"pkill -f {helper_py!r} 2>/dev/null || true",
        f"sleep 0.3",
        f"rm -rf {pycache!r}",
        f"echo 'Starting helper...'",
        f"nohup python3 -B {helper_py!r} --user aman > {log_file!r} 2>&1 &",
        f"echo \"Helper PID: $!\"",
        "SUDO_BLOCK",
        "",
        "if [ $? -ne 0 ]; then",
        "  echo 'sudo block failed. See above for errors.'",
        "  sleep 8; exit 1",
        "fi",
        "",
        "echo 'Waiting for helper socket...'",
        "for i in $(seq 1 30); do",
        "  sleep 1",
        "  if [ -S /run/smartqos/helper.sock ]; then",
        "    echo 'Helper is up! Closing this window...'",
        "    sleep 1; exit 0",
        "  fi",
        f"  if ! pgrep -f {helper_py!r} >/dev/null 2>&1; then",
        "    echo ''",
        "    echo 'Helper exited early. Full error log:'",
        "    echo '---'",
        f"    cat {log_file!r} 2>/dev/null",
        "    echo '---'",
        "    echo 'This window closes in 20 seconds.'",
        "    sleep 20; exit 1",
        "  fi",
        "done",
        f"echo 'Timed out. Log:'; cat {log_file!r} 2>/dev/null",
        "sleep 10",
    ]

    content = "\n".join(lines) + "\n"
    with open("/tmp/sqm-grant.sh", "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod("/tmp/sqm-grant.sh", 0o700)


class HotspotService:
    def __init__(self, network_ctx: NetworkContext, device_service) -> None:
        self.net = network_ctx
        self.devices = device_service

    def _iface_entry(self, name: str) -> dict | None:
        for i in self.net.interfaces():
            if i["name"] == name:
                return i
        return None

    def _gateway_ip(self, hotspot_iface: str | None) -> str | None:
        if not hotspot_iface:
            return None
        entry = self._iface_entry(hotspot_iface)
        if entry:
            for a in entry.get("addresses", []):
                if a.get("family") == "inet":
                    return a.get("addr")
        return None

    def status(self) -> HotspotStatus:
        hs = self.net.hotspot()
        cfg = self._load_config()
        connected = len(self.devices.list_devices())
        return HotspotStatus(
            state=hs.state,
            ssid=hs.ssid or cfg.get("ssid"),
            hotspot_interface=hs.hotspot_interface or cfg.get("hotspot_interface"),
            upstream_interface=cfg.get("upstream_interface") or self.net.default_route_iface(),
            gateway_ip=self._gateway_ip(hs.hotspot_interface),
            security=cfg.get("security"),
            band=cfg.get("band"),
            channel=hs.channel or cfg.get("channel"),
            connected_count=connected,
        )

    def start(self, ssid: str, password: str, hotspot_interface: str,
              upstream_interface: str, band: str | None, channel: int | None,
              security: str | None) -> dict:
        # Validate the chosen interface is actually AP-capable.
        entry = self._iface_entry(hotspot_interface)
        if not entry:
            raise ValidationError(f"interface {hotspot_interface} not found")
        wifi = entry.get("wifi") or {}
        if not wifi.get("supports_ap"):
            raise ValidationError(f"interface {hotspot_interface} does not support AP mode")
        if len(password) < 8:
            raise ValidationError("WPA2 password must be at least 8 characters")

        # Warn (not block) if reusing the active STA adapter — NM repurposes it.
        warnings: list[str] = []
        if wifi.get("supports_concurrent_sta_ap") and wifi.get("current_mode") == "managed":
            warnings.append(
                f"{hotspot_interface} is currently the upstream Wi-Fi; starting a hotspot "
                f"may drop that connection (same-channel constraint: {wifi.get('channels_constraint')})."
            )

        helper_client.call("hotspot.start", {
            "ssid": ssid, "password": password,
            "hotspot_interface": hotspot_interface,
            "upstream_interface": upstream_interface,
            "band": band, "channel": channel, "security": security,
        })
        self._save_config(ssid=ssid, hotspot_interface=hotspot_interface,
                          upstream_interface=upstream_interface,
                          band=band, channel=channel, security=security)
        audit_log("user", "hotspot.start", target=ssid,
                  after={"ssid": ssid, "hotspot_interface": hotspot_interface,
                         "upstream_interface": upstream_interface, "band": band, "channel": channel})
        return {"state": "started", "warnings": warnings}

    def stop(self) -> dict:
        helper_client.call("hotspot.stop", {})
        audit_log("user", "hotspot.stop", target=None)
        return {"state": "stopped"}

    def grant_permission(self) -> dict:
        """Open a terminal to (re)start the privileged helper.
        Always kills any existing helper first so the latest code is loaded."""
        if not os.environ.get("DISPLAY"):
            raise SmartQoSError(
                "cannot open a terminal: no DISPLAY. "
                "Run manually: sudo pkill -f helper.py; "
                "sudo python3 -B privileged-helper/helper.py --user aman"
            )
        repo = str(__import__("pathlib").Path(__file__).resolve().parents[3])
        _write_bootstrap(repo)
        term = next((t for t in _TERMINALS if shutil.which(t[0])), None)
        if term is None:
            raise SmartQoSError(
                "no terminal emulator found. Run: "
                "sudo pkill -f helper.py; sudo python3 -B privileged-helper/helper.py"
            )
        try:
            subprocess.Popen([term[0], *term[1]], env=os.environ.copy(), start_new_session=True)
        except OSError as e:
            raise SmartQoSError(f"could not open {term[0]}: {e}")
        audit_log("user", "helper.grant", target=term[0])
        return {"ok": True, "terminal": term[0],
                "message": "terminal opened — type your password to restart the helper"}

    # --- config persistence (no password) ---
    def _load_config(self) -> dict:
        from ..database import session_scope
        from ..models import NetworkConfig

        try:
            with session_scope() as s:
                row = s.query(NetworkConfig).order_by(NetworkConfig.id.desc()).first()
                if not row:
                    return {}
                return {
                    "ssid": row.ssid, "hotspot_interface": row.hotspot_interface,
                    "upstream_interface": row.upstream_interface,
                    "security": row.security, "band": row.band, "channel": row.channel,
                }
        except Exception:
            return {}

    def _save_config(self, **fields) -> None:
        from ..database import session_scope
        from ..models import NetworkConfig

        with session_scope() as s:
            row = s.query(NetworkConfig).order_by(NetworkConfig.id.desc()).first()
            if row is None:
                s.add(NetworkConfig(**fields))
            else:
                for k, v in fields.items():
                    setattr(row, k, v)
