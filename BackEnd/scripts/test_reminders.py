"""Fake-clock tests for the reminder engine.

Run: cd BackEnd && ./venv/bin/python scripts/test_reminders.py -v
Uses an in-memory SQLite DB, so real data is never touched and nothing is sent.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import reminder_service as svc
from app import store
from app.database import Base
from app.models import Document, Medicine, Patient, ReminderSettings

IST = svc.IST
PID = "p1"


def at(day: str, hhmm: str, sec: int = 0) -> datetime:
    y, mo, d = (int(x) for x in day.split("-"))
    h, mi = (int(x) for x in hhmm.split(":"))
    return datetime(y, mo, d, h, mi, sec, tzinfo=IST)


class Outbox:
    """Fake Telegram sender. Records (chat_id, text); can be told to fail."""
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.fail = False

    def __call__(self, chat_id, text):
        if self.fail:
            return False, "boom"
        self.sent.append((chat_id, text))
        return True, None


class ReminderTests(unittest.TestCase):
    def setUp(self):
        store._memory.clear()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.out = Outbox()
        with self.Session() as db:
            db.add(Patient(id=PID, name="Ammini Varghese", phone="9000000001"))
            db.add(ReminderSettings(
                patient_id=PID, enabled=True, channel_telegram=True, channel_family=True,
                telegram_chat_id="1001", family_chat_id="2002", family_name="Joel", missed_after_minutes=60))
            db.add(Medicine(id="metf", patient_id=PID, name="Metformin", dose="500 mg", times=["08:00", "20:00"],
                            instructions="After food", start_date="2026-09-01"))
            db.add(Medicine(id="clar", patient_id=PID, name="Clarithromycin", dose="500 mg", times=["20:00"],
                            start_date="2026-09-24", duration_days=7))
            db.commit()

    def tick(self, now):
        return svc.run_tick(now, send=self.out, session_factory=self.Session)

    # 1. sent once at the right minute, not twice, not at other minutes
    def test_dose_sent_once_at_right_minute(self):
        self.assertEqual(self.tick(at("2026-10-01", "07:59", 55))["dose"], 0)
        self.assertEqual(self.tick(at("2026-10-01", "08:00", 5))["dose"], 1)
        self.assertEqual(self.tick(at("2026-10-01", "08:00", 35))["dose"], 0)
        self.assertEqual(self.tick(at("2026-10-01", "08:01", 5))["dose"], 0)
        self.assertEqual(len(self.out.sent), 1)
        chat, text = self.out.sent[0]
        self.assertEqual(chat, "1001")
        self.assertEqual(text, "Time for Metformin 500 mg. Take it after food. Open MediThread and tap Taken.")

    def test_label_does_not_repeat_dose_already_in_name(self):
        with self.Session() as db:
            db.add(Medicine(id="gly", patient_id=PID, name="Glycomet 500", dose="500 mg", times=["06:00"],
                            start_date="2026-09-01"))
            db.commit()
        self.tick(at("2026-10-01", "06:00", 5))
        self.assertIn("Time for Glycomet 500.", self.out.sent[0][1])

    def test_same_dose_sends_again_next_day(self):
        self.tick(at("2026-10-01", "08:00", 5))
        self.assertEqual(self.tick(at("2026-10-02", "08:00", 5))["dose"], 1)

    # 2. course dates
    def test_course_start_and_end_respected(self):
        self.assertEqual(self.tick(at("2026-09-23", "20:00"))["dose"], 1)  # only Metformin; Clarithromycin not started
        self.out.sent.clear()
        self.assertEqual(self.tick(at("2026-09-30", "20:00"))["dose"], 2)  # day 7 of the course: both
        self.out.sent.clear()
        self.assertEqual(self.tick(at("2026-10-01", "20:00"))["dose"], 1)  # course over: Metformin only
        self.assertNotIn("Clarithromycin", self.out.sent[0][1])

    # 3. missed alert only after N minutes, once
    def test_missed_only_after_n_minutes_and_once(self):
        self.tick(at("2026-10-01", "08:00", 5))
        self.assertEqual(self.tick(at("2026-10-01", "08:59"))["missed"], 0)
        self.assertEqual(self.tick(at("2026-10-01", "09:01"))["missed"], 1)
        self.assertEqual(self.tick(at("2026-10-01", "09:02"))["missed"], 0)
        chat, text = self.out.sent[-1]
        self.assertEqual(chat, "2002")
        self.assertEqual(text, "Joel, Ammini has not marked Metformin 500 mg as taken since 8:00 AM.")

    def test_missed_falls_back_to_same_chat(self):
        with self.Session() as db:
            db.get(ReminderSettings, PID).family_chat_id = None
            db.commit()
        self.tick(at("2026-10-01", "08:00", 5))
        self.tick(at("2026-10-01", "09:05"))
        self.assertEqual(self.out.sent[-1][0], "1001")

    def test_missed_needs_family_channel(self):
        with self.Session() as db:
            db.get(ReminderSettings, PID).channel_family = False
            db.commit()
        self.tick(at("2026-10-01", "08:00", 5))
        self.assertEqual(self.tick(at("2026-10-01", "10:00"))["missed"], 0)

    # 4. marking taken cancels the missed alert
    def test_taken_cancels_missed(self):
        self.tick(at("2026-10-01", "08:00", 5))
        with self.Session() as db:
            svc.mark_taken(db, PID, "metf_0800", "2026-10-01")
        self.assertEqual(self.tick(at("2026-10-01", "09:30"))["missed"], 0)

    # 5. restart must not resend (in-memory store wiped, DB row remains)
    def test_restart_does_not_resend(self):
        self.assertEqual(self.tick(at("2026-10-01", "08:00", 5))["dose"], 1)
        store._memory.clear()
        self.assertEqual(self.tick(at("2026-10-01", "08:00", 40))["dose"], 0)

    # failure handling
    def test_failed_send_is_not_recorded_and_retries(self):
        self.out.fail = True
        self.assertEqual(self.tick(at("2026-10-01", "08:00", 5))["dose"], 0)
        self.out.fail = False
        self.assertEqual(self.tick(at("2026-10-01", "08:00", 35))["dose"], 1)

    def test_disabled_or_channel_off_sends_nothing(self):
        with self.Session() as db:
            db.get(ReminderSettings, PID).enabled = False
            db.commit()
        self.assertEqual(self.tick(at("2026-10-01", "08:00"))["dose"], 0)
        with self.Session() as db:
            s = db.get(ReminderSettings, PID)
            s.enabled, s.channel_telegram = True, False
            db.commit()
        self.assertEqual(self.tick(at("2026-10-01", "08:00"))["dose"], 0)

    # 6. refill + appointment: the day before, once
    def test_refill_day_before_once(self):
        with self.Session() as db:
            db.get(Medicine, "metf").refill_due = "2026-10-05"
            db.commit()
        self.assertEqual(self.tick(at("2026-10-03", "10:00"))["refill"], 0)
        self.assertEqual(self.tick(at("2026-10-04", "08:30"))["refill"], 0)  # before 09:00
        self.assertEqual(self.tick(at("2026-10-04", "10:00"))["refill"], 1)
        self.assertEqual(self.tick(at("2026-10-04", "10:01"))["refill"], 0)

    def test_appointment_day_before_once(self):
        with self.Session() as db:
            db.add(Document(id="d1", patient_id=PID, date="2026-09-28", type="prescription", title="x",
                            followup="Review after 5 days"))
            db.commit()
        self.assertEqual(self.tick(at("2026-10-02", "10:00"))["appointment"], 1)  # visit is 2026-10-03
        self.assertEqual(self.tick(at("2026-10-02", "11:00"))["appointment"], 0)


if __name__ == "__main__":
    unittest.main()
