"""Tests for email/password login, roles, invite codes and doctor access. In-memory SQLite, no network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_auth.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import store
from app.auth import hash_password, verify_password
from app.database import Base, get_db
from app.main import app
from app.models import InviteCode

PW = "correct horse 9"


class AuthTests(unittest.TestCase):
    def setUp(self):
        store._memory.clear()
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        def override():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override
        self.addCleanup(app.dependency_overrides.clear)
        self.c = TestClient(app)
        env = mock.patch.dict(os.environ, {"DEMO_MODE": "false"})
        env.start()
        self.addCleanup(env.stop)

    # ---- helpers
    def register(self, role="patient", email=None, name=None, **extra):
        email = email or f"{role}{len(self.c.cookies)}{os.urandom(2).hex()}@example.com"
        r = self.c.post("/api/auth/register", json={"role": role, "name": name or role.title() + " Person", "email": email, "password": PW, **extra})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        return email, {"Authorization": f"Bearer {d['token']}"}, d["profile"]

    def invite(self, h):
        r = self.c.post("/api/care/invite", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["code"]

    # ---- passwords
    def test_hash_and_verify(self):
        h = hash_password(PW)
        self.assertTrue(verify_password(PW, h))
        self.assertFalse(verify_password("wrong", h))
        self.assertNotEqual(h, hash_password(PW))  # random salt
        self.assertNotIn(PW, h)
        self.assertFalse(verify_password(PW, None))  # unknown user still runs a hash, never succeeds

    # ---- register / login
    def test_register_patient_and_login(self):
        email, h, prof = self.register("patient", "Pat@Example.com")
        self.assertEqual((prof["role"], prof["profileComplete"], prof["phone"]), ("patient", False, None))
        self.assertEqual(self.c.get("/api/patients/me", headers=h).status_code, 200)
        r = self.c.post("/api/auth/login", json={"email": "pat@example.com", "password": PW})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["email"], "pat@example.com")

    def test_register_rules(self):
        self.register("patient", "a@example.com")
        dup = self.c.post("/api/auth/register", json={"role": "doctor", "name": "Dr A", "email": "A@EXAMPLE.com", "password": PW})
        self.assertEqual(dup.status_code, 409)
        bad = self.c.post("/api/auth/register", json={"role": "patient", "name": "Bob", "email": "not-an-email", "password": PW})
        self.assertEqual(bad.status_code, 400)
        short = self.c.post("/api/auth/register", json={"role": "patient", "name": "Bob", "email": "b@example.com", "password": "short"})
        self.assertEqual(short.status_code, 422)
        role = self.c.post("/api/auth/register", json={"role": "admin", "name": "Bob", "email": "c@example.com", "password": PW})
        self.assertEqual(role.status_code, 422)

    def test_wrong_password_is_generic_and_throttled(self):
        email, _, _ = self.register("patient")
        for _ in range(5):
            r = self.c.post("/api/auth/login", json={"email": email, "password": "nope nope"})
            self.assertEqual((r.status_code, r.json()["detail"]), (401, "Email or password is incorrect."))
        unknown = self.c.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope nope"})
        self.assertEqual(unknown.json()["detail"], "Email or password is incorrect.")  # same text as a wrong password
        self.assertEqual(self.c.post("/api/auth/login", json={"email": email, "password": PW}).status_code, 429)

    def test_success_resets_the_counter(self):
        email, _, _ = self.register("patient")
        for _ in range(3):
            self.c.post("/api/auth/login", json={"email": email, "password": "nope nope"})
        self.assertEqual(self.c.post("/api/auth/login", json={"email": email, "password": PW}).status_code, 200)
        for _ in range(4):
            self.c.post("/api/auth/login", json={"email": email, "password": "nope nope"})
        self.assertEqual(self.c.post("/api/auth/login", json={"email": email, "password": PW}).status_code, 200)

    def test_otp_is_demo_only(self):
        self.assertEqual(self.c.post("/api/auth/otp/request", json={"phone": "9876543210"}).status_code, 404)
        self.assertEqual(self.c.post("/api/auth/otp/verify", json={"phone": "9876543210", "otp": "123456"}).status_code, 404)
        self.assertEqual(self.c.get("/api/auth/config").json(), {"demoLogin": False})
        with mock.patch.dict(os.environ, {"DEMO_MODE": "true"}):
            self.assertEqual(self.c.post("/api/auth/otp/verify", json={"phone": "9876543210", "otp": "123456"}).status_code, 200)
            self.assertEqual(self.c.get("/api/auth/config").json(), {"demoLogin": True})

    # ---- roles
    def test_roles_are_kept_apart(self):
        _, ph, _ = self.register("patient")
        _, dh, dprof = self.register("doctor", specialty="Cardiology", hospital="City Hospital")
        self.assertEqual((dprof["role"], dprof["specialty"]), ("doctor", "Cardiology"))
        self.assertEqual(self.c.get("/api/patients/me", headers=dh).status_code, 401)  # doctor on a patient route
        self.assertEqual(self.c.get("/api/patients/me/timeline", headers=dh).status_code, 401)
        self.assertEqual(self.c.get("/api/doctor/patients", headers=ph).status_code, 401)  # patient on a doctor route
        self.assertEqual(self.c.post("/api/care/invite", headers=dh).status_code, 401)
        self.assertEqual(self.c.get("/api/doctor/patients").status_code, 401)
        self.assertEqual(self.c.get("/api/auth/me", headers=dh).json()["role"], "doctor")
        self.assertEqual(self.c.get("/api/auth/me", headers=ph).json()["role"], "patient")

    # ---- invite + link
    def test_full_link_flow_and_revoke(self):
        _, ph, pprof = self.register("patient", name="Friend Patient")
        _, dh, _ = self.register("doctor", name="Dr Me")
        code = self.invite(ph)
        self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        r = self.c.post("/api/doctor/link", json={"code": code.lower()}, headers=dh)  # case and dash tolerant
        self.assertEqual((r.status_code, r.json()["name"]), (200, "Friend Patient"))
        pid = r.json()["patientId"]
        self.assertEqual([p["patientId"] for p in self.c.get("/api/doctor/patients", headers=dh).json()], [pid])
        self.assertEqual([d["name"] for d in self.c.get("/api/care/doctors", headers=ph).json()], ["Dr Me"])
        snap = self.c.get(f"/api/doctor/patients/{pid}/snapshot", headers=dh)
        self.assertEqual((snap.status_code, snap.json()["patient"]["name"]), (200, "Friend Patient"))
        tok = self.c.post(f"/api/doctor/patients/{pid}/console-token", headers=dh).json()
        self.assertEqual(tok["doctorName"], "Dr Me")
        self.assertEqual(self.c.get(f"/api/shares/{tok['token']}/snapshot").status_code, 200)  # existing console flow works
        start = self.c.post("/api/consultations/start", json={"patientToken": tok["token"], "doctorName": tok["doctorName"]})
        self.assertEqual(start.status_code, 200)
        # the patient sees who looked
        log = self.c.get("/api/patients/me/access-log", headers=ph).json()
        self.assertTrue(any(a["who"] == "Dr Me" and a["role"] == "Doctor" for a in log))
        # revoke
        H = {"X-Share-Token": tok["token"]}
        self.assertEqual(self.c.get(f"/api/consultations/{start.json()['consultationId']}", headers=H).status_code, 200)
        link_id = self.c.get("/api/care/doctors", headers=ph).json()[0]["linkId"]
        self.assertEqual(self.c.delete(f"/api/care/doctors/{link_id}", headers=ph).status_code, 200)
        self.assertEqual(self.c.get("/api/doctor/patients", headers=dh).json(), [])
        self.assertEqual(self.c.get(f"/api/doctor/patients/{pid}/snapshot", headers=dh).status_code, 404)
        self.assertEqual(self.c.post(f"/api/doctor/patients/{pid}/console-token", headers=dh).status_code, 404)
        self.assertEqual(self.c.delete(f"/api/care/doctors/{link_id}", headers=ph).status_code, 404)
        # the console link the doctor already held is dead too
        self.assertEqual(self.c.get(f"/api/shares/{tok['token']}/snapshot").status_code, 404)
        self.assertEqual(self.c.get(f"/api/consultations/{start.json()['consultationId']}", headers=H).status_code, 404)

    def test_relink_after_revoke_uses_a_new_code(self):
        _, ph, _ = self.register("patient")
        _, dh, _ = self.register("doctor")
        pid = self.c.post("/api/doctor/link", json={"code": self.invite(ph)}, headers=dh).json()["patientId"]
        link_id = self.c.get("/api/care/doctors", headers=ph).json()[0]["linkId"]
        self.c.delete(f"/api/care/doctors/{link_id}", headers=ph)
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": self.invite(ph)}, headers=dh).status_code, 200)
        self.assertEqual(self.c.get(f"/api/doctor/patients/{pid}/snapshot", headers=dh).status_code, 200)

    def test_code_is_single_use_and_expires(self):
        _, ph, _ = self.register("patient")
        _, d1, _ = self.register("doctor")
        _, d2, _ = self.register("doctor")
        code = self.invite(ph)
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": code}, headers=d1).status_code, 200)
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": code}, headers=d2).status_code, 400)  # already used
        code2 = self.invite(ph)
        with self.Session() as db:
            row = db.get(InviteCode, code2.replace("-", ""))
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": code2}, headers=d2).status_code, 400)  # expired
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": "ZZZZ-ZZZZ"}, headers=d2).status_code, 400)  # unknown

    def test_new_invite_replaces_the_old_unused_one(self):
        _, ph, _ = self.register("patient")
        _, dh, _ = self.register("doctor")
        first, second = self.invite(ph), self.invite(ph)
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": first}, headers=dh).status_code, 400)
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": second}, headers=dh).status_code, 200)

    def test_unlinked_doctor_cannot_see_anyone(self):
        _, ph, pprof = self.register("patient")
        _, dh, _ = self.register("doctor")
        for path in (f"/api/doctor/patients/{pprof['id']}/snapshot", "/api/doctor/patients/nope/snapshot"):
            self.assertEqual(self.c.get(path, headers=dh).status_code, 404)
        self.assertEqual(self.c.post(f"/api/doctor/patients/{pprof['id']}/console-token", headers=dh).status_code, 404)

    def test_doctor_cannot_guess_codes(self):
        _, dh, _ = self.register("doctor")
        for _ in range(10):
            self.assertEqual(self.c.post("/api/doctor/link", json={"code": "AAAA-AAAA"}, headers=dh).status_code, 400)
        self.assertEqual(self.c.post("/api/doctor/link", json={"code": "AAAA-AAAA"}, headers=dh).status_code, 429)

    def test_one_doctor_cannot_see_another_doctors_patient(self):
        _, ph, _ = self.register("patient")
        _, d1, _ = self.register("doctor")
        _, d2, _ = self.register("doctor")
        pid = self.c.post("/api/doctor/link", json={"code": self.invite(ph)}, headers=d1).json()["patientId"]
        self.assertEqual(self.c.get(f"/api/doctor/patients/{pid}/snapshot", headers=d2).status_code, 404)
        self.assertEqual(self.c.get("/api/doctor/patients", headers=d2).json(), [])


if __name__ == "__main__":
    unittest.main()
