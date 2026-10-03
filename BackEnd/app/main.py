import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from . import reminder_service, store
from .observability import RequestLogMiddleware, configure_logging
from sqlalchemy import text

from .database import DB_KIND, Base, SessionLocal, add_missing_columns, engine
from .routers import admin, agent, auth, doctor_agent, care, consultations, demo, doctor, doctors, documents, imports, patients, reminders, shares
from .seed import ensure_demo_reminder_settings, seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("RESET_DB") == "1":
        print("[db] RESET_DB=1: dropping all tables before create_all")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    added = add_missing_columns()
    if added:
        print(f"[db] Added missing columns: {', '.join(added)}")
    with SessionLocal() as db:
        if seed_if_empty(db):
            print("[seed] Loaded demo patient Ammini Varghese")
        ensure_demo_reminder_settings(db)
    try:
        from .agent import tasks as agent_tasks
        agent_tasks.purge_old()
    except Exception as e:  # housekeeping must never stop the server
        print(f"[agent] task purge skipped: {type(e).__name__}")
    reminder_service.start()
    try:
        yield
    finally:
        reminder_service.stop()


configure_logging()
app = FastAPI(title="MediThread API", lifespan=lifespan)

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def cors_origins() -> list[str]:
    """Allowed browser origins: CORS_ORIGINS (comma-separated) or the local dev servers.

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
    checks: dict[str, dict] = {}
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        checks["database"] = {"ok": True, "kind": DB_KIND}
    except Exception as e:
        checks["database"] = {"ok": False, "detail": type(e).__name__}
    checks["store"] = store.status()
    sch = reminder_service._scheduler
    checks["scheduler"] = {"ok": bool(sch is not None and sch.running)}
    from ai import ddi
    checks["ddi"] = {"ok": True, "dataset": "DDInter" if ddi.available() else "not built (curated rules only)"}
    checks["laya"] = {"ok": True, "enabled": bool((os.getenv("LAYA_URL") or "").strip())}
    ok = all(v["ok"] for v in checks.values())
    if not ok:
        response.status_code = 503
    return {"ready": ok, **checks}


# Single-service hosting: serve the built frontend from here when a build is present (a no-op under the Docker stack).
from . import static_site  # noqa: E402

static_site.mount(app)
