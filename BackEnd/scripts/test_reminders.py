"""Fake-clock tests for the reminder engine.

Run: cd BackEnd && ./venv/bin/python scripts/test_reminders.py -v
Uses an in-memory SQLite DB, so real data is never touched and nothing is sent.
"""
from __future__ import annotations

import sys
import unittest
from unittest import mock
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
        patcher = mock.patch.object(store, "_redis", None)  # tests never touch a real Redis, even when one is running
        patcher.start()
        self.addCleanup(patcher.stop)
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

    # ---- hourly "still to take" nudges
    def day(self, hhmm, sec=5):
        return at("2026-10-01", hhmm, sec)

    def test_nudge_every_hour_until_taken(self):
        self.tick(self.day("08:00"))                                   # the dose message
        self.assertEqual(self.tick(self.day("08:59", 50)).get("nudge"), 0)   # not an hour yet
        self.assertEqual(self.tick(self.day("09:00", 10)).get("nudge"), 1)
        self.assertEqual(self.tick(self.day("09:30")).get("nudge"), 0)       # only once per hour
        self.assertEqual(self.tick(self.day("10:01")).get("nudge"), 1)
        text = self.out.sent[-1][1]
        self.assertIn("Metformin 500 mg", text)
        self.assertIn("8:00 AM", text)
        self.assertIn("Still coming up today: Metformin 500 mg at 8:00 PM", text)  # what is left to have
        svc.mark_taken(self.Session(), PID, "metf_0800", "2026-10-01")
        self.assertEqual(self.tick(self.day("11:02")).get("nudge"), 0)       # taken: no more
        self.assertEqual(self.tick(self.day("12:05")).get("nudge"), 0)

    def test_one_message_lists_every_untaken_dose(self):
        with self.Session() as db:
            db.add(Medicine(id="stat", patient_id=PID, name="Atorvastatin", dose="10 mg", times=["08:00"], start_date="2026-09-01"))
            db.commit()
        self.tick(self.day("08:00"))
        self.out.sent.clear()
        self.assertEqual(self.tick(self.day("09:01")).get("nudge"), 1)
        mine = [t for c, t in self.out.sent if c == "1001"]
        self.assertEqual(len(mine), 1)
        self.assertIn("Atorvastatin", mine[0])
        self.assertIn("Metformin", mine[0])
        svc.mark_taken(self.Session(), PID, "metf_0800", "2026-10-01")
        self.out.sent.clear()
        self.assertEqual(self.tick(self.day("10:02")).get("nudge"), 1)
        mine = [t for c, t in self.out.sent if c == "1001"]
        self.assertNotIn("Metformin 500 mg (was", mine[0])                    # the taken one is dropped from the list
        self.assertIn("Atorvastatin", mine[0])

    def test_nudges_stop_after_the_limit(self):
        with self.Session() as db:
            db.query(Medicine).delete()
            db.add(Medicine(id="early", patient_id=PID, name="Thyronorm", dose="50 mcg", times=["06:00"], start_date="2026-09-01"))
            db.commit()
        self.tick(self.day("06:00"))
        sent = sum(self.tick(self.day(f"{h:02d}:02")).get("nudge", 0) for h in range(7, 22))
        self.assertEqual(sent, svc.MAX_NUDGES)
        with self.Session() as db:
            self.assertEqual(db.query(svc.SentDose).one().nudges, svc.MAX_NUDGES)

    def test_no_nudges_at_night(self):
        self.tick(self.day("20:00"))
        self.assertEqual(self.tick(self.day("22:05")).get("nudge", 0), 0)
        self.assertEqual(self.tick(at("2026-10-01", "23:30")).get("nudge", 0), 0)

    def test_failed_nudge_is_not_counted_and_retries(self):
        self.tick(self.day("08:00"))
        self.out.fail = True
        self.assertEqual(self.tick(self.day("09:01")).get("nudge"), 0)
        self.out.fail = False
        self.assertEqual(self.tick(self.day("09:02")).get("nudge"), 1)

    def test_stopped_medicine_or_ended_course_is_not_nudged(self):
        self.tick(self.day("08:00"))
        with self.Session() as db:
            db.get(Medicine, "metf").active = False
            db.commit()
        self.assertEqual(self.tick(self.day("09:01")).get("nudge"), 0)

    def test_no_telegram_chat_means_no_nudge(self):
        self.tick(self.day("08:00"))
        with self.Session() as db:
            db.get(ReminderSettings, PID).telegram_chat_id = None
            db.commit()
        self.out.sent.clear()
        self.tick(self.day("09:01"))
        self.assertEqual([c for c, _ in self.out.sent if c == "1001"], [])  # (the family chat has its own missed-dose notice)

    def test_yesterdays_untaken_dose_is_not_nudged_today(self):
        self.tick(at("2026-09-30", "20:00"))
        self.assertEqual(self.tick(at("2026-10-01", "07:00")).get("nudge", 0), 0)

    # ---- restart catch-up and bad data
    def test_dose_missed_during_a_restart_is_sent_late_but_only_within_20_minutes(self):
        self.assertEqual(self.tick(self.day("08:07"))["dose"], 1)       # server was down at 08:00
        self.assertEqual(self.tick(self.day("08:08"))["dose"], 0)       # and never twice
        store._memory.clear()
        with self.Session() as db:
            db.query(svc.SentDose).delete()
            db.commit()
        self.assertEqual(self.tick(self.day("08:25"))["dose"], 0)       # too late: no stale "time for" message

    def test_a_malformed_time_does_not_stop_other_reminders(self):
        with self.Session() as db:
            db.add(Medicine(id="bad", patient_id=PID, name="Odd", times=["8am", ""], start_date="2026-09-01"))
            db.commit()
        self.assertEqual(self.tick(self.day("08:00"))["dose"], 1)       # Metformin still goes out


if __name__ == "__main__":
    unittest.main()
