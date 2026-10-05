"""Queue, worker slots, janitor and async event stream against a REAL Redis (the unit suites never touch one).

    QUEUE_TEST_REDIS_URL=redis://localhost:6379/9 python scripts/test_queue_live.py

Use a throwaway database number: the test flushes it. The upload pipeline is replaced by a fake that sleeps, so no
Gemini or Groq call is made. Skips itself (exit 0) when QUEUE_TEST_REDIS_URL is not set.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import unittest
from pathlib import Path

URL = os.getenv("QUEUE_TEST_REDIS_URL", "").strip()
if not URL:
    print("QUEUE_TEST_REDIS_URL not set: skipping the live queue test")
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = URL
os.environ["QUEUE_MODE"] = "redis"
os.environ["WORKER_CONCURRENCY"] = "3"

from app import jobqueue, store, worker_main  # noqa: E402
from ai import pipeline  # noqa: E402

assert store._redis is not None, "could not connect to " + URL


def fake_pipeline(delay: float, boom: set[str] | None = None):
    live = {"now": 0, "max": 0}
    lock = threading.Lock()

    def process_job(job, bus):
        with lock:
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
        try:
            time.sleep(delay)
            if boom and job["sha"] in boom:
                raise RuntimeError("bug in the pipeline")
            job["status"] = "done"
            bus.send({"stage": "reading"})
            bus.send({"done": True, "result": {"ok": job["sha"]}})
        finally:
            with lock:
                live["now"] -= 1
    return process_job, live


class QueueLive(unittest.TestCase):
    def setUp(self):
        store._redis.flushdb()
        worker_main.stop.clear()
        worker_main.stats.update(done=0, failed=0, active=0)

    def _job(self, sha: str) -> str:
        job_id = "j" + sha
        jobqueue.create(job_id, {"status": "pending", "sha": sha, "patient_id": "p", "attempts": 0})
        jobqueue.enqueue(job_id)
        return job_id

    def _start_worker(self):
        t = threading.Thread(target=worker_main.main, daemon=True)
        t.start()
        return t

    def _stop_worker(self, t):
        worker_main.stop.set()
        t.join(timeout=10)

    def test_slots_run_jobs_at_the_same_time(self):
        fake, live = fake_pipeline(0.6)
        pipeline.process_job = fake
        ids = [self._job(f"a{i}") for i in range(6)]
        t0 = time.time()
        w = self._start_worker()
        deadline = time.time() + 10
        while time.time() < deadline and any((jobqueue.get(i) or {}).get("status") != "done" for i in ids):
            time.sleep(0.1)
        took = time.time() - t0
        self._stop_worker(w)
        self.assertTrue(all(jobqueue.get(i)["status"] == "done" for i in ids))
        self.assertEqual(live["max"], 3)                  # exactly WORKER_CONCURRENCY at once
        self.assertLess(took, 2.6)                        # 6 jobs x 0.6 s in 2 waves, not 6 in a row (3.6 s)
        self.assertEqual(store._redis.llen(jobqueue.PROCESSING + worker_main.ME), 0)   # all taken off the processing list

    def test_a_crashing_job_does_not_kill_the_worker(self):
        fake, _ = fake_pipeline(0.05, boom={"bad"})
        pipeline.process_job = fake
        # process_job in the real pipeline never raises, but a Redis hiccup or a bug could: the worker must survive
        bad, good = self._job("bad"), self._job("good")
        w = self._start_worker()
        deadline = time.time() + 8
        while time.time() < deadline and (jobqueue.get(good) or {}).get("status") != "done":
            time.sleep(0.1)
        alive = w.is_alive()
        self._stop_worker(w)
        self.assertTrue(alive)
        self.assertEqual(jobqueue.get(good)["status"], "done")
        self.assertEqual(jobqueue.get(bad)["status"], "error")     # the browser is told, not left waiting
        self.assertEqual(store._redis.llen(jobqueue.PROCESSING + worker_main.ME), 0)

    def test_janitor_puts_back_a_dead_workers_job_and_forgets_it(self):
        r = store._redis
        r.sadd(jobqueue.KNOWN, "ghost")                            # a worker that died holding a job
        jobqueue.create("jx", {"status": "running", "sha": "x", "attempts": 0})
        r.lpush(jobqueue.PROCESSING + "ghost", "jx")
        self.assertEqual(jobqueue.requeue_orphans(), 1)
        self.assertEqual(r.lrange(jobqueue.QUEUE, 0, -1), ["jx"])
        self.assertEqual(jobqueue.get("jx")["attempts"], 1)
        self.assertNotIn("ghost", r.smembers(jobqueue.KNOWN))
        # a live worker's list is left alone
        jobqueue.beat("alive")
        r.lpush(jobqueue.PROCESSING + "alive", "jy")
        self.assertEqual(jobqueue.requeue_orphans(), 0)

    def test_a_job_that_keeps_killing_workers_gets_an_error(self):
        r = store._redis
        r.sadd(jobqueue.KNOWN, "ghost")
        jobqueue.create("jz", {"status": "running", "sha": "z", "attempts": jobqueue.MAX_ATTEMPTS})
        r.lpush(jobqueue.PROCESSING + "ghost", "jz")
        self.assertEqual(jobqueue.requeue_orphans(), 0)
        self.assertEqual(jobqueue.get("jz")["status"], "error")

    def test_worker_index(self):
        self.assertFalse(jobqueue.any_worker())
        jobqueue.beat("w1", {"busy": False})
        self.assertTrue(jobqueue.any_worker())
        self.assertEqual([w["id"] for w in jobqueue.workers()], ["w1"])

    def test_async_events_stream_without_a_thread(self):
        async def go():
            jobqueue.create("je", {"status": "pending"})
            before = threading.active_count()
            waiters = [asyncio.create_task(jobqueue.aevents("je", "0", 3000)) for _ in range(60)]   # 60 open streams
            await asyncio.sleep(0.3)
            threads_while_waiting = threading.active_count()
            jobqueue.emit("je", {"stage": "reading"})
            jobqueue.emit("je", {"done": True, "result": {}})
            rows = await asyncio.gather(*waiters)
            return before, threads_while_waiting, rows
        before, during, rows = asyncio.run(go())
        self.assertLess(during - before, 5)                         # 60 streams did not take 60 threads
        self.assertTrue(all(len(r) >= 1 and r[0][1] == {"stage": "reading"} for r in rows))

    def test_incr_is_exact_under_contention(self):
        def hammer():
            for _ in range(200):
                store.incr("budget:test", ttl=60)
        ts = [threading.Thread(target=hammer) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(int(store.get_value("budget:test")), 1600)
        self.assertGreater(store._redis.ttl("budget:test"), 0)

    def test_startup_lock_is_exclusive_and_released(self):
        self.assertTrue(store.hold_lease("lock:startup-migrate", "a", 30))
        self.assertFalse(store.hold_lease("lock:startup-migrate", "b", 30))
        store.release_lease("lock:startup-migrate", "b")            # not the owner: no effect
        self.assertFalse(store.hold_lease("lock:startup-migrate", "b", 30))
        store.release_lease("lock:startup-migrate", "a")
        self.assertTrue(store.hold_lease("lock:startup-migrate", "b", 30))


if __name__ == "__main__":
    unittest.main()
