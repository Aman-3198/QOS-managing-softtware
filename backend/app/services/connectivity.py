"""Internet connectivity probe (unprivileged).

Probes DNS + TCP reachability by connecting to a hostname (which resolves via
the system resolver and then completes a bare TCP handshake — no application
data is sent). We connect to a *hostname*, not a raw IP, because some networks
block specific IPs while allowing the hostname-resolved address; a raw-IP probe
would falsely report "limited" on such networks.

Result mapping:
- "ok"      : at least one target host resolved AND connected (latency reported).
- "limited" : at least one host resolved, but none connected (captive / filtered).
- "none"    : no host resolved (no working resolver / no network).
- "unknown" : unexpected error.

Targets are tried in order (primary first, then fallbacks). Cached for
``ttl_s`` so the 1 Hz monitor does not open a connection every tick.
"""
from __future__ import annotations

import logging
import socket
import time

log = logging.getLogger("smartqos.connectivity")


class ConnectivityProbe:
    def __init__(
        self,
        host: str = "one.one.one.one",
        fallback_hosts: list[str] | None = None,
        port: int = 443,
        timeout_s: float = 2.0,
        ttl_s: float = 10.0,
    ) -> None:
        self.host = host
        self.fallback_hosts = list(fallback_hosts or [])
        self.port = port
        self.timeout_s = timeout_s
        self.ttl_s = ttl_s
        self._cached: tuple[str, float | None] = ("unknown", None)
        self._ts: float = 0.0

    def check(self) -> tuple[str, float | None]:
        now = time.monotonic()
        if now - self._ts < self.ttl_s:
            return self._cached
        result = self._probe()
        self._cached = result
        self._ts = now
        return result

    def _probe(self) -> tuple[str, float | None]:
        targets = [self.host, *self.fallback_hosts]
        dns_ok = False
        for h in targets:
            try:
                start = time.monotonic()
                with socket.create_connection((h, self.port), timeout=self.timeout_s):
                    latency_ms = round((time.monotonic() - start) * 1000, 1)
                return ("ok", latency_ms)  # resolved + connected
            except socket.gaierror:
                # DNS resolution failed for this host; try the next.
                continue
            except OSError:
                # Resolved but could not connect (refused/timeout) — DNS works.
                dns_ok = True
                continue
        if dns_ok:
            return ("limited", None)
        return ("none", None)
