"""Live numbers for the whole system, across every API copy (our CloudWatch).

Each API process counts its requests in memory and, every 2 s, adds them to 5 second buckets in Redis (one HINCRBY
per field, so no Redis call on the request path). Each process also writes a heartbeat with its lane queues.
`live()` reads the last minute of buckets plus every heartbeat (API copies, workers, schedulers) for the admin page.
Numbers only: no paths, users or record data are stored.
"""
from __future__ import annotations

import json
import os
import threading
import time

from . import store

BUCKET = 5          # seconds per bucket
KEEP = 900          # keep 15 minutes of buckets
HIST = (50, 100, 200, 300, 500, 800, 1200, 2000, 5000)   # latency buckets in ms (last one catches the rest)
ME = os.getenv("HOSTNAME") or "local"

_lock = threading.Lock()
_acc: dict[str, float] = {}
_started = False


def record(path: str, status: int, ms: float) -> None:
    if not path.startswith("/api") or path.startswith(("/api/health", "/api/admin/live", "/api/jobs/")):
        return
    b = next((h for h in HIST if ms <= h), "inf")
    with _lock:
        _acc["req"] = _acc.get("req", 0) + 1
        _acc["ms"] = _acc.get("ms", 0) + ms
        _acc[f"h{b}"] = _acc.get(f"h{b}", 0) + 1
        if status >= 500:
            _acc["e5"] = _acc.get("e5", 0) + 1
        elif status == 429:
            _acc["e429"] = _acc.get("e429", 0) + 1


def _flush() -> None:
    from . import concurrency
    with _lock:
        acc = dict(_acc)
        _acc.clear()
    shed = concurrency.stats["shed"] + concurrency.stats["timeouts"]
    if shed:
        acc["shed"] = shed
        concurrency.stats["shed"] = concurrency.stats["timeouts"] = 0
    r = store._redis
    lanes = concurrency.INSTANCE.snapshot() if concurrency.INSTANCE else {}
    now = time.time()
    store.set_value(f"hb:api:{ME}", json.dumps({"t": now, "lanes": lanes, "req": acc.get("req", 0)}), ttl=10)
    if r is not None:
        try:   # index of live API copies for the autoscaler (a sorted set, so it never has to KEYS the whole database)
            p = r.pipeline()
            p.zadd("hbz:api", {ME: now})
            p.zremrangebyscore("hbz:api", 0, now - 60)
            p.execute()
        except Exception:
            pass
    if not acc or r is None:
        return
    key = f"m:{int(time.time()) // BUCKET * BUCKET}"
    try:
        p = r.pipeline()
        for k, v in acc.items():
            if k == "ms":
                p.hincrbyfloat(key, k, round(v, 1))
            else:
                p.hincrby(key, k, int(v))
        p.expire(key, KEEP)
        p.execute()
    except Exception:
        pass   # metrics must never hurt a request


def start() -> None:
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            time.sleep(2)
            try:
                _flush()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True, name="metrics").start()


def _beats(prefix: str) -> list[dict]:
    out = []
    for k in store.keys_with_prefix(prefix):
        raw = store.get_value(k)
        try:
            val = json.loads(raw) if raw and raw.startswith("{") else {"role": raw}
        except ValueError:
            val = {}
        out.append({"id": k[len(prefix):], **val})
    return sorted(out, key=lambda x: x["id"])


def _pct(hist: dict[str, int], q: float) -> int | None:
    total = sum(hist.values())
    if not total:
        return None
    need, seen = total * q, 0
    for h in (*HIST, "inf"):
        seen += hist.get(f"h{h}", 0)
        if seen >= need:
            return h if h != "inf" else 5000
    return None


def live() -> dict:
    from . import breaker, jobqueue, reminder_service, tokens
    r = store._redis
    now = int(time.time()) // BUCKET * BUCKET
    series, hist30, tot = [], {}, {"req": 0, "e5": 0, "e429": 0, "shed": 0}
    if r is not None:
        p = r.pipeline()
        starts = [now - BUCKET * i for i in range(12, -1, -1)]   # the last ~minute, oldest first
        for s in starts:
            p.hgetall(f"m:{s}")
        rows = p.execute()
        for s, row in zip(starts, rows):
            row = {k: float(v) for k, v in (row or {}).items()}
            req = row.get("req", 0)
            series.append({"t": s, "rps": round(req / BUCKET, 1), "errors": int(row.get("e5", 0)), "shed": int(row.get("shed", 0)),
                           "avgMs": round(row["ms"] / req) if req else None})
            for k in tot:
                tot[k] += int(row.get(k, 0))
            if s >= now - 30:
                for k, v in row.items():
                    if k.startswith("h"):
                        hist30[k] = hist30.get(k, 0) + int(v)
    recent = [x["rps"] for x in series[-3:-1]] or [0]   # last full buckets (the current one is still filling)
    return {
        "at": time.time(),
        "rpsNow": round(sum(recent) / len(recent), 1),
        "p50": _pct(hist30, 0.5), "p95": _pct(hist30, 0.95),
        "lastMinute": tot,
        "series": series,
        "api": _beats("hb:api:"),
        "workers": jobqueue.workers() if store._redis is not None else [],
        "queue": jobqueue.depth() if jobqueue.on() else 0,
        "schedulers": _beats("hb:scheduler:"),
        "schedulerLeader": store.lease_owner(reminder_service.LEASE_KEY),
        "breakers": breaker.states(),
        "tokensToday": tokens.today(),
    }
