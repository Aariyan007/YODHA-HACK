"""Tests for the Laya decision layer and its safety contract. No network, no model: the Laya service is faked.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_decision.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ml" / "seed"))

from fastapi.testclient import TestClient

import handwritten
from ai import decision, laya_schema as S
from ai.triage_rules import LEVELS, emergency_hit, merge_urgency
from app import store
from app.main import app


def fake(urgency="routine", u=0.9, spec="general_physician", s=0.9):
    return {"urgency": urgency, "urgency_conf": u, "specialist": spec, "specialist_conf": s, "model": "fake", "cached": False, "ms": 5.0}


class RulesAndMerge(unittest.TestCase):
    def test_every_red_team_message_is_caught_by_rules_alone(self):
        missed = [t for t, _ in handwritten.REDTEAM if not emergency_hit(t)]
        self.assertEqual(missed, [])

    def test_no_false_emergency_on_ordinary_complaints(self):
        bad = [(t, u) for t, u, _, _ in handwritten.TEST if u != "emergency" and emergency_hit(t)]
        self.assertEqual(bad, [])

    def test_model_can_raise_but_never_lower(self):
        for rules in (None, *LEVELS):
            for model in LEVELS:
                level, _ = merge_urgency(rules, model, 0.99)
                if rules:
                    self.assertGreaterEqual(LEVELS.index(level), LEVELS.index(rules), (rules, model))
                self.assertGreaterEqual(LEVELS.index(level), LEVELS.index(model))

    def test_rules_emergency_is_final_even_if_the_model_disagrees(self):
        self.assertEqual(merge_urgency("emergency", "self_care", 0.999), ("emergency", "rules"))

    def test_low_confidence_model_is_ignored(self):
        self.assertEqual(merge_urgency(None, "emergency", 0.2), (None, "none"))
        self.assertEqual(merge_urgency("urgent", "emergency", 0.2), ("urgent", "rules"))

    def test_schema_ids_match_the_doctor_finder(self):
        from app.doctors import SPECIALTIES
        for name in S.SPECIALIST_NAME.values():
            self.assertIn(name, SPECIALTIES)


class TriageRoute(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def post(self, text, d):
        with mock.patch.object(decision, "triage", return_value=d), mock.patch.object(decision, "record_final"):
            return self.c.post("/api/triage", json={"text": text}).json()

    def test_rules_emergency_wins_over_a_calm_model(self):
        r = self.post("chest pain since morning", fake("self_care", 0.99))
        self.assertTrue(r["urgent"])
        self.assertEqual(r["specialist"], "Emergency / 108")

    def test_model_can_raise_to_emergency_when_rules_see_nothing(self):
        r = self.post("something feels very wrong, I am drifting away", fake("emergency", 0.93))
        self.assertTrue(r["urgent"])
        self.assertEqual(r["source"], "model")  # rules saw nothing, the model raised it
        self.assertEqual(r["urgency"], "emergency")

    def test_model_urgent_sets_soon_and_names_the_specialist(self):
        r = self.post("pain in my eye since morning", fake("urgent", 0.8, "ophthalmologist", 0.9))
        self.assertFalse(r["urgent"])
        self.assertTrue(r["soon"])
        self.assertEqual(r["specialist"], "Ophthalmologist")
        self.assertTrue(r["why"].startswith("Please see a doctor within a day."))
        self.assertEqual(r["specialistSource"], "model")

    def test_low_specialist_confidence_falls_back_to_keyword_rules(self):
        r = self.post("my knee hurts on stairs", fake("routine", 0.9, "dermatologist", 0.2))
        self.assertEqual(r["specialist"], "Orthopaedician")
        self.assertEqual(r["specialistSource"], "rules")

    def test_without_the_model_rules_still_answer(self):
        r = self.post("my knee hurts on stairs", None)
        self.assertEqual((r["specialist"], r["source"], r["model"]), ("Orthopaedician", "rules", None))
        r = self.post("something unclear", None)
        self.assertEqual(r["specialist"], "General Physician")  # 'unclear' must not match the 'ear' rule

    def test_malayalam_emergency_is_caught_without_the_model(self):
        r = self.post("നെഞ്ചുവേദനയും വിയർപ്പും", None)
        self.assertTrue(r["urgent"])


class Client(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(store, "_redis", None)
        patcher.start()
        self.addCleanup(patcher.stop)
        store._memory.clear()
        decision._fails, decision._open_until = 0, 0.0
        env = mock.patch.dict("os.environ", {"LAYA_URL": "http://laya.test", "LAYA_ALLOW_UNGATED": "1"})
        env.start()
        self.addCleanup(env.stop)
        decision._info.update(at=0.0, data=None)

    def service(self, status=200, answers=None, delay_fail=False):
        info = {"model": "m1", "loaded": True, "gate": {"ok": True}}
        answers = answers or {"urgency": {"choice": "urgent", "probabilities": {"urgent": 0.8}},
                              "specialist": {"choice": "ent", "probabilities": {"ent": 0.7}}}
        calls = {"decide": 0}

        class R:
            def __init__(s, code, body): s.status_code, s._b = code, body
            def raise_for_status(s):
                if s.status_code >= 400: raise RuntimeError(s.status_code)
            def json(s): return s._b

        class H:
            def get(self_, url, **kw): return R(200, info)
            def post(self_, url, **kw):
                calls["decide"] += 1
                if delay_fail: raise TimeoutError()
                return R(status, {"answers": answers, "model": "m1", "ms": 9})

        return H(), calls

    def test_answer_is_cached_and_audited_once(self):
        http, calls = self.service()
        with mock.patch.object(decision, "_http", return_value=http), mock.patch.object(decision, "_audit") as audit:
            a = decision.triage("pain in my ear")
            b = decision.triage("pain in my ear")
        self.assertEqual((a["urgency"], a["specialist"], a["cached"]), ("urgent", "ent", False))
        self.assertTrue(b["cached"])
        self.assertEqual(calls["decide"], 1)
        self.assertEqual(audit.call_count, 1)

    def test_failures_return_none_and_open_the_breaker(self):
        http, calls = self.service(delay_fail=True)
        with mock.patch.object(decision, "_http", return_value=http):
            for i in range(3):
                self.assertIsNone(decision.triage(f"text {i}"))
            n = calls["decide"]
            self.assertIsNone(decision.triage("another"))  # breaker is open: no call made
        self.assertEqual(calls["decide"], n)

    def test_disabled_without_a_url(self):
        with mock.patch.dict("os.environ", {"LAYA_URL": ""}):
            self.assertIsNone(decision.triage("pain"))

    def test_ungated_model_is_not_used_by_default(self):
        http, _ = self.service()
        info = {"model": "hub:typed-decisions", "loaded": True, "gate": {"ok": False}}
        http.get = lambda url, **kw: type("R", (), {"status_code": 200, "raise_for_status": lambda s: None, "json": lambda s: info})()
        with mock.patch.dict("os.environ", {"LAYA_ALLOW_UNGATED": "0"}), mock.patch.object(decision, "_http", return_value=http):
            self.assertIsNone(decision.triage("pain in my ear"))

    def test_garbage_answer_is_rejected(self):
        http, _ = self.service(answers={"urgency": {"choice": "banana", "probabilities": {}}, "specialist": {"choice": "ent", "probabilities": {"ent": 0.9}}})
        with mock.patch.object(decision, "_http", return_value=http), mock.patch.object(decision, "_audit"):
            self.assertIsNone(decision.triage("pain in my ear"))

    def test_audit_never_stores_the_text(self):
        http, _ = self.service()
        seen = {}
        with mock.patch.object(decision, "_http", return_value=http), mock.patch.object(decision, "_audit", side_effect=lambda *a, **k: seen.update(args=a)):
            decision.triage("my secret symptom words")
        self.assertNotIn("secret", json.dumps(seen["args"], default=str))


if __name__ == "__main__":
    unittest.main()
