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
        self.assertEqual(rss._parse("refresh 45m"), ("refresh-period", {"minutes": 45}))

    def test_refine_defaults_and_bounds(self):
        self.assertEqual(rss._parse("refine"), ("refine", {"days": 30}))
        self.assertEqual(rss._parse("refine 14d"), ("refine", {"days": 14}))
        with self.assertRaises(ValueError):
            rss._parse("refine 366d")

    def test_mute_and_add_scope(self):
        self.assertEqual(rss._parse("mute model spam"), ("mute", {"phrase": "model spam"}))
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

        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "commands.jsonl"
            with patch.object(rss, "_queue_path", return_value=queue):
                message = rss._handle("refresh 20m")
            self.assertIn("20 minutes", message)
            row = json.loads(queue.read_text(encoding="utf-8"))
            self.assertEqual(row["action"], "refresh-period")
            self.assertEqual(row["payload"], {"minutes": 20})
            self.assertTrue(row["id"])
    def test_refresh_transport_avoids_python_exec_flags(self):
        plugin = (_ENTRYPOINT.parent / "desktop" / "plugin.js").read_text(encoding="utf-8")
        self.assertIn("var rssRest = null", plugin)
        self.assertIn("rssRest = typeof ctx.rest === \"function\" ? ctx.rest : null", plugin)
        self.assertIn('rssRest("/commands"', plugin)
        self.assertIn('rssRest("/feed"', plugin)
        self.assertIn('rssRest("/reddit"', plugin)
        self.assertIn("Newswire starters", plugin)
        self.assertIn("Popular Reddit", plugin)
        self.assertIn("className: \"rss-subscribe-pill\"", plugin)
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


if __name__ == "__main__":
    unittest.main()
