"""Doctor Agent API. Same engine as the patient agent; the context is the doctor's own account plus ONE linked patient.
Every call re-checks the care link (404 when there is none, so patient ids cannot be probed), and the permission manager checks it
again for every tool."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import vault
from ..agent import tasks as agent_tasks
from ..agent.audit import AgentAuditLogger
from ..agent.context import AgentContext
from ..agent.registry import REGISTRY
from ..auth import current_doctor
from ..database import get_db
from ..models import AgentAudit, AgentFile, AgentTask, CareLink, Patient, User
from ..schemas import iso
from . import agent as A
from .documents import MAX_UPLOAD_BYTES

router = APIRouter(prefix="/api/doctor-agent", tags=["doctor-agent"])


def doctor_ctx(doctor: User, patient_id: str, db: Session, conv: str | None = None) -> AgentContext:
    link = db.scalar(select(CareLink).where(CareLink.patient_id == patient_id, CareLink.doctor_user_id == doctor.id, CareLink.status == "active"))
    patient = db.get(Patient, patient_id) if link else None
    if patient is None:
        raise HTTPException(404, "Patient not found")
    return AgentContext(db=db, role="doctor", actor_id=doctor.id, actor_name=doctor.name, patient_id=patient.id, lang="en", conversation_id=conv)


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=4500)
    patientId: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    conversationId: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]*$")
    fileId: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")


class ConfirmBody(BaseModel):
    id: str = Field(min_length=4, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    patientId: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    approve: bool


def _doctor_file(db: Session, doctor: User, patient_id: str, file_id: str) -> AgentFile:
    f = db.scalar(select(AgentFile).where(AgentFile.id == file_id, AgentFile.patient_id == patient_id, AgentFile.uploaded_by == doctor.id,
                                          AgentFile.status != "discarded"))
    if f is None:
        raise HTTPException(404, "File not found")
    return f


@router.post("/chat")
def chat(body: ChatBody, doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    A._limit(doctor.id)
    ctx = doctor_ctx(doctor, body.patientId, db, body.conversationId)
    if body.fileId:
        ctx.file_id = _doctor_file(db, doctor, ctx.patient_id, body.fileId).id
    out = A.engine().chat(ctx, body.text.strip())
    db.commit()
    return out


@router.post("/confirm")
def confirm(body: ConfirmBody, doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    out = A.engine().confirm(doctor_ctx(doctor, body.patientId, db), body.id, body.approve)
    db.commit()
    return out


@router.get("/tasks/{task_id}")
def task_status(task_id: str, doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    t = agent_tasks.owned(db, doctor.id, "doctor", task_id)
    if t is None:
        raise HTTPException(404, "Task not found")
    return agent_tasks.public(t)


@router.post("/tasks/{task_id}/cancel")
def task_cancel(task_id: str, patientId: str = Query(min_length=1, max_length=32), doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    out = A.engine().cancel(doctor_ctx(doctor, patientId, db), task_id)
    if out is None:
        raise HTTPException(404, "Task not found")
    return out


@router.post("/files")
async def upload_file(patientId: str = Query(min_length=1, max_length=32), file: UploadFile = File(...),
                      doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    """A document the doctor brings to the visit. Stored encrypted under the doctor's own name; the patient does not see it
    and it is never added to the patient's thread by the agent (the doctor agent can read, summarise and compare it)."""
    ctx = doctor_ctx(doctor, patientId, db)
    A._limit(doctor.id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    return A.ingest_upload(db, ctx, data, file.filename)


@router.get("/files/{file_id}/content")
def download(file_id: str, patientId: str = Query(min_length=1, max_length=32), doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    ctx = doctor_ctx(doctor, patientId, db)
    A.purge_expired(db, ctx.patient_id)
    f = _doctor_file(db, doctor, ctx.patient_id, file_id)
    try:
        data = vault.get(f.storage_key, f.id, f.patient_id)
    except vault.VaultError:
        raise HTTPException(410, "That file can no longer be opened.")
    AgentAuditLogger().record(ctx, None, "files.download", "ok", target=f.id)
    db.commit()
    return Response(data, media_type=f.mime, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                                      "Content-Disposition": f'attachment; filename="{A._safe_name(f.display_name, "bin")}"'})


@router.get("/history")
def history(patientId: str = Query(min_length=1, max_length=32), limit: int = 20, doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    ctx = doctor_ctx(doctor, patientId, db)
    rows = db.scalars(select(AgentAudit).where(AgentAudit.actor_id == doctor.id, AgentAudit.patient_id == ctx.patient_id, AgentAudit.agent_type == "doctor")
                      .order_by(AgentAudit.created_at.desc()).limit(max(1, min(limit, 50))))
    return [{"tool": r.tool, "category": r.category, "level": r.level, "status": r.status, "confirmed": r.confirmed, "at": iso(r.created_at)} for r in rows]


@router.get("/tools")
def tools(doctor: User = Depends(current_doctor)):
    return [{"name": t["name"], "description": t["description"], "level": t["level"]} for t in REGISTRY.describe("doctor")]
