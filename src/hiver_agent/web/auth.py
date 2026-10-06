"""Email/password auth with DB-backed sessions (HttpOnly cookie).

* Passwords: scrypt (stdlib ``hashlib``) with a per-user random salt.
* Sessions: random 256-bit token in an HttpOnly cookie; only its SHA-256 hash
  is stored in Postgres, so a DB leak does not leak live sessions.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request, Response

from hiver_agent.web import db

COOKIE_NAME = "hiver_session"
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "14"))
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        salt = base64.urlsafe_b64decode(pad(salt_b64))
        expected = base64.urlsafe_b64decode(pad(dk_b64))
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def create_session(response: Response, request: Request, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (_token_hash(token), user_id, expires),
        )
        # opportunistic cleanup of expired sessions
        conn.execute("DELETE FROM sessions WHERE expires_at < now()")
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def destroy_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with db.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))
    response.delete_cookie(COOKIE_NAME, path="/")


def optional_user(request: Request) -> Optional[dict[str, Any]]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with db.connection() as conn:
        row = conn.execute(
            """SELECT u.id, u.email, u.name
                 FROM sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = %s AND s.expires_at > now()""",
            (_token_hash(token),),
        ).fetchone()
    return row


def current_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency: 401 unless a valid session cookie is present."""
    db.ensure_schema()
    user = optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return user
