"""Agent API. The agent is an orchestration layer over existing services: it adds no data endpoints of its own
(documents, shares and reminders keep their routes). Patient agent here; the doctor agent has its own router."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store
from ..agent.context import AgentContext
from ..agent.engine import AgentEngine
from ..agent.registry import REGISTRY
from ..auth import current_patient
from ..database import get_db
from ..models import AgentAudit, Patient
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


@router.post("/chat")
def chat(body: ChatBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    _limit(patient.id)
    ctx = patient_ctx(patient, db, body.conversationId)
    out = engine().chat(ctx, body.text.strip())
    db.commit()  # audit rows
    return out


@router.post("/confirm")
def confirm(body: ConfirmBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    ctx = patient_ctx(patient, db)
    out = engine().confirm(ctx, body.id, body.approve)
    db.commit()
    return out


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
