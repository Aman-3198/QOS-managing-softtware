"""Unprivileged client for the privileged helper.

Talks to the root helper over a Unix socket authenticated by the shared token.
If the helper is down or the token is unreadable, callers get a
HelperUnavailableError so the API can return 503 instead of silently failing or
falling back to unprivileged shaping (which is impossible).

The client never sends secrets other than the token itself; the helper validates
every request independently.
"""
from __future__ import annotations

import json
import logging
import os
import socket
from typing import Any

from ..config import settings
from ..core.exceptions import HelperUnavailableError

log = logging.getLogger("smartqos.helper_client")

_TOKEN_CACHE: str | None = None


def _load_token() -> str:
    global _TOKEN_CACHE
    if _TOKEN_CACHE is not None:
        return _TOKEN_CACHE
    try:
        with open(settings.helper_token_file, encoding="utf-8") as f:
            _TOKEN_CACHE = f.read().strip()
        return _TOKEN_CACHE
    except OSError as e:
        raise HelperUnavailableError(
            f"cannot read helper token ({settings.helper_token_file}): {e}"
        )


def call(op: str, args: dict | None = None, timeout: float = 20.0) -> dict[str, Any]:
    """Send one allowlisted operation to the helper; return its JSON response.

    Raises HelperUnavailableError if the socket/token is inaccessible.
    Raises the helper's error message (as a RuntimeError) if the op reports failure.
    """
    token = _load_token()
    request = {"op": op, "token": token, "args": args or {}}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(settings.helper_socket)
            s.sendall((json.dumps(request) + "\n").encode("utf-8"))
            data = s.recv(65536).decode("utf-8")
    except OSError as e:
        raise HelperUnavailableError(f"helper socket unreachable: {e}")

    if not data:
        raise HelperUnavailableError("helper returned no response")
    resp = json.loads(data)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "helper operation failed"))
    return resp.get("data", {})


def is_available() -> bool:
    """Cheap liveness check used by /api/health."""
    try:
        _load_token()
        if not os.path.exists(settings.helper_socket):
            return False
        # A real ping would need an op; just confirm the socket file exists + readable token.
        return True
    except HelperUnavailableError:
        return False

def restart() -> dict:
    """Ask the running helper to re-exec itself with the latest file on disk.
    The helper re-execs after sending its response, so we wait briefly then
    verify the socket comes back before returning."""
    import time
    try:
        call("helper.restart", {}, timeout=5.0)
    except Exception:
        pass  # The helper may close the connection mid-exec — that's expected.

    # Wait up to 8 s for the socket to reappear (helper re-execs in ~0.3s).
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        time.sleep(0.5)
        if os.path.exists(settings.helper_socket):
            return {"ok": True, "restarted": True}
    return {"ok": False, "error": "helper did not come back after restart"}
