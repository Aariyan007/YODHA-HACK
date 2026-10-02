"""Voice endpoints, SpeechService fallback, admin metrics. In-memory SQLite, no network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_voice_admin.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

import test_agent_files as base
from app import speech
from app.models import AgentAudit, User

WAV = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 40


class Voice(base.ExtractBase):
    def v(self, data=WAV, h=None, q=""):
        return self.c.post("/api/agent/voice" + q, files={"file": ("v.wav", data, "audio/wav")}, headers=h or self.h1)

    def test_returns_only_text_and_runs_no_tool(self):
        with mock.patch.object(speech, "transcribe", return_value={"text": "log my bp 120/80", "language": "en", "engine": "whisper"}):
            r = self.v()
        self.assertEqual(r.json(), {"text": "log my bp 120/80", "language": "en", "engine": "whisper"})
        with self.Session() as db:
            tools = {a.tool for a in db.scalars(select(AgentAudit))}
        self.assertEqual(tools, {"voice.transcribe"})  # nothing was executed from speech

    def test_guards(self):
        self.assertEqual(self.c.post("/api/agent/voice", files={"file": ("v.wav", WAV, "audio/wav")}).status_code, 401)
        self.assertEqual(self.v(b"not audio at all").status_code, 415)
        self.assertEqual(self.v(b"").status_code, 400)
        self.assertEqual(self.v(WAV + b"0" * (6 * 1024 * 1024)).status_code, 413)

    def test_speech_errors_become_plain_messages(self):
        with mock.patch.object(speech, "transcribe", side_effect=speech.SpeechError("The speech service is busy.", 429)):
            r = self.v()
        self.assertEqual((r.status_code, r.json()["detail"]), (429, "The speech service is busy."))

    def test_doctor_voice_needs_a_link(self):
        d = self.c.post("/api/auth/register", json={"role": "doctor", "name": "Dr V", "email": "dv@example.com", "password": base.PW}).json()["token"]
        with self.Session() as db:
            pid = db.scalar(select(User).where(User.email == "one@example.com")).patient_id
        r = self.c.post(f"/api/doctor-agent/voice?patientId={pid}", files={"file": ("v.wav", WAV, "audio/wav")}, headers={"Authorization": "Bearer " + d})
        self.assertEqual(r.status_code, 404)


class Engine(unittest.TestCase):
    def test_elevenlabs_refused_falls_back_to_whisper(self):
        env = {"ELEVENLABS_API_KEY": "x", "GROQ_API_KEY": "y"}
        with mock.patch.dict(os.environ, env), \
             mock.patch.object(speech.httpx, "post", return_value=mock.Mock(status_code=401, json=lambda: {})), \
             mock.patch.object(speech.whisper, "transcribe", return_value={"text": "hello there", "language": "en"}):
            out = speech.transcribe(WAV, "v.wav", "audio/wav", "en")
        self.assertEqual((out["text"], out["engine"]), ("hello there", "whisper"))

    def test_elevenlabs_used_when_it_works_and_phantoms_dropped(self):
        ok = mock.Mock(status_code=200, json=lambda: {"text": "ബിപി നൂറ്റി ഇരുപത്", "language_code": "mal"})
        ghost = mock.Mock(status_code=200, json=lambda: {"text": "Thank you.", "language_code": "eng"})
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "x"}):
            with mock.patch.object(speech.httpx, "post", return_value=ok):
                self.assertEqual(speech.transcribe(WAV, "v.wav", "audio/wav")["engine"], "elevenlabs")
            with mock.patch.object(speech.httpx, "post", return_value=ghost):
                self.assertEqual(speech.transcribe(WAV, "v.wav", "audio/wav")["text"], "")

    def test_no_engine_at_all(self):
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "", "GROQ_API_KEY": ""}):
            with self.assertRaises(speech.SpeechError):
                speech.transcribe(WAV, "v.wav", "audio/wav")


class Admin(base.ExtractBase):
    def test_only_admin_emails_get_metrics_and_no_secrets_leak(self):
        with mock.patch.dict(os.environ, {"ADMIN_EMAILS": "one@example.com", "ELEVENLABS_API_KEY": "sk_secret_value"}):
            self.assertEqual(self.c.get("/api/admin/metrics", headers=self.h2).status_code, 404)
            self.assertEqual(self.c.get("/api/admin/metrics").status_code, 401)
            self.c.post("/api/agent/chat", json={"text": "what medicines am I on"}, headers=self.h1)
            r = self.c.get("/api/admin/metrics", headers=self.h1)
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["users"]["patients"], 2)
        self.assertIn("medications.list", [t["tool"] for t in j["agent"]["perTool"]])
        self.assertTrue(j["services"]["elevenlabs"])
        self.assertNotIn("sk_secret_value", r.text)
        self.assertNotIn("one@example.com", r.text)

    def test_no_admins_configured_means_nobody(self):
        with mock.patch.dict(os.environ, {"ADMIN_EMAILS": ""}):
            self.assertEqual(self.c.get("/api/admin/metrics", headers=self.h1).status_code, 404)


if __name__ == "__main__":
    unittest.main()
