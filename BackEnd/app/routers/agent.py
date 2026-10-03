"""Agent API. The agent is an orchestration layer over existing services: it adds no data endpoints of its own
(documents, shares and reminders keep their routes). Patient agent here; the doctor agent has its own router."""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store
from ..agent.context import AgentContext
from ..agent import tasks as agent_tasks
from ..agent.engine import AgentEngine
from ..agent.registry import REGISTRY
from ..auth import current_patient
from ..database import get_db
from ..models import AgentAudit, AgentFile, Patient
from .. import vault
from ..agent import ingest
from ..agent.audit import AgentAuditLogger
from .documents import MAX_UPLOAD_BYTES, detect_type
from ..schemas import iso

router = APIRouter(prefix="/api/agent", tags=["agent"])
_engine: AgentEngine | None = None
RATE_PER_MIN = 30


def engine() -> AgentEngine:
    global _engine
    if _engine is None:
        _engine = AgentEngine()
    return _engine


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    conversationId: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]*$")
    fileId: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")


class ConfirmBody(BaseModel):
    id: str = Field(min_length=4, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    approve: bool


def patient_ctx(patient: Patient, db: Session, conv: str | None = None) -> AgentContext:
    return AgentContext(db=db, role="patient", actor_id=patient.id, actor_name=patient.name, patient_id=patient.id,
                        lang=patient.language or "en", conversation_id=conv)


def _limit(actor: str) -> None:
    key = f"agent:rate:{actor}:{int(time.time() // 60)}"  # one counter per minute
    n = int(store.get_value(key) or 0) + 1
    store.set_value(key, str(n), ttl=90)
    if n > RATE_PER_MIN:
        raise HTTPException(429, "You are asking quickly. Please wait a moment.")


DAILY_LIMIT = int(os.getenv("AGENT_DAILY_LIMIT", "80"))


def _daily_budget(actor: str) -> None:
    """One person cannot use up the shared free AI quota: N questions a day, then a plain message."""
    from datetime import date
    key = f"agent:day:{actor}:{date.today().isoformat()}"
    n = int(store.get_value(key) or 0) + 1
    store.set_value(key, str(n), ttl=90000)
    if n > DAILY_LIMIT:
        raise HTTPException(429, "You have reached today's limit for the assistant. It resets tomorrow.")


@router.post("/chat")
def chat(body: ChatBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    _limit(patient.id)
    _daily_budget(patient.id)
    ctx = patient_ctx(patient, db, body.conversationId)
    if body.fileId:
        ctx.file_id = owned_file(db, patient, body.fileId).id  # 404 for someone else's file
    out = engine().chat(ctx, body.text.strip())
    db.commit()  # audit rows
    return out


@router.post("/confirm")
def confirm(body: ConfirmBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    ctx = patient_ctx(patient, db)
    out = engine().confirm(ctx, body.id, body.approve)
    db.commit()
    return out


@router.get("/tasks")
def my_tasks(limit: int = 10, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    from ..models import AgentTask
    rows = db.scalars(select(AgentTask).where(AgentTask.user_id == patient.id, AgentTask.agent_type == "patient")
                      .order_by(AgentTask.created_at.desc()).limit(max(1, min(limit, 30))))
    return [{**agent_tasks.public(t), "result": None, "createdAt": iso(t.created_at)} for t in rows]


@router.get("/tasks/{task_id}")
def task_status(task_id: str, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    t = agent_tasks.owned(db, patient.id, "patient", task_id)
    if t is None:
        raise HTTPException(404, "Task not found")
    return agent_tasks.public(t)


@router.post("/tasks/{task_id}/cancel")
def task_cancel(task_id: str, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    out = engine().cancel(patient_ctx(patient, db), task_id)
    if out is None:
        raise HTTPException(404, "Task not found")
    return out


@router.get("/shares/{ref}")
def share_qr(ref: str, patient: Patient = Depends(current_patient)):
    """The QR payload for a share the agent just made. The token never travels in a task result or the audit log: it is
    held for 15 minutes under a key only this patient can read, and is fetched here with the patient's login."""
    import json
    raw = store.get_value(f"agent:qr:{patient.id}:{ref}") if ref.isalnum() else None
    if raw is None:
        raise HTTPException(404, "That share is no longer available to show. Ask me to make a new one.")
    return json.loads(raw)


@router.get("/tools")
def tools(patient: Patient = Depends(current_patient)):
    return [{"name": t["name"], "description": t["description"], "level": t["level"]} for t in REGISTRY.describe("patient")]


@router.get("/history")
def history(limit: int = 20, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """The person's own agent activity (what the agent read or did), newest first."""
    rows = db.scalars(select(AgentAudit).where(AgentAudit.patient_id == patient.id, AgentAudit.agent_type == "patient")
                      .order_by(AgentAudit.created_at.desc()).limit(max(1, min(limit, 50))))
    return [{"tool": r.tool, "category": r.category, "level": r.level, "status": r.status, "confirmed": r.confirmed,
             "at": iso(r.created_at)} for r in rows]


# ---------- files ----------

MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "pdf": "application/pdf"}
TYPES = ("lab", "prescription", "visit", "scan")


def _safe_name(name: str | None, kind: str) -> str:
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = "".join(ch for ch in base if ch.isalnum() or ch in " ._-")[:100].strip(" .")
    return base or f"document.{kind}"


def file_out(f: AgentFile) -> dict:
    c = f.classification or {}
    return {"fileId": f.id, "name": f.display_name, "mime": f.mime, "size": f.size, "status": f.status,
            "type": c.get("type"), "confidence": c.get("confidence"),
            "needsType": c.get("type") is None and f.status != "discarded", "reason": c.get("reason"),
            "documentId": f.document_id, "createdAt": iso(f.created_at)}


def purge_expired(db: Session, patient_id: str) -> None:
    """Generated PDFs are short-lived: past their time the bytes are deleted."""
    from datetime import datetime, timezone
    for f in db.scalars(select(AgentFile).where(AgentFile.patient_id == patient_id, AgentFile.status == "generated")):
        exp = (f.classification or {}).get("expiresAt")
        if exp and datetime.fromisoformat(exp) < datetime.now(timezone.utc):
            vault.delete(f.storage_key)
            f.status = "discarded"
    db.flush()


def owned_file(db: Session, patient: Patient, file_id: str) -> AgentFile:
    purge_expired(db, patient.id)
    f = db.scalar(select(AgentFile).where(AgentFile.id == file_id, AgentFile.patient_id == patient.id, AgentFile.uploaded_by == patient.id, AgentFile.status != "discarded"))
    if f is None:  # same answer for missing and not yours
        raise HTTPException(404, "File not found")
    return f


def ingest_upload(db: Session, ctx: AgentContext, data: bytes, filename: str | None) -> dict:
    """Validate, classify and store one uploaded file for ctx.patient_id, uploaded by ctx.actor_id. Shared by both agents."""
    import hashlib
    if not vault.available():
        raise HTTPException(503, "File storage is not set up on this server.")
    if not data:
        raise HTTPException(400, "File is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is too large (limit is 10 MB).")
    kind = detect_type(data)
    if kind is None:
        raise HTTPException(415, "This file type is not supported. Please use a JPG, PNG, WEBP or PDF.")
    sha = hashlib.sha256(data).hexdigest()
    log = AgentAuditLogger()
    dup = db.scalar(select(AgentFile).where(AgentFile.patient_id == ctx.patient_id, AgentFile.uploaded_by == ctx.actor_id,
                                            AgentFile.sha256 == sha, AgentFile.status != "discarded"))
    if dup is not None:
        log.record(ctx, None, "files.upload", "ok", target=dup.id, detail="duplicate")
        db.commit()
        return {**file_out(dup), "duplicate": True}
    cls: dict = {"type": None, "confidence": 0.0, "source": "none", "reason": "needs reading first"}
    if kind == "pdf":
        texts, pages = ingest.pdf_pages(data)
        cls = ingest.classify("\n".join(texts))
        cls["pages"] = pages
        cls["hasText"] = any(texts)
    row = AgentFile(patient_id=ctx.patient_id, uploaded_by=ctx.actor_id, uploader_role=ctx.role, display_name=_safe_name(filename, kind),
                    mime=MIME[kind], size=len(data), sha256=sha, storage_key=vault.new_storage_key(),
                    status="classified" if cls["type"] else "uploaded", classification=cls)
    db.add(row)
    db.flush()
    try:
        vault.put(row.storage_key, data, row.id, ctx.patient_id)
    except vault.VaultError:
        db.rollback()
        raise HTTPException(503, "I could not store that file safely, so I did not keep it.")
    log.record(ctx, None, "files.upload", "ok", target=row.id, detail=f"{kind} {len(data)}B")
    db.commit()
    return {**file_out(row), "duplicate": False}


@router.post("/files")
async def upload_file(file: UploadFile = File(...), patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """Store a file encrypted and classify it. Nothing reaches the health thread from here: extraction and writing are
    separate steps, and writing needs the person's confirmation."""
    _limit(patient.id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)  # never buffer more than the limit plus one byte
    return ingest_upload(db, patient_ctx(patient, db), data, file.filename)


@router.get("/files")
def list_files(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    purge_expired(db, patient.id)
    db.commit()
    rows = db.scalars(select(AgentFile).where(AgentFile.patient_id == patient.id, AgentFile.uploaded_by == patient.id, AgentFile.status != "discarded")
                      .order_by(AgentFile.created_at.desc()).limit(50))
    return [file_out(f) for f in rows]


class TypeBody(BaseModel):
    type: str = Field(pattern=r"^(lab|prescription|visit|scan)$")


@router.post("/files/{file_id}/type")
def set_type(file_id: str, body: TypeBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """The person's answer when the agent could not tell what the document is."""
    f = owned_file(db, patient, file_id)
    f.classification = {**(f.classification or {}), "type": body.type, "confidence": 1.0, "source": "user", "reason": None}
    f.status = "classified" if f.status == "uploaded" else f.status
    AgentAuditLogger().record(patient_ctx(patient, db), None, "files.set_type", "ok", target=f.id, detail=body.type)
    db.commit()
    return file_out(f)


@router.get("/files/{file_id}/content")
def download_file(file_id: str, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """Authenticated download of the person's own file. Decrypted in memory, never cached, no path exposed."""
    f = owned_file(db, patient, file_id)
    try:
        data = vault.get(f.storage_key, f.id, f.patient_id)
    except vault.VaultError:
        raise HTTPException(410, "That file can no longer be opened.")
    AgentAuditLogger().record(patient_ctx(patient, db), None, "files.download", "ok", target=f.id)
    db.commit()
    return Response(data, media_type=f.mime, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                                      "Content-Disposition": f'attachment; filename="{_safe_name(f.display_name, "bin")}"'})


@router.delete("/files/{file_id}")
def delete_file(file_id: str, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """Remove the stored bytes. A record already confirmed into the timeline is a separate thing and stays."""
    f = owned_file(db, patient, file_id)
    vault.delete(f.storage_key)
    f.status = "discarded"
    AgentAuditLogger().record(patient_ctx(patient, db), None, "files.delete", "ok", target=f.id)
    db.commit()
    return {"ok": True}


# ---------- voice ----------

MAX_AUDIO = 6 * 1024 * 1024


def voice_to_text(db: Session, ctx: AgentContext, data: bytes, language: str | None) -> dict:
    """Shared by both agents. Returns only text for the person to read and edit: speech never creates a fact or runs a tool."""
    from .. import speech
    from .consultations import _sniff_audio
    if not data:
        raise HTTPException(400, "No audio was received.")
    if len(data) > MAX_AUDIO:
        raise HTTPException(413, "That recording is too long. Please keep it under a minute.")
    kind = _sniff_audio(data[:16])
    if kind is None:
        raise HTTPException(415, "That does not look like a recording this server can read.")
    mime, ext = kind
    try:
        out = speech.transcribe(data, f"voice.{ext}", mime, language if language in ("en", "ml", "hi", "ta") else None)
    except speech.SpeechError as e:
        raise HTTPException(e.status, str(e))
    AgentAuditLogger().record(ctx, None, "voice.transcribe", "ok", detail=f"{out['engine']} {len(data)}B {'empty' if not out['text'] else 'text'}")
    db.commit()
    return {"text": out["text"], "language": out["language"], "engine": out["engine"]}


@router.post("/voice")
async def voice(file: UploadFile = File(...), language: str | None = None, patient: Patient = Depends(current_patient),
                db: Session = Depends(get_db)):
    _limit(patient.id)
    return voice_to_text(db, patient_ctx(patient, db), await file.read(MAX_AUDIO + 1), language)
