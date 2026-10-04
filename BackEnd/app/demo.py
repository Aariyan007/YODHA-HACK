"""Demo mode helpers: reset Ammini to the clean seed, and a deep health check.

Both are only exposed when DEMO_MODE=true (see routers/demo.py). Nothing here returns or logs a key, token or
connection string.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text

from ai import pipeline, telegram
from . import reminder_service, store
from .database import DB_KIND, SessionLocal, engine
from .models import (AccessLog, Alert, Consultation, Document, Medicine, Observation, ReminderSettings,
                     SentDose, SentNotice)
from .seed import ALERTS, DEMO_ID, DOCUMENTS, MEDICINES, load_demo

SEED_DOC_IDS = {d[0] for d in DOCUMENTS}


# ---------- reset ----------

def reset_demo() -> dict:
    """Puts Ammini back to the seeded state: 8 records, 3 medicines, 3 alerts, Telegram reminders on.
    
    Deletes uploaded, imported and consultation records, sent-dose rows and the in-memory job caches.
    BackEnd/demo_cache is left alone so re-uploading the test images still replays instantly.
    """
    with SessionLocal() as db:
        extra_docs = list(db.scalars(select(Document).where(Document.patient_id == DEMO_ID, Document.id.not_in(SEED_DOC_IDS))))
        deleted = {
            "uploadedDocuments": sum(1 for d in extra_docs if d.origin != "fhir" and d.type != "visit"),
            "importedRecords": sum(1 for d in extra_docs if d.origin == "fhir"),
            "visitNotes": sum(1 for d in extra_docs if d.origin != "fhir" and d.type == "visit"),
        }
        med_ids = list(db.scalars(select(Medicine.id).where(Medicine.patient_id == DEMO_ID)))

        def wipe(model, key="patient_id"):
            return db.execute(delete(model).where(getattr(model, key) == DEMO_ID)).rowcount or 0

        # Agent files can point at timeline documents (document_id), so they go first, and their encrypted bytes go too.
        from . import vault
        from .models import AgentAudit, AgentFile, AgentTask
        for sk in db.scalars(select(AgentFile.storage_key).where(AgentFile.patient_id == DEMO_ID)):
            vault.delete(sk)
        deleted["agentFiles"] = wipe(AgentFile)
        deleted["agentTasks"] = wipe(AgentTask)
        deleted["agentAudit"] = wipe(AgentAudit)
        deleted["sentDoses"] = wipe(SentDose)
        deleted["sentNotices"] = wipe(SentNotice)
        deleted["consultations"] = wipe(Consultation)
        deleted["observations"] = wipe(Observation)
        deleted["medicines"] = wipe(Medicine)
        deleted["alerts"] = wipe(Alert)
        deleted["accessLogs"] = wipe(AccessLog)
        deleted["documents"] = wipe(Document)

        load_demo(db)
        # Keep her settings row (it holds the chat id she saved), just turn the reminders on.
        s = db.get(ReminderSettings, DEMO_ID)
        if s is None:
            s = ReminderSettings(patient_id=DEMO_ID, family_name="Joseph")
            db.add(s)
        s.telegram_chat_id = s.telegram_chat_id or (os.getenv("TELEGRAM_CHAT_ID") or "").strip() or None
        s.enabled = True
        s.channel_telegram = True
        s.channel_family = False
        s.missed_after_minutes = 60
        s.updated_at = datetime.now(reminder_service.IST)
        chat_set = bool(s.telegram_chat_id)
        db.commit()

        restored = {
            "documents": db.scalar(select(func.count()).select_from(Document).where(Document.patient_id == DEMO_ID)),
            "medicines": db.scalar(select(func.count()).select_from(Medicine).where(Medicine.patient_id == DEMO_ID)),
            "alerts": db.scalar(select(func.count()).select_from(Alert).where(Alert.patient_id == DEMO_ID)),
        }

    # In-memory / Redis state tied to the rows we just removed.
    jobs = len(pipeline.JOBS)
    pipeline.JOBS.clear()
    jobs += store.delete_prefix("job:")   # queue mode keeps job state and events in Redis
    store.delete_prefix("jobev:")
    files = 0
    for p in pipeline.UPLOADS.glob("*"):
        if p.is_file():
            p.unlink()
            files += 1
    keys = store.delete_prefix(f"taken:{DEMO_ID}:")
    for mid in set(med_ids) | {m["id"] for m in MEDICINES}:
        keys += store.delete_prefix(f"dose:{mid}@")

    return {
        "ok": True,
        "deleted": {**deleted, "uploadedFiles": files, "jobCaches": jobs, "storeKeys": keys},
        "restored": restored,
        "expected": {"documents": len(DOCUMENTS), "medicines": len(MEDICINES), "alerts": len(ALERTS)},
        "telegramReminders": {"on": True, "chatIdSet": chat_set, "botReady": telegram.ready()},
        "demoCacheKept": len(list(pipeline.CACHE.glob("*.json"))),
    }


# ---------- deep health ----------

def _ok(detail: str, **extra) -> dict:
    return {"status": "ok", "detail": detail, **extra}


def _down(detail: str) -> dict:
    return {"status": "down", "detail": detail}


def _why(e: Exception) -> str:
    """Class name plus the HTTP status if there is one. Never the message (it can echo a URL)."""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    return f"{type(e).__name__}" + (f" (HTTP {code})" if code else "")


def _database() -> dict:
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        return _ok("Supabase Postgres" if DB_KIND == "postgres" else "Local SQLite fallback")
    except Exception as e:
        return _down(_why(e))


def _redis() -> dict:
    if store.KIND != "redis":
        return {"status": "fallback", "detail": "In-memory store (Redis not used)"}
    try:
        store._redis.ping()
        return _ok("Redis")
    except Exception as e:
        return _down(_why(e))


def _gemini() -> dict:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return _down("Key is not set")
    try:
        from google import genai
        from google.genai import types
        from ai.extractor import MODELS
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=12000))  # Gemini rejects deadlines under 10 s
        last = "no model answered"
        for model in MODELS[:2]:  # the app falls through the model list, two tries is enough to know
            try:
                client.models.generate_content(model=model, contents="Reply with OK.",
                                               config=types.GenerateContentConfig(max_output_tokens=8))
                return _ok(model)
            except Exception as e:
                last = _why(e)
        return _down(last)
    except Exception as e:
        return _down(_why(e))


def _groq() -> dict:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return _down("Key is not set")
    try:
        from groq import Groq
        from ai.translator import MODEL
        Groq(api_key=key, timeout=8.0).chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=16, reasoning_effort="low")
        return _ok(MODEL)
    except Exception as e:
        return _down(_why(e))


def _telegram() -> dict:
    ok, detail = telegram.check()
    return _ok(detail) if ok else _down(detail)


def _scheduler() -> dict:
    sch = reminder_service._scheduler
    if sch is not None and sch.running:
        return _ok(f"Running, every {reminder_service.TICK_SECONDS}s")
    return _down("Not running")


def deep_health() -> dict:
    checks = {"database": _database, "redis": _redis, "gemini": _gemini, "groq": _groq,
              "telegram": _telegram, "scheduler": _scheduler}
    with ThreadPoolExecutor(max_workers=len(checks)) as ex:  # the slow ones are network calls
        futures = {k: ex.submit(fn) for k, fn in checks.items()}
        out = {k: f.result() for k, f in futures.items()}
    return {"allOk": all(v["status"] in ("ok", "fallback") for v in out.values()),
            "checkedAt": datetime.now(reminder_service.IST).isoformat(), **out}
