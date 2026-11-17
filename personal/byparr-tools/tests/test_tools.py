"""Dependency-free tests for byparr-tools. Run: python tests/test_tools.py"""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_package():
    spec = importlib.util.spec_from_file_location(
        "byparr_tools_pkg", ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["byparr_tools_pkg"] = module
    spec.loader.exec_module(module)
    return module


pkg = load_package()
from byparr_tools import config, cdp, extract, fallback, jar, queue, schemas, tools  # noqa: E402


class FakeCtx:
    def __init__(self, values=None):
        self.values = values or {}
        self.tools = []

    def get_config(self, key, default=None):
        return self.values.get(key, default)

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_middleware(self, *args, **kwargs):
        self.middleware = args


class RegistrationTests(unittest.TestCase):
    def test_all_tools_registered(self):
        ctx = FakeCtx()
        pkg.register(ctx)
        names = [t["name"] for t in ctx.tools]
        self.assertEqual(len(names), 9)
        for name, _ in schemas.TOOLS:
            self.assertIn(name, names)

    def test_no_host_specific_constants(self):
        banned = ("192.168.", "Bedroom", "theap", "192.168.1.217")
        sources = [ROOT / "__init__.py", ROOT / "plugin.yaml"]
        sources += list((ROOT / "byparr_tools").glob("*.py"))
        for path in sources:
            text = path.read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(token, text, f"{token} found in {path.name}")

    def test_config_schema_covers_read_keys(self):
        import re
        schema = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        body = (ROOT / "byparr_tools" / "config.py").read_text(encoding="utf-8")
        keys = set(re.findall(r'"([a-z_]+)":', body))
        for key in ("solver_url", "cdp_url", "cookie_jar_dir", "proxy_server"):
            self.assertIn(key, schema)
        self.assertTrue(keys.issuperset({"solver_url", "cdp_url"}))


class ConfigTests(unittest.TestCase):
    def test_defaults_are_portable(self):
        settings = config.Settings(FakeCtx())
        self.assertEqual(settings.solver_url(), "http://127.0.0.1:8191")
        self.assertEqual(settings.cdp_url(), "http://127.0.0.1:9222")

    def test_env_override(self):
        os.environ["FLARESOLVERR_URL"] = "http://example.test:8191/"
        try:
            settings = config.Settings(FakeCtx())
            self.assertEqual(settings.solver_url(), "http://example.test:8191")
        finally:
            os.environ.pop("FLARESOLVERR_URL", None)

    def test_ctx_value_wins(self):
        ctx = FakeCtx({"solver_url": "http://mysolver.local:9000"})
        self.assertEqual(config.Settings(ctx).solver_url(), "http://mysolver.local:9000")

    def test_unknown_key_does_not_raise(self):
        self.assertEqual(config.Settings(FakeCtx()).get("not_declared"), "")

    def test_timeout_units(self):
        settings = config.Settings(FakeCtx({"default_timeout_seconds": 45}))
        self.assertEqual(settings.timeout(None), 45)
        self.assertEqual(settings.timeout(90), 90)
        self.assertEqual(settings.timeout("bad"), 45)


class QueueTests(unittest.TestCase):
    def test_serialises_and_retries(self):
        q = queue.SolverQueue(spacing=0, retries=2)
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("transient")
            return "ok"

        self.assertEqual(q.run(flaky), "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(q.stats()["retried"], 2)

    def test_gives_up_after_retries(self):
        q = queue.SolverQueue(spacing=0, retries=1)
        with self.assertRaises(RuntimeError):
            q.run(lambda: (_ for _ in ()).throw(RuntimeError("always")))
        self.assertEqual(q.stats()["failed"], 1)


class ExtractTests(unittest.TestCase):
    def test_structured_output(self):
        html = """<html><head><title>Widget</title>
        <meta property="og:price" content="12.50">
        <script type="application/ld+json">{"@type":"Product","name":"Widget"}</script>
        </head><body><h1>Widget</h1><dt>Colour</dt><dd>Red</dd></body></html>"""
        result = extract.extract(html)
        self.assertEqual(result["title"], "Widget")
        self.assertEqual(result["meta"].get("og:price"), "12.50")
        self.assertEqual(result["jsonld"][0]["name"], "Widget")
        self.assertEqual(result["facts"][0], {"term": "Colour", "value": "Red"})

    def test_empty_html(self):
        self.assertEqual(extract.extract("")["count"] if "count" in extract.extract("") else extract.extract("")["facts"], [])


class JarTests(unittest.TestCase):
    def test_round_trip_and_redaction(self):
        j = jar.CookieJar(ttl=60)
        payload = [{"name": "cf_clearance", "value": "SECRET"}]
        described = j.put("s1", payload, "UA/1")
        self.assertEqual(described["names"], ["cf_clearance"])
        self.assertNotIn("SECRET", json.dumps(described))
        self.assertEqual(j.get("s1")["cookies"][0]["value"], "SECRET")
        self.assertTrue(j.clear("s1"))
        self.assertIsNone(j.get("s1"))

    def test_expiry(self):
        import time
        j = jar.CookieJar(ttl=1)
        j.put("s1", [{"name": "a", "value": "b"}])
        time.sleep(1.05)
        self.assertIsNone(j.get("s1"))


class ToolTests(unittest.TestCase):
    def setUp(self):
        tools.configure(FakeCtx())

    def test_solver_get_wall_detection(self):
        fake = {"status": "ok", "solution": {"response": "Just a moment...", "status": 403}}
        with mock.patch.object(tools, "_post", return_value=fake):
            result = json.loads(tools.solver_get({"url": "https://example.test"}))
        self.assertTrue(result["wall"])
        self.assertFalse(result["solved"])

    def test_solver_get_ok(self):
        fake = {"status": "ok", "solution": {"response": "x" * 2500, "status": 200}}
        with mock.patch.object(tools, "_post", return_value=fake):
            result = json.loads(tools.solver_get({"url": "https://example.test"}))
        self.assertTrue(result["solved"])
        self.assertEqual(result["bytes"], 2500)

    def test_cookies_redacted_and_session_stored(self):
        fake = {"status": "ok", "solution": {"userAgent": "UA/1", "cookies": [
            {"name": "cf_clearance", "value": "SECRET", "domain": ".x.test", "path": "/"},
        ]}}
        with mock.patch.object(tools, "_post", return_value=fake):
            result = json.loads(tools.solver_cookies({"url": "https://x.test", "session": "s1"}))
        self.assertIsNone(result["values"])
        self.assertEqual(result["jar"]["names"], ["cf_clearance"])
        self.assertNotIn("SECRET", json.dumps(result["jar"]))

    def test_load_truncates(self):
        fake = [{"page_content": "hello world", "metadata": {"source": "https://example.test"}}]
        with mock.patch.object(tools, "_post", return_value=fake):
            result = json.loads(tools.solver_load({"urls": ["https://example.test"], "maxChars": 5}))
        self.assertEqual(result["pages"][0]["text"], "hello")

    def test_status_reports_configured_url(self):
        with mock.patch.object(tools, "_get_json", return_value={"msg": "ok", "version": "1.2.3"}):
            result = json.loads(tools.solver_status({}))
        self.assertTrue(result["ok"])
        self.assertEqual(result["version"], "1.2.3")
        self.assertEqual(result["solver_url"], "http://127.0.0.1:8191")

    def test_bridge_requires_cookies(self):
        result = json.loads(tools.solver_bridge({}))
        self.assertFalse(result["ok"])

    def test_bridge_uses_jar(self):
        tools.configure(FakeCtx())
        with mock.patch.object(tools, "_post", return_value={"status": "ok", "solution": {
            "userAgent": "UA/1", "cookies": [{"name": "a", "value": "b"}],
        }}):
            tools.solver_cookies({"url": "https://x.test", "session": "s2"})
        with mock.patch.object(tools, "inject_cookies", return_value={"ok": True, "injected": 1}) as injected:
            result = json.loads(tools.solver_bridge({"session": "s2"}))
        self.assertTrue(result["ok"])
        self.assertEqual(injected.call_args.args[1], "http://127.0.0.1:9222")

    def test_fetch_falls_back_on_wall(self):
        class Walled:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"Just a moment..."

        with mock.patch.object(tools.urllib.request, "urlopen", return_value=Walled()):
            with mock.patch.object(tools, "_post", return_value={"status": "ok", "solution": {
                "response": "solved content that is certainly longer than two thousand characters " * 40,
                "status": 200,
            }}):
                result = json.loads(tools.solver_fetch({"url": "https://example.test"}))
        self.assertEqual(result["via"], "solver")


class MiddlewareTests(unittest.TestCase):
    def setUp(self):
        fallback.configure(FakeCtx())

    def test_passes_through_non_target_tool(self):
        called = []
        args = {"url": "https://example.test"}
        result = fallback.on_tool_execution(
            tool_name="terminal", args=args,
            next_call=lambda a: (called.append(a), "shell output")[1],
        )
        self.assertEqual(called, [args])
        self.assertEqual(result, "shell output")

    def test_replaces_walled_result(self):
        args = {"url": "https://example.test"}
        solved = {"ok": True, "solved": True, "html": "solved content " * 200}
        with mock.patch.object(tools, "solver_get", return_value=json.dumps(solved)):
            result = fallback.on_tool_execution(
                tool_name="web_extract", args=args,
                next_call=lambda a: "Just a moment...",
            )
        self.assertIn("solved content", result)

    def test_fail_open_on_error(self):
        def boom(a):
            return "Just a moment..."

        with mock.patch.object(tools, "solver_get", side_effect=RuntimeError("x")):
            result = fallback.on_tool_execution(
                tool_name="web_extract", args={"url": "https://example.test"},
                next_call=boom,
            )
        self.assertEqual(result, "Just a moment...")


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
