"""Dashboard password gate. TestClient over https so the Secure cookie is sent; no BigQuery."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import auth  # noqa: E402
from dashboard.api.main import app  # noqa: E402

PASSWORD = "correct horse"


class AuthTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": PASSWORD, "MAPS_BROWSER_KEY": "k"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app, base_url="https://testserver")

    def login(self, password=PASSWORD):
        return self.client.post("/api/login", json={"password": password})

    def test_health_is_open(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_api_requires_session(self):
        self.assertEqual(self.client.get("/api/config").status_code, 401)
        self.assertEqual(self.client.get("/api/traffic/latest").status_code, 401)

    def test_right_password_sets_cookie_and_opens_api(self):
        res = self.login()
        self.assertEqual(res.status_code, 204)
        header = res.headers["set-cookie"].lower()
        for attr in ("httponly", "secure", "samesite=lax", f"max-age={7 * 24 * 3600}"):
            self.assertIn(attr, header)
        self.assertEqual(self.client.get("/api/config").json(), {"maps_browser_key": "k"})

    def test_wrong_password_is_401_without_cookie(self):
        res = self.login("nope")
        self.assertEqual(res.status_code, 401)
        self.assertNotIn("set-cookie", res.headers)
        self.assertEqual(self.client.get("/api/config").status_code, 401)

    def test_login_closed_when_password_unset(self):
        with mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": ""}):
            self.assertEqual(self.login("").status_code, 401)

    def test_expired_cookie_is_401(self):
        long_ago = time.time() - auth.SESSION_SECONDS - 10
        self.client.cookies.set("session", auth.make_cookie(now=long_ago))
        self.assertEqual(self.client.get("/api/config").status_code, 401)

    def test_tampered_cookie_is_401(self):
        expiry, sig = auth.make_cookie().split(".")
        for bad in (f"{int(expiry) + 3600}.{sig}", f"{expiry}.{'0' * len(sig)}", "garbage", f"{expiry}."):
            self.client.cookies.clear()
            self.client.cookies.set("session", bad)
            self.assertEqual(self.client.get("/api/config").status_code, 401, bad)
        # Starlette decodes cookies as latin-1; non-ASCII must fail closed, not raise
        self.assertFalse(auth.valid_cookie(f"{expiry}.é"))

    def test_cookie_signed_with_another_password_is_401(self):
        with mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "other"}):
            cookie = auth.make_cookie()
        self.client.cookies.set("session", cookie)
        self.assertEqual(self.client.get("/api/config").status_code, 401)

    def test_unknown_api_path_is_not_the_spa(self):
        self.login()
        res = self.client.get("/api/nope")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.headers["content-type"], "application/json")


if __name__ == "__main__":
    unittest.main()
