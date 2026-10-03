"""Medicine safety questions: bad combinations, side effects (grounded in the label), usual timing. No network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_med_safety.py -v
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_agent_writes as base
from ai import drug_usage
from app.agent.tools import patient_read as pr
from app.models import Medicine, Patient

LABEL = {"openfda": {"generic_name": ["metformin hydrochloride"]},
         "information_for_patients": ["What are the possible side effects of metformin? Nausea, vomiting, stomach upset, diarrhea, and a metallic taste can happen when you start. "
                                      "Call your doctor right away if you feel very weak, tired, or have trouble breathing."],
         "boxed_warning": ["WARNING: LACTIC ACIDOSIS is a rare but serious complication."]}


class Verify(unittest.TestCase):
    SRC = "What are the possible side effects? Nausea, vomiting and diarrhea can happen. Call your doctor right away if you feel very weak."

    def test_only_quotes_that_are_really_in_the_source_survive(self):
        items = [{"effect": "nausea", "quote": "Nausea, vomiting and diarrhea can happen"},
                 {"effect": "hair loss", "quote": "Hair loss is common"},                      # invented
                 {"effect": "weakness", "quote": "Call your doctor right away if you feel very weak"},
                 {"effect": "headache", "quote": "Nausea, vomiting and diarrhea can happen"}]   # real quote, but it does not name headache
        out = drug_usage.verify_items(items, self.SRC)
        self.assertEqual([i["effect"] for i in out], ["nausea", "weakness"])

    def test_garbage_from_the_model_is_ignored(self):
        self.assertEqual(drug_usage.verify_items("nope", self.SRC), [])
        self.assertEqual(drug_usage.verify_items([None, 5, {"effect": "x"}], self.SRC), [])


class Tools(base.Writes):
    def setUp(self):
        super().setUp()
        drug_usage._side_cache.clear()
        with self.Session() as db:
            db.get(Patient, self.pid).allergies = ["Penicillin"]
            db.add(Medicine(id="m1", patient_id=self.pid, name="Clarithromycin 500", times=["08:00"], start_date="2026-10-03"))
            db.add(Medicine(id="m2", patient_id=self.pid, name="Atorvastatin 20", times=["21:00"], start_date="2026-10-03"))
            db.add(Medicine(id="m3", patient_id=self.pid, name="Amoxicillin 500", times=["09:00"], start_date="2026-10-03"))
            db.add(Medicine(id="m4", patient_id=self.pid, name="Zorbexil", times=[], start_date="2026-10-03"))
            db.add(Medicine(id="m5", patient_id=self.pid2, name="Warfarin", times=[], start_date="2026-10-03"))
            db.commit()

    def texts(self, r):
        return " ".join(str(b.get("title", "")) + " " + str(b.get("text", "")) for b in r["blocks"])

    def test_bad_combinations_and_allergy_are_found_and_unknown_names_admitted(self):
        r = self.say("is there any bad combination of medicine i am having")
        t = self.texts(r)
        self.assertEqual(r["steps"][0]["tool"], "medications.check_interactions")
        self.assertIn("Clarithromycin 500 with Atorvastatin 20", t)
        self.assertIn("Amoxicillin 500 and your", t)               # allergy
        self.assertIn("Zorbexil", t)                                # could not check: said so, not "all clear"
        self.assertNotIn("Warfarin", t)                             # another patient's medicine never appears
        self.assertIn("never stop a medicine", t)

    def test_no_medicines_is_not_all_clear(self):
        with self.Session() as db:
            for m in db.query(Medicine).filter_by(patient_id=self.pid):
                m.active = False
            db.commit()
        self.assertIn("no current medicines", self.texts(self.say("any bad combination of my medicines?")))

    def test_side_effects_come_from_verified_label_quotes(self):
        def extractor(system, user):
            return {"common": [{"effect": "nausea", "quote": "Nausea, vomiting, stomach upset, diarrhea, and a metallic taste can happen"},
                               {"effect": "hair loss", "quote": "Hair loss is very common"}],           # invented: must be dropped
                    "serious": [{"effect": "weakness", "quote": "Call your doctor right away if you feel very weak, tired, or have trouble breathing"}]}
        with mock.patch.object(drug_usage, "_fetch", lambda g: [LABEL]), mock.patch("app.agent.llm._groq_judge", extractor):
            r = self.say("any side effects of my medicines?")
        t = self.texts(r)
        self.assertIn("nausea", t.lower())
        self.assertIn("very weak", t)
        self.assertNotIn("hair loss", t.lower())
        self.assertIn("boxed warning", t)
        self.assertIn("Do not stop a medicine on your own", t)

    def test_side_effects_without_the_model_never_invents_a_summary(self):
        with mock.patch.object(drug_usage, "_fetch", lambda g: [LABEL]), mock.patch("app.agent.llm._groq_judge", lambda s, u: None):
            t = self.texts(self.say("what are the side effects of clarithromycin"))
        self.assertIn("could not summarise", t)
        self.assertNotIn("Nausea", t)

    def test_a_named_medicine_asks_about_only_that_one(self):
        from app.agent.planner import AgentPlanner
        n = AgentPlanner._named_medicine
        self.assertEqual(n("what are the side effects of telma"), "telma")
        self.assertEqual(n("any side effects for pantocid 40"), "pantocid")
        self.assertEqual(n("what can metformin cause"), "metformin")
        self.assertIsNone(n("any side effects of my medicines"))
        self.assertIsNone(n("what are the side effects"))

    def test_unknown_brand_is_admitted(self):
        with mock.patch.object(drug_usage, "_fetch", lambda g: []):
            t = self.texts(self.say("side effects of zorbexil"))
        self.assertIn("could not find a public label", t)


if __name__ == "__main__":
    unittest.main()
