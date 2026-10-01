"""Reminder settings, Telegram test, taken-marking, and demo helpers (Phase 5)."""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai import telegram
from .. import reminder_service as svc
from ..auth import current_patient
from ..database import get_db
from ..models import Medicine, Patient, ReminderSettings

router = APIRouter(prefix="/api", tags=["reminders"])

CHAT_ID_RE = re.compile(r"^-?\d{5,20}$")


class Channels(BaseModel):
    phone: bool = False
    telegram: bool = False
    family: bool = False


class SettingsBody(BaseModel):
    remindersEnabled: bool = False
    channels: Channels = Channels()
    telegramChatId: str | None = Field(default=None, max_length=40)
    familyChatId: str | None = Field(default=None, max_length=40)
    familyName: str | None = Field(default=None, max_length=60)
    missedAfterMinutes: int = Field(default=60, ge=1, le=1440)


def _clean_chat_id(value: str | None, label: str) -> str | None:
    v = (value or "").strip()
    if not v:
        return None
    if not CHAT_ID_RE.match(v):
        raise HTTPException(400, f"{label} should be a number like 123456789.")
    return v


def _get_or_create(db: Session, patient_id: str) -> ReminderSettings:
    row = db.get(ReminderSettings, patient_id)
    if row is None:
        row = ReminderSettings(patient_id=patient_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def settings_out(s: ReminderSettings) -> dict:
    return {
        "remindersEnabled": s.enabled,
        "channels": {"phone": s.channel_phone, "telegram": s.channel_telegram, "family": s.channel_family},
        "telegramChatId": s.telegram_chat_id,
        "familyChatId": s.family_chat_id,
        "familyName": s.family_name,
        "missedAfterMinutes": s.missed_after_minutes,
        "telegramReady": telegram.ready(),
        "demoMode": svc.demo_mode(),
    }


@router.get("/reminders/settings")
def get_settings(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    return settings_out(_get_or_create(db, patient.id))


@router.put("/reminders/settings")
def put_settings(body: SettingsBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    s = _get_or_create(db, patient.id)
    s.enabled = body.remindersEnabled
    s.channel_phone = body.channels.phone
    s.channel_telegram = body.channels.telegram
    s.channel_family = body.channels.family
    s.telegram_chat_id = _clean_chat_id(body.telegramChatId, "Telegram chat ID")
    s.family_chat_id = _clean_chat_id(body.familyChatId, "Family chat ID")
    s.family_name = (body.familyName or "").strip() or None
    s.missed_after_minutes = body.missedAfterMinutes
    s.updated_at = datetime.now(svc.IST)
    db.commit()
    db.refresh(s)
    return settings_out(s)


@router.post("/reminders/telegram/test")
def telegram_test(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    s = _get_or_create(db, patient.id)
    ok, err = telegram.send_to(s.telegram_chat_id, "MediThread is connected")
    if not ok:
        raise HTTPException(400, err or "Could not send the test message.")
    return {"ok": True}


@router.post("/reminders/{key}/taken")
def reminder_taken(key: str, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    from .patients import build_reminders, today
    day = today()
    if key not in {r["key"] for r in build_reminders(db, patient.id, day)}:
        raise HTTPException(404, "Reminder not found")
    svc.mark_taken(db, patient.id, key, day)
    return {"key": key, "date": day, "taken": True}


# ---------- demo helpers (DEMO_MODE=true only) ----------

def _require_demo() -> None:
    if not svc.demo_mode():
        raise HTTPException(404, "Not found")


@router.post("/demo/fire-reminder")
def fire_reminder(patient: Patient = Depends(current_patient)):
    _require_demo()
    return svc.fire_reminder_now(patient.id)


@router.post("/demo/fire-missed")
def fire_missed(patient: Patient = Depends(current_patient)):
    _require_demo()
    return svc.fire_missed_now(patient.id)
