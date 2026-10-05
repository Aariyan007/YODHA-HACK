import time

_T0 = time.time()
print("[boot] MediThread API starting: loading code", flush=True)   # if a host log lacks this line, the hang is before Python ran our code

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from . import reminder_service, store
from .observability import RequestLogMiddleware, configure_logging
from sqlalchemy import text

from .database import DB_KIND, Base, SessionLocal, add_missing_columns, add_missing_indexes, engine
from .routers import admin, agent, auth, doctor_agent, care, consultations, demo, doctor, doctors, documents, imports, patients, reminders, shares
from .models import new_id
from .seed import ensure_demo_reminder_settings, seed_if_empty


def _prepare_database() -> None:
    """Tables, new columns, indexes and the demo seed. Idempotent, but every API copy starts at the same moment in the
    Docker stack and two of them running ALTER TABLE or the seed at once can fail or insert twice. So one at a time,
    through a Redis lock: the others wait here (up to 90 s), then find everything already done."""
    owner = os.getenv("HOSTNAME") or new_id()
    key = "lock:startup-migrate"
    deadline = time.time() + 90
    waited = False
    _step("database: taking the startup lock")
    while not store.hold_lease(key, owner, 120):
        waited = True
        if time.time() > deadline:
            print("[db] startup lock still held after 90 s; going on (every step is safe to repeat)")
            break
        time.sleep(1)
    try:
        if os.getenv("RESET_DB") == "1" and not waited:   # a copy that had to wait is a peer of one that already did this
            print("[db] RESET_DB=1: dropping all tables before create_all")
            Base.metadata.drop_all(engine)
        _step("database: creating missing tables")
        Base.metadata.create_all(engine)
        _step("database: checking for new columns")
        added = add_missing_columns()
        _step("database: checking indexes")
        add_missing_indexes()
        if added:
            print(f"[db] Added missing columns: {', '.join(added)}")
        _step("database: demo data check")
        with SessionLocal() as db:
            if seed_if_empty(db):
                print("[seed] Loaded demo patient Ammini Varghese")
            ensure_demo_reminder_settings(db)
    finally:
        store.release_lease(key, owner)


# While startup is still running (slow or distant database) the port is already open: /api/health answers 200 (alive),
# /api/health/ready answers 503, and every other API call gets a quick 503 with Retry-After. Without this, a host that
# waits for the port (Render: 15 minutes) reports "no open ports detected", because uvicorn only listens after startup.
BOOT = {"booting": False, "step": "not started"}
STARTUP_WAIT = float(os.getenv("STARTUP_WAIT", "20"))   # seconds startup may hold the port back before it opens anyway


def _step(msg: str) -> None:
    BOOT["step"] = msg
    print(f"[boot] {msg} (+{time.time() - _T0:.1f}s)", flush=True)


async def _boot() -> None:
    await asyncio.to_thread(_prepare_database)
    try:
        from .agent import tasks as agent_tasks
        await asyncio.to_thread(agent_tasks.purge_old)
    except Exception as e:  # housekeeping must never stop the server
        print(f"[agent] task purge skipped: {type(e).__name__}")
    _step("starting the reminder scheduler")
    reminder_service.start()
    from . import metrics
    metrics.start()
    BOOT["booting"] = False
    _step("ready")


@asynccontextmanager
async def lifespan(app: FastAPI):
    BOOT["booting"] = True
    task = asyncio.create_task(_boot())
    await asyncio.wait({task}, timeout=STARTUP_WAIT)
    if task.done():
        task.result()   # a failure inside the window stops startup, as before
    else:
        print(f"[boot] still at '{BOOT['step']}' after {STARTUP_WAIT:.0f}s: opening the port now, the API answers 503 until it is done", flush=True)

        def _late(t: asyncio.Task) -> None:
            if not t.cancelled() and t.exception() is not None:
                print(f"[boot] startup FAILED at '{BOOT['step']}': {type(t.exception()).__name__}: {t.exception()}", flush=True)
                os._exit(1)   # fail loudly so the host restarts / marks the deploy failed, instead of serving 503s forever
        task.add_done_callback(_late)
    try:
        yield
    finally:
        if not task.done():
            task.cancel()
        reminder_service.stop()


class BootGate:
    """Quick 503 for API calls while startup is still running (health checks and static files go through)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if BOOT["booting"] and scope["type"] == "http" and path.startswith("/api") and not path.startswith("/api/health"):
            body = b'{"detail":"The server is still starting. Please try again in a moment."}'
            await send({"type": "http.response.start", "status": 503,
                        "headers": [(b"content-type", b"application/json"), (b"retry-after", b"3"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


configure_logging()
app = FastAPI(title="MediThread API", lifespan=lifespan)

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def cors_origins() -> list[str]:
    """Allowed browser origins: CORS_ORIGINS (comma separated) or the local dev servers.
    
    A bare "*" is never allowed unless DEMO_MODE=true, because the API sends credentials.
    """
    raw = [o.strip().rstrip("/") for o in (os.getenv("CORS_ORIGINS") or "").split(",") if o.strip()]
    if not raw:
        return DEV_ORIGINS
    if "*" in raw and not reminder_service.demo_mode():
        print("[cors] CORS_ORIGINS contains '*', which is only honoured with DEMO_MODE=true. Ignoring it.")
        raw = [o for o in raw if o != "*"]
    return raw or DEV_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .concurrency import InflightLimit
app.add_middleware(InflightLimit)  # keeps in-flight requests below the connection pool
app.add_middleware(BootGate)
app.add_middleware(RequestLogMiddleware)  # added last = outermost: logs every request, sets X-Request-Id

app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(shares.router)
app.include_router(documents.router)
app.include_router(consultations.router)
app.include_router(reminders.router)
app.include_router(imports.router)
app.include_router(demo.router)
app.include_router(care.router)
app.include_router(doctor.router)
app.include_router(doctors.router)
app.include_router(agent.router)
app.include_router(admin.router)
app.include_router(doctor_agent.router)


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "db": DB_KIND, "store": store.KIND}


@app.get("/api/health/ready")
def ready(response: Response):
    """Readiness for Docker/nginx: database, store (Redis or memory), scheduler. Never returns secrets."""
    if BOOT["booting"]:
        response.status_code = 503
        return {"ready": False, "boot": {"ok": False, "step": BOOT["step"]}}
    checks: dict[str, dict] = {}
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        checks["database"] = {"ok": True, "kind": DB_KIND}
    except Exception as e:
        checks["database"] = {"ok": False, "detail": type(e).__name__}
    checks["store"] = store.status()
    checks["scheduler"] = reminder_service.status()
    from ai import ddi
    checks["ddi"] = {"ok": True, "dataset": "DDInter" if ddi.available() else "not built (curated rules only)"}
    checks["laya"] = {"ok": True, "enabled": bool((os.getenv("LAYA_URL") or "").strip())}
    ok = all(v["ok"] for v in checks.values())
    if not ok:
        response.status_code = 503
    return {"ready": ok, **checks}


# Single service hosting: serve the built frontend from here when there is a build (does nothing in the Docker stack).
from . import static_site  # noqa: E402

static_site.mount(app)
