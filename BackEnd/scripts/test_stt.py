"""Speech-to-text logic tests. No network, no database writes.

    cd BackEnd && ./venv/bin/python -W ignore scripts/test_stt.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import medterms, transcribe  # noqa: E402
from app.routers.consultations import _sniff_audio  # noqa: E402


class WhisperFilter(unittest.TestCase):
    def seg(self, text, nsp=0.02, lp=-0.2, cr=1.3):
        return {"text": text, "no_speech_prob": nsp, "avg_logprob": lp, "compression_ratio": cr}

    def test_real_speech_kept(self):
        self.assertTrue(transcribe._keep_segment(self.seg(" Start Glycomet 500 twice daily.")))

    def test_phantom_phrase_on_silence_dropped(self):
        self.assertFalse(transcribe._keep_segment(self.seg(" Thank you.", nsp=0.9, lp=-1.4)))

    def test_phantom_phrase_dropped_even_if_confident(self):
        self.assertFalse(transcribe._keep_segment(self.seg("Thanks for watching")))

    def test_repetition_loop_dropped(self):
        self.assertFalse(transcribe._keep_segment(self.seg("ha ha ha ha ha ha", cr=3.1)))

    def test_empty_dropped(self):
        self.assertFalse(transcribe._keep_segment(self.seg("   ")))

    def test_prompt_has_patient_meds_first_and_is_short(self):
        p = transcribe.build_prompt(["Telma", "Atorva"])
        self.assertIn("Telma", p)
        self.assertLess(p.index("Telma"), p.index("Glycomet"))
        self.assertLessEqual(len(p), 400)


class MedicineCorrection(unittest.TestCase):
    def fix(self, text, meds=None):
        return medterms.correct(text, meds or [])

    def test_misheard_indian_brand_fixed(self):
        out, fx = self.fix("Start glycum at 500 mg twice daily.")
        self.assertIn("Glycomet", out)
        self.assertEqual(fx[0]["from"], "glycum")

    def test_misspelled_generic_fixed(self):
        out, _ = self.fix("Continue clarithromicin 500 mg twice daily.")
        self.assertIn("clarithromycin", out)

    def test_patient_own_medicine_fixed(self):
        out, _ = self.fix("Take atorvastin 20 mg at night.", ["Atorvastatin"])
        self.assertIn("tor", out.lower())

    def test_no_prescribing_context_untouched(self):
        text = "How is your sugar and the surgery recovery going?"
        self.assertEqual(self.fix(text), (text, []))

    def test_ordinary_words_untouched(self):
        text = "Take rest, drink water, tablet after dinner tonight."
        self.assertEqual(self.fix(text), (text, []))

    def test_already_correct_untouched(self):
        text = "The morning dose of Glycomet 500 mg is fine."
        self.assertEqual(self.fix(text), (text, []))

    def test_person_name_never_becomes_a_drug(self):
        text = "Prescribe Deepa a tablet for the cough twice daily."
        self.assertEqual(self.fix(text), (text, []))


class AudioSniff(unittest.TestCase):
    def test_known_formats(self):
        self.assertEqual(_sniff_audio(b"\x1aE\xdf\xa3" + b"0" * 12)[1], "webm")
        self.assertEqual(_sniff_audio(b"OggS" + b"0" * 12)[1], "ogg")
        self.assertEqual(_sniff_audio(b"RIFF\x00\x00\x00\x00WAVE" + b"0" * 4)[1], "wav")
        self.assertEqual(_sniff_audio(b"\x00\x00\x00\x18ftypM4A " + b"0" * 4)[1], "m4a")

    def test_not_audio_rejected(self):
        self.assertIsNone(_sniff_audio(b"<html>not audio.."))


if __name__ == "__main__":
    unittest.main()
