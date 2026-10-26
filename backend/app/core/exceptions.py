"""Application exceptions mapped to consistent HTTP error responses."""
from __future__ import annotations


class SmartQoSError(Exception):
    """Base application error."""

    code = "smartqos_error"
    status_code = 500


class ValidationError(SmartQoSError):
    code = "invalid_input"
    status_code = 400


class NotFoundError(SmartQoSError):
    code = "not_found"
    status_code = 404


class ConflictError(SmartQoSError):
    code = "conflict"
    status_code = 409


class HelperUnavailableError(SmartQoSError):
    """The privileged helper is down or unreachable (Phase 5+)."""

    code = "helper_unavailable"
    status_code = 503


class OperationFailedError(SmartQoSError):
    """A privileged operation failed and was rolled back (Phase 5+)."""

    code = "operation_failed"
    status_code = 503
