"""Hosting boundaries, using isolated temporary data and no participant recordings.

Run: python3 -m unittest discover -s tests -v
"""
import base64
import copy
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SANDBOX = tempfile.TemporaryDirectory(prefix="umuse-hosting-test-")
HOME = Path(SANDBOX.name)
TEST_ENV = {
    "UMUSE_HOSTED": "1", "UMUSE_DATA_DIR": str(HOME),
    "UMUSE_VAULT": str(HOME / "vault"), "UMUSE_USERNAME": "researcher",
    "UMUSE_PASSWORD": "test-only-password-at-least-24-characters",
}


class HostingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, TEST_ENV)
        cls.env.start()
        cls.module = importlib.import_module("web.app")
        cls.client = cls.module.app.test_client()
        cls.auth = {"Authorization": "Basic " + base64.b64encode(
            f"{TEST_ENV['UMUSE_USERNAME']}:{TEST_ENV['UMUSE_PASSWORD']}".encode()).decode()}

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        SANDBOX.cleanup()

    def test_private_routes_and_assets_require_sign_in(self):
        for path in ["/", "/reading/p01", "/results/p01", "/static/reading.js", "/analyze"]:
            response = self.client.post(path) if path == "/analyze" else self.client.get(path)
            self.assertEqual(response.status_code, 401, path)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        bad = "Basic " + base64.b64encode(b"researcher:wrong").decode()
        self.assertEqual(self.client.get("/", headers={"Authorization": bad}).status_code, 401)

    def test_health_is_public_and_page_explains_upload_destination(self):
        self.assertEqual(self.client.get("/healthz").json, {"status": "ok"})
        response = self.client.get("/", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"uploaded to this private uMuse server", response.data)
        self.assertNotIn(b"analysis runs on this computer", response.data)
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_upload_validation_and_cross_site_protection(self):
        self.assertEqual(self.client.post("/analyze", headers=self.auth).status_code, 400)
        response = self.client.post("/analyze", headers=self.auth,
                                    data={"audio": (io.BytesIO(b"not music"), "track.exe")})
        self.assertEqual(response.status_code, 415)
        response = self.client.post("/analyze", headers={**self.auth, "Origin": "https://other.example"})
        self.assertEqual(response.status_code, 403)
        with patch.dict(self.module.app.config, {"MAX_CONTENT_LENGTH": 100}):
            response = self.client.post("/analyze", headers=self.auth,
                                        data={"audio": (io.BytesIO(b"x" * 1000), "track.wav")})
        self.assertEqual(response.status_code, 413)

    def test_upload_deduplicates_and_reads_from_configured_storage(self):
        # Synthetic unavailable fixture is API plumbing, not an acoustic accuracy test.
        unavailable = {"available": False, "reason_if_unavailable": "Not measured in this API test."}
        data = {"track": {"code": "p01", "duration_seconds": 30,
                          "analysed_on": "2026-11-07", "pipeline": "Synthetic API test; no musical findings."},
                "music": {k: copy.deepcopy(unavailable) for k in ["harmony", "structure", "groove", "melody"]},
                "comparisons": copy.deepcopy(unavailable), "population_context": copy.deepcopy(unavailable)}
        self.assertEqual(self.module.check(data), [])
        with patch.object(self.module, "readable"), patch.object(self.module, "run", return_value=(data, [])):
            responses = [self.client.post("/analyze", headers=self.auth,
                         data={"audio": (io.BytesIO(b"synthetic test recording"), "test.wav"),
                               "title": "Synthetic test"}) for _ in range(2)]
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertFalse(responses[0].json["existing"])
        self.assertTrue(responses[1].json["existing"])
        self.assertEqual(responses[0].json["code"], responses[1].json["code"])
        self.assertTrue((HOME / "vault/audio/p01.wav").is_file())
        (HOME / "results").mkdir(exist_ok=True)
        (HOME / "results/p01.json").write_text(json.dumps(data))
        self.assertEqual(self.client.get("/results/p01", headers=self.auth).json["data"], data)
        data["track"]["duration_seconds"] = -1
        (HOME / "results/p01.json").write_text(json.dumps(data))
        self.assertEqual(self.client.get("/results/p01", headers=self.auth).status_code, 422)

    def test_busy_and_private_error_details(self):
        self.module.busy.acquire()
        try:
            response = self.client.post("/analyze", headers=self.auth,
                data={"audio": (io.BytesIO(b"test"), "test.wav")})
            self.assertEqual(response.status_code, 409)
        finally:
            self.module.busy.release()
        with patch.object(self.module, "readable", side_effect=RuntimeError("private/path/track.wav")):
            response = self.client.post("/analyze", headers=self.auth,
                data={"audio": (io.BytesIO(b"test"), "test.wav")})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b"private/path", response.data)

    def test_hosted_startup_fails_without_credentials(self):
        env = {**os.environ, "UMUSE_HOSTED": "1", "UMUSE_PASSWORD": ""}
        run = subprocess.run([sys.executable, "-c", "import web.app"], env=env, capture_output=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn(b"Hosted uMuse requires", run.stderr)
