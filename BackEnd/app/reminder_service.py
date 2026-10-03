"""Reminder engine: dose due, missed dose, refill and appointment messages.

`run_tick(now, send)` is a plain function with a clock and sender you can pass in, so tests can drive it with a fake
clock. The APScheduler job in `start()` just calls it every 30 seconds with the real IST time.

Logging: never log tokens, chat ids or message text, except a medicine name.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai import reminders as reminders_mod
from ai import telegram
from . import store
from .database import SessionLocal
from .models import Document, Medicine, Patient, ReminderSettings, SentDose, SentNotice, new_id

IST = ZoneInfo("Asia/Kolkata")
TICK_SECONDS = 30
NUDGE_EVERY = timedelta(minutes=60)   # "you have not marked it taken" reminder, hourly
MAX_NUDGES = 5                        # per dose, then it stops (the family missed-dose notice is separate)
NUDGE_UNTIL_HOUR = 22                 # no nudges at night (IST)
CATCH_UP = timedelta(minutes=20)      # a dose whose minute was missed (server restart) is still sent for 20 minutes
REFILL_HOUR = 9  # refill / appointment notices go out from 09:00 IST

Sender = Callable[[str | None, str], tuple[bool, str | None]]


# ---------- small helpers ----------

def demo_mode() -> bool:
    return (os.getenv("DEMO_MODE") or "").strip().lower() == "true"


def now_ist() -> datetime:
    return datetime.now(IST)


def dose_key(medicine_id: str, clock: str, day: str) -> str:
    return f"{medicine_id}@{clock}@{day}"


def reminder_key(medicine_id: str, clock: str) -> str:
    """Key used by the patient reminders list (`build_reminders`)."""
    return f"{medicine_id}_{clock.replace(':', '')}"


def _fmt_12h(clock: str) -> str:
    hh, mm = (int(x) for x in clock.split(":"))
    suffix = "AM" if hh < 12 else "PM"
    return f"{(hh % 12) or 12}:{mm:02d} {suffix}"


def med_label(m: Medicine) -> str:
    name = (m.name or "your medicine").strip()
    dose = (m.dose or "").strip()
    number = "".join(ch for ch in dose.split()[0] if ch.isdigit() or ch == ".") if dose else ""
    if dose and dose.lower() not in name.lower() and not (number and number in name):
        return f"{name} {dose}"
    return name


def in_course(m: Medicine, today: date) -> bool:
    """True if `today` is inside the medicine's course (start to start+N-1)."""
    if not m.active:
        return False
    if m.start_date:
        try:
            start = date.fromisoformat(m.start_date)
        except ValueError:
            start = None
        if start is not None:
            if today < start:
                return False
            if m.duration_days:
                if today > start + timedelta(days=m.duration_days - 1):
                    return False
    return True


def dose_message(m: Medicine) -> str:
    ins = (m.instructions or "").strip().rstrip(".")
    how = f" Take it {ins[0].lower() + ins[1:]}." if ins else ""
    return f"Time for {med_label(m)}.{how} Open MediThread and tap Taken."


def missed_message(settings: ReminderSettings, patient: Patient, m: Medicine, clock: str) -> str:
    who = (settings.family_name or "there").strip()
    first = (patient.name or "The patient").split()[0]
    return f"{who}, {first} has not marked {med_label(m)} as taken since {_fmt_12h(clock)}."


def is_taken(db: Session, row: SentDose) -> bool:
    if row.taken:
        return True
    return store.get_value(f"taken:{row.patient_id}:{row.date}:{reminder_key(row.medicine_id, row.clock)}") is not None


def mark_taken(db: Session, patient_id: str, key: str, day: str) -> None:
    """Record a dose as taken and cancel its missed-dose check."""
    store.set_value(f"taken:{patient_id}:{day}:{key}", datetime.now(IST).isoformat(), ttl=3 * 86400)
    med_id, _, hhmm = key.rpartition("_")
    if len(hhmm) != 4:
        return
    clock = f"{hhmm[:2]}:{hhmm[2:]}"
    row = db.scalar(select(SentDose).where(
        SentDose.patient_id == patient_id, SentDose.medicine_id == med_id,
        SentDose.clock == clock, SentDose.date == day))
    if row is not None and not row.taken:
        row.taken = True
        row.taken_at = datetime.now(IST)
        db.commit()


