"""Static frontend serving for single service hosting. No network.

Run: cd BackEnd && ./venv/bin/python -W ignore scripts/test_static_site.py -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import static_site


class Static(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "site"
        (root / "assets").mkdir(parents=True)
        (root / "index.html").write_text("<html>APP</html>")
        (root / "assets" / "a.js").write_text("console.log(1)")
        (root / "favicon.svg").write_text("<svg/>")
        (Path(self.tmp.name) / "secret.txt").write_text("outside the site folder")
        env = mock.patch.dict(os.environ, {"STATIC_DIR": str(root)})
        env.start()
        self.addCleanup(env.stop)
        app = FastAPI()

        @app.get("/api/ping")
        def ping():
            return {"ok": True}

        self.assertTrue(static_site.mount(app))
        self.c = TestClient(app)

    def test_pages_and_assets(self):
        self.assertIn("APP", self.c.get("/").text)
        self.assertIn("APP", self.c.get("/timeline").text)          # a client-side route gets the app
        self.assertIn("APP", self.c.get("/console/abc123").text)
        self.assertEqual(self.c.get("/assets/a.js").text, "console.log(1)")
        self.assertEqual(self.c.get("/favicon.svg").text, "<svg/>")

    def test_api_is_never_answered_with_the_page(self):
        self.assertEqual(self.c.get("/api/ping").json(), {"ok": True})
        r = self.c.get("/api/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("APP", r.text)

    def test_cannot_read_outside_the_folder(self):
        for p in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/assets/../../secret.txt"):
            self.assertNotIn("outside the site folder", self.c.get(p).text, p)

    def test_security_headers_and_no_cache_for_the_page(self):
        r = self.c.get("/")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertEqual(r.headers["x-frame-options"], "DENY")
        self.assertEqual(r.headers["cache-control"], "no-cache")

    def test_off_when_there_is_no_build(self):
        with mock.patch.dict(os.environ, {"STATIC_DIR": "/nonexistent"}):
            self.assertFalse(static_site.mount(FastAPI()))


if __name__ == "__main__":
    unittest.main()
