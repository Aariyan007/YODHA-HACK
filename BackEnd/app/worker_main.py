"""Upload worker: python -m app.worker_main

Takes jobs from the shared Redis queue and runs the upload pipeline (Gemini read, safety checks, summary, save).
Run as many copies as you like: each job goes to exactly one worker. Every worker also acts as the janitor and
puts back the jobs of workers that died (their heartbeat stopped).
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
stop = threading.Event()
stats = {"done": 0, "failed": 0, "busy": False, "job": None}


def _beat_forever() -> None:
    while not stop.wait(5):
        try:
            jobqueue.beat(ME, {"done": stats["done"], "failed": stats["failed"], "busy": stats["busy"]})
        except Exception:
            pass


def main() -> None:
    from ai import pipeline
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
    print(f"[worker] {ME} ready, {len(leftover)} job(s) requeued from before")
    last_sweep = 0.0
    while not stop.is_set():
        if time.time() - last_sweep > 15:
            moved = jobqueue.requeue_orphans()
            if moved:
                print(f"[worker] janitor put back {moved} job(s) from a dead worker")
            last_sweep = time.time()
        job_id = jobqueue.claim(ME, timeout=3)
        if job_id is None:
            continue
        job = jobqueue.get(job_id)
        if job is None:  # expired or reset
            jobqueue.finish(ME, job_id)
            continue
        stats.update(busy=True, job=job_id)
        jobqueue.update(job_id, status="running", worker=ME)
        pipeline.process_job(job, jobqueue.RedisBus(job_id))
        stats["done" if job.get("status") == "done" else "failed"] += 1
        stats.update(busy=False, job=None)
        jobqueue.finish(ME, job_id)
    print(f"[worker] {ME} stopped")


if __name__ == "__main__":
    main()
