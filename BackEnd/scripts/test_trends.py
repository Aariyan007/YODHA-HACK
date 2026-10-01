"""Tests for the lab trend alert. In-memory SQLite, nothing real is touched.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_trends.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Alert, Observation, Patient
from app.trends import check_trends, rising_run

PID = "p1"


class TrendTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.addCleanup(self.db.close)
        self.db.add(Patient(id=PID, name="Test", phone="9000000002"))
        self.db.commit()

    def add(self, date, value, code="hba1c", name="HbA1c", loinc=None):
        self.db.add(Observation(patient_id=PID, date=date, code=code, name=name, value=value, unit="%", loinc=loinc))
        self.db.flush()

    def trend_alerts(self):
        return list(self.db.scalars(select(Alert).where(Alert.patient_id == PID, Alert.kind == "trend")))

    def test_rising_run(self):
        self.assertEqual(rising_run([9.1, 7.9, 7.4, 7.2, 7.8, 8.2]), [7.2, 7.8, 8.2])
        self.assertEqual(rising_run([7.0, 7.1, 7.6, 8.2]), [7.0, 7.1, 7.6, 8.2])
        self.assertEqual(rising_run([7.0, 7.0, 7.1]), [7.0, 7.1])
        self.assertEqual(rising_run([8.0, 7.0]), [7.0])

    def test_four_rising_tests_make_one_alert_with_real_numbers(self):
        for d, v in [("2025-01-01", 7.0), ("2025-06-01", 7.1), ("2025-12-01", 7.6), ("2026-06-01", 8.2)]:
            self.add(d, v)
        out = check_trends(self.db, PID)
        self.assertEqual(len(out), 1)
        a = self.trend_alerts()[0]
        self.assertEqual(a.message, "Your HbA1c has risen in each of your last 4 tests: 7, 7.1, 7.6, 8.2. Show this to your doctor.")
        self.assertEqual((a.kind, a.severity), ("trend", "high"))
        self.assertIsNotNone(a.message_ml)

    def test_wording_has_no_cause_or_treatment(self):
        for d, v in [("2025-01-01", 7.0), ("2025-06-01", 7.1), ("2025-12-01", 7.6)]:
            self.add(d, v)
        check_trends(self.db, PID)
        text = self.trend_alerts()[0].message.lower()
        for bad in ("because", "caused", "due to", "take ", "stop ", "increase your", "diagnos", "insulin", "dose"):
            self.assertNotIn(bad, text)

    def test_two_results_or_falling_or_flat_make_no_alert(self):
        self.add("2025-01-01", 7.0)
        self.add("2025-06-01", 7.5)
        self.assertEqual(check_trends(self.db, PID), [])
        self.add("2025-12-01", 7.5)  # flat, not higher
        self.assertEqual(check_trends(self.db, PID), [])
        self.assertEqual(self.trend_alerts(), [])

    def test_seed_style_falling_history_makes_none(self):
        for d, v in [("2024-11-08", 9.1), ("2025-03-12", 7.9), ("2025-12-10", 7.4), ("2026-03-05", 7.2)]:
            self.add(d, v)
        self.assertEqual(check_trends(self.db, PID), [])

    def test_second_check_updates_instead_of_duplicating(self):
        for d, v in [("2025-01-01", 7.0), ("2025-06-01", 7.1), ("2025-12-01", 7.6)]:
            self.add(d, v)
        check_trends(self.db, PID)
        check_trends(self.db, PID)
        self.assertEqual(len(self.trend_alerts()), 1)
        self.add("2026-06-01", 8.2)
        check_trends(self.db, PID)
        rows = self.trend_alerts()
        self.assertEqual(len(rows), 1)
        self.assertIn("last 4 tests", rows[0].message)

    def test_resolved_alert_is_not_reused(self):
        for d, v in [("2025-01-01", 7.0), ("2025-06-01", 7.1), ("2025-12-01", 7.6)]:
            self.add(d, v)
        check_trends(self.db, PID)
        self.trend_alerts()[0].resolved = True
        self.db.flush()
        check_trends(self.db, PID)
        self.assertEqual(len(self.trend_alerts()), 2)

    def test_matches_by_loinc_and_name_when_code_is_unknown(self):
        self.add("2025-01-01", 7.0, code="unknown", name="Glycated Hb", loinc="4548-4")
        self.add("2025-06-01", 7.1, code="hba1c", name="HbA1c")
        self.add("2025-12-01", 7.6, code="unknown", name="HbA1c")
        self.assertEqual(len(check_trends(self.db, PID)), 1)

    def test_tests_where_higher_is_good_are_ignored(self):
        for d, v in [("2025-01-01", 40), ("2025-06-01", 44), ("2025-12-01", 50)]:
            self.add(d, v, code="hdl", name="HDL cholesterol")
        self.assertEqual(check_trends(self.db, PID), [])


if __name__ == "__main__":
    unittest.main()
