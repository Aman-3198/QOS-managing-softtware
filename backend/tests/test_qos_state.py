"""QoS state builder + command generation (pure logic, no root needed)."""
from __future__ import annotations

from app.services.qos_state import (
    CLASS_ID_MAX,
    CLASS_ID_MIN,
    DEFAULT_CLASS_MINOR,
    MARK_DOWN_BASE,
    MARK_UP_BASE,
    PARENT_CLASS_MINOR,
    ROOT_HANDLE,
    DeviceRule,
    allocate,
    build_desired_state,
    cleanup_nft,
    cleanup_tc_lines,
    nft_ruleset,
    tc_batch_lines,
)


def _rule(**kw) -> DeviceRule:
    base = dict(device_id="d1", mac="aa:bb:cc:dd:ee:ff", ip="10.42.0.5",
                dl_limit_mbps=5.0, ul_limit_mbps=2.0, priority="high",
                enabled=True, paused=False)
    base.update(kw)
    return DeviceRule(**base)


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------
def test_allocate_assigns_unique_class_ids_and_marks():
    rules = [_rule(device_id="d1"), _rule(device_id="d2", ip="10.42.0.6")]
    allocated, paused, warnings = allocate(rules)
    ids = {a.class_id for a in allocated}
    assert len(ids) == 2
    assert all(CLASS_ID_MIN <= i <= CLASS_ID_MAX for i in ids)
    for a in allocated:
        assert a.mark_up == MARK_UP_BASE | a.class_id
        assert a.mark_down == MARK_DOWN_BASE | a.class_id


def test_allocate_skips_paused_and_records_ip():
    rules = [_rule(paused=True), _rule(enabled=False), _rule(device_id="d2")]
    allocated, paused, warnings = allocate(rules)
    assert len(allocated) == 1                 # only the enabled, non-paused one
    assert paused == ["10.42.0.5"]              # paused device's IP recorded for drop rules


def test_allocate_warns_on_missing_ip():
    rules = [_rule(ip=None)]
    allocated, paused, warnings = allocate(rules)
    assert allocated == []
    assert any("no IPv4" in w for w in warnings)


def test_allocate_caps_class_count():
    rules = [_rule(device_id=f"d{i}", ip=f"10.42.0.{i}") for i in range(5)]
    # Force the cap by setting a tiny max in allocate via monkeypatching the range.
    from app.services import qos_state

    orig_min, orig_max = qos_state.CLASS_ID_MIN, qos_state.CLASS_ID_MAX
    qos_state.CLASS_ID_MIN = 0x10
    qos_state.CLASS_ID_MAX = 0x11  # only 2 ids available
    try:
        allocated, paused, warnings = allocate(rules)
    finally:
        qos_state.CLASS_ID_MIN, qos_state.CLASS_ID_MAX = orig_min, orig_max
    assert len(allocated) == 2
    assert any("max class count" in w for w in warnings)


# ---------------------------------------------------------------------------
# tc batch generation
# ---------------------------------------------------------------------------
def test_tc_upload_uses_ul_limit_and_up_marks():
    state = build_desired_state("eno1", "wlp4s0", [_rule()], parent_cap_mbps=100, min_rate_mbps=0.1)
    lines = tc_batch_lines(state, "up")
    assert not any(l.startswith("qdisc") for l in lines if "replace" not in l and "add" not in l)
    assert any(l.startswith("qdisc replace dev eno1 root") for l in lines) or \
           any(l.startswith("class replace dev eno1") for l in lines)
    assert any(f"classid 1:{PARENT_CLASS_MINOR:x}" in l for l in lines)
    assert any(f"classid 1:{DEFAULT_CLASS_MINOR:x}" in l for l in lines)
    a = state.rules[0]
    cid = f"1:{a.class_id:x}"
    class_line = next(l for l in lines if "class replace dev eno1" in l and f"classid {cid}" in l)
    assert "ceil 2000kbit" in class_line
    assert "prio 1" in class_line
    filt = next(l for l in lines if "filter replace dev eno1" in l)
    assert f"{a.mark_up:x}" in filt
    assert "flowid" in filt
    assert any("fq_codel" in l for l in lines)
    assert any(f"classid 1:{PARENT_CLASS_MINOR:x}" in l for l in lines)
    assert any(f"classid 1:{DEFAULT_CLASS_MINOR:x}" in l for l in lines)
    a = state.rules[0]
    cid = f"1:{a.class_id:x}"
    class_line = next(l for l in lines if "class replace dev eno1" in l and f"classid {cid}" in l)
    assert "ceil 2000kbit" in class_line
    assert "prio 1" in class_line
    filt = next(l for l in lines if "filter replace dev eno1" in l)
    assert f"{a.mark_up:x}" in filt
    assert "flowid" in filt
    assert f"classid {cid}" not in filt
    assert any("fq_codel" in l for l in lines)


def test_tc_download_uses_dl_limit_and_down_marks():
    state = build_desired_state("eno1", "wlp4s0", [_rule()])
    lines = tc_batch_lines(state, "down")
    a = state.rules[0]
    cid = f"1:{a.class_id:x}"
    class_line = next(l for l in lines if f"classid {cid}" in l and "class replace" in l)
    assert "ceil 5000kbit" in class_line
    filt = next(l for l in lines if "filter replace dev wlp4s0" in l)
    assert f"{a.mark_down:x}" in filt
    assert "flowid" in filt


def test_tc_unlimited_uses_parent_cap_as_ceil():
    state = build_desired_state("eno1", "wlp4s0", [_rule(ul_limit_mbps=None, dl_limit_mbps=None)])
    up = tc_batch_lines(state, "up")
    class_line = next(l for l in up if f"1:{state.rules[0].class_id:x}" in l and "classid" in l)
    assert "ceil 100000kbit" in class_line             # parent cap 100 Mbps


def test_tc_empty_when_interface_unknown():
    state = build_desired_state(None, "wlp4s0", [_rule()])
    assert tc_batch_lines(state, "up") == []
    state2 = build_desired_state("eno1", None, [_rule()])
    assert tc_batch_lines(state2, "down") == []


# ---------------------------------------------------------------------------
# nftables ruleset
# ---------------------------------------------------------------------------
def test_nft_ruleset_contains_marks_and_pause_drops():
    rules = [_rule(device_id="d1", ip="10.42.0.5"),
             _rule(device_id="d2", ip="10.42.0.6", paused=True)]
    state = build_desired_state("eno1", "wlp4s0", rules)
    text = nft_ruleset(state)
    assert "table inet smartqos {" in text
    assert "hook prerouting priority mangle" in text
    assert "hook postrouting priority mangle" in text
    assert "hook forward priority filter" in text
    # upload mark rule by src IP
    a = state.rules[0]
    assert f'ip saddr 10.42.0.5 meta mark set {hex(a.mark_up)}' in text
    assert f'ip daddr 10.42.0.5 meta mark set {hex(a.mark_down)}' in text
    # paused device gets drop rules (both directions)
    assert 'ip saddr 10.42.0.6 drop' in text
    assert 'ip daddr 10.42.0.6 drop' in text


def test_nft_ruleset_omits_ip_rules_when_no_hotspot():
    state = build_desired_state("eno1", None, [_rule()])
    text = nft_ruleset(state)
    assert "10.42.0.5" not in text    # no marking rules without a hotspot interface


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def test_cleanup_only_targets_app_owned_objects():
    assert cleanup_tc_lines("eno1") == [f"qdisc del dev eno1 root handle {ROOT_HANDLE} htb"]
    assert cleanup_nft() == "delete table inet smartqos\n"
