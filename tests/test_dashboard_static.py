"""Static serving: files in the Vite dist root (favicon, /brand/*) are returned; unknown paths get the SPA shell."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import main  # noqa: E402


class StaticTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        (root / "secret.txt").write_text("secret")  # outside dist: must never be served
        dist = root / "dist"
        (dist / "brand").mkdir(parents=True)
        (dist / "index.html").write_text("<html>shell</html>")
        (dist / "favicon.ico").write_bytes(b"ico")
        (dist / "brand" / "pertamina-retail-logo.png").write_bytes(b"png")
        patcher = mock.patch.object(main, "DIST", dist)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)

    def test_dist_files_are_served(self):
        res = self.client.get("/favicon.ico")
        self.assertEqual((res.status_code, res.content), (200, b"ico"))
        res = self.client.get("/brand/pertamina-retail-logo.png")
        self.assertEqual((res.status_code, res.content), (200, b"png"))

    def test_unknown_path_gets_spa_shell(self):
        res = self.client.get("/site/24.351.97")
        self.assertEqual((res.status_code, res.text), (200, "<html>shell</html>"))

    def test_path_traversal_gets_spa_shell(self):
        res = self.client.get("/..%2fsecret.txt")
        self.assertEqual((res.status_code, res.text), (200, "<html>shell</html>"))
        self.assertNotIn("secret", res.text)

    def test_unknown_api_path_is_not_the_spa_shell(self):
        res = self.client.get("/api/nope")
        self.assertEqual(res.status_code, 404)
        self.assertNotIn("shell", res.text)


if __name__ == "__main__":
    unittest.main()
