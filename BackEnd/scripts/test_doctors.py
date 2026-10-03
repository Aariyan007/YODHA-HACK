"""Tests for the doctor finder: India only origin, ranking, filters, query parsing, AI fallback.

No network (Groq is never called, there's no key in the test env). Uses the FICTIONAL sample directory in
BackEnd/data/doctors.json.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_doctors.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("GROQ_API_KEY", None)

from ai import doctor_ai
from app import doctors as f

NOON_WED = datetime(2026, 9, 30, 12, 0, tzinfo=f.IST)
NIGHT_WED = datetime(2026, 9, 30, 23, 30, tzinfo=f.IST)


def origin(city):
    return f.resolve_origin(None, None, city)


class DataTests(unittest.TestCase):
    def test_directory_is_kerala_heavy_and_marked_sample(self):
        docs = f.directory()
        kerala = sum(d["state"] == "Kerala" for d in docs)
        self.assertGreaterEqual(len(docs), 80)
        self.assertGreater(kerala / len(docs), 0.7)
        self.assertTrue(all(d["sample"] for d in docs))
        self.assertTrue(all(d["phone"].startswith("+91 00000") for d in docs))  # not real numbers

    def test_every_doctor_is_inside_india(self):
        self.assertTrue(all(f.in_india(d["lat"], d["lng"]) for d in f.directory()))


class OriginTests(unittest.TestCase):
    def test_device_location_in_india(self):
        o = f.resolve_origin(10.01, 76.34, None)
        self.assertEqual(o["source"], "device")

    def test_outside_india_falls_back(self):
        o = f.resolve_origin(51.5, -0.12, None, patient_city="Thrissur")
        self.assertTrue(o["outsideIndia"])
        self.assertEqual(o["label"], "Thrissur")
        o = f.resolve_origin(40.7, -74.0, None)
        self.assertEqual(o["label"], "Kochi")

    def test_city_beats_district(self):
        self.assertEqual(f.city_coords("Thrissur")["city"], "Thrissur")
        self.assertEqual(f.city_coords("Ernakulam")["district"], "Ernakulam")


class RankingTests(unittest.TestCase):
    def test_specialty_filter_and_department_label(self):
        r = f.search(origin("Kochi"), "Cardiologist", now=NOON_WED)
        self.assertTrue(r["results"])
        for d in r["results"]:
            self.assertTrue(d["specialty"] == "Cardiologist" or "Cardiologist" in d["specialties"])
            if d["specialty"] != "Cardiologist":
                self.assertEqual(d["department"], "Cardiologist")

    def test_near_before_far(self):
        r = f.search(origin("Thrissur"), "Cardiologist", now=NOON_WED)
        dists = [d["distanceKm"] for d in r["results"]]
        near = [x for x in dists if x <= 40]
        self.assertEqual(dists[: len(near)], near)  # everything within 40 km comes first
        self.assertTrue(r["relaxed"])               # and the widening is explained

    def test_emergency_is_nearest_24x7(self):
        r = f.search(origin("Pala"), emergency=True, now=NIGHT_WED)
        self.assertTrue(all(d["emergency24x7"] for d in r["results"]))
        dists = [d["distanceKm"] for d in r["results"]]
        self.assertEqual(dists, sorted(dists))
        self.assertTrue(all(d["openNow"] for d in r["results"]))

    def test_open_now_at_night(self):
        r = f.search(origin("Kochi"), open_now=True, now=NIGHT_WED)
        self.assertTrue(r["results"])
        self.assertTrue(all(d["emergency24x7"] for d in r["results"]))

    def test_rating_weighted_by_reviews(self):
        self.assertLess(f.bayes_rating(5.0, 4), f.bayes_rating(4.6, 900))

    def test_language_and_fee_filters(self):
        r = f.search(origin("Bengaluru"), language="Malayalam", max_fee=400, now=NOON_WED)
        for d in r["results"]:
            self.assertIn("Malayalam", d["languages"])
            self.assertLessEqual(d["feeInr"], 400)

    def test_far_specialist_offers_nearby_gp(self):
        r = f.search(origin("Kalpetta"), "Nephrologist", now=NOON_WED)
        self.assertTrue(r["nearbyGp"])
        self.assertTrue(all(d["distanceKm"] <= 40 for d in r["nearbyGp"]))


class QueryTests(unittest.TestCase):
    def test_parse(self):
        q = f.parse_query("Malayalam speaking heart doctor near Kakkanad open sunday under 500 rs")
        self.assertEqual(q, {"specialty": "Cardiologist", "language": "Malayalam", "day": "sun", "maxFee": 500, "city": "Kakkanad"})

    def test_short_words_are_whole_words(self):
        self.assertNotIn("specialty", f.parse_query("early appointment please"))  # "ear" in "early"
        self.assertEqual(f.parse_query("ear pain")["specialty"], "ENT specialist")

    def test_emergency_words(self):
        q = f.parse_query("chest pain right now")
        self.assertTrue(q.get("emergency"))

    def test_ai_parse_without_key_is_empty(self):
        self.assertEqual(doctor_ai.parse("kidney doctor"), {})


class ExplainTests(unittest.TestCase):
    def test_fallback_explains_every_pick_with_real_facts(self):
        r = f.search(origin("Kochi"), "Cardiologist", now=NOON_WED)
        picks = doctor_ai.explain(r["results"], {"need": "High blood pressure", "language": "Malayalam"})
        self.assertEqual([p["id"] for p in picks], [d["id"] for d in r["results"][:3]])
        for p, d in zip(picks, r["results"]):
            self.assertIn(f"{d['distanceKm']:g} km", p["why"])
            self.assertIn(str(d["rating"]), p["why"])
            self.assertEqual(p["source"], "rules")


if __name__ == "__main__":
    unittest.main()
