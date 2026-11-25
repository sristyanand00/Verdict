"""Accounts: password hashing, login tokens, and the login checks routes use.

    current_user   any logged-in, active account (401 / 403 otherwise)
    admin_user     the provider only (403 for analysts)

Tokens are random (32 bytes). The database keeps only a SHA-256 hash of each
token, so a copy of app.db does not let anyone log in. Passwords are hashed
with bcrypt. Neither a password nor a token is ever returned or logged, except
the token once, in the login or signup response.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import Depends, HTTPException, Request

#: How long a login lasts.
SESSION_HOURS = 24 * 7

MIN_PASSWORD = 8


def _prehash(password: str) -> bytes:
    # bcrypt reads at most 72 bytes. Hashing first keeps long passwords whole.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode("ascii"))
    except ValueError:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def current_user(request: Request) -> dict:
    """The logged-in user. 401 if the token is missing, unknown or expired."""
    token = bearer_token(request)
    if token is None:
        raise HTTPException(401, "Log in first.")
    user = request.app.state.verdict.store.session_user(token_hash(token))
    if user is None:
        raise HTTPException(401, "Your login has expired. Log in again.")
    if not user["active"]:
        raise HTTPException(403, "This account is turned off.")
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Only the provider can do this.")
    return user


def is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


class RateLimiter:
    """At most ``limit`` calls per ``window_s`` seconds for each key (an IP address).

    Kept in memory, so it is per server process. The deployment runs one
    process, which is enough to slow down password guessing.
    """

    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        if self.limit <= 0:
            return
        t = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and t - hits[0] > self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                raise HTTPException(429, "Too many tries. Wait a minute and try again.")
            hits.append(t)


def client_ip(request: Request) -> str:
    """The caller's IP address.

    Behind Cloudflare Tunnel every request comes from the tunnel, so with
    VERDICT_TRUST_PROXY=1 the address the proxy reports is used instead. Leave
    it off when the server is reached directly, or callers could fake it.
    """
    if os.environ.get("VERDICT_TRUST_PROXY", "").strip() in ("1", "true", "yes"):
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"
