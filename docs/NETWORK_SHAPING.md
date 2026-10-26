# Smart QoS Manager — Network Shaping Design

This is the technical core: how per-device upload **and** download bandwidth
limits, priorities, and pause/resume are *actually enforced* on Linux using
`tc` and `nftables`. It also documents the honest answer to the
"concurrent Wi-Fi upstream + hotspot" question and the limitations of each
shaping path.

## Topology assumptions (verified against this host)

Two realistic topologies. The app detects the upstream and hotspot interfaces
at runtime; it never hard-codes `eno1`/`wlp4s0`.

```
Topology 1 (recommended):           Topology 2 (limited, one Wi-Fi adapter):
  Internet                           Internet
    | eno1 (upstream, ethernet)        | wlp4s0 STA (upstream, managed)
    v                                  v
  [ laptop ]                         [ laptop ]  -- same radio, SAME channel
    | wlp4s0 (AP/hotspot)              | wlp4s0 becomes AP (drops STA!) ⚠
    v                                  v
  clients 10.42.0.0/24               clients
```

### The concurrent STA+AP question — honest answer

`iw list` for the MediaTek MT7921 reports the combination
`#{ managed } <= 2, #{ AP } <= 1, … #channels <= 1`. Interpretation:

- **Hardware level:** one managed + one AP virtual interface can coexist, but
  only on a **single shared channel** (the upstream AP's channel). So a
  same-channel STA+AP is *physically* possible.
- **NetworkManager behavior (decisive):** `nmcli device wifi hotspot ifname
  wlp4s0 …` **repurposes `wlp4s0` as the AP** and **drops the existing STA
  connection**. NM does not create a second managed interface to preserve the
  upstream. Therefore, with the NM-based hotspot, you cannot keep the upstream
  Wi-Fi on the same adapter.
- **Conclusion:** On this single-adapter laptop, the supported configuration is
  **Topology 1 (Ethernet upstream)**. True concurrent STA+AP requires either a
  **second Wi-Fi adapter** (USB) for the hotspot, or diverging from NM to a
  manual `iw` + `hostapd` setup that creates a second virtual interface pinned
  to the upstream channel — which we treat as an experimental alternative, not
  the default.

The app therefore:
1. Detects interfaces and their roles (STA / AP-capable / ethernet / etc.).
2. Offers the hotspot interface choice and warns if selecting the same adapter
   currently used as the upstream STA.
3. For Topology 1 it can pin the hotspot channel freely; for any same-adapter
   attempt it refuses to silently break the STA and explains the constraint.

This matches the spec: we did not assume concurrency works because the driver
lists both modes; we verified the combination string **and** NM's actual
behavior, and we report the limitation.

## Direction model

Two independent traffic directions, each shaped at the interface where that
direction's packets **leave** the laptop:

| Direction | Packets leave via | Source addr at shaping point | Dest addr |
|---|---|---|---|
| Upload (client → internet) | **upstream** egress (`eno1`) | NATed to laptop IP | internet |
| Download (internet → client) | **hotspot** egress (`wlp4s0`) | internet | client hotspot IP |

### Why egress HTB on each interface (not ingress/IFB)

- Upload egresses the upstream interface; an HTB root there shapes it cleanly
  with `rate`/`ceil` per client. This is the natural shaping point.
- Download egresses the hotspot interface toward the client; an HTB root there
  shapes the AP→client delivery, which is the effective per-client ceiling
  (a client cannot download faster than the AP transmits to it). This avoids
  the complexity of ingress policing or IFB redirection for download.
- **Documented limitation (download):** shaping the AP→client leg enforces the
  per-device ceiling effectively, but it does not "un-consume" upstream
  bandwidth that already arrived at the laptop. Under heavy aggregate download
  the upstream may still saturate momentarily before the per-client queues
  enforce ceilings. This is the standard trade-off of egress download shaping
  and is stated plainly in the UI, not hidden.

### The NAT problem and why we use firewall marks

Naive `tc u32` filters matching the client IP **break** for upload: by the time
the packet egresses the upstream interface, SNAT has rewritten `src` from the
client's hotspot IP to the laptop's upstream IP. A `u32 src <client_ip>`
filter on the upstream qdisc would never match.

Solution: set a **per-device firewall mark** with `nftables` *before* NAT, and
classify `tc` by mark (`fw` filter). Marks survive NAT, so the same mark that
describes "this packet belongs to device X" is present on the upstream egress.

```
                         nftables mangle (inet table: smartqos)
  prerouting  iifname "<hotspot>"   -> mark = map_up[ src_ip ]   (upload)
  postrouting oifname "<hotspot>"   -> mark = map_down[ dst_ip ] (download)
                         |
                         v (marks survive NAT & routing)
                  tc HTB on upstream egress   (upload classes, fw filters)
                  tc HTB on hotspot egress    (download classes, fw filters)
```

`map_up` / `map_down` are `nft` maps keyed by client IP, value = the device's
class-id-derived mark. When a DHCP lease changes, we **update the map entry**
for the new IP; stale IPs never misclassify a different device because the map
is the single source of truth, keyed by current IP.

## HTB class hierarchy

Per managed interface, an HTB root with a parent class bounding the aggregate,
and one child class per device that has a rule:

```
root 1: (HTB)
└─ 1:1  parent   rate=<iface_nominal_or_configured_cap>  ceil=same
   ├─ 1:10  device A   rate=<guaranteed_share>  ceil=<user_dl_cap>  prio=<P>
   │        └─ fq_codel  (leaf, low latency / fair queuing)
   ├─ 1:11  device B   ...
   └─ 1:12  default    rate=<residual>  ceil=<parent>  prio=3  (unclassified)
```

- `rate` = a *minimum guaranteed share* (small, e.g. parent_rate / N), used so
  HTB can lend/borrow. It is **not** the user's limit.
- `ceil` = the user's configured maximum (hard ceiling). This is what the UI's
  "limit" means: a hard maximum, not a guarantee.
- `prio` maps priority classes: `critical=0, high=1, normal=2, low=3`. Lower
  borrows first under congestion.
- `fq_codel` as the leaf qdisc per class reduces latency and provides fair
  queuing within the class.

### Priority is not a bandwidth reservation

A device set to "Critical" priority does **not** get more bandwidth or a
guaranteed rate beyond its `rate` minimum. Priority only affects **which class
borrows spare bandwidth first when the parent is saturated**. The UI states
this explicitly. The `rate` minimums are deliberately small and uniform so that
priority is a scheduling preference, not a reservation.

## Class-ID & mark allocation (ownership)

To avoid colliding with any pre-existing or future system tc config, all
app-owned handles live in a reserved range and are allocated centrally:

- Root qdisc handle: `1:` on each managed interface (we verify ownership
  before attaching/removing; see Ownership below).
- Device class handles: `1:0x10` … `1:0xFF` (a managed range, allocated from a
  monotonic counter and freed on rule removal).
- fw marks: `0xSQM`-prefixed range, e.g. `0x1000`–`0x10FF` for upload classes,
  `0x2000`–`0x20FF` for download classes. High bits identify "owned by Smart
  QoS Manager" + direction; low bits identify the device class.
- Allocation is persisted in the DB (`qos_rule.class_id`, `.mark_up`, `.mark_down`)
  so restarts reuse the same handles and there is no drift.

## nftables ownership

- A **dedicated table**: `inet smartqos`. All app rules live here.
- Chains: `sqm_mangle_pre` (hook prerouting, priority mangle),
  `sqm_mangle_post` (hook postrouting, priority mangle),
  `sqm_drop_paused` (hook forward, priority filter) for pause/resume.
- The system `filter`/`nat`/`mangle` tables are **never modified**. nftables
  evaluates all tables with the same hook by priority; our dedicated table is
  processed independently and does not require jumping from system chains.
- Pause/resume: `sqm_drop_paused` drops forwarded traffic for a paused client's
  IP **only on the forward path** (`iifname <hotspot> oifname <upstream>` and
  the reverse), while an explicit rule keeps the laptop's own management IP
  reachable (e.g. allow `ip daddr <hotspot_gw_ip>`). This never blocks the
  gateway's own management interface or the whole LAN.

## Conversions & units

- UI: Mbps (decimal). `1 Mbps = 1,000,000 bit/s`.
- tc: express as `<n>mbit` or `<n>kbit` (tc uses decimal `mbit`/`kbit`).
- Conversion: `tc_rate = mbps * 1000` → `<mbps*1000>kbit` (avoids float). For
  sub-Mbps, `kbit`. We never divide user input by 1024.
- Validation: rate must be `> 0` and `<= 10_000` Mbps and, if set, not exceed the
  configured parent cap. Zero/negative/malformed are rejected (400) with a clear
  message; "unlimited" is represented by absence of a `ceil` (class inherits
  parent), not by a sentinel number.

## Atomic apply + verify + rollback

Every rule change goes through `qos_state.build_desired()` → helper
`qos.apply`:

1. **Build desired state** from DB + live rules (a full object: qdiscs,
   classes, filters, nft rules, with app-owned markers).
2. **Diff** against the currently-applied state (last verified good).
3. **Apply** only the changes, in dependency order (qdisc → classes → filters →
   nft maps/chains). Each `tc`/`nft` call has a timeout.
4. **Verify** by reading back (`tc -s class show`, `nft list chain …`) and
   matching the desired handles + that classes have the right `ceil`/`prio`.
5. **Persist** the `qos_rule` row as `applied_at = now` only after verify.
6. **Rollback** on any failure: remove newly-added app-owned objects, re-apply
   the previous known-good state from a snapshot, mark the rule `pending`, and
   return a 503/error to the UI. The network is never left half-configured.

## Ownership & safe cleanup (no collateral damage)

- The helper **never** runs `tc qdisc del dev <iface> root` blindly or
  `nft flush ruleset`. Ever.
- Removal is **per-handle / per-chain**: `tc class del dev <iface> parent 1: 
  classid 1:NN` and `nft delete rule inet smartqos sqm_mangle_pre handle <h>`.
- Before deleting a root qdisc, the helper verifies it was created by us
  (handle in our reserved range +, where supported, a `tc` comment marker).
- On **shutdown** and on **uninstall**, the helper removes the `inet smartqos`
  table and our per-interface qdiscs. System networking is otherwise untouched.
- On **startup**, the helper reconciles: app-owned objects with no matching DB
  rule are removed (healing stale state); objects owned by others are left
  alone.

## IPv6

- `inet smartqos` handles both IPv4 and IPv6 in one table. If the hotspot
  advertises IPv6 (NM "shared" is IPv4-only by default), we mark/shape both
  families. If IPv6 is not routed on the hotspot, the diagnostics page reports
  "IPv6 not routed; shaping/pause apply to IPv4 only" and the UI reflects it.
  We **do not** claim to control IPv6 traffic that isn't being routed.

## Measurement sources (cross-reference, no double counting)

- **Aggregate** throughput: `/proc/net/dev` counters on upstream and hotspot
  interfaces (unprivileged, 1 Hz). This is the displayed total up/down.
- **Per-device** throughput: `tc` class `bstats`/`qstats` per device class
  (privileged read via helper). These measure shaped traffic per class — they
  do **not** double-count the aggregate because the aggregate comes from
  interface counters and the per-device from class counters (different layers).
  We document that per-device class stats reflect *classified* traffic; a
  device's unclassified traffic (if any escapes classification) shows in the
  `default` class, not in its own, and we surface that as a warning.
- When per-device stats are unavailable (helper down, classification not
  applied), the UI shows **"Unavailable"** rather than inventing a value.

## What this design does NOT claim

- No DPI / app identification. "Gaming"/"Streaming" policies are scheduling
  preferences + configured ceilings, not app detection.
- No guaranteed latency/loss elimination — only HTB+fq_codel scheduling.
- No reclaiming already-consumed upstream bandwidth on download.
- No IPv6 control where IPv6 is not routed.
- No shaping of traffic that bypasses our classification path (we minimize this
  with marks + a default class, and disclose any residual).
