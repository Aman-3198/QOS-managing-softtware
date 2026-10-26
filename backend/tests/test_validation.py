"""Input validation for QoS rates and priorities."""
from __future__ import annotations

import pytest

from app.core.constants import MAX_RATE_MBPS, PRIORITY_LEVELS
from app.core.exceptions import ValidationError
from app.core.rate import validate_priority, validate_rate_mbps


@pytest.mark.parametrize("bad", [0, -1, -0.001])
def test_rate_rejects_nonpositive(bad):
    with pytest.raises(ValidationError):
        validate_rate_mbps(bad)


def test_rate_rejects_nan_inf():
    with pytest.raises(ValidationError):
        validate_rate_mbps(float("nan"))
    with pytest.raises(ValidationError):
        validate_rate_mbps(float("inf"))


def test_rate_rejects_too_large():
    with pytest.raises(ValidationError):
        validate_rate_mbps(MAX_RATE_MBPS + 1)


def test_rate_accepts_positive_and_unlimited():
    assert validate_rate_mbps(5.0) == 5.0
    assert validate_rate_mbps(0.5) == 0.5
    assert validate_rate_mbps(MAX_RATE_MBPS) == MAX_RATE_MBPS


def test_rate_none_means_unlimited():
    # None is a valid sentinel meaning "no ceiling" — not an error.
    assert validate_rate_mbps(None) is None


def test_rate_rejects_non_number():
    with pytest.raises(ValidationError):
        validate_rate_mbps("fast")  # type: ignore[arg-type]


@pytest.mark.parametrize("p", PRIORITY_LEVELS)
def test_priority_accepts_valid(p):
    assert validate_priority(p) == p


def test_priority_defaults_to_normal():
    assert validate_priority(None) == "normal"


def test_priority_rejects_invalid():
    with pytest.raises(ValidationError):
        validate_priority("urgent")


def test_priority_rejects_non_string():
    with pytest.raises(ValidationError):
        validate_priority(99)  # type: ignore[arg-type]
