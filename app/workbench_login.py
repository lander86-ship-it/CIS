"""Experimental: log in to CIS WorkBench with username/email + password.

cis-bench itself only supports cookie-based auth. WorkBench is a Laravel app
whose login form POSTs ``_token`` (CSRF), ``login`` (email or username) and
``password`` to ``/login``. This module performs that form login server-side
and returns the resulting session cookies as a Netscape ``cookies.txt`` string,
which is then handed to ``cis-bench auth login --cookies``.

Best-effort: if the account uses 2FA/SSO or the form changes, login may fail —
the caller falls back to the cookies.txt upload. Passwords are never logged.
"""

from __future__ import annotations

import re
import time

import requests

BASE = "https://workbench.cisecurity.org"
LOGIN_URL = f"{BASE}/login"
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_TOKEN_RE = re.compile(r'name="_token"\s+value="([^"]+)"')
_META_CSRF_RE = re.compile(r'name="csrf-token"\s+content="([^"]+)"')


def _to_netscape(jar) -> str:
    lines = ["# Netscape HTTP Cookie File"]
    far_future = int(time.time()) + 60 * 60 * 24 * 365
    for c in jar:
        domain = c.domain or ""
        if "cisecurity" not in domain:
            continue
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        secure = "TRUE" if c.secure else "FALSE"
        expiry = str(int(c.expires)) if c.expires else str(far_future)
        lines.append("\t".join([domain, flag, c.path or "/", secure,
                                expiry, c.name, c.value or ""]))
    return "\n".join(lines) + "\n"


def login(username: str, password: str, timeout: int = 30) -> tuple[str | None, str]:
    """Return (netscape_cookies, "") on success, or (None, error_message)."""
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"})

    try:
        r = s.get(LOGIN_URL, timeout=timeout)
    except requests.RequestException as exc:
        return None, f"Could not reach CIS WorkBench: {exc}"

    m = _TOKEN_RE.search(r.text) or _META_CSRF_RE.search(r.text)
    token = m.group(1) if m else ""
    if not token:
        return None, "Could not find the login CSRF token (form may have changed)."

    try:
        resp = s.post(
            LOGIN_URL,
            data={"_token": token, "login": username, "password": password,
                  "remember": "on"},
            headers={"Referer": LOGIN_URL, "Origin": BASE},
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        return None, f"Login request failed: {exc}"

    # Failure: the login form is still present (bad credentials / 2FA page).
    still_login = ('name="password"' in resp.text) and ('name="login"' in resp.text)
    has_session = any("cisecurity" in (c.domain or "") and "session" in c.name.lower()
                      for c in s.cookies)
    if still_login or not has_session:
        return None, _error_from(resp.text) or (
            "Login failed — check the username/password. If the account uses "
            "2FA or SSO, use the cookies.txt option instead.")

    return _to_netscape(s.cookies), ""


def _error_from(html: str) -> str:
    # Laravel typically renders validation errors in an alert block.
    for pat in (r'<div[^>]*alert[^>]*>(.*?)</div>',
                r'class="[^"]*error[^"]*"[^>]*>(.*?)<'):
        m = re.search(pat, html, re.S | re.I)
        if m:
            txt = re.sub(r"<[^>]+>", " ", m.group(1))
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                return txt[:200]
    return ""
