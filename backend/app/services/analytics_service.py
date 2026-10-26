"""Analytics: historical traffic from the downsampled traffic_sample table.

Reads the aggregate + per-device samples that the monitor has been persisting
(every ~5s). History endpoints downsample to a fixed number of points for
charts. Export returns CSV (traffic counters only — no secrets, per the spec).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

RANGES = {"5m": 300, "1h": 3600, "24h": 86400, "7d": 604800}
MAX_POINTS = 120


def _rows(scope: str, device_id: str | None, secs: int) -> list[dict]:
    """Fetch samples as plain dicts (extracted within the session to avoid
    DetachedInstanceError). Stored timestamps are naive UTC (SQLite), so the
    cutoff is naive UTC too."""
    from ..database import session_scope
    from ..models import TrafficSample

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=secs)
    with session_scope() as s:
        q = s.query(TrafficSample).filter(
            TrafficSample.ts >= cutoff, TrafficSample.scope == scope
        )
        if device_id:
            q = q.filter(TrafficSample.scope_id == device_id)
        rows = q.order_by(TrafficSample.ts).all()
        return [
            {"ts": r.ts, "dl_bps": r.dl_bps, "ul_bps": r.ul_bps,
             "dl_bytes": r.dl_bytes, "ul_bytes": r.ul_bytes,
             "scope": r.scope, "scope_id": r.scope_id, "iface": r.iface}
            for r in rows
        ]


def _iso(ts) -> str:
    return ts.isoformat() if isinstance(ts, datetime) else str(ts)


def _downsample(rows: list[dict], target: int = MAX_POINTS) -> list[dict]:
    points = [{
        "ts": _iso(r["ts"]), "dl_bps": r["dl_bps"], "ul_bps": r["ul_bps"],
        "dl_bytes": r["dl_bytes"], "ul_bytes": r["ul_bytes"],
    } for r in rows]
    if len(points) <= target:
        return points
    step = len(points) / target
    out: list[dict] = []
    i = 0.0
    while i < len(points):
        bucket = points[int(i):int(i + step) + 1]
        if not bucket:
            i += step
            continue

        def avg(k):
            vals = [b[k] for b in bucket if b[k] is not None]
            return sum(vals) / len(vals) if vals else None
        out.append({
            "ts": bucket[-1]["ts"],
            "dl_bps": avg("dl_bps"), "ul_bps": avg("ul_bps"),
            "dl_bytes": max(b["dl_bytes"] for b in bucket),
            "ul_bytes": max(b["ul_bytes"] for b in bucket),
        })
        i += step
    return out


class AnalyticsService:
    def history(self, range_name: str = "1h", scope: str = "aggregate", device_id: str | None = None) -> dict:
        secs = RANGES.get(range_name, 3600)
        rows = _rows(scope, device_id, secs)
        return {"range": range_name, "scope": scope, "device_id": device_id,
                "samples": _downsample(rows)}

    def summary(self, range_name: str = "1h") -> dict:
        secs = RANGES.get(range_name, 3600)
        agg = _rows("aggregate", None, secs)
        total_dl = max((r["dl_bytes"] for r in agg), default=0)
        total_ul = max((r["ul_bytes"] for r in agg), default=0)
        peak_dl = max((r["dl_bps"] for r in agg if r["dl_bps"] is not None), default=0)
        peak_ul = max((r["ul_bps"] for r in agg if r["ul_bps"] is not None), default=0)
        dev_rows = _rows("device", None, secs)
        by_id: dict[str, list] = {}
        for r in dev_rows:
            by_id.setdefault(r["scope_id"], []).append(r)
        per_device = [{
            "id": did,
            "dl_bytes": max((r["dl_bytes"] for r in rs), default=0),
            "ul_bytes": max((r["ul_bytes"] for r in rs), default=0),
            "peak_dl_bps": max((r["dl_bps"] for r in rs if r["dl_bps"] is not None), default=0),
        } for did, rs in by_id.items()]
        return {"window": range_name, "total_dl_bytes": total_dl, "total_ul_bytes": total_ul,
                "peak_dl_bps": peak_dl, "peak_ul_bps": peak_ul, "per_device": per_device}

    def export_csv(self, range_name: str = "1h") -> str:
        secs = RANGES.get(range_name, 3600)
        rows = _rows("aggregate", None, secs)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["timestamp", "scope", "iface", "dl_bps", "ul_bps", "dl_bytes", "ul_bytes"])
        for r in rows:
            w.writerow([_iso(r["ts"]), r["scope"], r["iface"], r["dl_bps"], r["ul_bps"],
                        r["dl_bytes"], r["ul_bytes"]])
        return buf.getvalue()  # traffic counters only; no secrets
