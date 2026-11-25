"""/api/auth, /api/me and /api/admin: accounts, credits and the provider panel.

Every change to a balance is a row in the credit ledger (store/db.py), so a
balance can always be explained line by line.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request

from verdict.api.auth import (
    MIN_PASSWORD, SESSION_HOURS, admin_user, bearer_token, check_password, client_ip,
    current_user, hash_password, new_token, token_hash,
)
from verdict.api.deps import state
from verdict.api.schemas import ActiveRequest, CreditsRequest, LoginRequest, SignupRequest
from verdict.store.db import EmailTaken, NotEnoughCredits

router = APIRouter()

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: Same answer for an unknown email and a wrong password, so the login page
#: does not tell a stranger which emails have accounts.
WRONG_LOGIN = "Wrong email or password."


def _me(s, user: dict) -> dict:
    return {"user": user, "credits": s.store.credit_summary(user["id"]), "prices": s.prices()}


def _start_session(s, user: dict) -> dict:
    token = new_token()
    s.store.create_session(user["id"], token_hash(token), SESSION_HOURS)
    return {"token": token, "me": _me(s, user)}


def _auth_limit(request: Request) -> None:
    request.app.state.auth_limiter.check(client_ip(request))


# -- login and signup ------------------------------------------------------------

@router.post("/auth/signup")
def signup(body: SignupRequest, request: Request) -> dict:
    _auth_limit(request)
    s = state(request)
    email = body.email.strip()
    if not _EMAIL.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    if len(body.password) < MIN_PASSWORD:
        raise HTTPException(400, f"The password needs at least {MIN_PASSWORD} characters.")
    try:
        # Signup always makes an analyst. The provider account comes from config.
        user = s.store.create_user(
            body.name, email, hash_password(body.password), "analyst", s.signup_credits
        )
    except EmailTaken:
        raise HTTPException(409, "An account with this email already exists.") from None
    return _start_session(s, user)


@router.post("/auth/login")
def login(body: LoginRequest, request: Request) -> dict:
    _auth_limit(request)
    s = state(request)
    row = s.store.user_login_row(body.email)
    if row is None or not check_password(body.password, row["password_hash"]):
        raise HTTPException(401, WRONG_LOGIN)
    if not row["active"]:
        raise HTTPException(403, "This account is turned off. Ask the provider.")
    return _start_session(s, s.store.get_user(row["id"]))


@router.post("/auth/logout")
def logout(request: Request) -> dict:
    token = bearer_token(request)
    if token:
        state(request).store.delete_session(token_hash(token))
    return {"ok": True}


# -- the logged-in user ------------------------------------------------------------

@router.get("/me")
def me(request: Request, user: dict = Depends(current_user)) -> dict:
    return _me(state(request), user)


@router.get("/me/usage")
def my_usage(request: Request, user: dict = Depends(current_user)) -> list[dict]:
    return state(request).store.ledger(user["id"])


# -- the provider panel ------------------------------------------------------------

def _row_or_404(s, user_id: str) -> dict:
    rows = s.store.admin_user_rows(user_id)
    if not rows:
        raise HTTPException(404, f"Unknown account: {user_id}")
    return rows[0]


@router.get("/admin/users")
def admin_users(request: Request, _: dict = Depends(admin_user)) -> list[dict]:
    return state(request).store.admin_user_rows()


@router.get("/admin/users/{user_id}/usage")
def admin_usage(user_id: str, request: Request, _: dict = Depends(admin_user)) -> list[dict]:
    s = state(request)
    _row_or_404(s, user_id)
    return s.store.ledger(user_id)


@router.post("/admin/users/{user_id}/credits")
def admin_credits(
    user_id: str, body: CreditsRequest, request: Request, _: dict = Depends(admin_user)
) -> dict:
    s = state(request)
    _row_or_404(s, user_id)
    if body.amount == 0:
        raise HTTPException(400, "The amount must be a whole number other than 0.")
    kind = "grant" if body.amount > 0 else "remove"
    try:
        s.store.change_credits(user_id, kind, body.amount, note=(body.note or None))
    except NotEnoughCredits:
        raise HTTPException(
            400, f"This would take the balance below 0 (balance is {s.store.balance(user_id)})."
        ) from None
    return _row_or_404(s, user_id)


@router.post("/admin/users/{user_id}/active")
def admin_active(
    user_id: str, body: ActiveRequest, request: Request, admin: dict = Depends(admin_user)
) -> dict:
    s = state(request)
    _row_or_404(s, user_id)
    if user_id == admin["id"] and not body.active:
        raise HTTPException(400, "You cannot turn off your own account.")
    # Turning an account off also ends its logins.
    s.store.set_active(user_id, body.active)
    return _row_or_404(s, user_id)


def ensure_admin(s) -> None:
    """Create the provider account from config if it does not exist yet.

    There is no default password: without both settings, no admin is made.
    """
    if not (s.admin_email and s.admin_password):
        return
    if s.store.user_login_row(s.admin_email) is not None:
        return
    try:
        s.store.create_user("Provider", s.admin_email, hash_password(s.admin_password), "admin", 0)
    except EmailTaken:
        pass  # created by another process at the same moment
