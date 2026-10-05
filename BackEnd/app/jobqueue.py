"""Upload job queue: a Redis list is the queue (our SQS), worker containers take jobs from it (our Lambda),
and progress events go into a Redis stream so ANY API copy can stream them to the browser.

On only when QUEUE_MODE=redis and Redis is reachable (the Docker stack). Otherwise uploads run in a thread inside the
API process like before (local dev, Render).

Reliable hand-off: a worker moves a job from the queue into its own "processing" list in one atomic step. If the
worker dies, its heartbeat stops, and the janitor puts its jobs back on the queue (like an SQS visibility timeout).
A job that keeps killing workers gets a plain error after MAX_ATTEMPTS instead of looping forever.
"""
from __future__ import annotations

import json
import os
import time

from . import store

QUEUE = "q:pipeline"
PROCESSING = "q:processing:"     # + worker id
JOB = "job:"                     # + job id, the job's state as JSON
EVENTS = "jobev:"                # + job id, a Redis stream of progress events
HEARTBEAT = "hb:worker:"         # + worker id
KNOWN = "q:known-workers"        # set of worker ids that may have a processing list
TTL = 3600
MAX_ATTEMPTS = 2


def on() -> bool:
    return (os.getenv("QUEUE_MODE") or "").strip().lower() == "redis" and store._redis is not None


def _r():
    return store._redis


_blocking = None


def _rb():
    """A second connection for calls that wait on purpose (BLMOVE, XREAD BLOCK). The normal client gives up after 3 s,
    which is right for quick calls but would cut a 15 s wait short."""
    global _blocking
    if _blocking is None:
        import redis
        _blocking = redis.Redis.from_url(store.url, decode_responses=True, socket_connect_timeout=3, socket_timeout=30)
    return _blocking


_ablocking = None


def _arb():
    """The same blocking read as _rb, but async: waiting for an event costs a socket, not a thread. With threads, the
    default pool (about 32) capped how many uploads one API copy could stream at once."""
    global _ablocking
    if _ablocking is None:
        import redis.asyncio as aioredis
        _ablocking = aioredis.Redis.from_url(store.url, decode_responses=True, socket_connect_timeout=3, socket_timeout=30)
    return _ablocking


# ---- job state ----

def create(job_id: str, job: dict) -> None:
    _r().set(JOB + job_id, json.dumps(job), ex=TTL)


def get(job_id: str) -> dict | None:
    raw = _r().get(JOB + job_id)
    return json.loads(raw) if raw else None


def update(job_id: str, **fields) -> None:
    job = get(job_id) or {}
    job.update(fields)
    create(job_id, job)


# ---- events ----

def emit(job_id: str, event: dict) -> None:
    r = _r()
    r.xadd(EVENTS + job_id, {"d": json.dumps(event, ensure_ascii=False)}, maxlen=200)
    r.expire(EVENTS + job_id, TTL)
    if "done" in event:
        update(job_id, status="done", result=event.get("result"))
    elif "error" in event:
        update(job_id, status="error", error=event["error"])


def events(job_id: str, last: str = "0", block_ms: int = 15000) -> list[tuple[str, dict]]:
    """Events after `last`. Blocks up to block_ms for new ones (call it from a thread)."""
    out = _rb().xread({EVENTS + job_id: last}, count=50, block=block_ms) or []
    rows = []
    for _stream, items in out:
        for eid, fields in items:
            rows.append((eid, json.loads(fields["d"])))
    return rows


async def aevents(job_id: str, last: str = "0", block_ms: int = 15000) -> list[tuple[str, dict]]:
    """Async twin of events(): same result, no worker thread held while waiting."""
    out = await _arb().xread({EVENTS + job_id: last}, count=50, block=block_ms) or []
    return [(eid, json.loads(fields["d"])) for _stream, items in out for eid, fields in items]


async def aexists(job_id: str) -> bool:
    return bool(await _arb().exists(JOB + job_id))


class RedisBus:
    """Same interface as pipeline.Bus, but the events go to the shared stream."""
    def __init__(self, job_id: str):
        self.job_id = job_id

    def send(self, obj: dict) -> None:
        emit(self.job_id, obj)


# ---- queue ----

def enqueue(job_id: str) -> None:
    _r().lpush(QUEUE, job_id)


def claim(worker: str, timeout: float = 5) -> str | None:
    """Atomically move the oldest job into this worker's processing list. None if nothing came in time."""
    return _rb().blmove(QUEUE, PROCESSING + worker, timeout, "RIGHT", "LEFT")


def finish(worker: str, job_id: str) -> None:
    _r().lrem(PROCESSING + worker, 1, job_id)


def beat(worker: str, info: dict | None = None) -> None:
    r, now = _r(), time.time()
    p = r.pipeline()
    p.set(HEARTBEAT + worker, json.dumps({"t": now, **(info or {})}), ex=20)
    p.zadd("hbz:worker", {worker: now})              # index of live workers: counting needs no KEYS or SCAN
    p.sadd(KNOWN, worker)                            # every worker that may hold jobs, for the janitor
    p.zremrangebyscore("hbz:worker", 0, now - 60)
    p.execute()


def workers() -> list[dict]:
    """Live workers with their last heartbeat. Reads the index (hbz:worker) and one MGET, no keyspace scan."""
    r = _r()
    ids = r.zrangebyscore("hbz:worker", time.time() - 25, "+inf")
    raws = r.mget([HEARTBEAT + i for i in ids]) if ids else []
    out = []
    for wid, raw in zip(ids, raws):
        if raw is None:      # heartbeat expired a moment ago
            continue
        try:
            out.append({"id": wid, **json.loads(raw)})
        except ValueError:
            pass
    return out


def any_worker() -> bool:
    """Cheap check used on every upload: is at least one worker alive?"""
    return _r().zcount("hbz:worker", time.time() - 25, "+inf") > 0


def depth() -> int:
    return int(_r().llen(QUEUE))


def requeue_orphans() -> int:
    """Jobs held by workers whose heartbeat stopped go back on the queue. Returns how many moved."""
    r = _r()
    moved = 0
    for worker in r.smembers(KNOWN):
        if r.exists(HEARTBEAT + worker):
            continue
        key = PROCESSING + worker
        while (job_id := r.rpop(key)) is not None:
            job = get(job_id) or {}
            attempts = int(job.get("attempts", 0)) + 1
            if attempts > MAX_ATTEMPTS:
                emit(job_id, {"error": "This document couldn't be processed. Please try uploading it again."})
                continue
            update(job_id, attempts=attempts, status="pending")
            r.lpush(QUEUE, job_id)
            moved += 1
        if not r.llen(key):
            r.srem(KNOWN, worker)    # a dead worker with nothing left to put back is forgotten
    return moved
