"""Request ids and one JSON log line per request. Pure ASGI so it never buffers SSE streams.

Secrets travel in URL paths here (share tokens, job ids), so those parts are redacted before anything is logged.
Query strings are never logged.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import os
import time
import uuid

log = logging.getLogger("access")
_SECRET_PATHS = re.compile(r"(/api/shares/|/api/jobs/|/console/|/share/)[^/]+")
_QUIET = {"/api/health", "/health", "/api/health/ready"}  # Docker polls these every few seconds


SLOW_MS = float(os.getenv("SLOW_REQUEST_MS", "1000"))  # requests slower than this are logged as warnings with "slow":true


SERVED_BY = (os.getenv("HOSTNAME") or "local")[:12].encode()


def configure_logging() -> None:
    """Plain message lines to stdout (Docker collects stdout), our access lines are already JSON."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    root.setLevel(logging.INFO)
    # httpx logs full request URLs at INFO and the Telegram bot token is part of its URL. Keep the libraries quiet.
    for noisy in ("httpx", "httpcore", "urllib3", "google", "google_genai", "groq", "hpack", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True  # replaced by the JSON line below


class RequestLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        rid = (headers.get("x-request-id") or uuid.uuid4().hex[:16])[:64]
        scope.setdefault("state", {})["request_id"] = rid
        started = time.perf_counter()
        status = {"code": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
                message["headers"].append((b"x-served-by", SERVED_BY))  # which API copy answered (load balancing demo)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            from . import metrics
            metrics.record(path, status["code"], (time.perf_counter() - started) * 1000)
            if path not in _QUIET:
                client = scope.get("client")
                ms = round((time.perf_counter() - started) * 1000, 1)
                (log.warning if ms >= SLOW_MS else log.info)(json.dumps({
                    "t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rid": rid, "method": scope.get("method"),
                    "path": _SECRET_PATHS.sub(r"\1<redacted>", path), "status": status["code"],
                    "ms": ms, **({"slow": True} if ms >= SLOW_MS else {}), "ip": client[0] if client else None,
                }, separators=(",", ":")))
