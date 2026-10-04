"""Two lanes, a cap on each, and a quick "busy" answer when the queue is too long.

Each request holds one DB connection from its auth check until it ends, and runs on a small worker thread pool.
With more requests than connections or threads, requests holding a connection wait for a thread while threads wait
for a connection, and everything stalls until the pool times out (we saw 30 s timeouts with 100 people at once).
So only a few more than the pool get in at once, and the rest wait cheaply (a waiting request holds nothing).

Lanes (a "bulkhead"): routes that call an AI service take seconds, normal reads take milliseconds. AI routes get
their own small lane, so 50 people chatting with the Agent can't slow down someone opening their medicines.

Load shedding: if too many are already waiting, or a request waited too long, it gets a fast 503 with Retry-After
instead of hanging. Live streams (/api/jobs/) and health checks are never counted or shed.
"""
from __future__ import annotations

import asyncio
import json
import os
import re

MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "30"))          # fast lane
MAX_AI_INFLIGHT = int(os.getenv("MAX_AI_INFLIGHT", "8"))     # slow lane (AI calls)
MAX_WAITING = int(os.getenv("MAX_WAITING", "200"))           # more than this waiting: answer "busy" at once
QUEUE_TIMEOUT = float(os.getenv("QUEUE_TIMEOUT", "15"))      # waited this long for a slot: answer "busy"
_SKIP = ("/api/jobs/", "/api/health")
_AI = re.compile(
    r"^/api/(documents$|import/fhir$|triage$|patients/me/health-check$|doctors/(ask|recommend)$"
    r"|(agent|doctor-agent)/(chat|confirm|voice|files)$|consultations/.+/(line|audio|finalize|approve)$|consultations/demo/)"
)

stats = {"shed": 0, "timeouts": 0}   # read by the metrics module


def lane(method: str, path: str) -> str:
    if method in ("POST", "PUT") and _AI.match(path):
        return "ai"
    if method == "GET" and path in ("/api/patients/me/health-check", "/api/doctors/recommend"):
        return "ai"
    return "fast"


class _Lane:
    def __init__(self, size: int):
        self.size = size
        self.sem: asyncio.Semaphore | None = None
        self.waiting = 0
        self.active = 0


class InflightLimit:
    def __init__(self, app, fast: int | None = None, ai: int | None = None):
        global INSTANCE
        self.app = app
        self.lanes = {"fast": _Lane(fast or MAX_INFLIGHT), "ai": _Lane(ai or MAX_AI_INFLIGHT)}
        INSTANCE = self

    async def _busy(self, send, why: str) -> None:
        stats["shed" if why == "full" else "timeouts"] += 1
        body = json.dumps({"detail": "The server is busy right now. Please try again in a moment."}).encode()
        await send({"type": "http.response.start", "status": 503,
                    "headers": [(b"content-type", b"application/json"), (b"retry-after", b"2"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api") or path.startswith(_SKIP):
            return await self.app(scope, receive, send)
        ln = self.lanes[lane(scope.get("method", "GET"), path)]
        if ln.sem is None:
            ln.sem = asyncio.Semaphore(ln.size)
        if ln.sem.locked() and ln.waiting >= MAX_WAITING:
            return await self._busy(send, "full")
        ln.waiting += 1
        try:
            await asyncio.wait_for(ln.sem.acquire(), timeout=QUEUE_TIMEOUT)
        except asyncio.TimeoutError:
            ln.waiting -= 1
            return await self._busy(send, "timeout")
        ln.waiting -= 1
        ln.active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            ln.active -= 1
            ln.sem.release()

    def snapshot(self) -> dict:
        return {k: {"active": v.active, "waiting": v.waiting, "size": v.size} for k, v in self.lanes.items()}


INSTANCE: InflightLimit | None = None   # set in main.py so the metrics module can read the queue sizes
