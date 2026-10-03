"""Caps how many API requests are in flight at once.

Each request holds one DB connection from its auth check until it ends, and runs on a small worker thread pool.
With more requests than connections or threads, requests holding a connection wait for a thread while threads wait
for a connection, and everything stalls until the pool times out (we saw 30 s timeouts with 100 people at once).
Letting only a few more than the pool in, and queueing the rest cheaply (a waiting request holds nothing), keeps
every request fast. Live streams (/api/jobs/) and health checks aren't counted.
"""
from __future__ import annotations

import asyncio
import os

MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "30"))
_SKIP = ("/api/jobs/", "/api/health")


class InflightLimit:
    def __init__(self, app):
        self.app = app
        self._sem: asyncio.Semaphore | None = None

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api") or path.startswith(_SKIP):
            return await self.app(scope, receive, send)
        if self._sem is None:
            self._sem = asyncio.Semaphore(MAX_INFLIGHT)
        async with self._sem:
            await self.app(scope, receive, send)
