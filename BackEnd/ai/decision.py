"""Client for the Laya service (laya/app.py) plus the safety rails around it.

How it's used:
* Laya only advises. Callers run the Python rules first and merge with triage_rules.merge_urgency,
  which can raise urgency but never lower it.
* Any failure (down, slow, bad answer, model not passing its quality gate) returns None and the
  rules answer alone. Nothing here raises into a request.
* Answers are cached in Redis and logged in ai_decisions (hash only, no text).

Env: LAYA_URL (empty = off), LAYA_API_KEY, LAYA_TIMEOUT_MS (triage, default 4000, CPU takes 0.1-0.5 s natively
but 1.5-3 s in Docker on a Mac), LAYA_LINE_TIMEOUT_MS (consultation lines, default 1200),
LAYA_ALLOW_UNGATED=1 to use a model that hasn't passed the gate (dev only).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time

import httpx

from app import store
from . import laya_schema as S

log = logging.getLogger("decision")
CACHE_TTL = 24 * 3600
BREAKER_FAILS = 3
BREAKER_OPEN_S = 30.0
INFO_TTL_S = 60.0

_lock = threading.Lock()
_fails = 0
_open_until = 0.0
_info: dict = {"at": 0.0, "data": None}
_client: httpx.Client | None = None


def _url() -> str:
    return (os.getenv("LAYA_URL") or "").strip().rstrip("/")


def _headers() -> dict:
    key = (os.getenv("LAYA_API_KEY") or "").strip()
    return {"x-api-key": key} if key else {}


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=httpx.Timeout(10.0, connect=0.5))  # per-call budgets are set in _call
    return _client


def enabled() -> bool:
    return bool(_url())


def service_info() -> dict | None:
    """The service's /info, cached for a minute. None if we can't reach it."""
    now = time.time()
    if _info["data"] is not None and now - _info["at"] < INFO_TTL_S:
        return _info["data"]
    try:
        r = _http().get(f"{_url()}/info", headers=_headers())
        r.raise_for_status()
        _info.update(at=now, data=r.json())
    except Exception as e:
        log.warning("laya /info failed: %s", type(e).__name__)
        _info.update(at=now, data=None)
    return _info["data"]


def usable() -> bool:
    """On, reachable, breaker closed, and (unless allowed) the model passed its quality gate."""
    if not enabled() or time.time() < _open_until:
        return False
    info = service_info()
    if not info or not info.get("loaded"):
        return False
    return bool(info.get("gate", {}).get("ok")) or os.getenv("LAYA_ALLOW_UNGATED") == "1"


def _record_failure() -> None:
    global _fails, _open_until
    with _lock:
        _fails += 1
        if _fails >= BREAKER_FAILS:
            _open_until = time.time() + BREAKER_OPEN_S
            _fails = 0
            log.warning("laya circuit open for %ss", BREAKER_OPEN_S)


def _record_success() -> None:
    global _fails
    _fails = 0


def _budget(kind: str) -> httpx.Timeout:
    ms = float(os.getenv("LAYA_LINE_TIMEOUT_MS", "1200")) if kind == "line" else float(os.getenv("LAYA_TIMEOUT_MS", "4000"))
    return httpx.Timeout(ms / 1000.0, connect=0.5)


def _call(kind: str, state: dict, questions: dict) -> tuple[dict | None, bool, float | None, str | None]:
    """(answers, cached, latency_ms, model). answers is None if anything failed."""
    model_tag = (service_info() or {}).get("model") or "?"
    digest = hashlib.sha256(json.dumps([kind, state], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    ckey = f"laya:{model_tag}:{digest}"
    hit = store.get_value(ckey)
    if hit:
        try:
            return json.loads(hit), True, 0.0, model_tag
        except ValueError:
            pass
    t = time.perf_counter()
    try:
        r = _http().post(f"{_url()}/decide", json={"state": state, "questions": questions}, headers=_headers(), timeout=_budget(kind))
        r.raise_for_status()
        body = r.json()
        _record_success()
    except Exception as e:
        log.warning("laya call failed: %s", type(e).__name__)
        _record_failure()
        return None, False, None, None
    ms = (time.perf_counter() - t) * 1000
    store.set_value(ckey, json.dumps(body["answers"]), ttl=CACHE_TTL)
    _audit(kind, digest, body.get("model"), body["answers"], ms, False)
    return body["answers"], False, ms, body.get("model")


def _audit(kind, digest, model, result, ms, cached, final: dict | None = None) -> None:
    try:
        from app.database import SessionLocal
        from app.models import AiDecision

        with SessionLocal() as db:
            db.add(AiDecision(kind=kind, input_hash=digest, model=model, result=result, final=final or {}, latency_ms=ms, cached=cached))
            db.commit()
    except Exception as e:  # auditing must never break a request
        log.warning("ai_decisions write failed: %s", type(e).__name__)


def _top(answer: dict) -> tuple[str, float]:
    probs = answer.get("probabilities") or {}
    label = answer.get("choice")
    return label, float(probs.get(label, answer.get("confidence", 0.0)) or 0.0)


def triage(text: str) -> dict | None:
    """{urgency, urgency_conf, specialist, specialist_conf, model, cached, ms} or None (rules only)."""
    if not text.strip() or not usable():
        return None
    answers, cached, ms, model = _call("triage", S.triage_state(text), S.triage_questions())
    if not answers:
        return None
    try:
        urgency, u = _top(answers["urgency"])
        spec, s = _top(answers["specialist"])
    except (KeyError, TypeError):
        return None
    if urgency not in S.URGENCY or spec not in S.SPECIALISTS:
        return None
    return {"urgency": urgency, "urgency_conf": round(u, 3), "specialist": spec, "specialist_conf": round(s, 3),
            "model": model, "cached": cached, "ms": ms}


def line_flags(speaker: str, text: str) -> dict | None:
    """{flag: probability} for the consultation line questions, or None."""
    if len(text.strip()) < 6 or not usable():
        return None
    answers, _, _, _ = _call("line", S.line_state(speaker, text), S.line_questions())
    if not answers:
        return None
    out = {}
    for k in S.LINE_FLAGS:
        a = answers.get(k) or {}
        p = a.get("noul", a.get("probability"))
        if p is not None:
            out[k] = float(p)
    return out or None


def record_final(kind: str, text: str, final: dict) -> None:
    """Save what the app finally decided (after the rules merge) next to the model's answer. Best effort."""
    digest = hashlib.sha256(json.dumps([kind, S.triage_state(text) if kind == "triage" else text], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    _audit(kind + "-final", digest, None, {}, None, False, final)
