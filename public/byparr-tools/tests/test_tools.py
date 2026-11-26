"""Dependency-free tests for byparr-tools. Run: python tests/test_tools.py"""
import importlib.util
import json
import os
import sys
import types
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
from byparr_tools import config, cdp, extract, fallback, jar, queue, safety, schemas, tools  # noqa: E402


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
        for key in ("solver_url", "cdp_url", "cookie_jar_dir", "proxy_server",
                    "allow_private_targets"):
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

    def test_private_targets_off_by_default(self):
        self.assertFalse(config.Settings(FakeCtx()).bool_key("allow_private_targets"))


class SecretScopeTests(unittest.TestCase):
    def test_env_read_only_when_the_host_module_is_absent(self):
        os.environ["BYPARR_PROXY_PASSWORD"] = "pw"
        try:
            with mock.patch.object(config, "host_secret_scope", return_value=None):
                self.assertEqual(config.Settings(FakeCtx()).secrets(), {"proxy_password": "pw"})
        finally:
            os.environ.pop("BYPARR_PROXY_PASSWORD", None)

    def test_host_error_propagates_instead_of_reading_env(self):
        class UnscopedSecretError(RuntimeError):
            pass

        fake_scope = types.ModuleType("agent.secret_scope")

        def raise_unscoped(name, default=None):
            raise UnscopedSecretError(f"no profile secret scope active for {name}")

        fake_scope.get_secret = raise_unscoped
        fake_agent = types.ModuleType("agent")
        fake_agent.secret_scope = fake_scope
        saved = {name: sys.modules.get(name) for name in ("agent", "agent.secret_scope")}
        sys.modules["agent"] = fake_agent
        sys.modules["agent.secret_scope"] = fake_scope
        os.environ["BYPARR_PROXY_PASSWORD"] = "would-be-leaked"

        def restore():
            for name, value in saved.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
            os.environ.pop("BYPARR_PROXY_PASSWORD", None)

        self.addCleanup(restore)
        with self.assertRaises(UnscopedSecretError):
            config.Settings(FakeCtx()).secrets()


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


class SafetyTests(unittest.TestCase):
    """The floor enforced without core, and core's own verdict when it is importable."""

    def _local(self):
        return mock.patch.object(safety, "core", return_value=None)

    def test_rejects_loopback_private_and_metadata(self):
        cases = {
            "http://127.0.0.1:8191/": "private or internal",
            "http://localhost:8191/": "loopback hostname",
            "http://169.254.169.254/latest/meta-data/": "cloud metadata",
            "http://10.0.0.5/": "private or internal",
            "http://[::1]/": "private or internal",
            "ftp://example.test/x": "only http and https",
        }
        with self._local():
            for url, expected in cases.items():
                allowed, reason = safety.url_allowed(url)
                self.assertFalse(allowed, url)
                self.assertIn(expected, reason, url)

    def test_allows_public_names(self):
        with self._local():
            self.assertEqual(safety.url_allowed("https://example.test/page"), (True, ""))

    def test_lan_opt_in_keeps_the_metadata_floor(self):
        with self._local():
            self.assertTrue(safety.url_allowed("http://192.168.1.20/", allow_private=True)[0])
            self.assertFalse(safety.url_allowed("http://169.254.169.254/", allow_private=True)[0])
            self.assertFalse(safety.url_allowed("http://169.254.169.254/", allow_private=False)[0])

    def test_core_verdict_is_used_when_importable(self):
        fake = types.SimpleNamespace(is_safe_url=lambda url: False,
                                     is_always_blocked_url=lambda url: True)
        with mock.patch.object(safety, "core", return_value=fake):
            self.assertFalse(safety.url_allowed("https://example.test/")[0])
            self.assertFalse(safety.url_allowed("http://10.1.2.3/", allow_private=True)[0])
        fake_safe = types.SimpleNamespace(is_safe_url=lambda url: True,
                                          is_always_blocked_url=lambda url: False)
        with mock.patch.object(safety, "core", return_value=fake_safe):
            self.assertTrue(safety.url_allowed("https://example.test/")[0])
            self.assertTrue(safety.url_allowed("http://10.1.2.3/", allow_private=True)[0])

    def test_a_globally_permissive_host_does_not_reopen_address_literals(self):
        permissive = types.SimpleNamespace(is_safe_url=lambda url: True,
                                           is_always_blocked_url=lambda url: False)
        with mock.patch.object(safety, "core", return_value=permissive):
            self.assertFalse(safety.url_allowed("http://127.0.0.1:8191/")[0])
            self.assertFalse(safety.url_allowed("http://localhost:8191/")[0])
            self.assertEqual(safety.url_allowed("https://example.com/"), (True, ""))

    def test_host_check_error_is_not_approval(self):
        def boom(url):
            raise RuntimeError("resolver on fire")

        with mock.patch.object(safety, "core", return_value=types.SimpleNamespace(is_safe_url=boom)):
            allowed, reason = safety.url_allowed("https://example.test/")
        self.assertFalse(allowed)
        self.assertIn("host URL check failed", reason)


