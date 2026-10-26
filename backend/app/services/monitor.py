"""Monitoring engine + pub/sub hub (Phase 3: real read-only collection).

The monitor is a single background task (started in the app lifespan). At each
tick it reads aggregate byte counters from /proc/net/dev for the default-route
(upstream) interface and computes real download/upload rates. No privileged
operations, no network configuration changes, no fabricated numbers.

Measurement source (documented in NETWORK_SHAPING.md):
- Aggregate download = rx_bps on the upstream interface (bytes from the internet).
- Aggregate upload     = tx_bps on the upstream interface (bytes to the internet).
- Cumulative totals accumulate non-negative deltas (survive counter resets).
- Per-device accounting arrives in Phase 4/5 (tc class stats); until then the
  device list is empty and the UI shows "Unavailable", never a fake number.

A downsampled aggregate sample is persisted to SQLite at a configurable interval
(default 5 s) so Phase 8 has data; retention/aggregation is Phase 8's job.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from ..config import settings
from ..core.rate import compute_bps
from ..schemas import (
    AggregateTraffic,
    HotspotStatus,
    MonitorSnapshot,
    QoSSnapshot,
    UpstreamSnapshot,
)
from .connectivity import ConnectivityProbe
from .network_info import NetworkContext, read_proc_net_dev

log = logging.getLogger("smartqos.monitor")


class RateAccumulator:
    """Per-interface rate + cumulative-byte accumulator.

    Download uses the interface's rx counter; upload uses tx. On a counter reset
    (negative delta, e.g. interface restart/rollover) the rate for that interval
    is None (unavailable) and the cumulative total does not go backwards.
    """

    def __init__(self) -> None:
        self._last_rx: int | None = None
        self._last_tx: int | None = None
        self._last_ts: float | None = None
        self.dl_bytes_total: int = 0
        self.ul_bytes_total: int = 0
        self.dl_bps: float | None = None
        self.ul_bps: float | None = None

    def update(self, rx_bytes: int, tx_bytes: int, ts: float) -> None:
        if self._last_ts is None:
            # First sample: no rate yet, just seed the baseline.
            self._last_rx, self._last_tx, self._last_ts = rx_bytes, tx_bytes, ts
            self.dl_bps = None
            self.ul_bps = None
            return
        dt = ts - self._last_ts
        self.dl_bps = compute_bps(self._last_rx, rx_bytes, dt)
        self.ul_bps = compute_bps(self._last_tx, tx_bytes, dt)
        dl_delta = rx_bytes - self._last_rx
        ul_delta = tx_bytes - self._last_tx
        if dl_delta > 0:
            self.dl_bytes_total += dl_delta
        if ul_delta > 0:
            self.ul_bytes_total += ul_delta
        self._last_rx, self._last_tx, self._last_ts = rx_bytes, tx_bytes, ts


class MonitorHub:
    """In-memory pub/sub for monitor snapshots, with a latest-snapshot cache."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[MonitorSnapshot]] = set()
        self._latest: MonitorSnapshot | None = None

    async def subscribe(self) -> asyncio.Queue[MonitorSnapshot]:
        q: asyncio.Queue[MonitorSnapshot] = asyncio.Queue(maxsize=100)
        self._subs.add(q)
        if self._latest is not None:
            try:
                q.put_nowait(self._latest)
            except asyncio.QueueFull:
                pass
        return q

    def unsubscribe(self, q: asyncio.Queue[MonitorSnapshot]) -> None:
        self._subs.discard(q)

    async def publish(self, snapshot: MonitorSnapshot) -> None:
        self._latest = snapshot
        for q in list(self._subs):
            try:
                q.put_nowait(snapshot)
            except asyncio.QueueFull:
                log.warning("monitor subscriber queue full; dropping snapshot")

    @property
    def latest(self) -> MonitorSnapshot | None:
        return self._latest


