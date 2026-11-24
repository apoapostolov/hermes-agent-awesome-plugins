"""Tests for the RSS Reader fetch path (dashboard/plugin_api.py).

Runs ``_read_response`` against fake responses so no socket is opened. Both
editions are parametrised, because the two ``dashboard/plugin_api.py`` files are
byte-identical and one copy must not drift from the other.
Requires fastapi + pytest:
``python -m pytest personal/rss-reader/tests -q``
"""

from __future__ import annotations

import gzip
import importlib.util
import random
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parents[3]
EDITIONS = {
    "personal": REPO / "personal" / "rss-reader" / "dashboard" / "plugin_api.py",
    "public": REPO / "public" / "rss-reader" / "dashboard" / "plugin_api.py",
}
FEED = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<rss version="2.0"><channel><title>Hermes QA</title></channel></rss>'
)


class FakeHeaders:
    def __init__(self, encoding: str | None = None, charset: str | None = None) -> None:
        self.encoding = encoding
        self.charset = charset

    def get(self, name: str, default=None):
        if str(name).lower() == "content-encoding":
            return self.encoding if self.encoding is not None else default
        return default

    def get_content_charset(self, default=None):
        return self.charset or default


class FakeResponse:
    def __init__(self, payload: bytes, encoding: str | None = None) -> None:
        self.payload = payload
        self.offset = 0
        self.status = 200
        self.headers = FakeHeaders(encoding=encoding, charset=None)

    def read(self, size: int = -1) -> bytes:
        end = len(self.payload) if size is None or size < 0 else min(len(self.payload), self.offset + size)
        chunk = self.payload[self.offset:end]
        self.offset = end
        return chunk


@pytest.fixture(params=sorted(EDITIONS))
def plugin_api(request):
    path = EDITIONS[request.param]
    spec = importlib.util.spec_from_file_location(f"rss_reader_plugin_api_{request.param}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gzip_body_is_decompressed(plugin_api):
    """A Content-Encoding: gzip feed must arrive as the XML the server sent."""
    body = plugin_api._read_response(FakeResponse(gzip.compress(FEED), encoding="gzip"))
    assert body == FEED
    assert body.startswith(b"<?xml")
    assert "\ufffd" not in body.decode("utf-8")


def test_gzip_magic_bytes_are_decompressed_without_the_header(plugin_api):
    """Some servers compress while ignoring the identity request header."""
    body = plugin_api._read_response(FakeResponse(gzip.compress(FEED), encoding=None))
    assert body == FEED


def test_double_gzip_body_is_decompressed_twice(plugin_api):
    """A proxy may re-encode an already compressed body as `gzip, gzip`."""
    payload = gzip.compress(gzip.compress(FEED))
    body = plugin_api._read_response(FakeResponse(payload, encoding="gzip, gzip"))
    assert body == FEED


def test_one_declared_layer_still_undoes_every_layer_the_body_carries(plugin_api):
    """A header that names gzip once must not leave a second layer behind."""
    payload = gzip.compress(gzip.compress(FEED))
    body = plugin_api._read_response(FakeResponse(payload, encoding="gzip, identity"))
    assert body == FEED


def test_a_compressed_body_over_the_limit_with_a_small_feed_is_accepted(plugin_api):
    """The 2 MB limit applies to the feed, never to what came over the wire.

    Incompressible bytes make gzip grow the body, so this transfer is larger
    than the feed limit while the feed itself sits under it.
    """
    feed = random.Random(0).randbytes(plugin_api._MAX_BYTES - 10)
    payload = gzip.compress(feed)
    assert len(payload) > plugin_api._MAX_BYTES, "gzip must grow incompressible bytes here"
    assert len(feed) < plugin_api._MAX_BYTES
    assert plugin_api._read_response(FakeResponse(payload, encoding="gzip")) == feed


def test_the_wire_ceiling_still_bounds_the_read(plugin_api):
    oversized = b"x" * (plugin_api._MAX_COMPRESSED_BYTES + 1)
    with pytest.raises(ValueError, match="2 MB"):
        plugin_api._read_response(FakeResponse(oversized))


def test_stacked_layers_stop_at_the_layer_ceiling(plugin_api):
    payload = FEED
    for _ in range(plugin_api._MAX_LAYERS + 1):
        payload = gzip.compress(payload)
    with pytest.raises(ValueError, match="layers"):
        plugin_api._read_response(FakeResponse(payload, encoding="gzip"))


def test_identity_body_is_returned_untouched(plugin_api):
    body = plugin_api._read_response(FakeResponse(FEED, encoding="identity"))
    assert body == FEED


def test_size_limit_applies_to_the_decompressed_bytes(plugin_api):
    payload = gzip.compress(b"<rss>" + b"x" * (plugin_api._MAX_BYTES + 10) + b"</rss>")
    assert len(payload) < plugin_api._MAX_BYTES, "the bomb must arrive compressed"
    with pytest.raises(ValueError, match="2 MB"):
        plugin_api._read_response(FakeResponse(payload, encoding="gzip"))


def test_broken_gzip_body_fails_as_a_value_error(plugin_api):
    with pytest.raises(ValueError, match="gzip"):
        plugin_api._read_response(FakeResponse(b"this is not gzip", encoding="gzip"))


def test_truncated_gzip_body_fails_as_a_value_error(plugin_api):
    with pytest.raises(ValueError, match="gzip"):
        plugin_api._read_response(FakeResponse(gzip.compress(FEED)[:12], encoding="gzip"))
