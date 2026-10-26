"""Pure rate-calculation and unit-conversion math.

This module is intentionally side-effect free and import-safe so it can be
unit-tested directly. It implements the speed calculation and validation rules
described in the spec (Section 8) and NETWORK_SHAPING.md.

Conventions:
- Speeds are decimal Mbps: ``1 Mbps = 1_000_000 bit/s`` (NOT 1024-based).
- tc expresses rates as ``kbit``/``mbit`` (decimal), so ``mbps -> kbit`` is a
  plain ``* 1000``.
- Counter resets (interface restart, rollover) yield a *negative* delta. We
  treat a negative delta as "counter reset" and return ``None`` for that
  interval rather than emitting a bogus negative or huge rate.
"""
from __future__ import annotations

from .constants import MAX_RATE_MBPS
from .exceptions import ValidationError


def compute_bps(
    prev_bytes: int | None,
    curr_bytes: int | None,
    elapsed_s: float,
) -> float | None:
    """Bits per second between two byte counters over ``elapsed_s``.

    Returns ``None`` (meaning "unavailable for this interval") when:
    - either counter is missing,
    - elapsed time is non-positive,
    - the delta is negative (counter reset / interface restart / rollover).

    Never returns a negative or fabricated value.
    """
    if prev_bytes is None or curr_bytes is None:
        return None
    if elapsed_s is None or elapsed_s <= 0:
        return None
    delta = curr_bytes - prev_bytes
    if delta < 0:
        # Counter reset: do not invent a value this interval.
        return None
    return (delta * 8) / elapsed_s


def bps_to_mbps(bps: float | None) -> float | None:
    if bps is None:
        return None
    return bps / 1_000_000.0


def mbps_to_bps(mbps: float) -> float:
    return mbps * 1_000_000.0


def mbps_to_kbit(mbps: float) -> int:
    """User-facing Mbps -> tc ``kbit`` (decimal). Never fractional for tc."""
    return int(round(mbps * 1000))


def kbit_to_mbps(kbit: int) -> float:
    return kbit / 1000.0


def validate_rate_mbps(mbps: float | None, field: str = "rate") -> float | None:
    """Validate a user-supplied rate.

    ``None`` means "unlimited" (no ceil) and is allowed.
    Anything else must be strictly positive and ``<= MAX_RATE_MBPS``.
    Zero, negative, NaN, non-finite, or absurdly large values are rejected.
    """
    if mbps is None:
        return None
    if not isinstance(mbps, (int, float)):
        raise ValidationError(f"{field} must be a number")
    # Guard against NaN/inf even though pydantic usually catches them.
    if mbps != mbps or mbps in (float("inf"), float("-inf")):  # NaN check
        raise ValidationError(f"{field} must be a finite number")
    if mbps <= 0:
        raise ValidationError(f"{field} must be > 0 (use no limit for unlimited)")
    if mbps > MAX_RATE_MBPS:
        raise ValidationError(f"{field} must be <= {MAX_RATE_MBPS:g} Mbps")
    return float(mbps)


def validate_priority(priority: str | None) -> str:
    from .constants import PRIORITY_LEVELS

    if priority is None:
        return "normal"
    if priority not in PRIORITY_LEVELS:
        raise ValidationError(
            f"priority must be one of {', '.join(PRIORITY_LEVELS)}"
        )
    return priority