def _already_sent(db: Session, med_id: str, clock: str, day: str) -> bool:
    k = dose_key(med_id, clock, day)
    if store.get_value(f"dose:{k}") is not None:
        return True
    return db.scalar(select(SentDose.id).where(
        SentDose.medicine_id == med_id, SentDose.clock == clock, SentDose.date == day)) is not None


def _record_sent(db: Session, patient_id: str, med_id: str, clock: str, day: str, at: datetime) -> SentDose:
    row = SentDose(patient_id=patient_id, medicine_id=med_id, clock=clock, date=day, sent_at=at)
    db.add(row)
    db.commit()
    store.set_value(f"dose:{dose_key(med_id, clock, day)}", "1", ttl=2 * 86400)
    return row


# ---------- the tick ----------

def run_tick(now: datetime, send: Sender | None = None, session_factory=SessionLocal) -> dict:
    """Runs one scheduler pass at `now` (tz aware, IST). Returns counts for tests and logs."""
    send = send or telegram.send_to
    out = {"dose": 0, "missed": 0, "refill": 0, "appointment": 0}
    if not telegram.ready() and send is telegram.send_to:
        return out

    today = now.date()
    day = today.isoformat()
    clock_now = now.strftime("%H:%M")

    with session_factory() as db:
        enabled = db.scalars(select(ReminderSettings).where(ReminderSettings.enabled.is_(True)))
        for settings in list(enabled):
            patient = db.get(Patient, settings.patient_id)
            if patient is None:
                continue
            meds = list(db.scalars(select(Medicine).where(
                Medicine.patient_id == patient.id, Medicine.active.is_(True))))

            # 1. dose due
            if settings.channel_telegram and settings.telegram_chat_id:
                for m in meds:
                    if not in_course(m, today):
                        continue
                    for clock in (m.times or []):
                        try:
                            due_at = datetime.combine(today, datetime.strptime(clock, "%H:%M").time(), tzinfo=IST)
                        except ValueError:
                            continue  # a malformed time on a medicine must not stop everyone else's reminders
                        if not (timedelta(0) <= now - due_at < CATCH_UP) or _already_sent(db, m.id, clock, day):
                            continue
                        ok, _err = send(settings.telegram_chat_id, dose_message(m))
                        if ok:
                            _record_sent(db, patient.id, m.id, clock, day, now)
                            out["dose"] += 1
                        else:
                            print(f"[reminders] dose send failed for {m.name}")

            # 1b. hourly "still to take" nudge: one message per patient listing every dose not marked taken
            if settings.channel_telegram and settings.telegram_chat_id and now.hour < NUDGE_UNTIL_HOUR:
                out["nudge"] = out.get("nudge", 0) + _nudge(db, settings, patient, meds, today, now, send)

            # 2. missed dose -> family
            if settings.channel_family:
                target = settings.family_chat_id or settings.telegram_chat_id
                limit = timedelta(minutes=settings.missed_after_minutes or 60)
                rows = db.scalars(select(SentDose).where(
                    SentDose.patient_id == patient.id, SentDose.date == day,
                    SentDose.missed_notified.is_(False)))
                for row in list(rows):
                    if is_taken(db, row):
                        continue
                    sent_at = row.sent_at if row.sent_at.tzinfo else row.sent_at.replace(tzinfo=IST)
                    if now - sent_at < limit or not target:
                        continue
                    m = db.get(Medicine, row.medicine_id)
                    if m is None:
                        continue
                    ok, _err = send(target, missed_message(settings, patient, m, row.clock))
                    if ok:
                        row.missed_notified = True
                        db.commit()
                        out["missed"] += 1
                    else:
                        print(f"[reminders] missed-dose send failed for {m.name}")

            # 3. refill + appointment (once, from 09:00 IST, the day before)
            if settings.channel_telegram and settings.telegram_chat_id and now.hour >= REFILL_HOUR:
                tomorrow = today + timedelta(days=1)
                for m in meds:
                    if m.refill_due == tomorrow.isoformat():
                        if _notice_once(db, patient.id, f"refill:{m.id}:{m.refill_due}"):
                            ok, _ = send(settings.telegram_chat_id,
                                         f"{med_label(m)} needs a refill tomorrow. Please arrange it today.")
                            out["refill"] += 1 if ok else 0
                            if not ok:
                                _unmark_notice(db, f"refill:{m.id}:{m.refill_due}")
                for d in db.scalars(select(Document).where(
                        Document.patient_id == patient.id, Document.followup.is_not(None))):
                    due = appointment_date(d)
                    if due == tomorrow:
                        key = f"appt:{d.id}:{due.isoformat()}"
                        if _notice_once(db, patient.id, key):
                            ok, _ = send(settings.telegram_chat_id,
                                         "You have a follow-up visit tomorrow. Please keep your reports ready.")
                            out["appointment"] += 1 if ok else 0
                            if not ok:
                                _unmark_notice(db, key)
    return out


