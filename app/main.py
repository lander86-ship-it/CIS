"""FastAPI app: REST API + static Web UI wrapping the cis-bench CLI."""

from __future__ import annotations

import base64
import os
import re
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse, JSONResponse, RedirectResponse, Response,
)
from fastapi.staticfiles import StaticFiles

from . import auth, catalog, cis, cis_parse, llm, policy, workbench_login

STATIC_DIR = Path(__file__).parent / "static"
# Where an uploaded cookies.txt is stored before login.
DATA_DIR = Path(os.environ.get("HOME", "/data")) / ".cis-bench"

# Paths reachable without a session (login page + its submit + favicon).
PUBLIC_PATHS = {"/login", "/api/session/login", "/favicon.ico"}

app = FastAPI(
    title="CIS Benchmark UI",
    description="Web interface for the mitre/cis-bench CLI.",
    version="1.0.0",
)


@app.on_event("startup")
def _bootstrap_cookies() -> None:
    """Optionally pre-authenticate from a base64 cookies.txt secret.

    Set CIS_COOKIES_B64 to the base64 of a Netscape cookies.txt to have the
    server log in to CIS WorkBench on startup — handy for a headless deploy
    without committing the cookies. Best-effort; failures are non-fatal.
    """
    blob = os.environ.get("CIS_COOKIES_B64")
    if not blob:
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        dest = DATA_DIR / "cookies.txt"
        dest.write_bytes(base64.b64decode(blob))
        cis.auth_login_with_cookies(dest)
        dest.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - never block startup on this
        pass


@app.on_event("startup")
def _bootstrap_catalog() -> None:
    """Start loading the benchmark catalog in the background at boot."""
    try:
        catalog.ensure_loading()
    except Exception:  # noqa: BLE001
        pass


@app.middleware("http")
async def _require_session(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or auth.read_session(
            request.cookies.get(auth.COOKIE_NAME)):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "authentication required"},
                            status_code=401)
    return RedirectResponse("/login", status_code=302)


# --- Authentication --------------------------------------------------------


@app.get("/login")
def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/api/session/login")
def session_login(response: Response, username: str = Form(...),
                  password: str = Form(...)):
    if not auth.verify_user(username, password):
        return JSONResponse({"ok": False, "error": "Invalid credentials"},
                            status_code=401)
    token = auth.create_session(username.strip())
    resp = JSONResponse({"ok": True, "user": username.strip()})
    resp.set_cookie(auth.COOKIE_NAME, token, httponly=True, samesite="lax",
                    max_age=86400, path="/")
    return resp


@app.post("/api/session/logout")
def session_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


@app.get("/api/session")
def session_info(request: Request):
    user = auth.read_session(request.cookies.get(auth.COOKIE_NAME))
    return {"authenticated": bool(user), "user": user}


# --- API -------------------------------------------------------------------


@app.get("/api/health")
def health():
    res = cis.version()
    return {
        "cli_available": cis.cli_available(),
        "cli_version": res.stdout.strip() or res.stderr.strip(),
        "work_dir": str(cis.WORK_DIR),
        "ai": llm.status(),
    }


@app.get("/api/auth/status")
def auth_status():
    return cis.auth_status().as_dict()


