"""Tests for the FHIR bundle import. In-memory SQLite, Groq stubbed.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_fhir.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import fhir_import
from app.database import Base
from app.models import Alert, Document, Medicine, Observation, Patient

PID = "p1"
SAMPLE = json.loads((ROOT / "samples" / "aster_medcity_bundle.json").read_text())


class FhirTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            db.add(Patient(id=PID, name="Ammini", phone="9000000003", conditions=[], allergies=["Sulfa drugs"]))
            db.add(Medicine(patient_id=PID, name="Telma 40", generic="telmisartan", dose="40 mg", active=True))
            db.commit()
        for p in (mock.patch.object(fhir_import, "SessionLocal", self.Session),
                  mock.patch.object(fhir_import, "summarise", lambda facts, alerts: {"en": "Summary.", "ml": "സംഗ്രഹം."})):
            p.start()
            self.addCleanup(p.stop)

    def run_import(self, bundle):
        return fhir_import.import_bundle(PID, json.dumps(bundle).encode())

    def count(self, model):
        with self.Session() as db:
            return db.scalar(select(func.count()).select_from(model).where(model.patient_id == PID))

    def test_sample_maps_to_our_records(self):
        out = self.run_import(SAMPLE)
        self.assertEqual(out["imported"], {"timelineCards": 2, "observations": 3, "conditions": 1, "medicines": 1})
        self.assertEqual(out["total"], 7)
        self.assertIn("Imported 7 records", out["message"])
        with self.Session() as db:
            obs = {o.code: o for o in db.scalars(select(Observation).where(Observation.patient_id == PID))}
            self.assertEqual(obs["hba1c"].loinc, "4548-4")
            self.assertEqual((obs["sbp"].value, obs["dbp"].value), (138, 88))
            self.assertEqual(obs["sbp"].loinc, "8480-6")
            cond = db.get(Patient, PID).conditions
            self.assertEqual((cond[0]["name"], cond[0]["icd10"]), ("Vitamin D deficiency", "E55.9"))
            types = sorted(d.type for d in db.scalars(select(Document).where(Document.patient_id == PID)))
            self.assertEqual(types, ["lab", "visit"])
            med = db.scalar(select(Medicine).where(Medicine.name.like("Telmisartan%")))
            self.assertEqual((med.generic, med.times), ("telmisartan", ["08:00"]))
            doc = db.scalar(select(Document).where(Document.type == "visit"))
            self.assertEqual((doc.summary, doc.summary_ml, doc.origin), ("Summary.", "സംഗ്രഹം.", "fhir"))

    def test_same_checks_as_uploads_run(self):
        out = self.run_import(SAMPLE)
        kinds = {a["kind"] for a in out["alerts"]}
        self.assertIn("duplicate", kinds)  # Telmisartan vs the Telma 40 already taken
        with self.Session() as db:
            sbp = db.scalar(select(Observation).where(Observation.code == "sbp"))
        status = next(i["status"] for r in out["records"] for i in r["items"] if i.get("code") == "sbp")
        self.assertEqual(status, "watch")  # 138 is in the watch band for systolic BP

    def test_importing_twice_adds_nothing(self):
        self.run_import(SAMPLE)
        before = [self.count(m) for m in (Document, Observation, Medicine, Alert)]
        again = self.run_import(SAMPLE)
        self.assertTrue(again["alreadyImported"])
        self.assertEqual(again["total"], 0)
        self.assertEqual(again["duplicates"], 2)
        self.assertEqual([self.count(m) for m in (Document, Observation, Medicine, Alert)], before)
        with self.Session() as db:
            self.assertEqual(len(db.get(Patient, PID).conditions), 1)

    def test_unknown_resource_types_are_skipped(self):
        b = json.loads(json.dumps(SAMPLE))
        b["entry"].append({"resource": {"resourceType": "Coverage", "id": "c1"}})
        b["entry"].append({"resource": {"resourceType": "ImagingStudy", "id": "i1"}})
        b["entry"].append({"nonsense": True})
        out = self.run_import(b)
        self.assertEqual(out["total"], 7)
        self.assertEqual(out["ignored"], [{"type": "Coverage", "count": 1}, {"type": "ImagingStudy", "count": 1}])

    def test_rejects_bad_input_in_plain_language(self):
        for raw, needle in [
            (b"not json at all", "not valid JSON"),
            (b'{"resourceType": "Patient"}', "not a FHIR Bundle"),
            (b'[1, 2]', "not a FHIR Bundle"),
            (b'{"resourceType": "Bundle", "entry": []}', "no records"),
        ]:
            with self.assertRaises(fhir_import.FhirImportError) as cm:
                fhir_import.import_bundle(PID, raw)
            self.assertIn(needle, str(cm.exception))
        with self.assertRaises(fhir_import.FhirImportError) as cm:
            fhir_import.import_bundle(PID, b" " * (fhir_import.MAX_BYTES + 1))
        self.assertEqual(cm.exception.status, 413)

    def test_bundle_with_nothing_useful_imports_nothing(self):
        out = self.run_import({"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Coverage"}}]})
        self.assertEqual(out["total"], 0)
        self.assertIn("Nothing in this file", out["message"])

    def test_completed_medicine_is_saved_inactive_and_not_checked(self):
        b = json.loads(json.dumps(SAMPLE))
        b["entry"][-1]["resource"]["status"] = "completed"
        out = self.run_import(b)
        self.assertNotIn("duplicate", {a["kind"] for a in out["alerts"]})
        with self.Session() as db:
            med = db.scalar(select(Medicine).where(Medicine.name.like("Telmisartan%")))
            self.assertFalse(med.active)

    def test_import_raises_trend_alert_from_stored_observations(self):
        with self.Session() as db:
            for d, v in [("2026-01-01", 7.0), ("2026-03-01", 7.2)]:
                db.add(Observation(patient_id=PID, date=d, code="hba1c", name="HbA1c", value=v, unit="%"))
            db.commit()
        out = self.run_import(SAMPLE)  # 7.6 on 2026-06-10 makes 7.0, 7.2, 7.6
        trend = [a for a in out["alerts"] if a["kind"] == "trend"]
        self.assertEqual(len(trend), 1)
        self.assertIn("7, 7.2, 7.6", trend[0]["message"])


if __name__ == "__main__":
    unittest.main()
