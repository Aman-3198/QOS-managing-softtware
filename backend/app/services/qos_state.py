"""QoS state builder + command generation (pure, no root needed).

Given the user's rules and the two interfaces, this produces the exact Linux
``tc`` (HTB) and ``nftables`` configuration that the privileged helper applies.
All logic here is pure and import-safe so it is unit-tested without root.

Design (see docs/NETWORK_SHAPING.md):
- Upload (client -> internet): HTB on the UPSTREAM egress; classify by fw mark
  set in nft mangle prerouting (iif hotspot, by src IP).
- Download (internet -> client): HTB on the HOTSPOT egress; classify by fw mark
  set in nft mangle postrouting (oif hotspot, by dst IP).
- Marks survive NAT, so classification works through MASQUERADE.
- All app-owned objects live in a dedicated ``inet smartqos`` table + tc qdisc
  root handle ``1:`` with reserved class ids. Cleanup only removes these.

Rate units: user-facing decimal Mbps. tc uses decimal ``kbit`` (1 Mbps = 1000
kbit), so we emit integer kbit values (no floats in tc args).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.constants import PRIORITY_TO_PRIO
from ..core.rate import mbps_to_kbit

# --- Ownership markers / reserved ranges ---
ROOT_HANDLE = "1:"
PARENT_CLASS_MINOR = 1          # 1:1 parent class bounding the aggregate
DEFAULT_CLASS_MINOR = 0xFF      # 1:0xff for unclassified traffic
CLASS_ID_MIN = 0x10
CLASS_ID_MAX = 0xFE             # device class ids 0x10..0xFE (240 devices)
MARK_UP_BASE = 0x1000          # upload marks: 0x1000 | class_id
MARK_DOWN_BASE = 0x2000        # download marks: 0x2000 | class_id


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class DeviceRule:
    device_id: str
    mac: str | None = None
    ip: str | None = None              # current IPv4 of the client (for nft rules)
    dl_limit_mbps: float | None = None  # download ceiling; None = unlimited
    ul_limit_mbps: float | None = None  # upload ceiling; None = unlimited
    priority: str = "normal"
    enabled: bool = True
    paused: bool = False


@dataclass
class AllocatedRule:
    rule: DeviceRule
    class_id: int
    mark_up: int
    mark_down: int


@dataclass
class DesiredState:
    upstream_iface: str | None
    hotspot_iface: str | None
    parent_cap_mbps: float
    min_rate_mbps: float
    rules: list[AllocatedRule] = field(default_factory=list)  # classed (enabled, not paused, has ip)
    paused_ips: list[str] = field(default_factory=list)        # paused devices' IPv4s
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------
def allocate(rules: list[DeviceRule]) -> tuple[list[AllocatedRule], list[str], list[str]]:
    """Assign class ids + marks to classable rules.

    A rule is classable if it is enabled, not paused, has a known IPv4, and the
    hotspot/upstream interfaces exist (checked by the caller). Returns:
      (allocated_rules, paused_ips, warnings).
    Paused devices get no tc class (their traffic is dropped by nft first).
    """
    allocated: list[AllocatedRule] = []
    paused_ips: list[str] = []
    warnings: list[str] = []
    next_id = CLASS_ID_MIN
    for r in rules:
        if r.paused:
            if r.ip:
                paused_ips.append(r.ip)
            continue
        if not r.enabled:
            continue
        if not r.ip:
            warnings.append(f"device {r.device_id} has no IPv4; not shaped this cycle")
            continue
        if next_id > CLASS_ID_MAX:
            warnings.append("max class count reached; remaining devices unshaped")
            break
        allocated.append(AllocatedRule(
            rule=r,
            class_id=next_id,
            mark_up=MARK_UP_BASE | next_id,
            mark_down=MARK_DOWN_BASE | next_id,
        ))
        next_id += 1
    return allocated, paused_ips, warnings


def build_desired_state(
    upstream_iface: str | None,
    hotspot_iface: str | None,
    rules: list[DeviceRule],
    parent_cap_mbps: float = 100.0,
    min_rate_mbps: float = 0.1,
) -> DesiredState:
    allocated, paused_ips, warnings = allocate(rules)
    if not upstream_iface or not hotspot_iface:
        warnings.append("upstream or hotspot interface unknown; shaping not applied")
    return DesiredState(
        upstream_iface=upstream_iface,
        hotspot_iface=hotspot_iface,
        parent_cap_mbps=float(parent_cap_mbps),
        min_rate_mbps=float(min_rate_mbps),
        rules=allocated,
        paused_ips=paused_ips,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# tc batch generation (one interface, one direction)
# ---------------------------------------------------------------------------
def _kbit(mbps: float) -> str:
    return f"{mbps_to_kbit(mbps)}kbit"


def tc_batch_lines(state: DesiredState, direction: str) -> list[str]:
    """Generate tc -batch commands that work whether or not the qdisc already exists.

    Uses 'class replace' (idempotent: creates or updates) and skips the root
    qdisc line entirely — the helper's _apply_tc_batch does del+add for the root.
    The leaf fq_codel uses 'replace' so it works on both first apply and updates.
    """
    iface = state.upstream_iface if direction == "up" else state.hotspot_iface
    if not iface:
        return []
    cap = _kbit(state.parent_cap_mbps)
    mn  = _kbit(state.min_rate_mbps)
    lines: list[str] = []
    # Parent + default classes (replace = create-or-update, never fails if exists).
    lines.append(
        f"class replace dev {iface} parent {ROOT_HANDLE} classid 1:{PARENT_CLASS_MINOR:x} "
        f"htb rate {cap} ceil {cap} quantum 1514"
    )
    lines.append(
        f"class replace dev {iface} parent 1:{PARENT_CLASS_MINOR:x} "
        f"classid 1:{DEFAULT_CLASS_MINOR:x} htb rate {mn} ceil {cap} prio 3 quantum 1514"
    )
    for a in state.rules:
        limit_mbps = a.rule.ul_limit_mbps if direction == "up" else a.rule.dl_limit_mbps
        ceil     = _kbit(limit_mbps) if limit_mbps is not None else cap
        prio     = PRIORITY_TO_PRIO.get(a.rule.priority, PRIORITY_TO_PRIO["normal"])
        cid      = f"1:{a.class_id:x}"
        mark_hex = f"{(a.mark_up if direction == 'up' else a.mark_down):x}"
        lines.append(
            f"class replace dev {iface} parent 1:{PARENT_CLASS_MINOR:x} classid {cid} "
            f"htb rate {mn} ceil {ceil} prio {prio} quantum 1514"
        )
        lines.append(
            f"qdisc replace dev {iface} parent {cid} handle {a.class_id:x}: fq_codel"
        )
        lines.append(
            f"filter replace dev {iface} parent {ROOT_HANDLE} protocol ip prio 1 "
            f"fw handle {mark_hex} flowid {cid}"
        )
    return lines


# ---------------------------------------------------------------------------
# nftables ruleset (dedicated table; atomic apply via `nft -f -`)
# ---------------------------------------------------------------------------
def nft_ruleset(state: DesiredState) -> str:
    """Generate the full `inet smartqos` table text for `nft -f -`."""
    hs = state.hotspot_iface
    lines: list[str] = ["table inet smartqos {"]

    # Upload marking: prerouting, iif hotspot, by src IP -> mark_up.
    lines.append("    chain sqm_mangle_pre {")
    lines.append("        type filter hook prerouting priority mangle; policy accept;")
    if hs:
        for a in state.rules:
            if a.rule.ip:
                lines.append(
                    f'        iifname "{hs}" ip saddr {a.rule.ip} meta mark set {hex(a.mark_up)}'
                )
    lines.append("    }")

    # Download marking: postrouting, oif hotspot, by dst IP -> mark_down.
    lines.append("    chain sqm_mangle_post {")
    lines.append("        type filter hook postrouting priority mangle; policy accept;")
    if hs:
        for a in state.rules:
            if a.rule.ip:
                lines.append(
                    f'        oifname "{hs}" ip daddr {a.rule.ip} meta mark set {hex(a.mark_down)}'
                )
    lines.append("    }")

    # Pause: drop forwarded internet traffic for paused clients (keeps gateway
    # management reachable, which is INPUT not FORWARD).
    lines.append("    chain sqm_drop_paused {")
    lines.append("        type filter hook forward priority filter; policy accept;")
    if hs:
        for ip in state.paused_ips:
            lines.append(f'        iifname "{hs}" ip saddr {ip} drop')
            lines.append(f'        oifname "{hs}" ip daddr {ip} drop')
    lines.append("    }")

    lines.append("}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Cleanup (remove only app-owned objects)
# ---------------------------------------------------------------------------
def cleanup_tc_lines(iface: str) -> list[str]:
    """tc lines to remove our qdisc on an interface."""
    return [f"qdisc del dev {iface} root handle {ROOT_HANDLE} htb"]


def cleanup_nft() -> str:
    """nft statement to remove our dedicated table (only ours)."""
    return "delete table inet smartqos\n"
