"""Authentication (Phase 9).

Simple single-user auth: a salted PBKDF2 password hash stored in app_setting,
and HMAC-signed session tokens in a cookie. Auth is enforced only when a
password has been set — so dev stays open until the user configures one (the UI
shows an "auth disabled" banner). Login is rate-limited per IP.

No external dependencies (stdlib only).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

SESSION_TTL_S = 8 * 3600
LOGIN_MAX = 5
LOGIN_WINDOW_S = 60

_login_attempts: dict[str, list[float]] = {}


class AuthService:
    def _get(self, key: str) -> str | None:
        from ..database import session_scope
        from ..models import AppSetting
        try:
            with session_scope() as s:
                row = s.query(AppSetting).filter_by(key=key).first()
                return row.value if row else None
        except Exception:
            return None

    def _set(self, key: str, value: str) -> None:
        from ..database import session_scope
        from ..models import AppSetting
        from datetime import datetime, timezone
        with session_scope() as s:
            row = s.query(AppSetting).filter_by(key=key).first()
            if row is None:
                s.add(AppSetting(key=key, value=value, updated_at=datetime.now(timezone.utc)))
            else:
                row.value = value

    def has_password(self) -> bool:
        return bool(self._get("auth_password_hash"))

    def set_password(self, password: str) -> None:
        if len(password) < 8:
            from ..core.exceptions import ValidationError
            raise ValidationError("password must be at least 8 characters")
        salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
        self._set("auth_password_hash", f"pbkdf2$200000${salt.hex()}${dk.hex()}")

    def verify_password(self, password: str) -> bool:
        stored = self._get("auth_password_hash")
        if not stored:
            return False
        try:
            algo, iters, salt_hex, hash_hex = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
            return hmac.compare_digest(dk.hex(), hash_hex)
        except (ValueError, KeyError):
            return False

    def _secret(self) -> bytes:
        s = self._get("session_secret")
        if not s:
            s = secrets.token_hex(32)
            self._set("session_secret", s)
        return s.encode()

    def create_session(self) -> str:
        exp = int(time.time()) + SESSION_TTL_S
        payload = f"{exp}".encode()
        sig = hmac.new(self._secret(), payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload).decode() + "." + base64.urlsafe_b64encode(sig).decode()

    def verify_session(self, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        try:
            payload_b, sig_b = token.split(".", 1)
            payload = base64.urlsafe_b64decode(payload_b)
            sig = base64.urlsafe_b64decode(sig_b)
            exp = int(payload)
            if exp < time.time():
                return False
            expected = hmac.new(self._secret(), payload, hashlib.sha256).digest()
            return hmac.compare_digest(sig, expected)
        except Exception:
            return False

    def rate_limited(self, ip: str) -> bool:
        now = time.time()
        attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW_S]
        attempts.append(now)
        _login_attempts[ip] = attempts
        return len(attempts) > LOGIN_MAX
