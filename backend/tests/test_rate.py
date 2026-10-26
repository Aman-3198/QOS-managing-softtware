"""Speed-calculation and unit-conversion math (pure functions)."""
from __future__ import annotations

import math

import pytest

from app.core.rate import (
    bps_to_mbps,
    compute_bps,
    kbit_to_mbps,
    mbps_to_bps,
    mbps_to_kbit,
)


def test_compute_bps_basic():
    # 1,000,000 bytes in 1 s = 8,000,000 bit/s = 8 Mbps
    assert compute_bps(1_000_000, 2_000_000, 1.0) == 8_000_000.0


def test_compute_bps_zero_delta():
    assert compute_bps(500, 500, 1.0) == 0.0


def test_compute_bps_counter_reset_returns_none():
    # Negative delta => counter reset => unavailable, never negative.
    assert compute_bps(5_000_000, 100, 1.0) is None


def test_compute_bps_handles_none():
    assert compute_bps(None, 100, 1.0) is None
    assert compute_bps(100, None, 1.0) is None


def test_compute_bps_handles_bad_elapsed():
    assert compute_bps(0, 10, 0.0) is None
    assert compute_bps(0, 10, -1.0) is None


def test_bps_to_mbps_roundtrip():
    assert bps_to_mbps(8_000_000.0) == 8.0
    assert bps_to_mbps(None) is None
    assert mbps_to_bps(8.0) == 8_000_000.0


def test_mbps_to_kbit_decimal_not_binary():
    # 1 Mbps = 1000 kbit (decimal), NOT 1024.
    assert mbps_to_kbit(1.0) == 1000
    assert mbps_to_kbit(2.5) == 2500
    assert kbit_to_mbps(1000) == 1.0


def test_mbps_to_kbit_rounds():
    assert mbps_to_kbit(1.0001) == 1000
    assert mbps_to_kbit(0.5) == 500


def test_compute_bps_large_rate_sane():
    # 1 GB delta in 1s = 8 Gbps — no overflow/craziness.
    rate = compute_bps(0, 1_073_741_824, 1.0)
    assert rate is not None
    assert math.isclose(rate, 8_589_934_592.0, rel_tol=1e-9)
