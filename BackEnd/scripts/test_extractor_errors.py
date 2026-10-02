"""The upload error text must say what is actually wrong. Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_extractor_errors.py -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai.extractor import explain_error


class E(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.code = code


class Tests(unittest.TestCase):
    def test_quota(self):
        self.assertIn("free limit", explain_error(E(429, "RESOURCE_EXHAUSTED")))

    def test_bad_key(self):
        self.assertIn("GEMINI_API_KEY", explain_error(E(400, "API key not valid. Please pass a valid API key.")))
        self.assertIn("GEMINI_API_KEY", explain_error(E(403, "PERMISSION_DENIED")))

    def test_missing_model(self):
        self.assertIn("model", explain_error(E(404)))

    def test_busy_and_timeout(self):
        self.assertIn("busy", explain_error(E(503)))
        self.assertIn("too long", explain_error(TimeoutError("timed out")))

    def test_unknown_keeps_the_class_name(self):
        self.assertIn("ValueError", explain_error(ValueError("boom")))

    def test_message_never_contains_the_raw_error_text(self):
        self.assertNotIn("sk-secret", explain_error(E(400, "API key sk-secret not valid")))


if __name__ == "__main__":
    unittest.main()
