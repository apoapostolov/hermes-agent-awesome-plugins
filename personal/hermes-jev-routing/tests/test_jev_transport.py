"""The Jev HTTP transport with the socket replaced by a recorder.

Cloudflare's Browser Integrity Check answers urllib's default client signature
with HTTP 403 error 1010, which fail-opens every turn and leaves routing dead.
These cover the header that prevents it, not a live request.
"""

from __future__ import annotations

import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jev import JevError, urllib_transport  # noqa: E402

ENDPOINT = "https://opencode.ai/zen/v1/systemone"


class _Response:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _Recorder:
    """Stands in for urlopen: keeps every Request and answers a canned body."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.payload = {"answers": {}} if payload is None else payload
        self.error = error
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return _Response(self.payload)


class TransportTests(unittest.TestCase):
    def _record(self, headers: dict[str, str]) -> urllib.request.Request:
        recorder = _Recorder()
        with mock.patch("urllib.request.urlopen", recorder):
            urllib_transport(ENDPOINT, headers, {"state": {}, "model": "jev-latest"}, 2.0)
        self.assertEqual(1, len(recorder.requests))
        return recorder.requests[0]

    def test_transport_names_itself_instead_of_python_urllib(self):
        request = self._record({"Authorization": "Bearer key", "Content-Type": "application/json"})
        agent = request.get_header("User-agent")
        self.assertIsNotNone(agent)
        self.assertIn("hermes-jev-routing", agent)
        self.assertNotIn("Python-urllib", agent)

    def test_transport_keeps_a_caller_supplied_agent(self):
        request = self._record({"User-Agent": "curl/8.7.1"})
        self.assertEqual("curl/8.7.1", request.get_header("User-agent"))

    def test_transport_sends_the_key_and_the_body(self):
        request = self._record({"Authorization": "Bearer key", "Content-Type": "application/json"})
        self.assertEqual("Bearer key", request.get_header("Authorization"))
        self.assertEqual("POST", request.get_method())
        self.assertEqual(
            {"state": {}, "model": "jev-latest"},
            json.loads(request.data.decode("utf-8")),
        )

    def test_http_status_and_body_reach_the_caller(self):
        error = urllib.error.HTTPError(ENDPOINT, 403, "Forbidden", {}, None)
        error.read = lambda: b'error code: 1010'
        recorder = _Recorder(error=error)
        with mock.patch("urllib.request.urlopen", recorder):
            with self.assertRaises(JevError) as caught:
                urllib_transport(ENDPOINT, {"Authorization": "Bearer key"}, {}, 2.0)
        self.assertEqual(403, caught.exception.status)
        self.assertIn("error code: 1010", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
