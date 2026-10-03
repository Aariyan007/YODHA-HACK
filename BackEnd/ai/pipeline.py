"""Runs the upload pipeline.

The pipeline is a plain function. Each stage event goes onto an asyncio.Queue so the SSE endpoint can send it to the browser.

Stages: read, understand, code, explain, check
Last message: {"done": true, "result": {...}} or {"error": "..."}
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import store
from app.database import SessionLocal
from app.labs import code_for_name, loinc_for, slug
from app.vitals import from_extracted as vitals_from_extracted
from app.health_hooks import after_new_data, notify_patient
from app.models import AccessLog, Alert, Document, Medicine, Observation, Patient, new_id, now as utcnow
from . import reminders as reminders_mod
from . import telegram
from .extractor import ExtractError, extract
from .safety import analyse
from .translator import summarise

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "uploads"
CACHE = ROOT / "demo_cache"
UPLOADS.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

JOBS: dict[str, dict] = {}  # jobId -> {status, queue, loop, result?, error?}
STAGES_ORDER = ["read", "understand", "code", "explain", "check"]


# ---------- helpers ----------

def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _save_upload(data: bytes, filename: str, sha: str) -> Path:
    ext = Path(filename).suffix.lower() or ".bin"
    path = UPLOADS / f"{sha[:16]}{ext}"
    if not path.exists():
        path.write_bytes(data)
    return path


def _cache_path(sha: str) -> Path:
    return CACHE / f"{sha}.json"


def _save_cache(sha: str, result: dict) -> None:
    try:
        _cache_path(sha).write_text(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(f"[cache] write failed: {type(e).__name__}")


def _load_cache(sha: str) -> dict | None:
    p = _cache_path(sha)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _mime_from_name(name: str) -> str:
    name = name.lower()
    if name.endswith(".png"): return "image/png"
    if name.endswith(".jpg") or name.endswith(".jpeg"): return "image/jpeg"
    if name.endswith(".webp"): return "image/webp"
    if name.endswith(".pdf"): return "application/pdf"
    return "application/octet-stream"


# ---------- stage events (sync thread to async) ----------

class Bus:
    """Pushes stage events from a background thread to the SSE async loop."""
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self._loop = loop
        self._queue = queue

    def send(self, obj: dict) -> None:
        asyncio.run_coroutine_threadsafe(self._queue.put(obj), self._loop)


# ---------- the pipeline ----------

def _patient_context(db: Session, patient_id: str) -> tuple[Patient, list[dict]]:
    patient = db.get(Patient, patient_id)
    active = list(db.scalars(select(Medicine).where(Medicine.patient_id == patient_id, Medicine.active.is_(True))))
    return patient, [{"name": m.name, "generic": m.generic} for m in active]


def _lab_code_from_name(name: str) -> str | None:
    return code_for_name(name)


def _persist_result(patient_id: str, result: dict, sha: str, mime: str) -> dict:
    """Saves a cached result into the DB and returns it (with any new ids)."""
    rec = result["record"]
    reminders_list = result.get("reminders", [])
    alerts = result.get("alerts", [])

    with SessionLocal() as db:
        patient = db.get(Patient, patient_id)
        # Skip if this hash is already saved for the patient.
        existing = db.scalar(
            select(Document).where(Document.patient_id == patient_id, Document.file_hash == sha)
        )
        if existing is not None:
            return result

        doc_id = new_id()
        items = []
        for ob in rec.get("observations", []):
            items.append({
                "name": ob.get("name"), "code": ob.get("code"), "value": ob.get("value"),
                "unit": ob.get("unit"), "range": ob.get("range"), "status": ob.get("status"),
                "plain": ob.get("plain"),
            })
        for m in rec.get("medications", []):
            items.append({
                "name": m.get("name"), "generic": m.get("generic"), "dose": m.get("dose"),
                "frequency": m.get("schedule"), "duration": m.get("duration"), "purpose": m.get("purpose"),
            })
        source_text = ", ".join(x for x in (rec.get("provider"), rec.get("doctor")) if x) or None
        db.add(Document(
            id=doc_id, patient_id=patient_id, date=rec.get("date"), type=rec.get("type") or "prescription",
            title=rec.get("title") or "New record",
            source=source_text, summary=(rec.get("summary") or {}).get("en"),
            summary_ml=(rec.get("summary") or {}).get("ml"),
            tags=rec.get("tags", []), items=items,
            status=rec.get("status"), provider=rec.get("provider"), doctor=rec.get("doctor"),
            followup=rec.get("followUp"),
            source_kind=(rec.get("source") or {}).get("kind") or ("pdf" if mime == "application/pdf" else "image"),
            source_lines=(rec.get("source") or {}).get("lines", []),
            source_highlight=(rec.get("source") or {}).get("highlight", []),
            file_hash=sha,
        ))
        rec["id"] = doc_id  # keep caller in sync

        for ob in rec.get("observations", []):
            try:
                val = float(ob["value"])
            except (KeyError, TypeError, ValueError):
                continue
            db.add(Observation(
                patient_id=patient_id, document_id=doc_id, date=rec.get("date"),
                code=ob.get("code") or slug(ob.get("name")), name=ob.get("name") or "value",
                value=val, unit=ob.get("unit"), loinc=loinc_for(ob.get("code")),
                ref_range=(ob.get("range") or None) and str(ob.get("range"))[:60],
            ))

        for m in rec.get("medications", []):
            db.add(Medicine(
                patient_id=patient_id, document_id=doc_id,
                name=m.get("name") or "Medicine", generic=m.get("generic"),
                dose=m.get("dose"), frequency=m.get("schedule"),
                times=m.get("times") or [],
                instructions=m.get("purpose"),
                start_date=rec.get("date"), prescribed_by=rec.get("doctor"),
                duration_days=reminders_mod.parse_duration_days(m.get("schedule"), m.get("duration")),
            ))

        # Save alerts (new ids each time, drop the cached ones).
        saved_alerts = []
        for a in alerts:
            if a.get("kind") == "trend":
                continue  # recomputed below from stored Observations
            row = Alert(
                patient_id=patient_id, severity=a["severity"], kind=a["kind"],
                title=a["title"], message=a["message"], message_ml=a.get("messageMl"), data=a.get("data"),
            )
            db.add(row)
            db.flush()
            saved_alerts.append({
                "id": row.id, "severity": row.severity, "kind": row.kind,
                "title": row.title, "message": row.message, "messageMl": a.get("messageMl"),
                "resolved": False, "createdAt": datetime.now(timezone.utc).isoformat(),
            })

        db.flush()
        saved_alerts += after_new_data(db, patient_id)
        db.add(AccessLog(
            patient_id=patient_id, who=patient.name, role="Patient",
            action=f"Added {rec.get('type') or 'record'}", via="Upload",
        ))
        db.commit()

    return {"record": rec, "alerts": saved_alerts, "reminders": reminders_list}


def _run_sync(patient_id: str, data: bytes, filename: str, sha: str, bus: Bus, doc: dict | None = None) -> dict:
    """Runs every stage and returns the final result dict (for the SSE 'done' event)."""
    mime = _mime_from_name(filename)

    # read
    bus.send({"stage": "read"})
    # understand (same model call, split as a stage so the UI shows motion)
    bus.send({"stage": "understand"})
    if doc is None:  # the agent passes a document it already read and the person confirmed
        doc = extract(data, mime)

    # code: build full picture
    bus.send({"stage": "code"})
    with SessionLocal() as db:
        patient, existing = _patient_context(db, patient_id)
        allergies = list(patient.allergies or [])

        # Normalise observations with lab codes.
        obs = []
        for o in doc.get("observations", []):
            o = dict(o)
            if not o.get("code"):
                o["code"] = _lab_code_from_name(o.get("name")) or slug(o.get("name"))
            obs.append(o)
        # Vitals written on the page (BP, pulse, SpO2, weight) are readings too.
        have = {o["code"] for o in obs}
        obs += [v for v in vitals_from_extracted(doc.get("vitals")) if v["code"] not in have]

        analysis = analyse(
            patient_name=patient.name,
            patient_allergies=allergies,
            existing_medicines=existing,
            new_medicines=[dict(m) for m in doc.get("medicines", [])],
            observations=obs,
        )

    # explain
    bus.send({"stage": "explain"})
    for u in doc.get("uncertain_medicines") or []:  # handwriting we couldn't read for sure: never a medicine, always shown as a note
        analysis["alerts"].append({"severity": "medium", "kind": "handwriting", "title": f"Handwriting unclear: {str(u.get('name'))[:60]}",
                                   "message": f"I could not read this medicine name with confidence ({u.get('reason')}). It was not added to your medicines. "
                                              "Please check it with your doctor or pharmacist.",
                                   "data": {"name": str(u.get("name")), **(u.get("details") or {})}})
    summary = summarise(doc, analysis["alerts"])

    # check: reminders + persistence
    bus.send({"stage": "check"})
    rem_list = reminders_mod.build_reminders(analysis["medications"], doc.get("follow_up"))

    now_iso = datetime.now(timezone.utc).isoformat()
    with SessionLocal() as db:
        patient = db.get(Patient, patient_id)
        doc_id = new_id()
        date_s = doc.get("date_of_record") or datetime.now().date().isoformat()
        provider = doc.get("hospital")
        doctor = doc.get("doctor")
        source_text = ", ".join(x for x in (provider, doctor) if x) or None

        # Items for the generic timeline view (observations + prescriptions mixed).
        items = []
        for ob in analysis["observations"]:
            items.append({
                "name": ob.get("name"), "code": ob.get("code"), "value": ob.get("value"),
                "unit": ob.get("unit"), "range": ob.get("range"), "status": ob.get("status"),
                "plain": ob.get("plain"),
            })
        for m in analysis["medications"]:
            items.append({
                "name": m.get("name"), "generic": m.get("generic"), "dose": m.get("dose"),
                "frequency": m.get("schedule"), "duration": m.get("duration"), "purpose": m.get("purpose"),
            })

        db.add(Document(
            id=doc_id, patient_id=patient_id, date=date_s, type=doc.get("type") or "prescription",
            title=(doc.get("diagnoses") or ["New medical record"])[0][:200],
            source=source_text, summary=summary["en"], summary_ml=summary["ml"],
            tags=doc.get("diagnoses") or [], items=items,
            status=analysis["worst_status"], provider=provider, doctor=doctor,
            followup=doc.get("follow_up"),
            source_kind="pdf" if mime == "application/pdf" else "image",
            source_lines=doc.get("source_lines") or [],
            source_highlight=list(range(min(len(doc.get("source_lines") or []), 8))),
            file_hash=sha,
        ))

        # Save observations.
        for ob in analysis["observations"]:
            try:
                val = float(ob["value"])
            except (KeyError, TypeError, ValueError):
                continue
            db.add(Observation(
                patient_id=patient_id, document_id=doc_id, date=date_s,
                code=ob.get("code") or slug(ob.get("name")), name=ob.get("name") or "value",
                value=val, unit=ob.get("unit"), loinc=loinc_for(ob.get("code")),
                ref_range=(ob.get("range") or None) and str(ob.get("range"))[:60],
            ))

        # Save new medicines (duplicates still save, the alert warns the user).
        for m in analysis["medications"]:
            db.add(Medicine(
                patient_id=patient_id, document_id=doc_id,
                name=m.get("name") or "Medicine", generic=m.get("generic"),
                dose=m.get("dose"), frequency=m.get("schedule"),
                times=m.get("times") or reminders_mod.parse_schedule(m.get("schedule")),
                instructions=m.get("purpose"),
                start_date=date_s, prescribed_by=doctor,
                duration_days=reminders_mod.parse_duration_days(m.get("schedule"), m.get("duration")),
            ))

        # Save alerts (persist so they show on the Home page too).
        saved_alerts = []
        for a in analysis["alerts"]:
            row = Alert(
                patient_id=patient_id, severity=a["severity"], kind=a["kind"],
                title=a["title"], message=a["message"], data=a.get("data"),
                # message_ml is left in English for now, the translator could be used here later.
                message_ml=None,
            )
            db.add(row)
            db.flush()
            saved_alerts.append({
                "id": row.id, "severity": row.severity, "kind": row.kind,
                "title": row.title, "message": row.message, "messageMl": None, "data": row.data,
                "resolved": False, "createdAt": now_iso,
            })

        db.flush()
        saved_alerts += after_new_data(db, patient_id)
        db.add(AccessLog(
            patient_id=patient_id, who=patient.name, role="Patient",
            action=f"Added {doc.get('type') or 'record'}", via="Upload",
        ))
        db.commit()

    # Build the shape the frontend expects for the result.
    record = {
        "id": doc_id,
        "date": date_s,
        "type": doc.get("type") or "prescription",
        "status": analysis["worst_status"],
        "title": (doc.get("diagnoses") or ["New medical record"])[0][:200],
        "provider": provider,
        "doctor": doctor,
        "summary": summary,
        "observations": analysis["observations"],
        "medications": [
            {k: m.get(k) for k in ("name", "generic", "dose", "schedule", "times", "duration", "purpose")}
            for m in analysis["medications"]
        ],
        "followUp": doc.get("follow_up"),
        "source": {
            "kind": "pdf" if mime == "application/pdf" else "image",
            "lines": doc.get("source_lines") or [],
            "highlight": list(range(min(len(doc.get("source_lines") or []), 8))),
        },
        "isNew": True,
    }

    # Telegram to this patient's own chat (fire-and-forget).
    try:
        with SessionLocal() as db:
            notify_patient(db, patient_id, f"New {record['type']} added. {len(saved_alerts)} warnings. Open MediThread.")
    except Exception:
        pass

    return {"record": record, "alerts": saved_alerts, "reminders": rem_list}


# ---------- entry point used by the HTTP layer ----------

def start_job(patient_id: str, data: bytes, filename: str) -> tuple[str, bool]:
    """Returns (job_id, from_cache). Starts a background thread, or finishes right away."""
    sha = _hash(data)
    _save_upload(data, filename, sha)
    job_id = uuid.uuid4().hex

    # Duplicate-report check: same hash seen for this patient.
    with SessionLocal() as db:
        row = db.scalar(select(Document).where(Document.patient_id == patient_id, Document.file_hash == sha))
    if row is not None:
        JOBS[job_id] = {
            "status": "done", "patient_id": patient_id, "sha": sha,
            "error": "You already added this report. Open it on your Timeline.",
            "started": time.time(),
        }
        return job_id, True

    JOBS[job_id] = {
        "status": "pending", "patient_id": patient_id, "sha": sha,
        "started": time.time(), "cached": _cache_path(sha).exists(),
    }
    return job_id, _cache_path(sha).exists()


def _emit_cached(bus: Bus, result: dict) -> dict:
    for s in STAGES_ORDER:
        bus.send({"stage": s})
        time.sleep(0.08)  # just enough to animate, it's for a slow wifi demo
    return result


async def run_async(job_id: str) -> asyncio.Queue:
    """Attaches an SSE listener to a job and starts the worker if it hasn't started."""
    job = JOBS.get(job_id)
    if job is None:
        raise KeyError(job_id)

    # One queue per listener. Only one listener per job for now.
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    bus = Bus(loop, queue)

    def worker():
        try:
            if job.get("error"):
                bus.send({"error": job["error"]})
                return
            cached = _load_cache(job["sha"])
            if cached is not None:
                # Still save to DB when a fresh demo DB has no record yet.
                result = _persist_result(job["patient_id"], cached, job["sha"],
                                         _mime_from_name(_upload_name(job["sha"])))
                _emit_cached(bus, result)
            else:
                result = _run_sync(job["patient_id"], _read_upload(job["sha"]), _upload_name(job["sha"]), job["sha"], bus)
                _save_cache(job["sha"], result)
            job["result"] = result
            job["status"] = "done"
            bus.send({"done": True, "result": result})
        except ExtractError as e:
            job["status"] = "error"
            job["error"] = str(e)
            bus.send({"error": str(e)})
        except Exception as e:
            msg = f"Something went wrong while reading the document. ({type(e).__name__})"
            job["status"] = "error"
            job["error"] = msg
            print(f"[pipeline] {type(e).__name__}: {e}")
            bus.send({"error": msg})

    if job["status"] == "pending":
        job["status"] = "running"
        Thread(target=worker, daemon=True).start()
    elif job["status"] == "done" and "result" in job:
        # Replay for a reconnecting listener.
        for s in STAGES_ORDER:
            await queue.put({"stage": s})
        await queue.put({"done": True, "result": job["result"]})
    elif job.get("error"):
        await queue.put({"error": job["error"]})

    return queue


def _read_upload(sha: str) -> bytes:
    for p in UPLOADS.glob(f"{sha[:16]}.*"):
        return p.read_bytes()
    raise FileNotFoundError(sha)


def _upload_name(sha: str) -> str:
    for p in UPLOADS.glob(f"{sha[:16]}.*"):
        return p.name
    return f"{sha[:16]}.bin"