class Monitor:
    def __init__(
        self,
        hub: MonitorHub,
        interval_s: float = 1.0,
        network_ctx: NetworkContext | None = None,
        probe: ConnectivityProbe | None = None,
        persist_interval_s: int = 5,
        persist_enabled: bool = True,
        device_service: "object | None" = None,
    ) -> None:
        self.hub = hub
        self.interval_s = max(0.25, float(interval_s))
        self.net = network_ctx or NetworkContext()
        self.probe = probe or ConnectivityProbe()
        self.persist_interval_s = max(1, int(persist_interval_s))
        self.persist_enabled = persist_enabled
        self.device_service = device_service
        self._accum = RateAccumulator()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._last_persist_ts: float = 0.0
        self._warnings: list[str] = []

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="sqm-monitor")
            log.info("monitor started (interval=%.2fs)", self.interval_s)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None
        log.info("monitor stopped")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                snap = await self.collect()
                await self.hub.publish(snap)
            except Exception:  # never let the monitor die silently
                log.exception("monitor collect failed (continuing)")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass

    async def collect(self) -> MonitorSnapshot:
        now_mono = time.monotonic()
        counters = read_proc_net_dev()
        route = self.net.default_route()
        upstream_iface = route.get("dev") if route else None
        gateway = route.get("gateway") if route else None

        self._warnings = []
        if upstream_iface is None:
            self._warnings.append("no default route — upstream interface unknown")
        if not counters:
            self._warnings.append("could not read /proc/net/dev counters")

        # Real aggregate rate from the upstream interface (download=rx, upload=tx).
        if upstream_iface and upstream_iface in counters:
            c = counters[upstream_iface]
            self._accum.update(c["rx_bytes"], c["tx_bytes"], now_mono)
        else:
            # Upstream missing from counters: no rate this tick, keep totals.
            self._accum.dl_bps = None
            self._accum.ul_bps = None

        # Hotspot observation (real: AP interface active => started, else stopped).
        hs = self.net.hotspot()
        hotspot = HotspotStatus(
            state=hs.state,
            ssid=hs.ssid,
            hotspot_interface=hs.hotspot_interface,
            upstream_interface=upstream_iface,
            gateway_ip=gateway,
            channel=hs.channel,
            connected_count=0,  # device discovery is Phase 4
        )

        # Internet connectivity (cached probe).
        internet, latency_ms = self.probe.check()

        # Per-device discovery + rates (Phase 4). Empty when no hotspot is up.
        device_snapshots: list = []
        if self.device_service is not None:
            try:
                device_snapshots = self.device_service.tick()
            except Exception:
                log.debug("device_service.tick failed", exc_info=True)

        snap = MonitorSnapshot(
            ts=datetime.now(timezone.utc),
            hotspot=hotspot,
            upstream=UpstreamSnapshot(internet=internet, latency_ms=latency_ms),
            aggregate=AggregateTraffic(
                dl_bps=self._accum.dl_bps,
                ul_bps=self._accum.ul_bps,
                dl_bytes=self._accum.dl_bytes_total,
                ul_bytes=self._accum.ul_bytes_total,
            ),
            devices=device_snapshots,
            qos=[],
            warnings=list(self._warnings),
        )

        # Lightweight downsampled persistence (sets up Phase 8).
        if self.persist_enabled and (now_mono - self._last_persist_ts) >= self.persist_interval_s:
            self._last_persist_ts = now_mono
            await asyncio.to_thread(self._persist_sample, upstream_iface, snap)

        return snap

    def _persist_sample(self, iface: str | None, snap: MonitorSnapshot) -> None:
        try:
            from ..database import session_scope
            from ..models import TrafficSample

            with session_scope() as s:
                s.add(
                    TrafficSample(
                        scope="aggregate",
                        iface=iface,
                        dl_bytes=snap.aggregate.dl_bytes,
                        ul_bytes=snap.aggregate.ul_bytes,
                        dl_bps=snap.aggregate.dl_bps,
                        ul_bps=snap.aggregate.ul_bps,
                    )
                )
        except Exception:
            log.debug("traffic sample persist failed", exc_info=True)


def build_default_monitor(hub: MonitorHub) -> Monitor:
    """Factory used by the app lifespan (wires real NetworkContext + probe)."""
    return Monitor(
        hub=hub,
        interval_s=settings.monitor_interval_s,
        network_ctx=NetworkContext(),
        probe=ConnectivityProbe(
            host=settings.connectivity_host,
            ip=settings.connectivity_ip,
            port=settings.connectivity_port,
            timeout_s=settings.connectivity_timeout_s,
            ttl_s=settings.connectivity_ttl_s,
        ),
        persist_interval_s=settings.history_sample_interval_s,
        persist_enabled=True,
    )
