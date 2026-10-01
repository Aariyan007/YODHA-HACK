import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import reminder_service, store
from .database import DB_KIND, Base, SessionLocal, add_missing_columns, engine
from .routers import auth, consultations, demo, documents, imports, patients, reminders, shares
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
    reminder_service.start()
    try:
        yield
    finally:
        reminder_service.stop()


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

app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(shares.router)
app.include_router(documents.router)
app.include_router(consultations.router)
app.include_router(reminders.router)
app.include_router(imports.router)
app.include_router(demo.router)


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "db": DB_KIND, "store": store.KIND}
