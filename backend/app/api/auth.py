"""Auth API: login, logout, me, set-password. Single user (password only)."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from ..core.exceptions import ValidationError

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "sqm_session"


class LoginBody(BaseModel):
    password: str


class SetPasswordBody(BaseModel):
    password: str


@router.get("/me")
def me(request: Request):
    auth = request.app.state.auth_service
    token = request.cookies.get(COOKIE)
    return {"authenticated": auth.verify_session(token), "has_password": auth.has_password()}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    auth = request.app.state.auth_service
    ip = request.client.host if request.client else "?"
    if auth.rate_limited(ip):
        from ..core.exceptions import SmartQoSError
        raise SmartQoSError("too many login attempts, try later")
    if not auth.has_password():
        raise ValidationError("no password configured (auth is disabled in dev)")
    if not auth.verify_password(body.password):
        from ..core.exceptions import SmartQoSError
        raise SmartQoSError("invalid credentials")
    token = auth.create_session()
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=8 * 3600)
    return {"ok": True, "authenticated": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.post("/set-password")
def set_password(body: SetPasswordBody, request: Request):
    auth = request.app.state.auth_service
    # If a password already exists, require an authenticated session.
    if auth.has_password():
        token = request.cookies.get(COOKIE)
        if not auth.verify_session(token):
            from ..core.exceptions import SmartQoSError
            raise SmartQoSError("authenticate first to change the password")
    auth.set_password(body.password)
    return {"ok": True, "has_password": True}
