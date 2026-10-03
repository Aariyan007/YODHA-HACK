"""Tests for the interaction lookup (DDInter) and how ai/safety.py uses it.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_ddi.py -v
Needs data/ddi/ddi.sqlite (python scripts/build_ddi.py). Without it the DDInter cases are skipped.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import ddi, safety

HAVE_DB = ddi.available()
need_db = unittest.skipUnless(HAVE_DB, "run scripts/build_ddi.py first")


class DdiTests(unittest.TestCase):
    def test_synonyms_are_normalised(self):
        self.assertEqual(ddi.normalise("  Aspirin "), "acetylsalicylic acid")
        self.assertEqual(ddi.normalise("Paracetamol"), "acetaminophen")
        self.assertEqual(ddi.normalise("Metformin"), "metformin")

    @need_db
    def test_lookup_works_in_both_orders(self):
        self.assertEqual(ddi.level("clarithromycin", "atorvastatin"), "Major")
        self.assertEqual(ddi.level("atorvastatin", "clarithromycin"), "Major")

    @need_db
    def test_indian_names_reach_the_us_names(self):
        self.assertEqual(ddi.level("aspirin", "warfarin"), ddi.level("acetylsalicylic acid", "warfarin"))
        self.assertIsNotNone(ddi.level("aspirin", "warfarin"))

    @need_db
    def test_unknown_drug_and_unknown_pair_return_none(self):
        self.assertIsNone(ddi.level("notarealdrug", "metformin"))
        self.assertFalse(ddi.known_drug("notarealdrug"))
        self.assertTrue(ddi.known_drug("metformin"))

    @need_db
    def test_dataset_is_big_and_attributed(self):
        info = ddi.info()
        self.assertGreater(int(info["pairs"]), 100_000)
        self.assertIn("CC BY-NC-SA", info["license"])

    # ---- how safety.py uses it
    def test_curated_message_wins_over_the_dataset(self):
        sev, msg = safety.check_pair_level("clarithromycin", "atorvastatin")
        self.assertEqual(sev, "high")
        self.assertNotIn("DDInter", msg)  # the hand-written patient text, not the generic one

    @need_db
    def test_major_from_dataset_is_high_and_moderate_is_medium(self):
        majors = [(a, b) for a, b in [("amlodipine", "simvastatin"), ("ibuprofen", "warfarin")] if ddi.level(a, b) == "Major"]
        self.assertTrue(majors)
        for a, b in majors:
            if (tuple(sorted((a, b)))) not in safety.PAIRS:
                self.assertEqual(safety.check_pair_level(a, b)[0], "high")
        self.assertEqual(ddi.level("metformin", "clarithromycin"), "Moderate")
        self.assertEqual(safety.check_pair_level("metformin", "clarithromycin")[0], "medium")
        self.assertIn("moderate", safety.check_pair_level("metformin", "clarithromycin")[1])

    @need_db
    def test_pair_nobody_knows_gives_no_alert(self):
        self.assertIsNone(safety.check_pair_level("notarealdrug", "metformin"))
        self.assertIsNone(safety.check_pair("zzz-unknown", "yyy-unknown"))

    def test_without_the_database_the_curated_rules_still_work(self):
        with mock.patch.object(ddi, "level", lambda a, b: None):
            self.assertEqual(safety.check_pair_level("clarithromycin", "atorvastatin")[0], "high")
            self.assertIsNone(safety.check_pair_level("metformin", "clarithromycin"))

    @need_db
    def test_analyse_reports_dataset_clashes_with_their_severity(self):
        out = safety.analyse(patient_name="T", patient_allergies=[], existing_medicines=[{"name": "Glycomet 500", "generic": "metformin"}],
                             new_medicines=[{"name": "Clarithromycin 500", "generic": "clarithromycin"}], observations=[])
        clash = [a for a in out["alerts"] if a["kind"] == "clash"]
        self.assertEqual(len(clash), 1)
        self.assertEqual(clash[0]["severity"], "medium")  # Moderate in DDInter


if __name__ == "__main__":
    unittest.main()
