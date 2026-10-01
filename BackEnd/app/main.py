from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import store
from .database import DB_KIND, Base, SessionLocal, engine
from .routers import auth, patients, shares
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if seed_if_empty(db):
            print("[seed] Loaded demo patient Ammini Varghese")
    yield


app = FastAPI(title="MediThread API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(shares.router)


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "db": DB_KIND, "store": store.KIND}
