"""Upload worker: python -m app.worker_main

Takes jobs from the shared Redis queue and runs the upload pipeline (Gemini read, safety checks, summary, save).
Run as many copies as you like: each job goes to exactly one worker. Every copy also runs WORKER_CONCURRENCY jobs at
once (a job spends most of its time waiting on Gemini and Groq, so threads multiply throughput without more
containers or more memory than the image bytes). Every worker also acts as the janitor and puts back the jobs of
workers that died (their heartbeat stopped).
"""
from __future__ import annotations

import os
import signal
import threading
import time

os.environ.setdefault("QUEUE_MODE", "redis")
os.environ["SCHEDULER"] = "off"

from . import jobqueue, store  # noqa: E402
from .models import new_id  # noqa: E402

ME = os.getenv("HOSTNAME") or new_id()
CONCURRENCY = max(1, int(os.getenv("WORKER_CONCURRENCY", "3")))
stop = threading.Event()
_lock = threading.Lock()
stats = {"done": 0, "failed": 0, "active": 0}


def _bump(**changes: int) -> None:
    with _lock:
        for k, v in changes.items():
            stats[k] += v


def _beat_forever() -> None:
    while not stop.wait(5):
        try:
            jobqueue.beat(ME, {"done": stats["done"], "failed": stats["failed"], "busy": stats["active"] > 0,
                               "active": stats["active"], "slots": CONCURRENCY})
        except Exception:
            pass


def _run_job(job_id: str) -> None:
    """One claimed job, start to finish. Never raises, and always takes the job off this worker's processing list
    unless the process is going down (then the janitor puts it back)."""
    from ai import pipeline
    try:
        job = jobqueue.get(job_id)
        if job is None:  # expired or reset
            return
        jobqueue.update(job_id, status="running", worker=ME)
        _bump(active=1)
        try:
            pipeline.process_job(job, jobqueue.RedisBus(job_id))
        finally:
            _bump(active=-1)
        _bump(**{"done" if job.get("status") == "done" else "failed": 1})
    except Exception as e:  # a Redis hiccup or a bug: say so to the browser instead of leaving it waiting
        _bump(failed=1)
        print(f"[worker] job {job_id} crashed: {type(e).__name__}: {e}")
        try:
            jobqueue.emit(job_id, {"error": "Something went wrong while reading the document. Please try again."})
        except Exception:
            pass
    finally:
        try:
            jobqueue.finish(ME, job_id)
        except Exception:
            pass


def _slot(n: int) -> None:
    """One of the CONCURRENCY loops: wait for a job, run it, repeat."""
    while not stop.is_set():
        try:
            job_id = jobqueue.claim(ME, timeout=3)
        except Exception as e:  # Redis restarting: wait and try again, don't die
            print(f"[worker] slot {n}: queue unavailable ({type(e).__name__}), retrying")
            stop.wait(2)
            continue
        if job_id is not None:
            _run_job(job_id)


def main() -> None:
    from ai import pipeline  # noqa: F401  (import now, so a broken install fails at start, not on the first job)
    if threading.current_thread() is threading.main_thread():   # tests run main() in a thread
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
    if not jobqueue.on():
        print("[worker] needs Redis and QUEUE_MODE=redis; nothing to do")
        return
    jobqueue.beat(ME)
    threading.Thread(target=_beat_forever, daemon=True).start()
    # jobs this worker held when it last died go straight back on the queue
    leftover = store._redis.lrange(jobqueue.PROCESSING + ME, 0, -1)
    for job_id in leftover:
        store._redis.lrem(jobqueue.PROCESSING + ME, 1, job_id)
        jobqueue.enqueue(job_id)
    print(f"[worker] {ME} ready with {CONCURRENCY} slot(s), {len(leftover)} job(s) requeued from before")
    slots = [threading.Thread(target=_slot, args=(i,), daemon=True, name=f"slot-{i}") for i in range(CONCURRENCY)]
    for t in slots:
        t.start()
    last_sweep = 0.0
    while not stop.wait(1):
        if time.time() - last_sweep > 15:
            try:
                moved = jobqueue.requeue_orphans()
                if moved:
                    print(f"[worker] janitor put back {moved} job(s) from a dead worker")
            except Exception as e:
                print(f"[worker] janitor skipped ({type(e).__name__})")
            last_sweep = time.time()
    # finish the jobs in hand (the container gets a grace period for this), then leave
    for t in slots:
        t.join(timeout=50)
    print(f"[worker] {ME} stopped")


if __name__ == "__main__":
    main()
