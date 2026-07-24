"""Benchmark catalog: list + background pre-load.

On startup we kick off a background refresh (if the local catalog is empty) so
that by the time a user logs in the catalog is already loading — and, once the
volume-backed catalog.db is populated, instantly available on later boots.
"""

from __future__ import annotations

import json
import threading

from . import cis

_state = {"status": "idle", "error": "", "count": 0}
_lock = threading.Lock()
_LIST_KEYS = ("benchmarks", "results", "items", "data", "catalog", "records")


def status() -> dict:
    with _lock:
        return dict(_state)


def _normalize(data) -> list:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            v = data.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        # fall back to the first list-of-dicts value
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def get_benchmarks() -> tuple[list | None, "cis.Result"]:
    """Return the catalog as a list of dicts (or None if unavailable)."""
    res = cis.run(["list", "--output-format", "json"], timeout=120)
    if not res.ok:
        return None, res
    try:
        return _normalize(json.loads(res.stdout)), res
    except (ValueError, TypeError):
        return None, res


def _refresh_worker() -> None:
    res = cis.catalog_refresh()
    items, _ = get_benchmarks()
    with _lock:
        if items:
            _state.update(status="ready", error="", count=len(items))
        elif res.ok:
            _state.update(status="ready", error="", count=0)
        else:
            _state.update(status="error",
                          error=(res.stderr or res.stdout or "refresh failed")[:300])


def ensure_loading() -> None:
    """If the catalog is empty, start a background refresh (idempotent)."""
    items, _ = get_benchmarks()
    if items:
        with _lock:
            _state.update(status="ready", count=len(items))
        return
    with _lock:
        if _state["status"] == "refreshing":
            return
        _state.update(status="refreshing", error="")
    threading.Thread(target=_refresh_worker, daemon=True).start()
