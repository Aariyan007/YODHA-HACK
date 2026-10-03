"""Write actions (L3) end to end: preview, confirmation, verification, audit, secrets, L4. In-memory SQLite, no network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_agent_writes.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

import test_agent_files as base
from ai import pipeline
from app import store
from app.agent.planner import AgentPlanner
from app.agent.llm import NullLLM
from app.agent.registry import REGISTRY
from app.models import (Alert, AccessLog, AgentAudit, AgentFile, AgentTask, CareLink, Document, Medicine, Observation, Patient, ShareLink, User)


class Writes(base.ExtractBase):
    def setUp(self):
        super().setUp()
        for target, name, value in ((pipeline, "SessionLocal", self.Session),
                                    (pipeline, "summarise", lambda doc, alerts: {"en": "Summary EN", "ml": "Summary ML"}),
                                    (pipeline, "notify_patient", lambda *a, **k: None)):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        with self.Session() as db:
            self.pid = db.scalar(select(Patient).where(Patient.name == "one")).id
            self.pid2 = db.scalar(select(Patient).where(Patient.name == "two")).id

    # helpers
    def say(self, text, fid=None, h=None):
        return self.chat(text, fid, h or self.h1).json()

    def confirm(self, r, approve=True, h=None):
        cid = r["confirmation"]["id"]
        resp = self.c.post("/api/agent/confirm", json={"id": cid, "approve": approve}, headers=h or self.h1)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def count(self, model, **where):
        with self.Session() as db:
            return len(db.scalars(select(model).filter_by(**where)).all())


class AddFromFileTests(Writes):
    def test_add_requires_confirmation_then_writes_only_verified_values(self):
        fid = self.up(base.text_pdf(base.LAB2)).json()["fileId"]
        self.say("what is in this file", fid)
        r = self.say("add it to my thread", fid)
        self.assertEqual(r["status"], "waiting_for_confirmation")
        self.assertEqual(self.count(Document), 0)  # nothing yet
        labels = [p["label"] for p in r["confirmation"]["preview"]]
        values = " ".join(p["value"] for p in r["confirmation"]["preview"])
        self.assertIn("HbA1c 8.2", values)
        self.assertIn("Left out (not in the text)", labels)
        done = self.confirm(r)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(self.count(Document, patient_id=self.pid), 1)
        with self.Session() as db:
            codes = {o.code for o in db.scalars(select(Observation).where(Observation.patient_id == self.pid))}
            f = db.get(AgentFile, fid)
        self.assertEqual(codes, {"hba1c", "creatinine"})  # the invented potassium never reached the record
        self.assertEqual(f.status, "confirmed")
        self.assertTrue(any(b["type"] == "timeline_event" for b in done["blocks"]))

    def test_decline_writes_nothing(self):
        fid = self.up(base.text_pdf(base.LAB2)).json()["fileId"]
        self.say("what is in this file", fid)
        r = self.say("add it to my thread", fid)
        done = self.confirm(r, approve=False)
        self.assertEqual(done["status"], "cancelled")
        self.assertEqual(self.count(Document), 0)

    def test_cannot_add_twice(self):
        fid = self.up(base.text_pdf(base.LAB2)).json()["fileId"]
        self.say("what is in this file", fid)
        self.confirm(self.say("add it to my thread", fid))
        r = self.say("add it to my thread", fid)
        self.assertEqual(r["status"], "failed")
        self.assertEqual(self.count(Document), 1)

    def test_unknown_type_must_be_answered_first(self):
        doc = dict(base.LAB_DOC, type="prescription")  # disagrees with the words -> type unknown
        with mock.patch.object(base.ftools, "EXTRACTOR", lambda d, m: doc):
            fid = self.up(base.text_pdf(base.LAB2)).json()["fileId"]
            self.say("what is in this file", fid)
        r = self.say("add it to my thread", fid)
        self.assertEqual(r["status"], "failed")
        self.assertIn("what kind of document", str(r["blocks"]))
        self.c.post(f"/api/agent/files/{fid}/type", json={"type": "lab"}, headers=self.h1)
        self.assertEqual(self.say("add it to my thread", fid)["status"], "waiting_for_confirmation")


class SharingTests(Writes):
    def test_qr_is_real_and_token_never_in_task_audit_or_response(self):
        r = self.say("make a qr for my labs")
        self.assertEqual(r["status"], "waiting_for_confirmation")
        self.assertEqual(self.count(ShareLink), 0)
        done = self.confirm(r)
        act = next(b for b in done["blocks"] if b["type"] == "action")
        self.assertEqual((act["kind"], act["scope"]), ("show_qr", "labs"))
        with self.Session() as db:
            link = db.scalar(select(ShareLink).where(ShareLink.patient_id == self.pid))
            self.assertIsNotNone(link)
            dump = str(done) + str([t.steps for t in db.scalars(select(AgentTask))]) + str([(a.detail, a.target, a.result_ref) for a in db.scalars(select(AgentAudit))])
        self.assertNotIn(link.token, dump)
        qr = self.c.get(f"/api/agent/shares/{act['ref']}", headers=self.h1).json()
        self.assertEqual(qr["url"], f"/share/{link.token}")
        self.assertEqual(self.c.get(f"/api/agent/shares/{act['ref']}", headers=self.h2).status_code, 404)  # not for anyone else
        # and the link really opens the snapshot, limited to labs
        snap = self.c.get(f"/api/shares/{link.token}/snapshot").json()
        self.assertEqual(snap["scope"], "labs")

    def test_revoke_all_kills_the_link_and_is_verified(self):
        self.confirm(self.say("create a share link"))
        with self.Session() as db:
            tok = db.scalar(select(ShareLink)).token
        self.assertEqual(self.c.get(f"/api/shares/{tok}/snapshot").status_code, 200)
        done = self.confirm(self.say("stop sharing"))
        self.assertEqual(done["status"], "completed")
        self.assertEqual(self.c.get(f"/api/shares/{tok}/snapshot").status_code, 404)

    def test_cannot_revoke_someone_elses_link_by_ref(self):
        self.confirm(self.say("create a share link"))
        refs = [b["key"] for b in self.say("who can see my records")["blocks"] if b["type"] == "care_item"]
        self.assertEqual(len(refs), 1)
        from app.agent.context import AgentContext
        from app.agent.executor import AgentExecutor
        with self.Session() as db:
            ctx = AgentContext(db=db, role="patient", actor_id=self.pid2, actor_name="two", patient_id=self.pid2)
            r = AgentExecutor().run(ctx, "sharing.revoke", {"ref": refs[0]})
        self.assertEqual(r.status, "failed")
        self.assertEqual(self.count(ShareLink), 1)

    def test_remove_doctor_access(self):
        with self.Session() as db:
            db.add(User(id="du", email="d@x.com", password_hash="x", role="doctor", name="Dr Rao"))
            db.add(CareLink(patient_id=self.pid, doctor_user_id="du"))
            db.commit()
        r = self.say("remove Dr Rao access")
        self.assertEqual(r["status"], "waiting_for_confirmation")
        self.assertIn("Dr Rao", str(r["confirmation"]["preview"]))
        self.confirm(r)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(CareLink)).status, "revoked")


class DoseAndReadingTests(Writes):
    def setUp(self):
        super().setUp()
        with self.Session() as db:
            db.add(Medicine(patient_id=self.pid, name="Metformin", dose="500 mg", times=["08:00"]))
            db.add(Medicine(patient_id=self.pid2, name="Metformin", dose="500 mg", times=["08:00"]))
            db.commit()

    def test_mark_taken(self):
        r = self.say("mark metformin as taken")
        self.assertIn("Metformin", str(r["confirmation"]["preview"]))
        self.assertEqual(self.confirm(r)["status"], "completed")
        self.assertTrue(next(b for b in self.say("what is due today")["blocks"] if b["type"] == "care_item")["taken"])
        self.assertEqual(self.say("mark metformin as taken")["status"], "failed")  # nothing left to mark
        with self.Session() as db:  # the other patient's dose is untouched
            from app.routers.patients import build_reminders, today
            self.assertFalse(build_reminders(db, self.pid2, today())[0]["taken"])

    def test_log_reading_shows_numbers_and_writes_after_yes(self):
        r = self.say("log my bp 128/82 and pulse 74")
        vals = " ".join(p["value"] for p in r["confirmation"]["preview"])
        self.assertIn("128", vals)
        self.assertIn("82", vals)
        self.assertEqual(self.count(Observation, patient_id=self.pid), 0)
        self.assertEqual(self.confirm(r)["status"], "completed")
        with self.Session() as db:
            got = {o.code: o.value for o in db.scalars(select(Observation).where(Observation.patient_id == self.pid))}
        self.assertEqual(got, {"sbp": 128.0, "dbp": 82.0, "pulse": 74.0})

    def test_half_a_bp_is_refused_not_guessed(self):
        r = self.say("log my bp 128")
        self.assertIn(r["status"], ("failed", "completed"))
        self.assertEqual(self.count(Observation, patient_id=self.pid), 0)

    def test_asking_about_a_reading_does_not_write(self):
        self.say("what was my bp")
        self.assertEqual(self.count(Observation), 0)


class UnclearHandwriting(Writes):
    def setUp(self):
        super().setUp()
        with self.Session() as db:
            for name in ("Chymoral Forte", "Volini Gel"):
                db.add(Alert(patient_id=self.pid, severity="medium", kind="handwriting", title=f"Handwriting unclear: {name}",
                             message="I could not read this medicine name with confidence."))
            db.commit()

    def meds(self):
        with self.Session() as db:
            return sorted(m.name for m in db.scalars(select(Medicine).where(Medicine.patient_id == self.pid)))

    def open_unclear(self):
        with self.Session() as db:
            return db.scalars(select(Alert).where(Alert.patient_id == self.pid, Alert.kind == "handwriting", Alert.resolved.is_(False))).all()

    def test_confirming_all_adds_them_after_a_yes_and_clears_the_alerts(self):
        r = self.say("those unclear handwriting medicines are correct, add them")
        self.assertEqual(r["status"], "waiting_for_confirmation")
        vals = " ".join(p["value"] for p in r["confirmation"]["preview"])
        self.assertIn("Chymoral Forte", vals)
        self.assertIn("Volini Gel", vals)
        self.assertEqual(self.meds(), [])                         # nothing yet
        self.assertEqual(self.confirm(r)["status"], "completed")
        self.assertEqual(self.meds(), ["Chymoral Forte", "Volini Gel"])
        self.assertEqual(self.open_unclear(), [])

    def test_only_the_named_one(self):
        from app.agent.context import AgentContext
        from app.agent.executor import AgentExecutor
        with self.Session() as db:
            ctx = AgentContext(db=db, role="patient", actor_id=self.pid, actor_name="one", patient_id=self.pid)
            r = AgentExecutor().run(ctx, "medications.confirm_unclear", {"names": ["volini"]})
            self.assertEqual(r.status, "needs_confirmation")
            cid = r.confirmation["id"]
            self.assertTrue(AgentExecutor().confirm(ctx, cid, True).ok)
            db.commit()
        self.assertEqual(self.meds(), ["Volini Gel"])
        self.assertEqual([a.title for a in self.open_unclear()], ["Handwriting unclear: Chymoral Forte"])

    def test_unknown_name_and_nothing_waiting_are_refused(self):
        from app.agent.context import AgentContext
        from app.agent.executor import AgentExecutor
        with self.Session() as db:
            ctx = AgentContext(db=db, role="patient", actor_id=self.pid, actor_name="one", patient_id=self.pid)
            self.assertEqual(AgentExecutor().run(ctx, "medications.confirm_unclear", {"names": ["Zorbexil"]}).status, "failed")
        with self.Session() as db:
            for a in db.scalars(select(Alert)):
                a.resolved = True
            db.commit()
        r = self.say("those unclear medicines are correct, add them")
        self.assertEqual(r["status"], "failed")
        self.assertEqual(self.meds(), [])

    def test_other_patients_unclear_medicines_are_not_touched(self):
        with self.Session() as db:
            db.add(Alert(patient_id=self.pid2, severity="medium", kind="handwriting", title="Handwriting unclear: Secretol", message="x"))
            db.commit()
        self.confirm(self.say("those unclear handwriting medicines are correct, add them"))
        with self.Session() as db:
            self.assertEqual(db.scalars(select(Medicine).where(Medicine.patient_id == self.pid2)).all(), [])
            self.assertFalse(db.scalar(select(Alert).where(Alert.title == "Handwriting unclear: Secretol")).resolved)

    def test_allergy_clash_is_surfaced_in_the_confirmation(self):
        with self.Session() as db:
            db.get(Patient, self.pid).allergies = ["Penicillin"]
            db.add(Alert(patient_id=self.pid, severity="medium", kind="handwriting", title="Handwriting unclear: Amoxicillin", message="x"))
            db.commit()
        r = self.say("those unclear handwriting medicines are correct, add them")
        self.assertTrue(any(p["label"].startswith("Warning") for p in r["confirmation"]["preview"]), r["confirmation"]["preview"])


class SafetyTests(Writes):
    def test_medicine_changes_are_explained_never_done(self):
        with self.Session() as db:
            db.add(Medicine(patient_id=self.pid, name="Metformin", dose="500 mg", times=["08:00"]))
            db.commit()
        for text in ("stop my metformin", "should I double my dose", "increase the dose of metformin"):
            r = self.say(text)
            self.assertIn("cannot start, stop or change", r["blocks"][0]["text"], text)
            self.assertEqual([s["tool"] for s in r["steps"]], ["medications.list"])
        with self.Session() as db:
            self.assertTrue(db.scalar(select(Medicine)).active)

    def test_writes_are_audited_with_confirmation_flag(self):
        self.confirm(self.say("create a share link"))
        with self.Session() as db:
            rows = db.scalars(select(AgentAudit).where(AgentAudit.tool == "sharing.create").order_by(AgentAudit.created_at)).all()
        self.assertEqual([(r.status, r.confirmed) for r in rows], [("needs_confirmation", False), ("ok", True)])

    def test_planner_rules_for_writes(self):
        p = AgentPlanner(REGISTRY, NullLLM())
        cases = {"make a qr code for my doctor": "sharing.create", "stop sharing": "sharing.revoke", "who can see my records": "sharing.active",
                 "log bp 120/80": "health.log_reading", "mark telma as taken": "careloop.mark_taken", "remove dr. rao access": "care.revoke_doctor"}
        for text, tool in cases.items():
            self.assertEqual(p.plan("patient", text).steps[0].tool, tool, text)


if __name__ == "__main__":
    unittest.main()