@app.post("/api/auth/login")
async def auth_login(cookies: UploadFile = File(...)):
    """Authenticate headless using an uploaded Netscape cookies.txt."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "cookies.txt"
    content = await cookies.read()
    dest.write_bytes(content)
    try:
        res = cis.auth_login_with_cookies(dest)
    finally:
        # Don't keep the raw cookies file around after login.
        dest.unlink(missing_ok=True)
    if res.ok:
        try:
            catalog.ensure_loading()
        except Exception:  # noqa: BLE001
            pass
    return res.as_dict()


@app.post("/api/auth/login-browser")
def auth_login_browser(browser: str = Form("chrome")):
    """Authenticate by pulling cookies from a local browser (native mode)."""
    return cis.auth_login_with_browser(browser).as_dict()


@app.post("/api/auth/login-credentials")
def auth_login_credentials(username: str = Form(...), password: str = Form(...)):
    """Experimental: sign in to CIS WorkBench with username/email + password.

    Performs the WorkBench form login server-side, then feeds the resulting
    cookies to cis-bench. Falls back message on failure; passwords not logged.
    """
    if not username.strip() or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    try:
        cookies_txt, err = workbench_login.login(username.strip(), password)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "stderr": f"Login error: {exc}"},
                            status_code=502)
    if not cookies_txt:
        return JSONResponse({"ok": False, "stderr": err or "Login failed"},
                            status_code=401)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "cookies.txt"
    dest.write_text(cookies_txt)
    try:
        res = cis.auth_login_with_cookies(dest)
    finally:
        dest.unlink(missing_ok=True)
    if res.ok:
        try:
            catalog.ensure_loading()
        except Exception:  # noqa: BLE001
            pass
    return res.as_dict()


@app.get("/api/catalog/status")
def catalog_status():
    """Lightweight catalog state (starts a background build if idle)."""
    return catalog.status_or_start()


def _trunc(res, n=4000):
    d = res.as_dict()
    for k in ("stdout", "stderr"):
        if d.get(k) and len(d[k]) > n:
            d[k] = d[k][:n] + f"\n…(+{len(d[k]) - n} chars)"
    return d


@app.get("/api/diagnostics")
def diagnostics(q: str = "ubuntu"):
    """Raw cis-bench output for troubleshooting search/catalog issues."""
    return {
        "cli_available": cis.cli_available(),
        "auth_status": _trunc(cis.auth_status()),
        "catalog_state": catalog.status(),
        "list_json": _trunc(cis.run(["list", "--output-format", "json"], timeout=60)),
        "search_json": _trunc(cis.run(["search", q, "--output-format", "json"], timeout=60)),
        "search_plain": _trunc(cis.run(["search", q], timeout=60)),
        "export_help": _trunc(cis.run(["export", "--help"], timeout=30)),
    }


@app.post("/api/catalog/refresh")
def catalog_refresh():
    return cis.catalog_refresh().as_dict()


@app.get("/api/search")
def search(q: str = "", platform_type: str | None = None):
    res = cis.search(q, platform_type)
    payload = res.as_dict()
    payload["json"] = res.json_payload()
    return payload


@app.get("/api/list")
def list_catalog():
    res = cis.list_catalog()
    payload = res.as_dict()
    payload["json"] = res.json_payload()
    return payload


@app.get("/api/catalog")
def catalog_endpoint():
    """Return the full benchmark catalog, pre-loading it if needed.

    Response: {status: ready|refreshing|error, benchmarks: [...], error}.
    The UI polls this until status == "ready".
    """
    items, res = catalog.get_benchmarks()
    if items:
        return {"status": "ready", "count": len(items), "benchmarks": items}
    catalog.ensure_loading()
    st = catalog.status()
    status = st["status"] if st["status"] in ("refreshing", "error") else "refreshing"
    return {"status": status, "error": st.get("error", ""), "benchmarks": []}


@app.post("/api/export")
def export(
    identifier: str = Form(...),
    fmt: str = Form(...),
    style: str | None = Form(None),
    filename: str | None = Form(None),
):
    if not identifier.strip():
        raise HTTPException(status_code=400, detail="identifier is required")
    res, out_path = cis.export(identifier, fmt, style, filename)
    payload = res.as_dict()
    if out_path is not None:
        payload["file"] = out_path.name
        payload["download_url"] = f"/api/files/{out_path.name}"
    return JSONResponse(payload)


@app.post("/api/policy")
def generate_policy(
    identifier: str = Form(...),
    title: str | None = Form(None),
    bench_title: str | None = Form(None),
    author: str = Form("Corporate Cybersecurity"),
    version: str = Form("1.0"),
    src_format: str = Form("xccdf"),
    use_ai: bool = Form(True),
):
    """Generate a SABIC-styled Word policy from a selected CIS benchmark.

    Exports the benchmark via cis-bench (XCCDF preferred, JSON fallback),
    parses it, and renders it into the SABIC template.
    """
    identifier = identifier.strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier is required")

    # 1) Pull the benchmark content from cis-bench as XCCDF (the only
    #    structured format `cis-bench export` supports that we can parse).
    fmt = "xccdf"
    res, data = cis.export_bytes(identifier, fmt)
    if data is None:
        payload = res.as_dict() if res else {"ok": False, "stderr": "export failed"}
        payload["detail"] = ("cis-bench could not export this benchmark as XCCDF. "
                             "Check authentication and the benchmark ID. Raw error above.")
        return JSONResponse(payload, status_code=502)

    # 2) Parse into the normalised model.
    try:
        bench = cis_parse.parse_benchmark(data, fmt)
    except Exception as exc:  # noqa: BLE001 - surface any parse issue
        return JSONResponse(
            {"ok": False, "stderr": f"Could not parse {fmt} export: {exc}"},
            status_code=422)

    # Prefer the ID the user actually selected.
    if identifier.isdigit():
        bench.id = identifier
    # The catalog/search result carries the authoritative benchmark name; use
    # it (the XCCDF title can be missing or generic on STIG-styled exports).
    if bench_title and bench_title.strip():
        bench.title = bench_title.strip()
        bench.platform = cis_parse._platform_from_title(bench.title) or bench.platform

    if bench.control_count == 0:
        return JSONResponse(
            {"ok": False,
             "stderr": "No controls were found in the benchmark export. "
                       "Try the other source format or verify the benchmark.",
             "parsed": {"title": bench.title, "sections": len(bench.sections)}},
            status_code=422)

    # 3) Render the policy into the SABIC template.
    meta = policy.PolicyMeta(
        title=(title or "").strip(),
        version=version.strip() or "1.0",
        author=author.strip() or "Corporate Cybersecurity",
        date=date.today().strftime("%d/%m/%Y"),
    )
    # Optionally draft the narrative sections with Claude (falls back to static
    # templates if unavailable or on any failure). Controls stay verbatim.
    narrative = None
    ai_used = False
    if use_ai and llm.available():
        narrative = llm.generate_narrative(bench, meta)
        ai_used = narrative is not None

    try:
        doc = policy.build_policy(bench, meta, narrative=narrative)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"ok": False, "stderr": f"Policy generation failed: {exc}"},
            status_code=500)

    # File name: <CIS benchmark name>_YYYYMMDD.docx
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", bench.title or "policy")[:60].strip("_")
    out_name = f"{base or 'policy'}_{date.today().strftime('%Y%m%d')}.docx"
    out_path = cis.WORK_DIR / out_name
    out_path.write_bytes(doc)

    return {
        "ok": True,
        "file": out_name,
        "download_url": f"/api/files/{out_name}",
        "source_format": fmt,
        "ai_used": ai_used,
        "benchmark": {
            "id": bench.id, "title": bench.title, "version": bench.version,
            "platform": bench.platform, "sections": len(bench.sections),
            "controls": bench.control_count,
        },
    }


@app.get("/api/files")
def files():
    return {"files": cis.list_files()}


@app.get("/api/files/{name}")
def download(name: str):
    target = cis.resolve_download(name)
    if target is None:
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(
        target,
        filename=target.name,
        media_type="application/octet-stream",
    )


# --- Static UI (mounted last so /api/* wins) -------------------------------

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
