"""Scale and resilience pieces: circuit breakers, request lanes, load shedding. No network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_scale.py -v
"""
import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "")

from app import breaker, concurrency, store  # noqa: E402

store._redis = None  # tests never touch a real Redis


class Boom(Exception):
    def __init__(self, code=None):
        super().__init__("boom")
        self.status_code = code


class BreakerTest(unittest.TestCase):
    def setUp(self):
        store._memory.clear()
        breaker._local.clear()

    def run_guard(self, name, exc=None):
        with breaker.guard(name):
            if exc:
                raise exc

    def test_opens_after_threshold_and_skips_calls(self):
        for _ in range(breaker.THRESHOLD):
            with self.assertRaises(Boom):
                self.run_guard("svc", Boom(503))
        with self.assertRaises(breaker.BreakerOpen):
            self.run_guard("svc")
        self.assertEqual(breaker.states()[0]["state"], "open")

    def test_a_bad_request_does_not_count(self):
        for _ in range(breaker.THRESHOLD + 2):
            with self.assertRaises(Boom):
                self.run_guard("svc", Boom(400))
        self.run_guard("svc")  # still closed

    def test_success_resets_the_count(self):
        for _ in range(breaker.THRESHOLD - 1):
            with self.assertRaises(Boom):
                self.run_guard("svc", Boom(500))
        self.run_guard("svc")
        with self.assertRaises(Boom):
            self.run_guard("svc", Boom(500))
        self.run_guard("svc")  # one failure after a success is not enough to open

    def test_half_open_trial_closes_on_success(self):
        for _ in range(breaker.THRESHOLD):
            with self.assertRaises(Boom):
                self.run_guard("svc", Boom(503))
        st = breaker._read("svc")
        st["open_until"] = 1  # cooldown is over
        breaker._write("svc", st)
        self.run_guard("svc")  # the one trial call works
        self.assertEqual(breaker._read("svc").get("open_until"), 0)

    def test_half_open_trial_failing_opens_again(self):
        for _ in range(breaker.THRESHOLD):
            with self.assertRaises(Boom):
                self.run_guard("svc", Boom(503))
        st = breaker._read("svc")
        st["open_until"] = 1
        breaker._write("svc", st)
        with self.assertRaises(Boom):
            self.run_guard("svc", Boom(503))
        with self.assertRaises(breaker.BreakerOpen):
            self.run_guard("svc")

    def test_open_breaker_counts_as_a_limit_for_the_visit_note(self):
        from ai import consultation
        self.assertTrue(consultation._is_limit(breaker.BreakerOpen("groq:x")))

    def test_gemini_breaker_has_a_plain_message(self):
        from ai import extractor
        self.assertIn("try again in a minute", extractor.explain_error(breaker.BreakerOpen("gemini")))


class LeaseTest(unittest.TestCase):
    def setUp(self):
        store._memory.clear()

    def test_only_one_holder(self):
        self.assertTrue(store.hold_lease("lease:x", "a", 60))
        self.assertFalse(store.hold_lease("lease:x", "b", 60))
        self.assertTrue(store.hold_lease("lease:x", "a", 60))  # the holder renews
        self.assertEqual(store.lease_owner("lease:x"), "a")

    def test_lease_passes_on_when_the_leader_stops_renewing(self):
        store.hold_lease("lease:x", "a", 60)
        store._memory["lease:x"] = ("a", 1.0)  # expired long ago: leader died
        self.assertTrue(store.hold_lease("lease:x", "b", 60))

    def test_standby_scheduler_does_not_send(self):
        from app import reminder_service as rs
        calls = []
        old = rs.run_tick
        rs.run_tick = lambda now, *a, **k: calls.append(now)
        try:
            store.hold_lease(rs.LEASE_KEY, "someone-else", 60)
            rs._job()
            self.assertEqual(calls, [])
            self.assertEqual(rs._role["role"], "standby")
            store._memory.pop(rs.LEASE_KEY)
            rs._job()
            self.assertEqual(len(calls), 1)
            self.assertEqual(rs._role["role"], "leader")
        finally:
            rs.run_tick = old

    def test_scheduler_off_means_ready_without_one(self):
        from app import reminder_service as rs
        os.environ["SCHEDULER"] = "off"
        try:
            self.assertFalse(rs.enabled())
            self.assertTrue(rs.status()["ok"])
        finally:
            os.environ.pop("SCHEDULER")


class LaneTest(unittest.TestCase):
    def test_ai_routes_use_the_slow_lane(self):
        L = concurrency.lane
        self.assertEqual(L("POST", "/api/agent/chat"), "ai")
        self.assertEqual(L("POST", "/api/documents"), "ai")
        self.assertEqual(L("POST", "/api/consultations/abc123/audio"), "ai")
        self.assertEqual(L("GET", "/api/patients/me/health-check"), "ai")
        self.assertEqual(L("GET", "/api/patients/me/timeline"), "fast")
        self.assertEqual(L("GET", "/api/agent/tasks/abc"), "fast")
        self.assertEqual(L("POST", "/api/auth/login"), "fast")


def _app(delay):
    async def app(scope, receive, send):
        await asyncio.sleep(delay)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    return app


