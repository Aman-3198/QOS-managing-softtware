"""Structured logging with secret redaction.

A redacting filter scrubs values of fields whose name matches a secret pattern
(``password``, ``psk``, ``secret``, ``token``). The helper token itself is
added to the redaction set in Phase 9 once it exists. Logs go to console (dev)
and to ``logs/smartqos.log`` (rotated).
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
from pathlib import Path

# Field names whose logged values must never appear in plaintext.
_SECRET_NAME_RE = re.compile(r"(?i)(password|passwd|psk|secret|token|apikey|api_key)")

# Values to scrub outright (e.g. the helper token) — populated at runtime.
_LITERAL_SCRUB: set[str] = set()


def add_scrub_value(value: str | None) -> None:
    """Register a literal string (e.g. the helper token) to be scrubbed from logs."""
    if value and len(value) >= 8:
        _LITERAL_SCRUB.add(value)


class RedactingFilter(logging.Filter):
    """Redact secret-ish values in log records.

    Operates on ``record.msg`` and ``record.args`` for ``key=value`` style logs,
    and scrubs any registered literal secret strings anywhere they appear.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        msg = record.getMessage()
        # Scrub registered literals first (longest first to avoid partial leaks).
        for secret in sorted(_LITERAL_SCRUB, key=len, reverse=True):
            if secret and secret in msg:
                msg = msg.replace(secret, "[REDACTED]")
        # Scrub key=value pairs for secret-ish keys.
        msg = _SECRET_NAME_RE.sub(
            lambda m: f"{m.group(0)}=[REDACTED]",
            re.sub(
                r"(?i)\b(password|passwd|psk|secret|token|apikey|api_key)\s*=\s*\S+",
                lambda m: f"{m.group(1)}=[REDACTED]",
                msg,
            ),
        )
        # Replace the record's message with the redacted form and clear args so
        # reformatting cannot reintroduce secrets.
        record.msg = msg
        record.args = ()
        return True


def setup_logging(level: str = "INFO", log_dir: str | None = None) -> logging.Logger:
    """Configure root + app logging. Idempotent."""
    root = logging.getLogger()
    # Avoid duplicate handlers on re-init (tests / reloads).
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(RedactingFilter())
    root.addHandler(console)

    if log_dir:
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            file_h = logging.handlers.RotatingFileHandler(
                os.path.join(log_dir, "smartqos.log"),
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
            )
            file_h.setFormatter(fmt)
            file_h.addFilter(RedactingFilter())
            root.addHandler(file_h)
        except OSError:
            # Non-fatal: console logging still works if the log dir is unavailable.
            pass

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Quiet noisy libs.
    for noisy in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger("smartqos")
