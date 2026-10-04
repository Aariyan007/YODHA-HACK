"""Circuit breakers for the outside AI services (Groq models, Gemini, speech).

When a service keeps failing (down, timing out, out of quota) we stop calling it for a short while and let the
fallback answer straight away, instead of every request waiting 25 s for the same failure. The state lives in the
shared store (Redis), so all API copies and workers see the same breaker.

States: closed (normal), open (skip calls for COOLDOWN s), half-open (one trial call; it closes on success,
re-opens on failure).
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager

from . import store

THRESHOLD = int(os.getenv("BREAKER_THRESHOLD", "3"))      # failures in a row before it opens
COOLDOWN = float(os.getenv("BREAKER_COOLDOWN", "30"))     # seconds to stay open
PROBE = 10.0                                              # how long one half-open trial may take

_local: dict[str, tuple[float, dict]] = {}                # tiny read cache so a hot path doesn't hit Redis every call
_lock = threading.Lock()


class BreakerOpen(Exception):
    """The service failed too often just now. Callers treat this like any other failure and use their fallback."""


def _key(name: str) -> str:
    return f"cb:{name}"


def _read(name: str) -> dict:
    now = time.time()
    with _lock:
        hit = _local.get(name)
        if hit and now - hit[0] < 1.0:
            return dict(hit[1])
    try:
        st = json.loads(store.get_value(_key(name)) or "{}")
    except ValueError:
        st = {}
    with _lock:
        _local[name] = (now, st)
    return dict(st)


def _write(name: str, st: dict) -> None:
    with _lock:
        _local[name] = (time.time(), st)
    store.set_value(_key(name), json.dumps(st), ttl=3600)


def allow(name: str) -> bool:
    st = _read(name)
    until = st.get("open_until", 0)
    if not until:
        return True
    now = time.time()
    if now < until:
        return False
    # half-open: let exactly one trial through and push the window so others keep skipping meanwhile
    st["open_until"] = now + PROBE
    st["half_open"] = True
    _write(name, st)
    return True


def success(name: str) -> None:
    st = _read(name)
    if st.get("fails") or st.get("open_until"):
        _write(name, {"fails": 0, "open_until": 0, "last_ok": time.time()})


def failure(name: str, kind: str = "") -> None:
    st = _read(name)
    fails = int(st.get("fails", 0)) + 1
    st.update({"fails": fails, "last_error": kind[:40], "last_fail": time.time()})
    if fails >= THRESHOLD or st.get("half_open"):
        st["open_until"] = time.time() + COOLDOWN
        st["opened"] = int(st.get("opened", 0)) + 1
        st.pop("half_open", None)
    _write(name, st)


_OUR_FAULT = {400, 404, 413, 415, 422}   # a bad request from one user must not shut the service off for everyone


def counts(e: BaseException) -> bool:
    """Does this error mean the SERVICE is in trouble (down, slow, out of quota, key refused)?"""
    if isinstance(e, (TypeError, ValueError, KeyError, BreakerOpen)):
        return False   # our own call shape or parsing, not the service
    code = getattr(e, "status_code", None) or getattr(e, "code", None) or getattr(e, "status", None)
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None
    if code in _OUR_FAULT:
        return False
    return True


@contextmanager
def guard(name: str):
    """Wrap one outside call. Raises BreakerOpen without calling when the breaker is open.
    Only errors that point at the service count (see counts), so one bad upload can't block everyone."""
    if not allow(name):
        raise BreakerOpen(name)
    try:
        yield
    except Exception as e:
        if counts(e):
            failure(name, type(e).__name__)
        raise
    else:
        success(name)


def states() -> list[dict]:
    """Every breaker we know about, for the admin page."""
    out = []
    now = time.time()
    for k in store.keys_with_prefix("cb:"):
        name = k[3:]
        st = _read(name)
        until = st.get("open_until", 0)
        out.append({"name": name, "state": "open" if until and now < until else "closed",
                    "fails": st.get("fails", 0), "opened": st.get("opened", 0), "lastError": st.get("last_error"),
                    "reopensIn": max(0, round(until - now)) if until and now < until else 0})
    return sorted(out, key=lambda r: r["name"])
