#!/usr/bin/env python3
"""Smart QoS Manager privileged helper. VERSION=3

Runs as root. Exposes a strict allowlist of network operations over a locked
Unix socket authenticated by a shared token. Never runs arbitrary commands,
never uses shell=True, never interpolates user input into a command string.

Start: sudo python3 privileged-helper/helper.py --user aman
Setup: sudo bash privileged-helper/setup.sh  (one-time)
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import logging.handlers
import os
import socket
import socketserver
import subprocess
import sys
import tempfile
from pathlib import Path

# Make the backend qos_state importable without running the backend app.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
_BACKEND_DIR = _REPO / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.qos_state import (  # noqa: E402
    DeviceRule,
    build_desired_state,
    cleanup_nft,
    cleanup_tc_lines,
    nft_ruleset,
    tc_batch_lines,
)

# --- Fixed executable paths ---
TC     = "/usr/sbin/tc"
NFT    = "/usr/sbin/nft"
IP     = "/usr/sbin/ip"
NMCLI  = "/usr/bin/nmcli"

ALLOWED_OPS = {
    "qos.apply", "qos.clear", "stats.read", "sysctl.set",
    "hotspot.start", "hotspot.stop", "helper.restart",
}
ALLOWED_SYSCTLS = {
    "net.ipv4.ip_forward":           "/proc/sys/net/ipv4/ip_forward",
    "net.ipv6.conf.all.forwarding":  "/proc/sys/net/ipv6/conf/all/forwarding",
}
COMMAND_TIMEOUT = 15.0
HOTSPOT_CON = "smartqos-hotspot"

log = logging.getLogger("smartqos.helper")
_TOKEN: bytes = b""


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def _load_token(path: str) -> bytes:
    with open(path, encoding="utf-8") as f:
        return f.read().strip().encode("utf-8")


def _run(args: list[str], stdin: str | None = None,
         timeout: float = COMMAND_TIMEOUT) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            input=(stdin.encode() if stdin is not None else None),
            capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.SubprocessError, OSError) as e:
        return 127, f"{type(e).__name__}: {e}"


def _set_sysctl(name: str, value: bool) -> bool:
    path = ALLOWED_SYSCTLS.get(name)
    if not path:
        return False
    try:
        with open(path, "w") as f:
            f.write("1" if value else "0")
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# tc / nft helpers
# ---------------------------------------------------------------------------
def _apply_tc_batch(iface: str, lines: list[str]) -> tuple[bool, str]:
    """Apply tc commands for one interface.
    Always runs 'qdisc del root' first (ignoring failure — no qdisc may exist yet),
    then runs the add/class/filter commands as a batch."""
    if not lines:
        return True, ""
    # Step 1: delete any existing root qdisc (ignore errors).
    _run([TC, "qdisc", "del", "dev", iface, "root"], timeout=5.0)

    # Step 2: run the rest (add qdisc + classes + filters) as a batch.
    add_lines = [l for l in lines if not l.startswith("qdisc del")]
    if not add_lines:
        return True, ""
    with tempfile.NamedTemporaryFile("w", suffix=".tc", delete=False) as f:
        f.write("\n".join(add_lines) + "\n")
        path = f.name
    try:
        rc, out = _run([TC, "-batch", path])
        return rc == 0, out
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _apply_nft(ruleset: str) -> tuple[bool, str]:
    _run([NFT, "delete", "table", "inet", "smartqos"], timeout=5.0)
    rc, out = _run([NFT, "-f", "-"], stdin=ruleset)
    return rc == 0, out


def _verify(state) -> tuple[bool, str]:
    for iface, direction in [
        (state.upstream_iface, "up"),
        (state.hotspot_iface, "down"),
    ]:
        if not iface:
            continue
        rc, out = _run([TC, "class", "show", "dev", iface], timeout=5.0)
        if rc != 0:
            return False, f"tc class show {iface} failed"
        for a in state.rules:
            if f"1:{a.class_id:x}" not in out:
                return False, f"class 1:{a.class_id:x} missing on {iface}"
    rc, out = _run([NFT, "list", "table", "inet", "smartqos"], timeout=5.0)
    if rc != 0:
        return False, "nft smartqos table missing"
    return True, ""


# ---------------------------------------------------------------------------
# Hotspot operations
# ---------------------------------------------------------------------------
def _delete_hotspot_profile() -> None:
    _run([NMCLI, "connection", "delete", HOTSPOT_CON], timeout=10.0)


def op_hotspot_start(args: dict) -> dict:
    ssid     = str(args.get("ssid", "")).strip()
    password = str(args.get("password", ""))
    iface    = args.get("hotspot_interface")
    if not iface or not ssid:
        return {"ok": False, "error": "ssid and hotspot_interface required"}
    if len(password) < 8:
        return {"ok": False, "error": "WPA2 password must be at least 8 characters"}

    _set_sysctl("net.ipv4.ip_forward", True)
    _delete_hotspot_profile()

    cmd = [NMCLI, "device", "wifi", "hotspot",
           "ifname", iface, "con-name", HOTSPOT_CON,
           "ssid", ssid, "password", password]
    if args.get("band") in ("a", "bg"):
        cmd += ["band", args["band"]]
    if isinstance(args.get("channel"), int) and args["channel"] > 0:
        cmd += ["channel", str(args["channel"])]

    rc, out = _run(cmd, timeout=30.0)
    if rc != 0:
        return {"ok": False, "error": f"nmcli hotspot failed: {out.strip()}"}
    return {"ok": True, "data": {"ssid": ssid, "interface": iface}}


def op_hotspot_stop(args: dict) -> dict:
    _run([NMCLI, "connection", "down", HOTSPOT_CON], timeout=15.0)
    _delete_hotspot_profile()
    return {"ok": True, "data": {"stopped": True}}


def op_helper_restart(args: dict) -> dict:
    """Signal the main thread to re-exec. Uses SIGUSR1 which is caught in main()."""
    import signal
    import threading
    def _signal():
        import time
        time.sleep(0.2)
        os.kill(os.getpid(), signal.SIGUSR1)
    threading.Thread(target=_signal, daemon=True).start()
    return {"ok": True, "data": {"restarting": True}}


# ---------------------------------------------------------------------------
# QoS operations
# ---------------------------------------------------------------------------
def op_qos_apply(args: dict) -> dict:
    rules = [DeviceRule(**r) for r in args.get("rules", [])]
    state = build_desired_state(
        upstream_iface=args.get("upstream_iface"),
        hotspot_iface=args.get("hotspot_iface"),
        rules=rules,
        parent_cap_mbps=args.get("parent_cap_mbps", 100.0),
        min_rate_mbps=args.get("min_rate_mbps", 0.1),
    )
    if not state.upstream_iface or not state.hotspot_iface:
        return {"ok": False, "error": "upstream or hotspot interface unknown"}

    up_lines   = tc_batch_lines(state, "up")
    down_lines = tc_batch_lines(state, "down")
    ruleset    = nft_ruleset(state)

    ok, out = _apply_tc_batch(state.upstream_iface, up_lines)
    if not ok:
        return {"ok": False, "error": f"tc up failed: {out.strip()}"}

    ok, out = _apply_tc_batch(state.hotspot_iface, down_lines)
    if not ok:
        _apply_tc_batch(state.upstream_iface,
                        cleanup_tc_lines(state.upstream_iface))
        return {"ok": False, "error": f"tc down failed: {out.strip()}"}

    ok, out = _apply_nft(ruleset)
    if not ok:
        _apply_tc_batch(state.upstream_iface,
                        cleanup_tc_lines(state.upstream_iface))
        _apply_tc_batch(state.hotspot_iface,
                        cleanup_tc_lines(state.hotspot_iface))
        _run([NFT, "delete", "table", "inet", "smartqos"], timeout=5.0)
        return {"ok": False, "error": f"nft failed: {out.strip()}"}

    verified, vmsg = _verify(state)
    if not verified:
        op_qos_clear({"interfaces": [state.upstream_iface, state.hotspot_iface]})
        return {"ok": False, "error": f"verify failed: {vmsg}"}

    return {"ok": True, "data": {
        "upstream": state.upstream_iface, "hotspot": state.hotspot_iface,
        "classes": len(state.rules), "paused": len(state.paused_ips),
    }}


def op_qos_clear(args: dict) -> dict:
    msgs = []
    for iface in args.get("interfaces", []):
        if not iface:
            continue
        ok, out = _apply_tc_batch(iface, cleanup_tc_lines(iface))
        msgs.append(f"{iface}: {'cleared' if ok else 'failed'}")
    _run([NFT, "delete", "table", "inet", "smartqos"], timeout=5.0)
    msgs.append("nft: cleared")
    return {"ok": True, "data": {"detail": "; ".join(msgs)}}


def op_stats_read(args: dict) -> dict:
    iface = args.get("interface")
    if not iface:
        return {"ok": False, "error": "interface required"}
    rc, out = _run([TC, "-s", "class", "show", "dev", iface], timeout=5.0)
    if rc != 0:
        return {"ok": False, "error": out.strip()}
    return {"ok": True, "data": {"stats": out}}


def op_sysctl_set(args: dict) -> dict:
    name  = args.get("name")
    value = args.get("value")
    if name not in ALLOWED_SYSCTLS:
        return {"ok": False, "error": f"sysctl {name!r} not allowed"}
    if not _set_sysctl(name, bool(value)):
        return {"ok": False, "error": f"could not write {name}"}
    return {"ok": True, "data": {"name": name, "set": bool(value)}}


# ---------------------------------------------------------------------------
# Dispatch table (all op_* functions must be defined above this line)
# ---------------------------------------------------------------------------
DISPATCH = {
    "qos.apply":      op_qos_apply,
    "qos.clear":      op_qos_clear,
    "stats.read":     op_stats_read,
    "sysctl.set":     op_sysctl_set,
    "hotspot.start":  op_hotspot_start,
    "hotspot.stop":   op_hotspot_stop,
    "helper.restart": op_helper_restart,
}


# ---------------------------------------------------------------------------
# Unix socket server
# ---------------------------------------------------------------------------
class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            line = self.rfile.readline()
            if not line:
                return
            req = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._respond({"ok": False, "error": "invalid json"})
            return

        token = req.get("token", "")
        if not hmac.compare_digest(str(token).encode(), _TOKEN):
            self._respond({"ok": False, "error": "auth failed"})
            return

        op = req.get("op")
        if op not in ALLOWED_OPS:
            self._respond({"ok": False, "error": f"op {op!r} not allowed"})
            return

        args = req.get("args") or {}
        try:
            result = DISPATCH[op](args)
        except Exception as e:
            log.exception("op %s failed", op)
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self._respond(result)

    def _respond(self, obj: dict) -> None:
        self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Smart QoS Manager privileged helper")
    ap.add_argument("--socket",      default="/run/smartqos/helper.sock")
    ap.add_argument("--token",       default="/etc/smartqos/helper.token")
    ap.add_argument("--backend-dir", default=str(_BACKEND_DIR))
    ap.add_argument("--user",        default="aman",
                    help="dashboard user whose group may access the socket")
    args = ap.parse_args()

    Path("/var/log/smartqos").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                "/var/log/smartqos/helper.log",
                maxBytes=2_000_000, backupCount=3,
            ),
        ],
    )

    global _TOKEN
    try:
        _TOKEN = _load_token(args.token)
    except OSError as e:
        log.error("cannot read token %s: %s — run: sudo bash privileged-helper/setup.sh", args.token, e)
        return 2

    sock_path = args.socket
    os.makedirs(os.path.dirname(sock_path), exist_ok=True)
    if os.path.exists(sock_path):
        os.unlink(sock_path)

    server = socketserver.ThreadingUnixStreamServer(sock_path, Handler)
    os.chmod(sock_path, 0o660)
    try:
        import pwd
        gid = pwd.getpwnam(args.user).pw_gid
        os.chown(sock_path, 0, gid)
    except (KeyError, OSError):
        log.warning("could not set socket group to %s; backend may not connect", args.user)

    log.info("helper listening on %s", sock_path)
    import signal

    def _handle_sigusr1(signum, frame):
        """Re-exec with the latest code on disk (triggered by helper.restart op)."""
        log.info("SIGUSR1 received — re-execing with latest code")
        server.server_close()
        try:
            os.unlink(sock_path)
        except OSError:
            pass
        os.execv(sys.executable, [sys.executable, "-B", __file__] + sys.argv[1:])

    signal.signal(signal.SIGUSR1, _handle_sigusr1)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            os.unlink(sock_path)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
