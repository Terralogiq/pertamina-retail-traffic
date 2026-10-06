"""Unit tests for collector/httpjson.py: key scrubbing and retry policy.

`urllib.request.urlopen` and `time.sleep` are patched; no network.
"""
import io
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "collector"))

import httpjson  # noqa: E402

KEY = "AIzaFAKEKEY1234567890"
URL = "https://example.test/v1/thing"


def http_error(code, body=""):
    return urllib.error.HTTPError(URL, code, "err", {}, io.BytesIO(body.encode()))


class OkResponse:
    def __init__(self, body=b'{"ok": true}'):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def call(side_effect, **kw):
    """Run request_json against a scripted urlopen; return (result, urlopen mock, sleep mock)."""
    with mock.patch("urllib.request.urlopen", side_effect=side_effect) as uo, \
            mock.patch("time.sleep") as sl:
        return httpjson.request_json("POST", URL, {}, {"a": 1}, secret=KEY, **kw), uo, sl


class TestScrubbing(unittest.TestCase):
    def test_http_error_body_with_key_is_scrubbed(self):
        body = f"API key not valid: {KEY}. Please pass a valid key."
        (resp, err), _, _ = call([http_error(400, body)])
        self.assertIsNone(resp)
        self.assertIn("***", err)
        self.assertNotIn(KEY, err)

    def test_url_error_reason_with_key_is_scrubbed(self):
        exc = urllib.error.URLError(f"failed to reach {URL}?key={KEY}")
        (resp, err), _, _ = call([exc, exc, exc])
        self.assertIsNone(resp)
        self.assertIn("***", err)
        self.assertNotIn(KEY, err)


class TestRetry(unittest.TestCase):
    def test_429_then_200_succeeds(self):
        (resp, err), uo, sl = call([http_error(429), OkResponse()])
        self.assertEqual((resp, err), ({"ok": True}, None))
        self.assertEqual(uo.call_count, 2)
        sl.assert_called_once_with(1)

    def test_503_503_200_succeeds(self):
        (resp, err), uo, sl = call([http_error(503), http_error(503), OkResponse()])
        self.assertEqual((resp, err), ({"ok": True}, None))
        self.assertEqual(uo.call_count, 3)
        self.assertEqual([c.args[0] for c in sl.call_args_list], [1, 2])

    def test_persistent_503_gives_up_after_three_attempts(self):
        (resp, err), uo, _ = call([http_error(503)] * 3)
        self.assertIsNone(resp)
        self.assertTrue(err.startswith("HTTP 503"))
        self.assertEqual(uo.call_count, 3)

    def test_400_and_403_are_not_retried(self):
        for code in (400, 403):
            with self.subTest(code=code):
                (resp, err), uo, sl = call([http_error(code, "nope")])
                self.assertIsNone(resp)
                self.assertTrue(err.startswith(f"HTTP {code}"))
                self.assertEqual(uo.call_count, 1)
                sl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
