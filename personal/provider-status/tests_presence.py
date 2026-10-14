from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parent
if not (PLUGIN / "plugin.yaml").exists():
    PLUGIN = Path(r"C:/Users/theap/AppData/Local/hermes/plugins/provider-status")
PACKAGE = "provider_status_presence_test"


def _load():
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    spec = importlib.util.spec_from_file_location(
        PACKAGE,
        PLUGIN / "__init__.py",
        submodule_search_locations=[str(PLUGIN)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__path__ = [str(PLUGIN)]
    module.__package__ = PACKAGE
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.hooks = []
        self.commands = []
        self.tools = []
        self.cli = []
        self.platforms = []
        self.skills = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, cb):
        self.hooks.append(name)

    def register_command(self, name, handler, description=""):
        self.commands.append(name)

    def register_tool(self, **kwargs):
        self.tools.append(kwargs["name"])

    def register_cli_command(self, **kwargs):
        self.cli.append(kwargs["name"])

    def register_platform_handler(self, platform, factory):
        self.platforms.append(platform)

    def register_skill(self, name, path):
        self.skills.append(name)


class TestQuotaBridge(unittest.TestCase):
    def test_provider_map_oauth_aliases(self):
        bridge = _load().quota_bridge if False else None
        mod = importlib.import_module(f"{PACKAGE}.quota_bridge")
        self.assertEqual(mod.provider_to_pid("xai-oauth"), "grok")
        self.assertEqual(mod.provider_to_pid("openai-codex"), "codex")
        self.assertEqual(mod.provider_to_pid("zai"), "glm")
        self.assertEqual(mod.provider_to_pid(""), None)

    def test_sanitize_drops_secrets(self):
        mod = importlib.import_module(f"{PACKAGE}.quota_bridge")
        raw = {
            "ok": True,
            "name": "Grok (xAI)",
            "remaining": 42.0,
            "percent": 58.0,
            "access_token": "secret",
            "refresh_token": "also-secret",
            "pool": ["sk-live-please-drop"],
            "email": "me@example.com",
            "quotas": [{"label": "Weekly", "percent": 42.0}],
        }
        clean = mod.sanitize_status("grok", raw)
        blob = json.dumps(clean)
        self.assertNotIn("secret", blob)
        self.assertNotIn("sk-live", blob)
        self.assertNotIn("me@example.com", blob)
        self.assertEqual(clean["remaining"], 42.0)
        self.assertEqual(clean["kind"], "exhaust")
        self.assertEqual(clean["quotas"][0]["label"], "Weekly")

    def test_credit_kind_keeps_balance(self):
        mod = importlib.import_module(f"{PACKAGE}.quota_bridge")
        clean = mod.sanitize_status("deepseek", {"ok": True, "balance": 12.4, "granted": 20})
        self.assertEqual(clean["kind"], "credit")
        self.assertEqual(clean["balance"], 12.4)

    def test_roundtrip_file(self):
        mod = importlib.import_module(f"{PACKAGE}.quota_bridge")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod.upsert(root, "grok", {"ok": True, "remaining": 77, "name": "Grok"})
            got = mod.for_provider(root, "xai-oauth")
            self.assertIsNotNone(got)
            self.assertEqual(got["remaining"], 77)
            disk = json.loads((root / "quota-cache.json").read_text(encoding="utf-8"))
            self.assertIn("providers", disk)
            self.assertNotIn("access_token", json.dumps(disk))


class TestRender(unittest.TestCase):
    def setUp(self):
        _load()
        self.metrics = importlib.import_module(f"{PACKAGE}.presence_metrics")
        self.render = importlib.import_module(f"{PACKAGE}.presence_render")
        self.config = importlib.import_module(f"{PACKAGE}.presence_config")

    def _snap(self, **kw):
        quota = kw.pop("quota", None)
        return self.metrics.Snapshot(
            model=kw.get("model", "grok-4.6"),
            provider=kw.get("provider", "xai-oauth"),
            tps=kw.get("tps", 84.0),
            context_used=kw.get("context_used", 12000),
            context_length=kw.get("context_length", 200000),
            context_pct=kw.get("context_pct", 6.0),
            inflight=kw.get("inflight", False),
            quota=quota,
        )

    def test_compact_includes_speed_context_quota(self):
        cfg = self.config.PresenceConfig()
        snap = self._snap(quota={"ok": True, "id": "grok", "name": "Grok", "remaining": 61, "kind": "exhaust"})
        text = self.render.compact_status(snap, cfg)
        self.assertIn("tok/s", text)
        self.assertIn("ctx", text)
        self.assertIn("Grok", text)
        self.assertIn("61%", text)

    def test_default_bar_width_is_five(self):
        # Discord's member list truncates the state, so the shipped bar is short.
        self.assertEqual(self.config.PresenceConfig().bar_width, 5)

    def test_bar_width_is_configurable_and_drives_render(self):
        ctx = FakeCtx({"discord_bar_width": 8})
        cfg = self.config.PresenceConfig.from_ctx(ctx)
        self.assertEqual(cfg.bar_width, 8)
        snap = self._snap(
            context_pct=50.0,
            quota={"ok": True, "id": "grok", "name": "Grok", "remaining": 50, "kind": "exhaust"},
        )
        segs = dict(self.render.segments(snap, cfg))
        ctx_bar = segs["context"].split(cfg.separator)[0]
        quota_text = segs["quota"].replace(self.render.GLYPH_QUOTA, "").strip()
        quota_bar = quota_text.split(cfg.separator)[0]
        self.assertEqual(len(ctx_bar), 8)
        self.assertEqual(ctx_bar, "▰▰▰▰▱▱▱▱")
        self.assertEqual(len(quota_bar), 8)
        self.assertEqual(quota_bar, "▰▰▰▰▱▱▱▱")

    def test_bar_width_clamps_to_range(self):
        cfg = self.config.PresenceConfig.from_ctx(FakeCtx({"discord_bar_width": 99}))
        self.assertEqual(cfg.bar_width, 20)
        cfg = self.config.PresenceConfig.from_ctx(FakeCtx({"discord_bar_width": 1}))
        self.assertEqual(cfg.bar_width, 3)

    def test_credit_balance_segment(self):
        cfg = self.config.PresenceConfig()
        snap = self._snap(
            provider="deepseek",
            quota={"ok": True, "id": "deepseek", "name": "DeepSeek", "kind": "credit", "balance": 12.4, "remaining": 62},
        )
        segs = dict(self.render.segments(snap, cfg))
        self.assertIn("quota", segs)
        self.assertIn("balance", segs)
        self.assertIn("$12.40", segs["balance"])

    def test_missing_quota_omits_segment(self):
        cfg = self.config.PresenceConfig()
        segs = dict(self.render.segments(self._snap(quota=None), cfg))
        self.assertNotIn("quota", segs)
        self.assertNotIn("balance", segs)

    def test_dnd_on_low_quota(self):
        cfg = self.config.PresenceConfig(quota_warn_remaining=20)
        snap = self._snap(quota={"ok": True, "remaining": 10, "kind": "exhaust"})
        self.assertEqual(self.render.presence_status(snap, cfg, 0.0), "dnd")

    def test_idle_when_quiet(self):
        cfg = self.config.PresenceConfig(idle_after_seconds=10)
        snap = self.metrics.Snapshot(last_activity=1.0)
        self.assertEqual(self.render.presence_status(snap, cfg, 20.0), "idle")


class TestMetricsQuotaAttach(unittest.TestCase):
    def test_snapshot_reads_cache_for_session_provider(self):
        _load()
        metrics = importlib.import_module(f"{PACKAGE}.presence_metrics")
        bridge = importlib.import_module(f"{PACKAGE}.quota_bridge")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.upsert(root, "grok", {"ok": True, "remaining": 55, "name": "Grok"})
            c = metrics.MetricsCollector(plugin_root=root)
            c.on_post_api_request(
                provider="xai-oauth",
                model="grok-4.6",
                api_duration=1.0,
                usage={"output_tokens": 80, "prompt_tokens": 400, "total_tokens": 480},
                context_length=200000,
            )
            snap = c.snapshot()
            self.assertEqual(snap.provider, "xai-oauth")
            self.assertAlmostEqual(snap.tps, 80.0)
            self.assertEqual(snap.quota["remaining"], 55)
            self.assertAlmostEqual(snap.context_pct, 0.2)


class TestShowFlags(unittest.TestCase):
    """The three headline parts are checkboxes and ship on by default."""

    def setUp(self):
        _load()
        self.config = importlib.import_module(f"{PACKAGE}.presence_config")
        self.render = importlib.import_module(f"{PACKAGE}.presence_render")
        self.metrics = importlib.import_module(f"{PACKAGE}.presence_metrics")

    def _snap(self):
        return self.metrics.Snapshot(
            model="grok-4.6", provider="xai-oauth", tps=84.0,
            context_used=12000, context_length=200000, context_pct=6.0,
            quota={"ok": True, "id": "grok", "name": "Grok", "remaining": 61, "kind": "exhaust"},
        )

    def test_headline_parts_default_on(self):
        cfg = self.config.PresenceConfig()
        self.assertTrue(cfg.show_tokens_per_second)
        self.assertTrue(cfg.show_context)
        self.assertTrue(cfg.show_quota)
        self.assertTrue(cfg.show_balance)

    def test_each_checkbox_drops_only_its_own_part(self):
        snap = self._snap()
        for flag, marker in (
            ("discord_show_tokens_per_second", "tok/s"),
            ("discord_show_context", "ctx"),
            ("discord_show_quota", "Grok"),
        ):
            for mode in ("compact", "rotate"):
                cfg = self.config.PresenceConfig.from_ctx(
                    FakeCtx({"discord_presence_mode": mode, flag: False})
                )
                for turn in range(4):  # rotate needs several turns to cover parts
                    text = self.render.render_status(snap, cfg, turn)
                    self.assertNotIn(
                        marker, text,
                        f"{flag}=False still renders {marker!r} in {mode} mode: {text}",
                    )
        cfg = self.config.PresenceConfig.from_ctx(FakeCtx({}))
        text = self.render.render_status(snap, cfg)
        for marker in ("tok/s", "ctx", "Grok"):
            self.assertIn(marker, text)

    def test_balance_checkbox_isolates_the_dollar_line(self):
        snap = self.metrics.Snapshot(
            model="deepseek-chat", provider="deepseek", tps=84.0,
            context_used=12000, context_length=200000, context_pct=6.0,
            quota={
                "ok": True, "id": "deepseek", "name": "DeepSeek",
                "kind": "credit", "balance": 12.4, "remaining": 62,
            },
        )
        on = self.config.PresenceConfig()
        self.assertIn("$12.40", self.render.render_status(snap, on))
        off = self.config.PresenceConfig.from_ctx(FakeCtx({"discord_show_balance": False}))
        self.assertNotIn("$12.40", self.render.render_status(snap, off))

    def test_context_bar_subtoggle_only_touches_the_context_segment(self):
        snap = self._snap()
        cfg = self.config.PresenceConfig.from_ctx(FakeCtx({"discord_show_context_bar": False}))
        segs = dict(self.render.segments(snap, cfg))
        self.assertNotIn("▰", segs["context"])
        self.assertNotIn("▱", segs["context"])
        self.assertIn("% ctx", segs["context"])
        # the quota bar is independent and still draws
        self.assertIn("▰", dict(self.render.segments(snap, self.config.PresenceConfig()))["quota"])

    def test_quota_bar_subtoggle_only_touches_the_quota_segment(self):
        snap = self._snap()
        cfg = self.config.PresenceConfig.from_ctx(FakeCtx({"discord_show_quota_bar": False}))
        segs = dict(self.render.segments(snap, cfg))
        self.assertNotIn("▰", segs["quota"].replace(self.render.GLYPH_QUOTA, ""))
        self.assertNotIn("▱", segs["quota"].replace(self.render.GLYPH_QUOTA, ""))
        self.assertIn("61% Grok", segs["quota"])
        # the context bar is untouched and still draws its full width
        self.assertEqual(len(segs["context"].split(cfg.separator)[0]), cfg.bar_width)


class TestRegister(unittest.TestCase):
    def test_register_wires_hooks_and_discord(self):
        mod = _load()
        ctx = FakeCtx()
        mod.register(ctx)
        self.assertIn("post_api_request", ctx.hooks)
        self.assertIn("discord", ctx.platforms)
        self.assertIn("pulse", ctx.commands)
        self.assertIn("agent_pulse", ctx.tools)
        self.assertIn("session-pulse", ctx.cli)

    def test_disabled_skips_hooks(self):
        mod = _load()
        ctx = FakeCtx({"discord_presence_enabled": False})
        mod._config = None
        mod.register(ctx)
        self.assertEqual(ctx.hooks, [])
        self.assertEqual(ctx.platforms, [])
        self.assertIn("pulse", ctx.commands)


if __name__ == "__main__":
    unittest.main()