def _nudge(db: Session, settings: ReminderSettings, patient: Patient, meds: list[Medicine], today: date, now: datetime, send: Sender) -> int:
    """Hourly reminder for doses already announced today and not marked taken. Stops on its own: once taken, after
    MAX_NUDGES, when the medicine is stopped or its course ends, and never at night.
    """
    by_id = {m.id: m for m in meds}
    due: list[tuple[SentDose, Medicine]] = []
    for row in db.scalars(select(SentDose).where(SentDose.patient_id == patient.id, SentDose.date == today.isoformat())):
        m = by_id.get(row.medicine_id)
        if m is None or not in_course(m, today) or is_taken(db, row) or (row.nudges or 0) >= MAX_NUDGES:
            continue
        last = row.last_nudge_at or row.sent_at
        last = last if last.tzinfo else last.replace(tzinfo=IST)
        if now - last >= NUDGE_EVERY:
            due.append((row, m))
    if not due:
        return 0
    due.sort(key=lambda x: x[0].clock)
    lines = [f"- {med_label(m)} (was due {_fmt_12h(r.clock)})" for r, m in due]
    pending = _pending_later(db, patient.id, meds, today, now)
    text = "Reminder: these are not marked as taken yet:\n" + "\n".join(lines)
    if pending:
        text += "\nStill coming up today: " + ", ".join(pending) + "."
    text += "\nIf you already took them, tap Taken in MediThread and I will stop reminding you."
    claimed = []
    for r, _m in due:  # claim first, so two scheduler passes can never both send
        r.nudges = (r.nudges or 0) + 1
        r.last_nudge_at = now
        claimed.append(r)
    db.commit()
    ok, _err = send(settings.telegram_chat_id, text)
    if not ok:
        for r in claimed:
            r.nudges = max(0, (r.nudges or 1) - 1)
            r.last_nudge_at = None
        db.commit()
        print("[reminders] nudge send failed")
        return 0
    return 1


def _pending_later(db: Session, patient_id: str, meds: list[Medicine], today: date, now: datetime) -> list[str]:
    """Doses later today that haven't been announced yet, as 'Name at 9:00 PM'."""
    sent = {(r.medicine_id, r.clock) for r in db.scalars(select(SentDose).where(SentDose.patient_id == patient_id, SentDose.date == today.isoformat()))}
    out = []
    for m in meds:
        if not in_course(m, today):
            continue
        for clock in m.times or []:
            if clock > now.strftime("%H:%M") and (m.id, clock) not in sent:
                out.append((clock, f"{med_label(m)} at {_fmt_12h(clock)}"))
    return [t for _, t in sorted(out)]


def appointment_date(doc: Document) -> date | None:
    """Follow-up date = document date + N days from the follow-up text (default 7)."""
    if not doc.followup or not doc.date:
        return None
    try:
        base = date.fromisoformat(doc.date)
    except ValueError:
        return None
    days = reminders_mod.parse_duration_days(None, doc.followup) or 7
    return base + timedelta(days=days)


