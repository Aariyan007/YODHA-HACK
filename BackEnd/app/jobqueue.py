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
    _r().set(HEARTBEAT + worker, json.dumps({"t": time.time(), **(info or {})}), ex=20)


def workers() -> list[dict]:
    out = []
    for k in store.keys_with_prefix(HEARTBEAT):
        raw = store.get_value(k)
        try:
            out.append({"id": k[len(HEARTBEAT):], **json.loads(raw or "{}")})
        except ValueError:
            pass
    return out


def depth() -> int:
    return int(_r().llen(QUEUE))


def requeue_orphans() -> int:
    """Jobs held by workers whose heartbeat stopped go back on the queue. Returns how many moved."""
    r = _r()
    moved = 0
    for key in store.keys_with_prefix(PROCESSING):
        worker = key[len(PROCESSING):]
        if r.exists(HEARTBEAT + worker):
            continue
        while (job_id := r.rpop(key)) is not None:
            job = get(job_id) or {}
            attempts = int(job.get("attempts", 0)) + 1
            if attempts > MAX_ATTEMPTS:
                emit(job_id, {"error": "This document couldn't be processed. Please try uploading it again."})
                continue
            update(job_id, attempts=attempts, status="pending")
            r.lpush(QUEUE, job_id)
            moved += 1
    return moved