async def _hit(mw, path, method="GET"):
    out = {}

    async def send(m):
        if m["type"] == "http.response.start":
            out["status"] = m["status"]

    async def receive():
        return {"type": "http.request", "body": b""}

    await mw({"type": "http", "path": path, "method": method, "headers": []}, receive, send)
    return out["status"]


class SheddingTest(unittest.TestCase):
    def test_too_many_waiting_get_a_fast_503(self):
        old = concurrency.MAX_WAITING
        concurrency.MAX_WAITING = 3
        try:
            mw = concurrency.InflightLimit(_app(0.2), fast=2, ai=1)

            async def go():
                return await asyncio.gather(*[_hit(mw, "/api/patients/me/timeline") for _ in range(10)])
            codes = asyncio.run(go())
        finally:
            concurrency.MAX_WAITING = old
        self.assertIn(503, codes)
        self.assertGreaterEqual(codes.count(200), 5)  # 2 running + 3 waiting get served

    def test_waiting_too_long_gets_a_503(self):
        old = concurrency.QUEUE_TIMEOUT
        concurrency.QUEUE_TIMEOUT = 0.1
        try:
            mw = concurrency.InflightLimit(_app(0.5), fast=1, ai=1)

            async def go():
                return await asyncio.gather(_hit(mw, "/api/x"), _hit(mw, "/api/x"))
            codes = sorted(asyncio.run(go()))
        finally:
            concurrency.QUEUE_TIMEOUT = old
        self.assertEqual(codes, [200, 503])

    def test_ai_lane_full_does_not_block_reads(self):
        mw = concurrency.InflightLimit(_app(0.3), fast=5, ai=1)

        async def go():
            slow = [asyncio.create_task(_hit(mw, "/api/agent/chat", "POST")) for _ in range(3)]
            await asyncio.sleep(0.05)
            t0 = asyncio.get_running_loop().time()
            code = await _hit(mw, "/api/patients/me/medicines")
            took = asyncio.get_running_loop().time() - t0
            await asyncio.gather(*slow)
            return code, took
        code, took = asyncio.run(go())
        self.assertEqual(code, 200)
        self.assertLess(took, 0.5)  # did not queue behind the 3 slow AI calls (0.9 s)

    def test_streams_and_health_are_never_limited(self):
        mw = concurrency.InflightLimit(_app(0.2), fast=1, ai=1)

        async def go():
            return await asyncio.gather(*[_hit(mw, "/api/jobs/abc/events") for _ in range(5)])
        self.assertEqual(asyncio.run(go()), [200] * 5)


class CountersTest(unittest.TestCase):
    def setUp(self):
        store._memory.clear()

    def test_incr_does_not_lose_counts_under_contention(self):
        import threading

        def hammer():
            for _ in range(300):
                store.incr("budget:x", ttl=60)
        ts = [threading.Thread(target=hammer) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(int(store.get_value("budget:x")), 2400)

    def test_incr_expiry_is_set_once_unless_refreshed(self):
        store.incr("k", ttl=100)
        first = store._memory["k"][1]
        store.incr("k", ttl=100)
        self.assertEqual(store._memory["k"][1], first)           # fixed window: later calls do not push it out
        import time
        time.sleep(0.01)
        store.incr("k", ttl=100, refresh=True)
        self.assertGreater(store._memory["k"][1], first)         # sliding window (login lock): pushed out

    def test_budget_counts_atomically_and_stops_at_the_limit(self):
        from app import budget
        budget.LIMITS["upload"] = 3
        got = [budget.try_spend("p1", "upload") for _ in range(5)]
        self.assertEqual(got, [True, True, True, False, False])
        self.assertTrue(budget.try_spend("p2", "upload"))        # another person has their own count

    def test_lease_can_be_released_only_by_its_owner(self):
        self.assertTrue(store.hold_lease("lock:t", "a", 30))
        store.release_lease("lock:t", "b")
        self.assertFalse(store.hold_lease("lock:t", "b", 30))
        store.release_lease("lock:t", "a")
        self.assertTrue(store.hold_lease("lock:t", "b", 30))


class LruTest(unittest.TestCase):
    def test_it_forgets_the_oldest_past_its_size(self):
        from app.lru import LRU
        c = LRU(max_items=3, ttl=60)
        for i in range(5):
            c.put(str(i), i)
        self.assertEqual(len(c), 3)
        self.assertIsNone(c.get("0"))
        self.assertEqual(c.get("4"), 4)

    def test_reading_keeps_an_entry_alive_and_none_is_cacheable(self):
        from app.lru import LRU
        c = LRU(max_items=2, ttl=60)
        c.put("a", None)
        c.put("b", 1)
        self.assertIsNone(c.get("a", "missing"))                 # a stored None is a hit, not a miss
        c.put("c", 2)                                            # drops "b" (the least recently used), not "a"
        self.assertEqual(c.get("b", "missing"), "missing")
        self.assertIsNone(c.get("a", "missing"))

    def test_entries_expire(self):
        from app.lru import LRU
        c = LRU(max_items=5, ttl=0.05)
        c.put("a", 1)
        import time
        time.sleep(0.1)
        self.assertEqual(c.get("a", "gone"), "gone")


if __name__ == "__main__":
    unittest.main()
