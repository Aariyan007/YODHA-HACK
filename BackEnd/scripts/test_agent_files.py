"""Vault + file ingestion tests. In-memory SQLite, temp vault dir, no network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_agent_files.py -v
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import store, vault
from app.agent import ingest
from app.database import Base, get_db
from app.main import app
from app.models import AgentAudit, AgentFile

PW = "correct horse 9"
KEY = base64.urlsafe_b64encode(b"k" * 32).decode()


def text_pdf(lines: list[str]) -> bytes:
    """A tiny valid one-page PDF with a text layer."""
    body = "BT /F1 12 Tf 50 750 Td 14 TL " + " ".join(f"({l.replace('(', '[').replace(')', ']')}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(body)} >>\nstream\n{body}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    return out + f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode()


LAB = ["Pathology Laboratory Report", "Specimen: blood. Sample collected 01-09-2026", "HbA1c 8.2 % Reference range 4.0-5.6",
       "Creatinine 1.1 mg/dl units", "LDL Cholesterol 130 mg/dl", "Result verified by pathologist"]


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"FILE_ENC_KEY": KEY, "VAULT_DIR": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_roundtrip_and_ciphertext_is_not_plaintext(self):
        k = vault.new_storage_key()
        vault.put(k, b"HbA1c 8.2 secret", "f1", "p1")
        raw = next(Path(self.tmp.name).rglob("*.bin")).read_bytes()
        self.assertNotIn(b"secret", raw)
        self.assertEqual(vault.get(k, "f1", "p1"), b"HbA1c 8.2 secret")

    def test_wrong_owner_or_id_fails(self):
        k = vault.new_storage_key()
        vault.put(k, b"data", "f1", "p1")
        with self.assertRaises(vault.VaultError):
            vault.get(k, "f1", "p2")
        with self.assertRaises(vault.VaultError):
            vault.get(k, "f2", "p1")

    def test_tamper_detected(self):
        k = vault.new_storage_key()
        vault.put(k, b"data data data", "f1", "p1")
        p = next(Path(self.tmp.name).rglob("*.bin"))
        b = bytearray(p.read_bytes())
        b[-1] ^= 1
        p.write_bytes(bytes(b))
        with self.assertRaises(vault.VaultError):
            vault.get(k, "f1", "p1")

    def test_fails_closed_without_key(self):
        with mock.patch.dict(os.environ, {"FILE_ENC_KEY": ""}):
            self.assertFalse(vault.available())
            with self.assertRaises(vault.VaultError):
                vault.put("abc123", b"x", "f", "p")
        self.assertEqual(list(Path(self.tmp.name).rglob("*.bin")), [])

    def test_bad_storage_key_rejected(self):
        with self.assertRaises(vault.VaultError):
            vault.get("../../etc/passwd", "f", "p")


class IngestTests(unittest.TestCase):
    def test_pdf_text_and_classification(self):
        pages, n = ingest.pdf_pages(text_pdf(LAB))
        self.assertEqual(n, 1)
        c = ingest.classify("\n".join(pages))
        self.assertEqual(c["type"], "lab")
        self.assertGreaterEqual(c["confidence"], 0.6)
        self.assertEqual(ingest.text_lines(pages)[0]["page"], 1)

    def test_ambiguous_text_is_not_guessed(self):
        c = ingest.classify("Dear Sir, please find attached the document we discussed last week regarding the matter at hand.")
        self.assertIsNone(c["type"])

    def test_no_text_layer_needs_reading(self):
        self.assertIsNone(ingest.classify("")["type"])

    def test_garbage_pdf_does_not_raise(self):
        self.assertEqual(ingest.pdf_pages(b"%PDF-1.4 not really"), ([], 0))


class FileApiTests(unittest.TestCase):
    def setUp(self):
        store._memory.clear()
        p = mock.patch.object(store, "_redis", None)
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"FILE_ENC_KEY": KEY, "VAULT_DIR": self.tmp.name, "DEMO_MODE": "false"})
        env.start()
        self.addCleanup(env.stop)
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        def override():
            d = self.Session()
            try:
                yield d
            finally:
                d.close()

        app.dependency_overrides[get_db] = override
        self.addCleanup(app.dependency_overrides.clear)
        self.c = TestClient(app)
        self.h1 = self.reg("one@example.com")
        self.h2 = self.reg("two@example.com")

    def reg(self, email):
        r = self.c.post("/api/auth/register", json={"role": "patient", "name": email.split("@")[0], "email": email, "password": PW})
        return {"Authorization": "Bearer " + r.json()["token"]}

    def up(self, data, h=None, name="r.pdf"):
        return self.c.post("/api/agent/files", files={"file": (name, data, "application/octet-stream")}, headers=h or self.h1)

    def test_upload_classifies_and_stores_encrypted(self):
        r = self.up(text_pdf(LAB))
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertEqual((j["type"], j["status"], j["needsType"]), ("lab", "classified", False))
        self.assertNotIn("storage", str(j).lower())
        blob = b"".join(p.read_bytes() for p in Path(self.tmp.name).rglob("*.bin"))
        self.assertNotIn(b"HbA1c", blob)
        got = self.c.get(f"/api/agent/files/{j['fileId']}/content", headers=self.h1)
        self.assertEqual(got.content, text_pdf(LAB))
        self.assertEqual(got.headers["cache-control"], "no-store")

    def test_other_patient_cannot_read_or_delete(self):
        fid = self.up(text_pdf(LAB)).json()["fileId"]
        self.assertEqual(self.c.get(f"/api/agent/files/{fid}/content", headers=self.h2).status_code, 404)
        self.assertEqual(self.c.delete(f"/api/agent/files/{fid}", headers=self.h2).status_code, 404)
        self.assertEqual(self.c.get("/api/agent/files", headers=self.h2).json(), [])
        self.assertEqual(self.c.get(f"/api/agent/files/{fid}/content").status_code, 401)

    def test_validation(self):
        self.assertEqual(self.up(b"MZ not a document").status_code, 415)
        self.assertEqual(self.up(b"").status_code, 400)
        self.assertEqual(self.up(b"%PDF-1.4" + b"0" * (10 * 1024 * 1024 + 5)).status_code, 413)

    def test_unclear_document_asks_then_user_answer_sticks(self):
        j = self.up(text_pdf(["Dear Sir, please find attached the document we discussed last week regarding the matter at hand."])).json()
        self.assertTrue(j["needsType"])
        r = self.c.post(f"/api/agent/files/{j['fileId']}/type", json={"type": "prescription"}, headers=self.h1).json()
        self.assertEqual((r["type"], r["needsType"]), ("prescription", False))
        self.assertEqual(self.c.post(f"/api/agent/files/{j['fileId']}/type", json={"type": "dance"}, headers=self.h1).status_code, 422)

    def test_duplicate_is_not_stored_twice_and_filename_is_sanitised(self):
        a = self.up(text_pdf(LAB), name="../../etc/<script>x.pdf").json()
        b = self.up(text_pdf(LAB)).json()
        self.assertTrue(b["duplicate"])
        self.assertEqual(a["fileId"], b["fileId"])
        self.assertNotIn("/", a["name"])
        self.assertNotIn("<", a["name"])
        self.assertEqual(len(list(Path(self.tmp.name).rglob("*.bin"))), 1)

    def test_delete_removes_bytes(self):
        fid = self.up(text_pdf(LAB)).json()["fileId"]
        self.assertTrue(self.c.delete(f"/api/agent/files/{fid}", headers=self.h1).json()["ok"])
        self.assertEqual(list(Path(self.tmp.name).rglob("*.bin")), [])
        self.assertEqual(self.c.get(f"/api/agent/files/{fid}/content", headers=self.h1).status_code, 404)

    def test_no_key_means_503_and_nothing_stored(self):
        with mock.patch.dict(os.environ, {"FILE_ENC_KEY": ""}):
            self.assertEqual(self.up(text_pdf(LAB)).status_code, 503)
        with self.Session() as db:
            self.assertEqual(db.scalars(select(AgentFile)).all(), [])

    def test_uploads_are_audited_without_content(self):
        self.up(text_pdf(LAB))
        with self.Session() as db:
            row = db.scalar(select(AgentAudit).where(AgentAudit.tool == "files.upload"))
        self.assertIsNotNone(row)
        self.assertNotIn("HbA1c", f"{row.detail}{row.target}")


if __name__ == "__main__":
    unittest.main()
