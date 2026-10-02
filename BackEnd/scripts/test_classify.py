"""Visit-classification grounding tests. No network: the model's reply is faked.

    cd BackEnd && ./venv/bin/python -W ignore scripts/test_classify.py -v

The model may propose anything. These tests check that code keeps only what the transcript supports.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import visit_classify as vc  # noqa: E402

LINES = [
    {"speaker": "doctor", "text": "Good morning, how was the drive in this heavy rain?"},            # 0 small talk
    {"speaker": "patient", "text": "Fine doctor. I have had fever and a dry cough for three days."},  # 1
    {"speaker": "doctor", "text": "It looks like a viral fever. Start paracetamol 650 mg twice daily after food."},  # 2
    {"speaker": "doctor", "text": "Continue Telma 40 mg in the morning. Stop ibuprofen."},          # 3
    {"speaker": "patient", "text": "I also take vitamin D sometimes."},                              # 4
    {"speaker": "doctor", "text": "Get a CBC and chest X-ray done. Drink plenty of fluids."},        # 5
    {"speaker": "doctor", "text": "Come back after five days."},                                      # 6
]


def good_raw():
    return {
        "complaints": [{"text": "Fever and dry cough for three days", "source_lines": [1]}],
        "diagnoses": [{"text": "Viral fever", "source_lines": [2]}],
        "medicines": [
            {"name": "paracetamol", "action": "start", "dose": "650 mg", "frequency": "twice daily",
             "timing": "after food", "duration": None, "instructions": None, "source_lines": [2]},
            {"name": "Telma", "action": "continue", "dose": "40 mg", "frequency": None,
             "timing": "in the morning", "duration": None, "instructions": None, "source_lines": [3]},
            {"name": "ibuprofen", "action": "stop", "dose": None, "frequency": None, "timing": None,
             "duration": None, "instructions": None, "source_lines": [3]},
        ],
        "tests": [{"text": "CBC and chest X-ray", "source_lines": [5]}],
        "advice": [{"text": "Drink plenty of fluids", "source_lines": [5]}],
        "referrals": [],
        "follow_up": {"text": "Come back after five days", "source_lines": [6]},
        "ignored_lines": [0, 4],
    }


class Grounding(unittest.TestCase):
    def test_good_output_is_kept(self):
        out = vc.validate(good_raw(), LINES)
        self.assertEqual([m["name"] for m in out["medicines"]], ["paracetamol", "Telma", "ibuprofen"])
        self.assertEqual(out["diagnoses"][0]["text"], "Viral fever")
        self.assertEqual(out["follow_up"]["source_lines"], [6])
        self.assertEqual(out["ignored_lines"], [0, 4])
        self.assertEqual(out["medicines"][0]["dose"], "650 mg")
        self.assertEqual(out["medicines"][0]["timing"], "after food")

    def test_actions_survive(self):
        out = vc.validate(good_raw(), LINES)
        self.assertEqual({m["name"]: m["action"] for m in out["medicines"]},
                         {"paracetamol": "start", "Telma": "continue", "ibuprofen": "stop"})

    def test_invented_diagnosis_dropped(self):
        raw = good_raw()
        raw["diagnoses"].append({"text": "Pneumonia", "source_lines": [2]})  # doctor never said it
        out = vc.validate(raw, LINES)
        self.assertEqual([d["text"] for d in out["diagnoses"]], ["Viral fever"])

    def test_diagnosis_cited_only_from_patient_dropped(self):
        raw = good_raw()
        raw["diagnoses"] = [{"text": "Dry cough", "source_lines": [1]}]
        self.assertEqual(vc.validate(raw, LINES)["diagnoses"], [])

    def test_medicine_only_patient_mentioned_dropped(self):
        raw = good_raw()
        raw["medicines"].append({"name": "vitamin D", "action": "start", "source_lines": [4]})
        names = [m["name"] for m in vc.validate(raw, LINES)["medicines"]]
        self.assertNotIn("vitamin D", names)

    def test_medicine_name_not_in_cited_lines_dropped(self):
        raw = good_raw()
        raw["medicines"].append({"name": "Azithromycin", "action": "start", "source_lines": [2]})
        names = [m["name"] for m in vc.validate(raw, LINES)["medicines"]]
        self.assertNotIn("Azithromycin", names)

    def test_invented_dose_is_nulled_not_kept(self):
        raw = good_raw()
        raw["medicines"][0]["dose"] = "1000 mg"  # transcript says 650 mg
        self.assertIsNone(vc.validate(raw, LINES)["medicines"][0]["dose"])

    def test_invented_duration_and_frequency_nulled(self):
        raw = good_raw()
        raw["medicines"][1]["duration"] = "30 days"      # Telma line has no duration words
        raw["medicines"][2]["frequency"] = "twice daily"  # ibuprofen line has no frequency words
        out = vc.validate(raw, LINES)
        self.assertIsNone(out["medicines"][1]["duration"])
        self.assertIsNone(out["medicines"][2]["frequency"])

    def test_item_without_valid_source_lines_dropped(self):
        raw = good_raw()
        raw["tests"] = [{"text": "MRI brain", "source_lines": [99]}, {"text": "Lipid profile", "source_lines": []}]
        self.assertEqual(vc.validate(raw, LINES)["tests"], [])

    def test_unknown_action_defaults_to_start(self):
        raw = good_raw()
        raw["medicines"][0]["action"] = "increase-a-lot"
        self.assertEqual(vc.validate(raw, LINES)["medicines"][0]["action"], "start")

    def test_duplicates_collapsed(self):
        raw = good_raw()
        raw["medicines"].append(dict(raw["medicines"][0]))
        names = [m["name"].lower() for m in vc.validate(raw, LINES)["medicines"]]
        self.assertEqual(names.count("paracetamol"), 1)

    def test_garbage_in_gives_none_or_empty(self):
        self.assertIsNone(vc.validate("nope", LINES))
        self.assertIsNone(vc.validate(good_raw(), []))
        out = vc.validate({}, LINES)
        self.assertEqual(out["medicines"], [])
        self.assertIsNone(out["follow_up"])

    def test_generic_filled_for_known_brand(self):
        out = vc.validate(good_raw(), LINES)
        self.assertEqual(out["medicines"][1]["generic"], "telmisartan")


class FallbackSafety(unittest.TestCase):
    """The plan-text fallback (used when the AI is rate-limited) must not create wrong prescriptions."""

    def setUp(self):
        from app.routers.consultations import _extract_medicines_from_plan
        self.ex = _extract_medicines_from_plan
        self.lines = [
            {"speaker": "doctor", "text": "Good. Stop paracetamol now. Continue Telma 40 mg in the morning."},
            {"speaker": "doctor", "text": "Start Pantop 40 mg once daily before breakfast for 14 days."},
        ]

    def test_stop_sentence_never_creates_a_medicine(self):
        names = [m["name"].lower() for m in self.ex(None, self.lines, [])]
        self.assertNotIn("paracetamol", names)

    def test_medicine_already_on_the_list_is_not_duplicated(self):
        active = [{"name": "Telma", "generic": "telmisartan"}]
        names = [m["name"].lower() for m in self.ex(None, self.lines, active)]
        self.assertNotIn("telma", names)
        self.assertIn("pantop", names)

    def test_details_come_from_the_medicines_own_sentence(self):
        pantop = next(m for m in self.ex(None, self.lines, []) if m["name"].lower() == "pantop")
        self.assertEqual(pantop["dose"], "40 mg")
        self.assertEqual(pantop["duration"], "14 d")


class RateLimitError(Exception):  # same class name the Groq SDK uses; the code matches on the name
    def __init__(self, retry_after=None):
        super().__init__("rate limited")
        self.response = type("R", (), {"headers": {"retry-after": retry_after} if retry_after is not None else {}})()


class LimitHandling(unittest.TestCase):
    """_chat_json: fall back to the other model on a rate limit; wait only for SHORT limits; never wait out a daily one."""

    def run_case(self, behaviours, **kw):
        from unittest import mock
        from ai import consultation as ca
        calls = []

        def fake_once(system, user, max_tokens, model=None):
            calls.append(model or ca.MODEL)
            b = behaviours[min(len(calls) - 1, len(behaviours) - 1)]
            if isinstance(b, Exception):
                raise b
            return b

        with mock.patch.object(ca, "_chat_json_once", fake_once), mock.patch("time.sleep") as sleep:
            out = ca._chat_json("s", "u", 100, **kw)
        return out, calls, sleep

    def test_main_model_ok_no_fallback(self):
        out, calls, _ = self.run_case([{"ok": 1}], fallback_model="small")
        self.assertEqual((out, calls), ({"ok": 1}, ["openai/gpt-oss-120b"]))

    def test_rate_limited_uses_fallback_model(self):
        out, calls, sleep = self.run_case([RateLimitError(), {"ok": 2}], fallback_model="small")
        self.assertEqual(out, {"ok": 2})
        self.assertEqual(calls[-1], "small")
        sleep.assert_not_called()

    def test_both_limited_short_wait_then_retry_main(self):
        out, calls, sleep = self.run_case([RateLimitError(3), RateLimitError(3), {"ok": 3}],
                                          fallback_model="small", wait_on_limit=8.0)
        self.assertEqual(out, {"ok": 3})
        sleep.assert_called_once()

    def test_daily_limit_is_never_waited_out(self):
        out, calls, sleep = self.run_case([RateLimitError(274), RateLimitError(274)],
                                          fallback_model="small", wait_on_limit=8.0)
        self.assertIsNone(out)
        sleep.assert_not_called()

    def test_live_calls_never_wait_or_fall_back(self):
        out, calls, sleep = self.run_case([RateLimitError(2)])
        self.assertIsNone(out)
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()

    def test_other_errors_do_not_trigger_fallback(self):
        out, calls, _ = self.run_case([ValueError("boom")], fallback_model="small", wait_on_limit=8.0)
        self.assertIsNone(out)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