def _notice_once(db: Session, patient_id: str, key: str) -> bool:
    """Claim a once-only notice. True if this call claimed it."""
    if db.get(SentNotice, key) is not None:
        return False
    db.add(SentNotice(key=key, patient_id=patient_id))
    db.commit()
    return True


def _unmark_notice(db: Session, key: str) -> None:
    row = db.get(SentNotice, key)
    if row is not None:
        db.delete(row)
        db.commit()


# ---------- demo helpers ----------

def next_due_dose(db: Session, patient_id: str, now: datetime) -> tuple[Medicine, str] | None:
    """Next upcoming (medicine, clock) for today (wraps around to the earliest clock)."""
    today = now.date()
    cands: list[tuple[str, Medicine]] = []
    for m in db.scalars(select(Medicine).where(Medicine.patient_id == patient_id, Medicine.active.is_(True))):
        if in_course(m, today):
            cands.extend((c, m) for c in (m.times or []))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    nxt = next((c for c in cands if c[0] >= now.strftime("%H:%M")), cands[0])
    return nxt[1], nxt[0]


def fire_reminder_now(patient_id: str, now: datetime | None = None, send: Sender | None = None) -> dict:
    now = now or now_ist()
    send = send or telegram.send_to
    with SessionLocal() as db:
        s = db.get(ReminderSettings, patient_id)
        if s is None or not s.telegram_chat_id:
            return {"sent": False, "error": "Save a Telegram chat ID first."}
        pair = next_due_dose(db, patient_id, now)
        if pair is None:
            return {"sent": False, "error": "No active medicines with dose times."}
        m, clock = pair
        msg = dose_message(m)
        ok, err = send(s.telegram_chat_id, msg)
        if not ok:
            return {"sent": False, "error": err}
        day = now.date().isoformat()
        if not _already_sent(db, m.id, clock, day):
            _record_sent(db, patient_id, m.id, clock, day, now)
        return {"sent": True, "kind": "dose", "medicine": m.name, "clock": clock, "message": msg}


def fire_missed_now(patient_id: str, now: datetime | None = None, send: Sender | None = None) -> dict:
    now = now or now_ist()
    send = send or telegram.send_to
    with SessionLocal() as db:
        s = db.get(ReminderSettings, patient_id)
        patient = db.get(Patient, patient_id)
        target = (s.family_chat_id or s.telegram_chat_id) if s else None
        if s is None or not target:
            return {"sent": False, "error": "Save a Telegram chat ID first."}
        day = now.date().isoformat()
        row = db.scalar(select(SentDose).where(
            SentDose.patient_id == patient_id, SentDose.date == day, SentDose.taken.is_(False)
        ).order_by(SentDose.sent_at.desc()))
        if row is not None:
            m, clock = db.get(Medicine, row.medicine_id), row.clock
        else:
            pair = next_due_dose(db, patient_id, now)
            if pair is None:
                return {"sent": False, "error": "No active medicines with dose times."}
            m, clock = pair
        msg = missed_message(s, patient, m, clock)
        ok, err = send(target, msg)
        if not ok:
            return {"sent": False, "error": err}
        if row is not None:
            row.missed_notified = True
            db.commit()
        return {"sent": True, "kind": "missed", "medicine": m.name, "clock": clock, "message": msg}


# ---------- APScheduler wiring ----------

_scheduler = None


def _job() -> None:
    try:
        run_tick(now_ist())
    except Exception as e:  # never let the scheduler die
        print(f"[reminders] tick failed: {type(e).__name__}")


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    if not telegram.ready():
        print("[reminders] TELEGRAM_BOT_TOKEN missing: scheduler runs but sends nothing.")
    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler = BackgroundScheduler(timezone=IST)
    _scheduler.add_job(_job, "interval", seconds=TICK_SECONDS, id="reminder_tick",
                       max_instances=1, coalesce=True, misfire_grace_time=20)
    _scheduler.start()
    print(f"[reminders] scheduler started (every {TICK_SECONDS}s, IST)")


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
