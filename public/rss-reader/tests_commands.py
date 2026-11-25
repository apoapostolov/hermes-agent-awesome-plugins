import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_ENTRYPOINT = Path(__file__).with_name("__init__.py")
_SPEC = importlib.util.spec_from_file_location("rss_reader_entrypoint", _ENTRYPOINT)
rss = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(rss)


class RssCommandTests(unittest.TestCase):
    def test_refresh_forms(self):
        self.assertEqual(rss._parse("refresh"), ("refresh", {}))
        self.assertEqual(rss._parse("refresh 30m"), ("refresh-period", {"minutes": 30}))

    def test_refine_defaults_and_bounds(self):
        self.assertEqual(rss._parse("refine"), ("refine", {"days": 30}))
        self.assertEqual(rss._parse("refine 14d"), ("refine", {"days": 14}))
        self.assertEqual(rss._parse("refine starred"), ("refine-starred", {}))
        self.assertEqual(rss._parse("refine stars"), ("refine-starred", {}))
        with self.assertRaises(ValueError):
            rss._parse("refine 366d")

    def test_mute_and_add_scope(self):
        self.assertEqual(rss._parse("mute model spam"), ("add-filter", {"kind": "keyword", "phrase": "model spam"}))
        self.assertEqual(
            rss._parse("add example.com, Example to Research"),
            ("add", {"source": "example.com, Example", "folder": "Research"}),
        )
        self.assertEqual(
            rss._parse("add example.com"),
            ("add", {"source": "example.com", "folder": ""}),
        )

    def test_mark_read_digest_and_health_forms(self):
        self.assertEqual(rss._parse("mark-read all"), ("mark-read", {"scope": "all"}))
        self.assertEqual(
            rss._parse("mark-read folder Research"),
            ("mark-read", {"scope": "folder", "target": "Research"}),
        )
        self.assertEqual(
            rss._parse("mark-read feed Daily News"),
            ("mark-read", {"scope": "feed", "target": "Daily News"}),
        )
        self.assertEqual(
            rss._parse("digest unread 7d"),
            ("digest", {"scope": "unread", "days": 7}),
        )
        self.assertEqual(
            rss._parse("digest unread"),
            ("digest", {"scope": "unread", "days": None}),
        )
        self.assertEqual(rss._parse("digest saved"), ("digest", {"scope": "saved"}))
        self.assertEqual(rss._parse("health"), ("health", {}))
        with self.assertRaises(ValueError):
            rss._parse("mark-read")
        with self.assertRaises(ValueError):
            rss._parse("digest unread 366d")
        with self.assertRaises(ValueError):
            rss._parse("health now")

        message = rss._handle("refresh 30m")
        self.assertIn("30 minutes", message)
        self.assertEqual(rss._LAST_EVENT["event"], "plugin.rss-reader.command")
        self.assertEqual(rss._LAST_EVENT["payload"]["action"], "refresh-period")
        self.assertEqual(rss._LAST_EVENT["payload"]["payload"], {"minutes": 30})
        self.assertTrue(rss._LAST_EVENT["payload"]["id"])
    def test_refresh_transport_avoids_python_exec_flags(self):
        plugin = (_ENTRYPOINT.parent / "desktop" / "plugin.js").read_text(encoding="utf-8")
        self.assertIn("var rssRest = null", plugin)
        self.assertIn("rssRest = typeof ctx.rest === \"function\" ? ctx.rest : null", plugin)
        self.assertIn('onEvent("plugin.rss-reader.command"', plugin)
        self.assertIn('rssRest("/feed"', plugin)
        self.assertIn('rssRest("/reddit"', plugin)
        self.assertIn("Popular starters", plugin)
        self.assertIn("Popular Reddit", plugin)
        self.assertIn("className: \"rss-subscribe-pill\"", plugin)
        self.assertIn("function expandSubscribeUrl", plugin)
        self.assertIn("async function runLearnInterests", plugin)
        self.assertIn("Search, or provide RSS or Atom URL, or r/name Reddit community", plugin)
        self.assertIn("https://www.reddit.com/r/", plugin)
        self.assertNotIn("Test-Path -LiteralPath", plugin)
        self.assertNotIn("Get-Content -Raw -LiteralPath", plugin)
        self.assertNotIn("Resolve-DnsName", plugin)
        self.assertNotIn("GzipStream", plugin)
        self.assertNotIn("python -c", plugin)
        self.assertNotIn("pythonLiteral", plugin)
        self.assertNotIn("gzip -c", plugin)
        self.assertNotIn("cut -c", plugin)
        self.assertNotIn("powershell.exe", plugin)
        self.assertNotIn("EncodedCommand", plugin)
        self.assertNotIn("shell.exec", plugin)
        self.assertIn('rssRest("/article"', plugin)
        self.assertIn("async function readGradingSkill", plugin)
        self.assertIn("async function syncGradingTags", plugin)
        self.assertIn("async function ensureGradingSkill", plugin)
        self.assertIn('rssRest("/grading-skill"', plugin)
        self.assertNotIn("'$env:TEMP'", plugin)
        self.assertNotIn("captureArticleNow(host2, rawUrl, route, owner, options = {}) {\n  const run", plugin)
        self.assertNotIn("echo %OS%", plugin)
        self.assertNotIn("echo %TEMP%", plugin)


