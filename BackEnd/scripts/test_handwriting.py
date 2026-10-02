"""Handwriting two-pass logic: preprocess, compare, uncertain handling, agent surface. No network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_handwriting.py -v
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from ai import handwriting as hw
from app.agent import extract as ex


def png(w=400, h=300):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (200, 190, 170)).save(b, "PNG")
    return b.getvalue()


class Compare(unittest.TestCase):
    def test_agreeing_known_drug_is_certain(self):
        c, u = hw.compare([{"name": "Metformin", "dose": "500 mg"}], [{"name": "Metformin", "confidence": "high"}])
        self.assertEqual((len(c), len(u)), (1, 0))

    def test_disagreement_is_uncertain_not_guessed(self):
        c, u = hw.compare([{"name": "Telmisartan"}], [{"name": "Tolazamide", "confidence": "high"}])
        self.assertEqual(c, [])
        self.assertIn("do not agree", u[0]["reason"])
        self.assertEqual(u[0]["alternative"], "Tolazamide")

    def test_unreadable_letters_are_uncertain(self):
        c, u = hw.compare([{"name": "Amlo?ipine"}], [{"name": "Amlo?ipine", "confidence": "high"}])
        self.assertEqual((c, u[0]["reason"]), ([], "part of the name is not legible"))

    def test_low_confidence_second_reading_is_uncertain(self):
        c, u = hw.compare([{"name": "Metformin"}], [{"name": "Metformin", "confidence": "low"}])
        self.assertEqual(len(u), 1)

    def test_agreed_but_not_a_real_drug_is_uncertain(self):
        c, u = hw.compare([{"name": "Zorbexil"}], [{"name": "Zorbexil", "confidence": "high"}])
        self.assertIn("does not match a drug", u[0]["reason"])

    def test_missing_in_second_reading(self):
        c, u = hw.compare([{"name": "Metformin"}], [])
        self.assertEqual(len(u), 1)


class Flow(unittest.TestCase):
    def doc(self):
        return {"handwritten": True, "medicines": [{"name": "Metformin", "dose": "500 mg"}, {"name": "Telmisartan"}], "source_lines": ["x"]}

    def test_second_pass_splits_certain_and_uncertain_and_keeps_question_marks(self):
        second = {"lines": ["Rx", "Metformin 500 mg BD", "Tel?? 40"], "medicines": [{"name": "Metformin", "confidence": "high"}, {"name": "Tel??", "confidence": "low"}]}
        d = hw.second_pass(None, lambda *a, **k: json.dumps(second), png(), "image/png", self.doc())
        self.assertEqual([m["name"] for m in d["medicines"]], ["Metformin"])
        self.assertEqual(d["uncertain_medicines"][0]["name"], "Telmisartan")
        self.assertIn("Tel?? 40", d["source_lines"])

    def test_failed_second_pass_trusts_nothing(self):
        def boom(*a, **k):
            raise RuntimeError("busy")
        d = hw.second_pass(None, boom, png(), "image/png", self.doc())
        self.assertEqual(d["medicines"], [])
        self.assertEqual(len(d["uncertain_medicines"]), 2)

    def test_preprocess_upscales_and_greys_images_only(self):
        out = Image.open(io.BytesIO(hw.preprocess(png(), "image/png")))
        self.assertEqual((out.mode, max(out.size)), ("L", 1800))
        self.assertEqual(hw.preprocess(b"%PDF-1.4", "application/pdf"), b"%PDF-1.4")
        self.assertEqual(hw.preprocess(b"garbage", "image/png"), b"garbage")


class AgentSurface(unittest.TestCase):
    def test_uncertain_medicines_are_listed_never_in_clean_doc(self):
        doc = {"handwritten": True, "type": "prescription", "medicines": [{"name": "Metformin", "dose": "500 mg"}],
               "uncertain_medicines": [{"name": "Telmisartan", "alternative": "Tolazamide", "reason": "the two readings of the page do not agree on this name"}],
               "observations": [], "diagnoses": [], "vitals": {}}
        lines = [{"n": 1, "page": 1, "text": "Metformin 500 mg BD"}, {"n": 2, "page": 1, "text": "Tel?? 40"}]
        out = ex.verify(doc, lines)
        self.assertEqual([m["name"] for m in out["clean_doc"]["medicines"]], ["Metformin"])
        self.assertTrue(any("Telmisartan" in u["text"] and "Tolazamide" in u["text"] for u in out["unverified"]))
        self.assertTrue(any("handwritten" in w for w in out["warnings"]))


if __name__ == "__main__":
    unittest.main()
