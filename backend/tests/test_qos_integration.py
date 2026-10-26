"""Network integration test: proves Linux HTB actually constrains throughput.

Requires root (network namespaces) and iperf3. Skips gracefully otherwise, so
the unprivileged unit suite stays green. Run it explicitly with:

    sudo apt install -y iperf3
    sudo -E uv run pytest backend/tests/test_qos_integration.py -s

This is the test the spec demands before claiming shaping works: a rate limited
to 5 Mbit must actually measure around 5 Mbit, well below the unshaped baseline.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

import pytest


def _run(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _iperf_recv_mbps(ns_server, ns_client, seconds):
    # iperf3 -s -1 handles one client then exits; server prints JSON to stdout.
    srv = subprocess.Popen(
        ["ip", "netns", "exec", ns_server, "iperf3", "-s", "-1", "-J", "-p", "5201"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    c = _run(["ip", "netns", "exec", ns_client, "iperf3", "-c", "10.0.0.1",
              "-t", str(seconds), "-J", "-p", "5201"], timeout=seconds + 15)
    try:
        srv.wait(timeout=5)
    except subprocess.TimeoutExpired:
        srv.kill()
    data = json.loads(c.stdout)
    return data["end"]["sum_received"]["bits_per_second"] / 1e6


@pytest.mark.skipif(os.geteuid() != 0, reason="needs root for network namespaces")
def test_htb_limits_throughput():
    if shutil.which("iperf3") is None:
        pytest.skip("iperf3 not installed (sudo apt install iperf3)")
    if shutil.which("ip") is None:
        pytest.skip("iproute2 not found")

    NS1, NS2 = "sqm_t_ns1", "sqm_t_ns2"
    V1, V2 = "sqm_t_v1", "sqm_t_v2"

    def ip(*a):
        return _run(["ip", *a], timeout=10)

    # Clean any leftovers from a previous aborted run.
    ip("netns", "del", NS1)
    ip("netns", "del", NS2)

    try:
        ip("netns", "add", NS1)
        ip("netns", "add", NS2)
        ip("link", "add", V1, "type", "veth", "peer", "name", V2)
        ip("link", "set", V1, "netns", NS1)
        ip("link", "set", V2, "netns", NS2)
        ip("netns", "exec", NS1, "ip", "addr", "add", "10.0.0.1/24", "dev", V1)
        ip("netns", "exec", NS2, "ip", "addr", "add", "10.0.0.2/24", "dev", V2)
        for ns in (NS1, NS2):
            ip("netns", "exec", ns, "ip", "link", "set", V1 if ns == NS1 else V2, "up")
            ip("netns", "exec", ns, "ip", "link", "set", "lo", "up")

        # 1) Unshaped baseline (only limited by the veth/CPU) — should be high.
        baseline = _iperf_recv_mbps(NS1, NS2, seconds=2)
        assert baseline > 20, f"baseline unexpectedly low: {baseline:.1f} Mbps"

        # 2) Apply HTB limiting the SENDER (NS2) egress to 5 Mbit.
        ip("netns", "exec", NS2, "tc", "qdisc", "add", "dev", V2, "root",
           "handle", "1:", "htb", "default", "10")
        ip("netns", "exec", NS2, "tc", "class", "add", "dev", V2, "parent", "1:",
           "classid", "1:1", "htb", "rate", "1000mbit")
        ip("netns", "exec", NS2, "tc", "class", "add", "dev", V2, "parent", "1:1",
           "classid", "1:10", "htb", "rate", "5mbit", "ceil", "5mbit")

        shaped = _iperf_recv_mbps(NS1, NS2, seconds=5)

        # The decisive assertion: the shaped rate is far below baseline AND ~5 Mbit.
        assert shaped < baseline * 0.5, f"shaping had little effect: {shaped:.1f} vs {baseline:.1f}"
        assert 3.0 < shaped < 8.5, f"shaped rate not ~5 Mbps: {shaped:.2f} Mbps"

        # 3) Cleanup: removing our qdisc restores the link to no shaping.
        ip("netns", "exec", NS2, "tc", "qdisc", "del", "dev", V2, "root")
        after = _iperf_recv_mbps(NS1, NS2, seconds=2)
        assert after > shaped * 2, f"cleanup did not restore throughput: {after:.1f}"
    finally:
        ip("netns", "del", NS1)
        ip("netns", "del", NS2)
