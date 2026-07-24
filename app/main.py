"""FastAPI app: REST API + static Web UI wrapping the cis-bench CLI."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import cis, cis_parse, policy

STATIC_DIR = Path(__file__).parent / "static"
# Where an uploaded cookies.txt is stored before login.
DATA_DIR = Path(os.environ.get("HOME", "/data")) / ".cis-bench"

app = FastAPI(
    title="CIS Benchmark UI",
    description="Web interface for the mitre/cis-bench CLI.",
    version="1.0.0",
)


# --- API -------------------------------------------------------------------


@app.get("/api/health")
def health():
    res = cis.version()
    return {
        "cli_available": cis.cli_available(),
        "cli_version": res.stdout.strip() or res.stderr.strip(),
        "work_dir": str(cis.WORK_DIR),
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
    return res.as_dict()


@app.post("/api/auth/login-browser")
def auth_login_browser(browser: str = Form("chrome")):
    """Authenticate by pulling cookies from a local browser (native mode)."""
    return cis.auth_login_with_browser(browser).as_dict()


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
    author: str = Form("Corporate Cybersecurity"),
    version: str = Form("1.0"),
    src_format: str = Form("xccdf"),
):
    """Generate a SABIC-styled Word policy from a selected CIS benchmark.

    Exports the benchmark via cis-bench (XCCDF preferred, JSON fallback),
    parses it, and renders it into the SABIC template.
    """
    identifier = identifier.strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier is required")

    # 1) Pull the benchmark content from cis-bench.
    fmt = src_format if src_format in ("xccdf", "json") else "xccdf"
    res, data = cis.export_bytes(identifier, fmt)
    if data is None and fmt == "xccdf":
        fmt = "json"
        res, data = cis.export_bytes(identifier, "json")
    if data is None:
        payload = res.as_dict() if res else {"ok": False, "stderr": "export failed"}
        payload["detail"] = ("cis-bench could not export this benchmark. "
                             "Check authentication and the benchmark ID.")
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
    try:
        doc = policy.build_policy(bench, meta)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"ok": False, "stderr": f"Policy generation failed: {exc}"},
            status_code=500)

    safe = re.sub(r"[^A-Za-z0-9._-]+", "_",
                  meta.title or bench.title)[:50].strip("_")
    out_name = f"{safe or 'policy'}.docx"
    out_path = cis.WORK_DIR / out_name
    out_path.write_bytes(doc)

    return {
        "ok": True,
        "file": out_name,
        "download_url": f"/api/files/{out_name}",
        "source_format": fmt,
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
