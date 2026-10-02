"""Client for the Laya decision service (laya/app.py), with the guard rails around it.

Contract (see docs in README, "AI decision layer"):
  * Laya is advisory. Callers run the Python rules FIRST and merge with `triage_rules.merge_urgency`, which can only
    raise a level, never lower it.
  * Every failure (service down, slow, bad answer, quality gate not passed) returns None, and the caller answers from
    rules alone. Nothing here ever raises into a request.
  * Answers are cached in Redis (key = model + hash of the input) and audited in `ai_decisions` (hash only, no text).

Env: LAYA_URL (e.g. http://laya:8080; empty = disabled), LAYA_API_KEY, LAYA_TIMEOUT_MS (default 800),
LAYA_ALLOW_UNGATED=1 to use a model whose evaluation gate has not passed (development).
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
        _client = httpx.Client(timeout=httpx.Timeout(float(os.getenv("LAYA_TIMEOUT_MS", "800")) / 1000.0, connect=0.5))
    return _client


def enabled() -> bool:
    return bool(_url())


def service_info() -> dict | None:
    """/info of the service, cached for a minute. None when unreachable."""
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
    """Enabled, reachable, breaker closed, and (unless explicitly allowed) the model passed its quality gate."""
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


def _call(kind: str, state: dict, questions: dict) -> tuple[dict | None, bool, float | None, str | None]:
    """(answers, cached, latency_ms, model). answers is None on any failure."""
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
        r = _http().post(f"{_url()}/decide", json={"state": state, "questions": questions}, headers=_headers())
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
    """{urgency, urgency_conf, specialist, specialist_conf, model, cached, ms} or None (use rules only)."""
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
    """{flag: probability} for the consultation-line questions, or None."""
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
    """Store what the app finally decided (after the rules merge) next to the model's answer. Best effort."""
    digest = hashlib.sha256(json.dumps([kind, S.triage_state(text) if kind == "triage" else text], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    _audit(kind + "-final", digest, None, {}, None, False, final)
