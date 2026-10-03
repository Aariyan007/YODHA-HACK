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
    if url.startswith("postgresql") and (os.getenv("DB_POOL_MODE") or "").strip().lower() == "transaction":
        # Supabase's session pooler (port 5432) allows few clients in total; the transaction pooler (6543) allows many.
        # Safe here: we use plain SQL with no prepared statements, advisory locks or session state.
        url = url.replace(":5432/", ":6543/")
    if url.startswith("postgresql"):
        try:
            # Supabase's session pooler allows only a handful of client connections per project, so keep this process small:
            # 3 + 2 overflow, recycled every 5 minutes (the default 5 + 10 can starve other processes and the tests).
            # The transaction pooler (6543) multiplexes many clients over few server connections, so a bigger local pool is safe
            # there; without it, 100 people at once queued behind 5 connections and timed out. Override with DB_POOL_SIZE / DB_MAX_OVERFLOW.
            big = (os.getenv("DB_POOL_MODE") or "").strip().lower() == "transaction"
            size = int(os.getenv("DB_POOL_SIZE") or (20 if big else 3))
            over = int(os.getenv("DB_MAX_OVERFLOW") or (20 if big else 2))
            eng = create_engine(url, pool_pre_ping=True, pool_size=size, max_overflow=over, pool_recycle=300, pool_timeout=15,
                                connect_args={"connect_timeout": 8})
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


_INDEXES = [
    ("ix_documents_patient_date", "documents", "patient_id, date"),
    ("ix_observations_patient_date", "observations", "patient_id, date"),
    ("ix_alerts_patient_resolved", "alerts", "patient_id, resolved"),
    ("ix_agent_audit_actor", "agent_audit", "actor_id"),
]


def add_missing_indexes() -> list[str]:
    """Composite indexes for the queries every page makes (patient + date, open alerts). Idempotent and safe to re-run."""
    made: list[str] = []
    for name, table, cols in _INDEXES:
        try:
            with engine.begin() as conn:
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})'))
            made.append(name)
        except Exception as e:  # an index is an optimisation: never stop the server over one
            print(f"[db] index {name} skipped: {e}")
    return made


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
