"""Optional: serves the built React app from this same process (single service hosting like Render).

Only on when a folder with index.html exists (STATIC_DIR, default /app/static). In the Docker stack nginx serves the
frontend, so nothing here is active. Same origin means no CORS, and the job event stream (SSE) reaches the API directly.
API paths never get the page back: an unknown /api/... is a plain 404.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "microphone=(self), geolocation=(self), camera=()",
}


def static_dir() -> Path | None:
    d = Path(os.getenv("STATIC_DIR") or "/app/static")
    return d if (d / "index.html").is_file() else None


class _Headers(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        for k, v in HEADERS.items():
            resp.headers.setdefault(k, v)
        return resp


def mount(app: FastAPI) -> bool:
    root = static_dir()
    if root is None:
        return False
    app.add_middleware(_Headers)
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(404, "Not found")
        target = (root / full_path).resolve()
        if full_path and root.resolve() in target.parents and target.is_file():  # a real file (favicon, manifest), never outside root
            return FileResponse(target)
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})  # client-side routes

    return True
