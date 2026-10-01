import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

SQLITE_URL = f"sqlite:///{Path(__file__).resolve().parents[1] / 'medithread.db'}"


def _make_engine():
    url = os.getenv("DATABASE_URL", "").strip()
    # Normalise any Postgres scheme (postgres://, postgresql+psycopg://, ...) to psycopg2.
    if url.startswith("postgres") and "://" in url:
        url = "postgresql+psycopg2://" + url.split("://", 1)[1]
    if url.startswith("postgresql"):
        try:
            eng = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 8})
            with eng.connect() as conn:
                conn.execute(text("select 1"))
            print("[db] Connected to Supabase Postgres")
            return eng, "postgres"
        except Exception as e:
            print(f"[db] WARNING: Postgres connection failed ({type(e).__name__}). Falling back to local SQLite.")
    else:
        print("[db] DATABASE_URL missing or not Postgres. Using local SQLite.")
    eng = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    return eng, "sqlite"


engine, DB_KIND = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