class RssCookieTests(unittest.TestCase):
    def test_youtube_cookie_text_rejects_file_paths(self):
        api_file = Path(__file__).parent / "dashboard" / "plugin_api.py"
        spec = importlib.util.spec_from_file_location("rss_reader_plugin_api", api_file)
        plugin_api = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(plugin_api)

        self.assertEqual(plugin_api._cookie_header("/tmp/cookies=secret.txt"), "")
        self.assertEqual(plugin_api._cookie_header("C:/Users/Apo/cookies=secret.txt"), "")
        self.assertEqual(plugin_api._cookie_header("Cookie: SID=abc; HSID=def"), "SID=abc; HSID=def")
        netscape = "# Netscape HTTP Cookie File" + chr(10) + chr(9).join(
            [".youtube.com", "TRUE", "/", "TRUE", "0", "SID", "secret"]
        )
        self.assertEqual(plugin_api._cookie_header(netscape), "SID=secret")


class RssGzipResponseTests(unittest.TestCase):
    def setUp(self):
        api_file = Path(__file__).parent / "dashboard" / "plugin_api.py"
        spec = importlib.util.spec_from_file_location("rss_reader_plugin_api", api_file)
        self.api = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.api)

    @staticmethod
    def _response(body: bytes, encoding: str | None = None):
        class _Headers(dict):
            def get_content_charset(self):
                return "utf-8"

        class _Response:
            status = 200

            def __init__(self):
                self.headers = _Headers({"Content-Encoding": encoding} if encoding else {})

            def read(self, _size=-1):
                return body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        return _Response()

    def test_identity_body_is_returned_unchanged(self):
        payload = b'<?xml version="1.0"?><rss version="2.0"></rss>'
        self.assertEqual(self.api._read_response(self._response(payload)), payload)

    def test_gzip_body_is_decompressed(self):
        import gzip

        payload = (
            b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<rss version="2.0"><channel><item>ok</item></channel></rss>'
        )
        self.assertEqual(
            self.api._read_response(self._response(gzip.compress(payload), "gzip")),
            payload,
        )

    def test_gzip_over_limit_is_rejected(self):
        import gzip

        payload = b"x" * (self.api._MAX_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "exceeds 2 MB"):
            self.api._read_response(self._response(gzip.compress(payload), "gzip"))

    def test_invalid_gzip_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "declared gzip but the body is not valid gzip"):
            self.api._read_response(self._response(b"not gzip data", "gzip"))

    def test_download_decodes_gzip_feed_to_text(self):
        import gzip

        payload = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel><title>Company Blog</title>'
            '<item><title>One</title></item></channel></rss>'
        ).encode("utf-8")
        response = self._response(gzip.compress(payload), "gzip")
        opener = type("Opener", (), {"open": lambda _self, _req, timeout=None: response})()
        with patch.object(self.api, "build_opener", return_value=opener), patch.object(
            self.api, "_public_addresses", return_value=None
        ):
            result = self.api._download(
                "https://example.com/blog/feed.xml", {"Accept-Encoding": "identity"}
            )
        self.assertEqual(result["status"], 200)
        self.assertIn("<title>Company Blog</title>", result["text"])
        self.assertNotIn("\ufffd", result["text"])


if __name__ == "__main__":
    unittest.main()
