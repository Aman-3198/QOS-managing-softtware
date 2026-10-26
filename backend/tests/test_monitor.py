"""RateAccumulator behavior: real rate + cumulative totals + reset handling."""
from __future__ import annotations

from app.services.monitor import RateAccumulator


def test_first_update_has_no_rate():
    acc = RateAccumulator()
    acc.update(rx_bytes=1000, tx_bytes=2000, ts=0.0)
    assert acc.dl_bps is None
    assert acc.ul_bps is None
    assert acc.dl_bytes_total == 0
    assert acc.ul_bytes_total == 0


def test_rate_computed_from_delta():
    acc = RateAccumulator()
    acc.update(1_000_000, 500_000, ts=0.0)       # baseline
    acc.update(2_000_000, 500_000, ts=1.0)       # +1 MB rx in 1s = 8 Mbps
    assert acc.dl_bps == 8_000_000.0
    assert acc.ul_bps == 0.0                      # no tx change
    assert acc.dl_bytes_total == 1_000_000
    assert acc.ul_bytes_total == 0


def test_counter_reset_yields_no_rate_and_no_negative_total():
    acc = RateAccumulator()
    acc.update(5_000_000, 5_000_000, ts=0.0)
    acc.update(100, 100, ts=1.0)  # negative delta => counter reset
    assert acc.dl_bps is None      # the reset tick itself has no rate
    assert acc.ul_bps is None
    # Totals must NOT decrease on a reset.
    assert acc.dl_bytes_total == 0
    assert acc.ul_bytes_total == 0
    # After the reset, the reset value is the new baseline; the next tick
    # computes a real rate from that baseline (100 -> 1000 = 900 B in 1 s).
    acc.update(1000, 1000, ts=2.0)
    assert acc.dl_bps == 7_200.0  # 900 bytes * 8 / 1s
    assert acc.dl_bytes_total == 900
    assert acc.ul_bytes_total == 900


def test_cumulative_totals_accumulate():
    acc = RateAccumulator()
    acc.update(0, 0, ts=0.0)
    acc.update(100, 50, ts=1.0)
    acc.update(150, 60, ts=2.0)
    assert acc.dl_bytes_total == 150
    assert acc.ul_bytes_total == 60
