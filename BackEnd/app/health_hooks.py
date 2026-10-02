"""What runs after any new health data is saved (upload, import, visit, home reading, seed).

One place so every path gets the same checks:
  1. trend alerts (app/trends.py)
  2. danger checks over the whole record (app/risk.py)
  3. a Telegram message for a NEW emergency, to the patient's own chat and the family chat

Telegram goes only to chats saved in this patient's reminder settings, never to the
server default, so one patient's news never reaches another patient's phone.
"""
from __future__ import annotations

from threading import Thread

from sqlalchemy.orm import Session

from ai import telegram
from .models import Patient, ReminderSettings
from .risk import refresh_risk_alerts
from .trends import check_trends


def patient_chats(db: Session, patient_id: str, family: bool = False) -> list[str]:
    """Telegram chats this patient has turned on. family=True adds the family chat."""
    s = db.get(ReminderSettings, patient_id)
    if s is None or not s.channel_telegram:
        return []
    chats = [s.telegram_chat_id] if s.telegram_chat_id else []
    if family and s.channel_family and s.family_chat_id and s.family_chat_id not in chats:
        chats.append(s.family_chat_id)
    return chats


def send_later(chats: list[str], message: str) -> None:
    """Fire-and-forget so a slow Telegram never holds up an HTTP response."""
    if not chats or not telegram.ready():
        return

    def run():
        for chat in chats:
            telegram.send_to(chat, message)

    Thread(target=run, daemon=True).start()


def notify_patient(db: Session, patient_id: str, message: str, family: bool = False) -> None:
    send_later(patient_chats(db, patient_id, family), message)


def after_new_data(db: Session, patient_id: str) -> list[dict]:
    """Run trend + risk checks. Returns the trend alerts touched (for upload results). Does not commit."""
    touched = check_trends(db, patient_id)
    _risks, emergencies = refresh_risk_alerts(db, patient_id)
    if emergencies:
        patient = db.get(Patient, patient_id)
        who = patient.name if patient and patient.name else "The patient"
        lines = [f"MediThread urgent: {who}"] + [f"- {r['title']}: {r['message']}" for r in emergencies]
        notify_patient(db, patient_id, "\n".join(lines), family=True)
    return touched
