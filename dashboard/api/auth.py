"""Password gate: POST /api/login sets a stateless signed cookie; require_session guards every other /api route.

The cookie is "<expiry unix seconds>.<hex HMAC-SHA256 of the expiry>", keyed from DASHBOARD_PASSWORD, so any
instance can verify it and rotating the secret logs everyone out. Without DASHBOARD_PASSWORD nothing passes.
"""
import hashlib
import hmac
import os
import time

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

COOKIE = "session"
SESSION_SECONDS = 7 * 24 * 3600

router = APIRouter()


def _password():
    return os.environ.get("DASHBOARD_PASSWORD", "").rstrip("\r\n")


def _key(password):
    return hmac.new(password.encode(), b"traffic-dashboard-session-key", hashlib.sha256).digest()


def _sign(expiry, password):
    return hmac.new(_key(password), str(expiry).encode(), hashlib.sha256).hexdigest()


def make_cookie(now=None):
    expiry = int((time.time() if now is None else now) + SESSION_SECONDS)
    return f"{expiry}.{_sign(expiry, _password())}"


def valid_cookie(value, now=None):
    password = _password()
    if not password or not value:
        return False
    expiry, _, sig = value.partition(".")
    if not expiry.isdigit() or not hmac.compare_digest(sig.encode(), _sign(expiry, password).encode()):
        return False
    return int(expiry) > (time.time() if now is None else now)


def require_session(session: str | None = Cookie(default=None)):
    if not valid_cookie(session):
        raise HTTPException(status_code=401, detail="unauthorized")


class LoginBody(BaseModel):
    password: str


@router.post("/api/login", status_code=204)
def login(body: LoginBody):
    expected = _password()
    # Compare digests so the length of the password does not leak through the comparison time.
    ok = bool(expected) and hmac.compare_digest(
        hashlib.sha256(body.password.encode()).digest(), hashlib.sha256(expected.encode()).digest())
    if not ok:
        raise HTTPException(status_code=401, detail="wrong password")
    response = Response(status_code=204)
    response.set_cookie(COOKIE, make_cookie(), max_age=SESSION_SECONDS,
                        httponly=True, secure=True, samesite="lax", path="/")
    return response
