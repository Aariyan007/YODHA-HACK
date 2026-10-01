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


def add_missing_columns() -> list[str]:
    """Add model columns that exist in code but not in the DB (nullable ADD COLUMN only).

    `create_all` creates missing tables but never alters existing ones, so new
    columns on old tables would 500. This keeps upgrades non-destructive.
    """
    from sqlalchemy import inspect

    added: list[str] = []
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have or col.primary_key:
                continue
            ddl_type = col.type.compile(dialect=engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl_type}'))
            added.append(f"{table.name}.{col.name}")
    return added


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
