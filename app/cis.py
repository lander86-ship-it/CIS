"""Thin, safe wrapper around the `cis-bench` command-line tool.

The web layer never builds a shell string: every call goes through
:func:`run` with an explicit argument list (``shell=False``), so user input
cannot inject extra commands. Higher-level helpers whitelist formats/styles
and sanitize filenames before they ever reach the CLI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Where exported files are written (and served for download).
WORK_DIR = Path(os.environ.get("CIS_WORK_DIR", "/work"))

# Path to the cis-bench executable (overridable for odd installs / venvs).
CIS_BIN = os.environ.get("CIS_BENCH_BIN", "cis-bench")

# Hard ceiling so a hung network call can't wedge a request forever.
DEFAULT_TIMEOUT = int(os.environ.get("CIS_BENCH_TIMEOUT", "600"))

# Whitelists — anything outside these is rejected before hitting the CLI.
VALID_FORMATS = {"yaml", "csv", "json", "markdown", "xccdf"}
VALID_STYLES = {"cis", "disa", "stig"}
VALID_BROWSERS = {"chrome", "firefox", "edge", "safari", "brave", "chromium"}

_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class Result:
    """Outcome of a single cis-bench invocation."""

    ok: bool
    returncode: int
    stdout: str
    stderr: str
    command: list[str]

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "command": " ".join(self.command),
        }

    def json_payload(self):
        """Best-effort parse of stdout as JSON; None if not JSON."""
        text = self.stdout.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return None


def cli_available() -> bool:
    """True if the cis-bench executable is on PATH."""
    return shutil.which(CIS_BIN) is not None


def run(args: list[str], timeout: int = DEFAULT_TIMEOUT) -> Result:
    """Invoke ``cis-bench <args>`` safely and capture its output.

    Runs with ``cwd=WORK_DIR`` so any relative output paths land in the
    mounted work directory. Never uses a shell.
    """
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    command = [CIS_BIN, *args]
    try:
        proc = subprocess.run(  # noqa: S603 - list form, shell=False
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORK_DIR),
            env=os.environ.copy(),
            check=False,
        )
    except FileNotFoundError:
        return Result(
            ok=False,
            returncode=127,
            stdout="",
            stderr=(
                f"'{CIS_BIN}' not found. Is cis-bench installed and on PATH?"
            ),
            command=command,
        )
    except subprocess.TimeoutExpired:
        return Result(
            ok=False,
            returncode=124,
            stdout="",
            stderr=f"Command timed out after {timeout}s.",
            command=command,
        )
    return Result(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        command=command,
    )


# --- High-level helpers used by the API ------------------------------------


def version() -> Result:
    return run(["--version"], timeout=30)


def auth_status() -> Result:
    return run(["auth", "status"], timeout=60)


def auth_login_with_cookies(cookies_path: Path) -> Result:
    return run(["auth", "login", "--cookies", str(cookies_path)], timeout=120)


def auth_login_with_browser(browser: str) -> Result:
    """Log in by extracting session cookies from a local browser.

    Only works when cis-bench runs natively on the user's machine (not inside
    a container), since it reads the browser's local cookie store.
    """
    b = (browser or "").lower().strip()
    if b not in VALID_BROWSERS:
        return Result(False, 2, "", f"Unsupported browser: {browser!r}", [])
    return run(["auth", "login", "--browser", b], timeout=180)


def catalog_refresh() -> Result:
    return run(["catalog", "refresh"])


def search(query: str, platform_type: str | None = None) -> Result:
    """Search the catalog. Tries JSON output, falls back to plain text."""
    base = ["search"]
    if query:
        base.append(query)
    if platform_type:
        base += ["--platform-type", platform_type]

    # Prefer machine-readable output when the CLI supports it.
    res = run([*base, "--output-format", "json"], timeout=120)
    if res.ok:
        return res
    # Older/other subcommands may not accept the flag; retry plain.
    return run(base, timeout=120)


def list_catalog(output_format: str = "json") -> Result:
    return run(["list", "--output-format", output_format], timeout=120)


def sanitize_filename(name: str, default: str) -> str:
    """Reduce an arbitrary name to a safe basename (no path traversal)."""
    name = Path(name or "").name  # strip any directory components
    name = _FILENAME_RE.sub("_", name).strip("._")
    return name or default


def export(
    identifier: str,
    fmt: str,
    style: str | None = None,
    filename: str | None = None,
) -> tuple[Result, Path | None]:
    """Export/get a benchmark into WORK_DIR.

    ``identifier`` may be a numeric benchmark ID (uses ``export``) or a free
    text query (uses ``get``). Returns the Result plus the output path if the
    file was produced.
    """
    fmt = fmt.lower().strip()
    if fmt not in VALID_FORMATS:
        return (
            Result(False, 2, "", f"Unsupported format: {fmt!r}", []),
            None,
        )

    ext = {"yaml": "yaml", "csv": "csv", "json": "json",
           "markdown": "md", "xccdf": "xml"}[fmt]
    safe_id = _FILENAME_RE.sub("_", identifier)[:40].strip("_") or "benchmark"
    out_name = sanitize_filename(filename, f"{safe_id}.{ext}")
    out_path = WORK_DIR / out_name

    is_id = identifier.strip().isdigit()
    args = ["export" if is_id else "get", identifier.strip(),
            "--format", fmt, "-o", str(out_path)]

    # --style only applies to XCCDF output.
    if fmt == "xccdf" and style:
        style = style.lower().strip()
        if style in VALID_STYLES:
            args += ["--style", style]

    res = run(args)
    return res, (out_path if out_path.exists() else None)


def list_files() -> list[dict]:
    """List downloadable files in WORK_DIR."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(WORK_DIR.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            stat = p.stat()
            files.append({"name": p.name, "size": stat.st_size})
    return files


def resolve_download(name: str) -> Path | None:
    """Resolve a filename to a real file inside WORK_DIR (no traversal)."""
    safe = Path(name).name
    target = (WORK_DIR / safe).resolve()
    work_root = WORK_DIR.resolve()
    if work_root in target.parents and target.is_file():
        return target
    return None