class ToolTests(unittest.TestCase):
    def setUp(self):
        tools.configure(FakeCtx())
        local = mock.patch.object(safety, "core", return_value=None)
        local.start()
        self.addCleanup(local.stop)

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

    def test_private_urls_never_reach_the_solver(self):
        posted = []
        with mock.patch.object(tools, "_post", side_effect=lambda *a, **k: posted.append(a) or {}):
            for url in ("http://127.0.0.1:8191/", "http://169.254.169.254/latest/meta-data/"):
                result = json.loads(tools.solver_get({"url": url}))
                self.assertFalse(result["ok"])
                self.assertIn("rejected", result["error"])
                cookies = json.loads(tools.solver_cookies({"url": url}))
                self.assertFalse(cookies["ok"])
        self.assertEqual(posted, [])

    def test_lan_target_needs_the_opt_in(self):
        fake = {"status": "ok", "solution": {"response": "x" * 2500, "status": 200}}
        with mock.patch.object(tools, "_post", return_value=fake):
            self.assertFalse(json.loads(tools.solver_get({"url": "http://192.168.1.20/"}))["ok"])
        tools.configure(FakeCtx({"allow_private_targets": True}))
        with mock.patch.object(tools, "_post", return_value=fake):
            self.assertTrue(json.loads(tools.solver_get({"url": "http://192.168.1.20/"}))["ok"])
        self.assertFalse(json.loads(tools.solver_get({"url": "http://169.254.169.254/"}))["ok"])

    def test_load_checks_every_url(self):
        posted = []
        with mock.patch.object(tools, "_post", side_effect=lambda *a, **k: posted.append(a) or []):
            result = json.loads(tools.solver_load({
                "urls": ["https://example.test/ok", "http://127.0.0.1:2019/config/"]}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["rejected"][0]["url"], "http://127.0.0.1:2019/config/")
        self.assertEqual(posted, [])

    def test_load_still_truncates(self):
        fake = [{"page_content": "hello world", "metadata": {"source": "https://example.test"}}]
        with mock.patch.object(tools, "_post", return_value=fake):
            result = json.loads(tools.solver_load({"urls": ["https://example.test"], "maxChars": 5}))
        self.assertEqual(result["pages"][0]["text"], "hello")

    def test_cookies_redacted_and_session_stored(self):
        fake = {"status": "ok", "solution": {"userAgent": "UA/1", "cookies": [
            {"name": "cf_clearance", "value": "SECRET", "domain": ".x.test", "path": "/"},
        ]}}
        with mock.patch.object(tools, "_post", return_value=fake):
            result = json.loads(tools.solver_cookies({"url": "https://x.test", "session": "s1"}))
        self.assertIsNone(result["values"])
        self.assertNotIn("SECRET", json.dumps(result))
        for cookie in result["cdp"]["cookies"]:
            self.assertNotIn("value", cookie)
        self.assertEqual(result["jar"]["names"], ["cf_clearance"])

    def test_cookie_values_on_request(self):
        fake = {"status": "ok", "solution": {"userAgent": "UA/1", "cookies": [
            {"name": "cf_clearance", "value": "SECRET", "domain": ".x.test", "path": "/"},
        ]}}
        with mock.patch.object(tools, "_post", return_value=fake):
            shown = json.loads(tools.solver_cookies(
                {"url": "https://x.test", "showValues": True}))
        self.assertEqual(shown["cdp"]["cookies"][0]["value"], "SECRET")
        self.assertEqual(shown["values"]["cf_clearance"], "SECRET")

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
        stored = tools._jar.get("s2")
        self.assertEqual(stored["cookies"][0]["value"], "b")
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

        with mock.patch.object(tools, "_direct_open", return_value=Walled()):
            with mock.patch.object(tools, "_post", return_value={"status": "ok", "solution": {
                "response": "solved content that is certainly longer than two thousand characters " * 40,
                "status": 200,
            }}):
                result = json.loads(tools.solver_fetch({"url": "https://example.test"}))
        self.assertEqual(result["via"], "solver")

    def test_fetch_refuses_private_target(self):
        called = []
        with mock.patch.object(tools, "_direct_open", side_effect=lambda *a, **k: called.append(a)):
            result = json.loads(tools.solver_fetch({"url": "http://127.0.0.1:9222/json"}))
        self.assertFalse(result["ok"])
        self.assertEqual(called, [])


class RedirectTests(unittest.TestCase):
    def setUp(self):
        local = mock.patch.object(safety, "core", return_value=None)
        local.start()
        self.addCleanup(local.stop)

    def test_redirect_hop_to_private_is_blocked(self):
        handler = tools._SafeRedirects(False)
        with self.assertRaises(tools._RedirectBlocked):
            handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1:2019/config/")
        with self.assertRaises(tools._RedirectBlocked):
            handler.redirect_request(None, None, 302, "Found", {}, "http://169.254.169.254/")

    def test_fetch_reports_a_blocked_redirect(self):
        tools.configure(FakeCtx())

        def blocked(url, timeout, allow_private=False):
            raise tools._RedirectBlocked("redirect to http://127.0.0.1/ blocked: private or internal address")

        with mock.patch.object(tools, "_direct_open", side_effect=blocked):
            result = json.loads(tools.solver_fetch({"url": "https://example.test/"}))
        self.assertEqual(result["via"], "direct")
        self.assertIn("redirect_blocked", result)


class ProxyTests(unittest.TestCase):
    def test_schemas_expose_no_proxy_fields(self):
        for schema in (schemas.SOLVER_GET, schemas.SOLVER_COOKIES):
            props = schema["parameters"]["properties"]
            for key in ("proxyServer", "proxyUsername", "proxyPassword"):
                self.assertNotIn(key, props)

    def test_tool_arguments_cannot_choose_the_proxy(self):
        tools.configure(FakeCtx({"proxy_server": "http://proxy.test:8080"}))
        os.environ["BYPARR_PROXY_USERNAME"] = "svc"
        os.environ["BYPARR_PROXY_PASSWORD"] = "pw"
        self.addCleanup(os.environ.pop, "BYPARR_PROXY_USERNAME", None)
        self.addCleanup(os.environ.pop, "BYPARR_PROXY_PASSWORD", None)
        seen = {}

        def fake_post(path, payload, timeout, headers=None):
            seen.update(headers or {})
            return {"status": "ok", "solution": {"response": "x" * 2500, "status": 200}}

        with mock.patch.object(safety, "core", return_value=None):
            with mock.patch.object(tools, "_post", side_effect=fake_post):
                result = json.loads(tools.solver_get({
                    "url": "https://example.test/",
                    "proxyServer": "http://attacker.test:1",
                    "proxyUsername": "attacker",
                    "proxyPassword": "attacker",
                }))
        self.assertTrue(result["ok"])
        self.assertEqual(seen["X-Proxy-Server"], "http://proxy.test:8080")
        self.assertEqual(seen["X-Proxy-Username"], "svc")
        self.assertEqual(seen["X-Proxy-Password"], "pw")

    def test_no_proxy_configured_reads_no_secret(self):
        tools.configure(FakeCtx())
        with mock.patch.object(config.Settings, "secrets",
                                side_effect=AssertionError("secret read")) as secrets:
            self.assertEqual(tools._proxy_headers(), {})
        self.assertFalse(secrets.called)


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

    def test_reads_the_web_extract_urls_list(self):
        solved = {"ok": True, "solved": True, "html": "solved content " * 200}
        with mock.patch.object(tools, "solver_get", return_value=json.dumps(solved)) as solver:
            result = fallback.on_tool_execution(
                tool_name="web_extract", args={"urls": ["https://example.test/page"]},
                next_call=lambda a: "Just a moment...",
            )
        self.assertIn("solved content", result)
        self.assertEqual(solver.call_args.args[0]["url"], "https://example.test/page")

    def test_default_targets_are_url_shaped(self):
        self.assertEqual(fallback._targets(), {"web_extract"})
        self.assertEqual(fallback._url({"code": "print(1)"}), "")

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
