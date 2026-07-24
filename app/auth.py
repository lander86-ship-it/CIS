"""Minimal session authentication for the Web UI.

Users are configured via the ``APP_USERS`` environment variable:

    APP_USERS="alice:s3cret,bob@example.com:pa55word"

(entries separated by commas; username and password by the first colon —
so passwords may not contain ``,`` or ``:``). Real passwords therefore live in
the environment / deployment secrets, never in the repository.

Sessions are stateless: a cookie carries ``base64(user|expiry).hmac`` signed
with ``APP_SECRET`` (a random per-process key if unset). No third-party deps.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

_SECRET = (os.environ.get("APP_SECRET") or secrets.token_hex(32)).encode()
_TTL = int(os.environ.get("APP_SESSION_TTL", "86400"))  # seconds (default 1 day)
COOKIE_NAME = "cisbench_session"


def _users() -> dict[str, str]:
    raw = os.environ.get("APP_USERS", "Lander:1234")
    users: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        user, pwd = part.split(":", 1)
        if user.strip():
            users[user.strip()] = pwd
    return users


def verify_user(username: str, password: str) -> bool:
    expected = _users().get((username or "").strip())
    if expected is None:
        # Run a dummy compare to reduce user-enumeration timing differences.
        hmac.compare_digest("x" * 16, "y" * 16)
        return False
    return hmac.compare_digest(expected, password or "")


def create_session(username: str) -> str:
    exp = str(int(time.time()) + _TTL)
    payload = base64.urlsafe_b64encode(f"{username}|{exp}".encode()).decode()
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    good = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig):
        return None
    try:
        raw = base64.urlsafe_b64decode(payload.encode()).decode()
        username, exp = raw.rsplit("|", 1)
        if int(exp) < int(time.time()):
            return None
        return username
    except (ValueError, TypeError):
        return None
