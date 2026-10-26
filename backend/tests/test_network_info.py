"""Network info parsing + live discovery (read-only)."""
from __future__ import annotations

import pytest

from app.services.network_info import (
    NetworkContext,
    parse_proc_net_dev,
    read_proc_net_dev,
)


SAMPLE = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:  442257    2018    0    0    0     0          0         0   442257    2018    0    0    0     0       0          0
  eno1:       0       0    0    0    0     0          0         0        0       0    0    0    0     0       0       0
wlp4s0: 404156595  286447    0    0    0     0          0         0 15245513  108720    0    0    0     0       0       0
"""


def test_parse_proc_net_dev_extracts_bytes():
    c = parse_proc_net_dev(SAMPLE)
    assert set(c.keys()) == {"lo", "eno1", "wlp4s0"}
    assert c["wlp4s0"]["rx_bytes"] == 404156595
    assert c["wlp4s0"]["tx_bytes"] == 15245513
    assert c["eno1"]["rx_bytes"] == 0
    assert c["lo"]["rx_bytes"] == 442257


def test_parse_proc_net_dev_ignores_short_lines():
    text = "header1\nheader2\n  x:\n"
    assert parse_proc_net_dev(text) == {}


def test_read_proc_net_dev_live_has_loopback():
    # Integration: /proc/net/dev always exists on Linux and has lo.
    c = read_proc_net_dev()
    assert "lo" in c
    assert c["lo"]["rx_bytes"] >= 0


@pytest.mark.parametrize("iface_field", ["rx_bytes", "tx_bytes", "rx_packets"])
def test_counters_are_integers(iface_field):
    c = read_proc_net_dev()
    for name, stats in c.items():
        assert isinstance(stats[iface_field], int), f"{name}.{iface_field}"


def test_network_context_interfaces_includes_loopback():
    # Integration: real host has loopback + at least one other interface.
    ctx = NetworkContext()
    ifaces = ctx.interfaces()
    names = [i["name"] for i in ifaces]
    assert "lo" in names
    assert len(names) >= 2


def test_network_context_default_route_is_string_or_none():
    ctx = NetworkContext()
    iface = ctx.default_route_iface()
    assert iface is None or isinstance(iface, str)
