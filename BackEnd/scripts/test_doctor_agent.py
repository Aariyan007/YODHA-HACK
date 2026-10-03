"""Doctor Agent: link checks, brief, changes since visit, conflicts, missing info, draft + approve, files, PDF.
In-memory SQLite, no network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_doctor_agent.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

import test_agent_files as base
from ai import consultation as consult_ai, visit_classify
from app.models import (Alert, AgentAudit, AgentFile, CareLink, Consultation, Document, Medicine, Observation, Patient, User)
from app.routers import consultations as C

SOAP = {"subjective": {"text": "Fatigue for two weeks.", "source_lines": [1]}, "objective": {"text": "BP 150/90.", "source_lines": [2]},
        "assessment": {"text": "Doctor noted possible poor control.", "source_lines": [3]}, "plan": {"text": "Review in 2 weeks.", "source_lines": [4]}}


class DoctorBase(base.ExtractBase):
    def setUp(self):
        super().setUp()
        for target, name, value in ((consult_ai, "_chat_json", lambda *a, **k: None), (consult_ai, "final_soap", lambda lines: {k: dict(v) for k, v in SOAP.items()}),
                                    (visit_classify, "classify", lambda lines, names: None), (C, "notify_patient", lambda *a, **k: None)):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        r = self.c.post("/api/auth/register", json={"role": "doctor", "name": "Dr Rao", "email": "rao@example.com", "password": base.PW})
        self.hd = {"Authorization": "Bearer " + r.json()["token"]}
        r = self.c.post("/api/auth/register", json={"role": "doctor", "name": "Dr Other", "email": "other@example.com", "password": base.PW})
        self.hd2 = {"Authorization": "Bearer " + r.json()["token"]}
        with self.Session() as db:
            self.pid = db.scalar(select(Patient).where(Patient.name == "one")).id
            self.pid2 = db.scalar(select(Patient).where(Patient.name == "two")).id
        code = self.c.post("/api/care/invite", headers=self.h1).json()["code"]
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": code}, headers=self.hd).status_code, 200)

    def seed(self):
        with self.Session() as db:
            p = db.get(Patient, self.pid)
            p.conditions, p.allergies = [{"name": "Type 2 diabetes"}, {"name": "Hypertension"}], ["Penicillin"]
            db.add_all([
                Document(id="v1", patient_id=self.pid, date="2026-03-01", type="visit", title="Clinic visit", followup=None),
                Document(id="l1", patient_id=self.pid, date="2026-02-20", type="lab", title="Old lab"),
                Document(id="l2", patient_id=self.pid, date="2026-09-10", type="lab", title="New lab"),
                Observation(patient_id=self.pid, document_id="l1", date="2026-02-20", code="hba1c", name="HbA1c", value=7.2, unit="%"),
                Observation(patient_id=self.pid, document_id="l2", date="2026-09-10", code="hba1c", name="HbA1c", value=8.4, unit="%"),
                Medicine(patient_id=self.pid, document_id="v1", name="Metformin", dose="500 mg", times=["08:00"], start_date="2026-03-01"),
                Medicine(patient_id=self.pid, document_id="l2", name="Metformin", dose="850 mg", times=["08:00"], start_date="2026-09-10"),
                Medicine(patient_id=self.pid, document_id="l2", name="Amoxicillin", dose="500 mg", times=["09:00"], start_date="2026-09-10"),
                # another patient's data that must never leak
                Observation(patient_id=self.pid2, date="2026-09-11", code="hba1c", name="HbA1c", value=13.3, unit="%"),
            ])
            db.commit()

    def d(self, text, pid=None, h=None, fid=None, conv=None):
        r = self.c.post("/api/doctor-agent/chat", json={"text": text, "patientId": pid or self.pid, "fileId": fid, "conversationId": conv}, headers=h or self.hd)
        if r.status_code != 200:
            return r
        return base.ExtractBase._R(r, self.c, h or self.hd) if False else self._finish(r, h or self.hd)

    def _finish(self, r, h):
        j = r.json()
        if j.get("status") == "running":
            t = self.c.get(f"/api/doctor-agent/tasks/{j['taskId']}", headers=h).json()
            j = {**t["result"], "status": t["status"], "taskId": t["taskId"], "intent": t["intent"], "conversationId": j["conversationId"]}
        return type("R", (), {"status_code": r.status_code, "json": lambda self_: j})()

    def confirm(self, j, approve=True, pid=None, h=None):
        r = self.c.post("/api/doctor-agent/confirm", json={"id": j["confirmation"]["id"], "patientId": pid or self.pid, "approve": approve}, headers=h or self.hd)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class AccessTests(DoctorBase):
    def test_link_required_and_patient_ids_not_probeable(self):
        self.assertEqual(self.d("brief", pid=self.pid2).status_code, 404)           # not linked
        self.assertEqual(self.d("brief", pid="nope").status_code, 404)              # does not exist: same answer
        self.assertEqual(self.d("brief", h=self.hd2).status_code, 404)              # another doctor, no link
        self.assertEqual(self.d("brief").status_code, 200)

    def test_roles_do_not_cross(self):
        self.assertEqual(self.c.post("/api/doctor-agent/chat", json={"text": "hi", "patientId": self.pid}, headers=self.h1).status_code, 401)
        self.assertEqual(self.c.post("/api/agent/chat", json={"text": "hi"}, headers=self.hd).status_code, 401)

    def test_revoke_cuts_the_doctor_off_at_once(self):
        self.assertEqual(self.d("brief").status_code, 200)
        link = self.c.get("/api/care/doctors", headers=self.h1).json()[0]["linkId"]
        self.assertEqual(self.c.delete(f"/api/care/doctors/{link}", headers=self.h1).status_code, 200)
        self.assertEqual(self.d("brief").status_code, 404)

    def test_doctor_agent_has_no_patient_only_tools(self):
        names = {t["name"] for t in self.c.get("/api/doctor-agent/tools", headers=self.hd).json()}
        self.assertFalse(names & {"sharing.create", "sharing.revoke", "careloop.mark_taken", "health.log_reading", "records.add_from_file", "care.revoke_doctor"})
        self.assertTrue({"doctor.brief", "consult.draft_from_notes", "consult.approve_draft"} <= names)

    def test_actions_are_audited_as_doctor_agent(self):
        self.d("brief")
        with self.Session() as db:
            row = db.scalar(select(AgentAudit).where(AgentAudit.tool == "doctor.brief"))
        self.assertEqual((row.agent_type, row.actor_role, row.patient_id), ("doctor", "doctor", self.pid))


class InsightTests(DoctorBase):
    def test_changes_since_last_visit(self):
        self.seed()
        j = self.d("what changed since the last visit").json()
        self.assertIn("2026-03-01", j["blocks"][0]["text"])
        cmp_ = next(b for b in j["blocks"] if b["type"] == "comparison")
        self.assertEqual((cmp_["before"]["value"], cmp_["after"]["value"]), (7.2, 8.4))
        self.assertIn("New lab", str(j["blocks"]))
        self.assertNotIn("13.3", str(j))

    def test_conflicts_are_flagged_for_verification_never_resolved(self):
        self.seed()
        j = self.d("any conflicts in the record").json()
        titles = [b["title"] for b in j["blocks"] if b["type"] == "warning"]
        self.assertTrue(all(t.startswith("Please verify") for t in titles))
        joined = " ".join(titles)
        self.assertIn("different doses", joined)
        self.assertIn("allergy", joined.lower())
        txt = " ".join(b["text"] for b in j["blocks"] if b["type"] == "warning")
        self.assertIn("500 mg", txt)
        self.assertIn("850 mg", txt)          # both sides shown
        self.assertNotIn("recommend", txt.lower())

    def test_missing_info_hints(self):
        self.seed()
        j = self.d("what am I missing").json()
        text = " ".join(b["text"] for b in j["blocks"])
        self.assertIn("kidney test", text)
        self.assertIn("blood pressure", text)
        self.assertIn("No weight", text)
        self.assertIn("follow-up", text)

    def test_brief_has_the_essentials(self):
        self.seed()
        j = self.d("pre-visit brief").json()
        kinds = [b["type"] for b in j["blocks"]]
        self.assertIn("medication", kinds)
        self.assertIn("metric", kinds)
        self.assertIn("Penicillin", str(j["blocks"]))
        self.assertNotIn("13.3", str(j))


class DraftTests(DoctorBase):
    NOTES = "Patient has fatigue for two weeks. BP is 150 by 90. Possible poor control. Review in two weeks."

    def test_draft_is_not_saved_until_approved(self):
        j = self.d("draft a note: " + self.NOTES).json()
        self.assertEqual(j["status"], "completed", j)
        self.assertIn("NOT saved", j["blocks"][0]["text"])
        self.assertIn("Fatigue for two weeks", str(j["blocks"]))
        with self.Session() as db:
            self.assertEqual(db.scalars(select(Document).where(Document.patient_id == self.pid)).all(), [])
            self.assertEqual(db.scalar(select(Consultation)).status, "draft")
        a = self.d("approve the draft", conv=j["conversationId"]).json()
        self.assertEqual(a["status"], "waiting_for_confirmation")
        self.assertIn("Subjective", str(a["confirmation"]["preview"]))
        with self.Session() as db:
            self.assertEqual(db.scalars(select(Document).where(Document.patient_id == self.pid)).all(), [])  # still nothing
        done = self.confirm(a)
        self.assertEqual(done["status"], "completed")
        with self.Session() as db:
            self.assertEqual(db.scalar(select(Consultation)).status, "approved")
            self.assertEqual(len(db.scalars(select(Document).where(Document.patient_id == self.pid, Document.type == "visit")).all()), 1)

    def test_declined_approval_saves_nothing(self):
        j = self.d("draft a note: " + self.NOTES).json()
        a = self.d("approve the draft", conv=j["conversationId"]).json()
        self.assertEqual(self.confirm(a, approve=False)["status"], "cancelled")
        with self.Session() as db:
            self.assertEqual(db.scalar(select(Consultation)).status, "draft")
            self.assertEqual(db.scalars(select(Document).where(Document.patient_id == self.pid)).all(), [])

    def test_approve_without_a_draft_asks_first(self):
        j = self.d("approve the note").json()
        self.assertEqual(j["steps"], [])
        self.assertIn("no draft", j["blocks"][0]["text"])

    def test_another_doctor_cannot_approve_this_draft(self):
        j = self.d("draft a note: " + self.NOTES).json()
        with self.Session() as db:
            cid = db.scalar(select(Consultation)).id
        from app.agent.context import AgentContext
        from app.agent.executor import AgentExecutor
        with self.Session() as db:
            do = db.scalar(select(User).where(User.email == "other@example.com"))
            db.add(CareLink(patient_id=self.pid, doctor_user_id=do.id))
            db.commit()
            ctx = AgentContext(db=db, role="doctor", actor_id=do.id, actor_name="Dr Other", patient_id=self.pid)
            r = AgentExecutor().run(ctx, "consult.approve_draft", {"consultationId": cid})
        self.assertEqual(r.status, "failed")  # the preview refuses: it is not their draft


class PatientOnlyNotes(DoctorBase):
    """"Handwriting unclear" is a note to the patient about their own upload. Doctors and share links never see it."""
    def setUp(self):
        super().setUp()
        with self.Session() as db:
            db.add(Alert(patient_id=self.pid, severity="medium", kind="handwriting", title="Handwriting unclear: Zerodol SP", message="I could not read this."))
            db.add(Alert(patient_id=self.pid, severity="high", kind="lab", title="Platelets are very low", message="Low."))
            db.commit()

    def titles(self, alerts):
        return {a["title"] for a in alerts}

    def test_patient_still_sees_both(self):
        self.assertEqual(self.titles(self.c.get("/api/patients/me/alerts", headers=self.h1).json()),
                         {"Handwriting unclear: Zerodol SP", "Platelets are very low"})

    def test_share_link_snapshot_hides_it(self):
        tok = self.c.post("/api/shares", json={"hours": 2, "scope": "full"}, headers=self.h1).json()["token"]
        got = self.titles(self.c.get(f"/api/shares/{tok}/snapshot").json()["alerts"])
        self.assertEqual(got, {"Platelets are very low"})

    def test_linked_doctor_view_hides_it(self):
        got = self.titles(self.c.get(f"/api/doctor/patients/{self.pid}/snapshot", headers=self.hd).json()["alerts"])
        self.assertEqual(got, {"Platelets are very low"})

    def test_doctor_agent_hides_it(self):
        from app.agent.context import AgentContext
        from app.agent.executor import AgentExecutor
        with self.Session() as db:
            ctx = AgentContext(db=db, role="doctor", actor_id=db.scalar(select(User).where(User.email == "rao@example.com")).id,
                               actor_name="Dr Rao", patient_id=self.pid)
            for tool, args in (("health.alerts", {}), ("doctor.changes_since_visit", {"since": "2020-01-01"}), ("doctor.brief", {})):
                r = AgentExecutor().run(ctx, tool, args)
                self.assertTrue(r.ok, tool)
                self.assertNotIn("Handwriting", str(r.blocks), tool)
                self.assertNotIn("Zerodol", str(r.blocks), tool)

    def test_pdfs_that_get_handed_over_hide_it(self):
        import io
        from pypdf import PdfReader
        for who, h, text in (("patient", self.h1, "make a pdf summary"),):
            j = self.chat(text, None, h).json()
            fid = next(b for b in j["blocks"] if b["type"] == "pdf")["fileId"]
            data = self.c.get(f"/api/agent/files/{fid}/content", headers=h).content
            pdf_text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
            self.assertIn("Platelets are very low", pdf_text)
            self.assertNotIn("Zerodol", pdf_text)


class DoctorFilesAndPdf(DoctorBase):
    def up_d(self, data):
        return self.c.post(f"/api/doctor-agent/files?patientId={self.pid}", files={"file": ("x.pdf", data, "application/pdf")}, headers=self.hd)

    def test_doctor_file_is_private_to_the_doctor_and_readable_by_the_agent(self):
        j = self.up_d(base.text_pdf(base.LAB2)).json()
        self.assertEqual(self.c.get("/api/agent/files", headers=self.h1).json(), [])                       # the patient does not see it
        self.assertEqual(self.c.get(f"/api/agent/files/{j['fileId']}/content", headers=self.h1).status_code, 404)
        self.assertEqual(self.c.get(f"/api/doctor-agent/files/{j['fileId']}/content?patientId={self.pid}", headers=self.hd2).status_code, 404)
        r = self.d("summarise this file", fid=j["fileId"]).json()
        self.assertEqual(r["status"], "completed")
        self.assertIn("lab report", str(r["blocks"]))
        steps = [x["tool"] for x in self.d("add it to the thread", fid=j["fileId"]).json()["steps"]]
        self.assertNotIn("records.add_from_file", steps)  # no write tool for doctors
        with self.Session() as db:
            self.assertEqual(db.scalars(select(Document).where(Document.patient_id == self.pid)).all(), [])

    def test_doctor_upload_needs_a_link(self):
        r = self.c.post(f"/api/doctor-agent/files?patientId={self.pid2}", files={"file": ("x.pdf", base.text_pdf(base.LAB), "application/pdf")}, headers=self.hd)
        self.assertEqual(r.status_code, 404)

    def test_doctor_pdf(self):
        self.seed()
        j = self.d("make a pdf").json()
        pdf = next(b for b in j["blocks"] if b["type"] == "pdf")
        self.assertEqual(pdf["kind"], "doctor_brief")
        data = self.c.get(f"/api/doctor-agent/files/{pdf['fileId']}/content?patientId={self.pid}", headers=self.hd).content
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertEqual(self.c.get(f"/api/agent/files/{pdf['fileId']}/content", headers=self.h1).status_code, 404)
        from pypdf import PdfReader
        import io
        text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
        for needle in ("Pre-visit brief", "different doses", "Penicillin", "not medical advice"):
            self.assertIn(needle, text)
        self.assertNotIn("13.3", text)

    def test_patient_cannot_make_a_doctor_pdf(self):
        from app.agent.context import AgentContext
        from app.agent.executor import AgentExecutor
        with self.Session() as db:
            ctx = AgentContext(db=db, role="patient", actor_id=self.pid, actor_name="one", patient_id=self.pid)
            self.assertEqual(AgentExecutor().run(ctx, "pdf.generate", {"kind": "doctor_brief"}).status, "failed")


if __name__ == "__main__":
    unittest.main()
