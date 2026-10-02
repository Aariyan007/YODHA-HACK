"""Tests for the danger checks, vitals parsing, lab rules and the AI-review guard.

In-memory SQLite. No network: Groq is never called (no key in the test env, and
the review tests call the guard functions directly).

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_risk.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("GROQ_API_KEY", None)
os.environ.pop("TELEGRAM_BOT_TOKEN", None)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ai import health_review
from app.database import Base
from app.labs import code_for_name, direction, lab_status, parse_range, slug, status_from_range
from app.models import Alert, Observation, Patient
from app.risk import assess, refresh_risk_alerts
from app.trends import check_trends
from app.vitals import from_extracted, from_text

PID = "p1"
TODAY = date(2026, 10, 2)


class Base_(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.addCleanup(self.db.close)
        self.db.add(Patient(id=PID, name="Test", phone="9000000003"))
        self.db.commit()

    def add(self, code, value, d="2026-10-02", name=None, unit=None):
        self.db.add(Observation(patient_id=PID, date=d, code=code, name=name or code, value=value, unit=unit))
        self.db.flush()

    def bp(self, s, d_, when="2026-10-02"):
        self.add("sbp", s, when, "Systolic BP", "mmHg")
        self.add("dbp", d_, when, "Diastolic BP", "mmHg")

    def risks(self):
        return assess(self.db, PID, TODAY)

    def keys(self):
        return {(r["key"], r["level"]) for r in self.risks()}


class BloodPressureTests(Base_):
    def test_normal_bp_has_no_risk(self):
        self.bp(118, 76)
        self.assertEqual(self.risks(), [])

    def test_levels(self):
        for (s, d), level in [((134, 82), "watch"), ((146, 88), "high"), ((182, 100), "emergency"), ((150, 121), "emergency")]:
            with self.subTest(bp=(s, d)):
                self.setUp()
                self.bp(s, d)
                r = self.risks()[0]
                self.assertEqual((r["key"], r["level"]), ("bp", level))
                self.assertIn(f"{s}/{d}", r["message"])  # real numbers, both of them

    def test_emergency_specialist_and_108(self):
        self.bp(190, 118)
        r = self.risks()[0]
        self.assertTrue(r["emergency"])
        self.assertEqual(r["specialist"], "Emergency")
        self.assertIn("108", r["message"])

    def test_old_crisis_reading_is_not_an_emergency(self):
        self.bp(190, 125, "2026-01-10")
        r = self.risks()[0]
        self.assertEqual(r["level"], "high")
        self.assertFalse(r["emergency"])
        self.assertIn("6 months old", r["message"])

    def test_newest_reading_wins(self):
        self.bp(170, 105, "2026-09-01")
        self.bp(122, 78, "2026-10-01")
        self.assertEqual(self.risks(), [])

    def test_low_bp(self):
        self.bp(84, 52)
        self.assertIn(("bp", "high"), self.keys())
        self.assertIn("low", self.risks()[0]["title"].lower())


class OtherDangerTests(Base_):
    def test_sugar_levels(self):
        self.add("fbs", 420)
        self.assertIn(("glucose_high", "emergency"), self.keys())

    def test_low_sugar_uses_newest_glucose_of_any_kind(self):
        self.add("ppbs", 260, "2026-09-30")
        self.add("rbs", 52, "2026-10-02")
        self.assertIn(("glucose_low", "emergency"), self.keys())
        self.assertNotIn("glucose_high", {k for k, _ in self.keys()})

    def test_kidney_potassium_oxygen(self):
        self.add("creatinine", 2.4)
        self.add("potassium", 6.3)
        self.add("spo2", 88)
        k = self.keys()
        self.assertIn(("creatinine", "high"), k)
        self.assertIn(("potassium", "emergency"), k)
        self.assertIn(("spo2_low", "emergency"), k)
        self.assertEqual(self.risks()[0]["level"], "emergency")  # worst first

    def test_one_risk_per_test_and_direction(self):
        self.add("hba1c", 9.6)
        self.assertEqual([r["level"] for r in self.risks() if r["key"] == "hba1c"], ["high"])

    def test_weight_change(self):
        self.add("weight", 70, "2026-08-01")
        self.add("weight", 64, "2026-10-01")
        self.assertIn(("weight_change", "watch"), self.keys())

    def test_rising_trend_dropped_when_same_test_is_already_high(self):
        for d, v in [("2026-01-01", 131), ("2026-04-01", 139), ("2026-08-01", 152)]:
            self.bp(v, 80, d)
        keys = {k for k, _ in self.keys()}
        self.assertIn("bp", keys)
        self.assertNotIn("rising_sbp", keys)

    def test_wording_never_prescribes(self):
        for code, v in [("fbs", 300), ("creatinine", 2.5), ("potassium", 6.5), ("ldl", 200), ("hb", 6.5), ("tsh", 12)]:
            self.add(code, v)
        self.bp(185, 121)
        for r in self.risks():
            text = r["message"].lower()
            for banned in ("you have ", "take ", "stop taking", "increase", "dose", "diagnos"):
                self.assertNotIn(banned, text, r["message"])


class AlertTests(Base_):
    def test_one_open_alert_per_risk_and_auto_resolve(self):
        self.bp(150, 95, "2026-09-01")
        refresh_risk_alerts(self.db, PID, TODAY)
        refresh_risk_alerts(self.db, PID, TODAY)
        rows = list(self.db.scalars(select(Alert).where(Alert.kind == "risk", Alert.resolved.is_(False))))
        self.assertEqual(len(rows), 1)
        self.bp(120, 78, "2026-10-01")
        refresh_risk_alerts(self.db, PID, TODAY)
        rows = list(self.db.scalars(select(Alert).where(Alert.kind == "risk", Alert.resolved.is_(False))))
        self.assertEqual(rows, [])

    def test_new_emergency_reported_once(self):
        self.bp(190, 124)
        _, em1 = refresh_risk_alerts(self.db, PID, TODAY)
        _, em2 = refresh_risk_alerts(self.db, PID, TODAY)
        self.assertEqual(len(em1), 1)
        self.assertEqual(em2, [])

    def test_bp_trend_is_one_alert_with_pairs(self):
        for d, (s, dd) in [("2026-01-01", (128, 80)), ("2026-04-01", (136, 86)), ("2026-08-01", (144, 92))]:
            self.bp(s, dd, d)
        out = check_trends(self.db, PID)
        self.assertEqual([a["title"] for a in out], ["Blood pressure is rising"])
        self.assertIn("128/80, 136/86, 144/92", out[0]["message"])


class VitalsAndLabsTests(unittest.TestCase):
    def test_from_extracted(self):
        got = {o["code"]: o["value"] for o in from_extracted({"bp": "150/96", "pulse": "88 bpm", "spo2": 97, "weight_kg": None, "temp_f": 38.5})}
        self.assertEqual(got, {"sbp": 150, "dbp": 96, "pulse": 88, "spo2": 97, "temp": 101.3})

    def test_from_extracted_drops_nonsense(self):
        self.assertEqual(from_extracted({"bp": "80/120"}), [])  # top must be bigger
        self.assertEqual(from_extracted({"pulse": 900}), [])

    def test_from_text_spoken(self):
        got = {o["code"]: o["value"] for o in from_text("Your BP is 182 by 121 today, pulse 104. Fasting sugar was 268. Oxygen 93")}
        self.assertEqual(got, {"sbp": 182, "dbp": 121, "pulse": 104, "fbs": 268, "spo2": 93})

    def test_from_text_ignores_doses(self):
        self.assertEqual(from_text("Add Tab Glycomet 500 mg BD to support sugar control. Pulse oximeter at home."), [])

    def test_code_for_name(self):
        for name, code in [("HbA1c (Glycated Haemoglobin)", "hba1c"), ("Fasting Blood Sugar", "fbs"), ("Post prandial glucose", "ppbs"),
                           ("Serum Creatinine", "creatinine"), ("S. Potassium", "potassium"), ("Hb", "hb"),
                           ("Platelet count", "platelets"), ("SGPT (ALT)", "sgpt"), ("Hematocrit", None), ("Salt", None)]:
            with self.subTest(name=name):
                self.assertEqual(code_for_name(name), code)

    def test_unknown_tests_get_distinct_codes(self):
        self.assertNotEqual(slug("Ferritin"), slug("Calcium"))
        self.assertTrue(slug("Ferritin").startswith("x_"))

    def test_printed_ranges(self):
        self.assertEqual(parse_range("70 - 110 mg/dL"), (70, 110))
        self.assertEqual(parse_range("<5.7"), (None, 5.7))
        self.assertEqual(parse_range("> 40"), (40, None))
        self.assertEqual(status_from_range(120, "70-110"), "watch")
        self.assertEqual(status_from_range(200, "70-110"), "alert")
        self.assertEqual(status_from_range(90, "70-110"), "good")
        self.assertEqual(lab_status("x_ferritin", 500, "30 - 300"), "alert")

    def test_direction(self):
        self.assertEqual(direction("hb", 8), "low")
        self.assertEqual(direction("ldl", 160), "high")
        self.assertIsNone(direction("ldl", 80))


class ReviewGuardTests(unittest.TestCase):
    FACTS = {"readings": [{"code": "sbp", "values": [["2026-03-01", 128], ["2026-10-01", 146]]}]}

    def test_numbers_must_come_from_the_record(self):
        allowed = health_review._allowed_numbers(self.FACTS)
        self.assertTrue(health_review._safe("Your BP went from 128 in March to 146 now.", allowed))
        self.assertFalse(health_review._safe("Your BP went from 128 to 171.", allowed))

    def test_banned_advice(self):
        allowed = health_review._allowed_numbers(self.FACTS)
        for bad in ("You have hypertension.", "Stop taking Telma.", "Increase the dose of Amlodipine.", "Take 10 mg at night."):
            with self.subTest(text=bad):
                self.assertFalse(health_review._safe(bad, allowed))

    def test_fallback_without_groq(self):
        series = [{"code": "sbp", "name": "Systolic BP", "unit": "mmHg", "points": [{"date": "2026-03-01", "value": 128}, {"date": "2026-10-01", "value": 146}]}]
        risks = [{"title": "High blood pressure", "level": "high"}]
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": ""}):  # a real key in .env must not make this call Groq
            out = health_review.review({}, series, [], [], risks)
        self.assertEqual(out["source"], "rules")
        self.assertEqual(out["points"][0]["kind"], "worse")
        self.assertIn("High blood pressure".lower(), out["headline"].lower())


if __name__ == "__main__":
    unittest.main()
