"""Regression tests for Voice Gate.

No dependencies and no test runner: the host process has neither PyYAML nor
pytest for plugin code, so this drives the module directly.

    python tests/test_voice_gate.py

Exit code 0 means every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
PERSONAL = (PLUGIN / "profile.py").is_file()
FAILURES: list[str] = []

SLOP = (
    "# Notes\n\nIn today's fast-paced world we delve into the tapestry of a pivotal platform. "
    "It plays a crucial role and serves as a testament to the team.\n\n"
    "Moreover, it is seamless. Furthermore, it is robust. In conclusion, this is a turning point.\n"
)
CLEAN = (
    "# Notes\n\nThe release adds a settings page and fixes the blank row on load.\n\n"
    "Install it with the command below, then open Plugins and check the row.\n"
)


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
        return
    FAILURES.append(name)
    print(f"  FAIL {name}{': ' + detail if detail else ''}")


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Ctx:
    def __init__(self, config: dict):
        self.config = config
        self.hooks: dict = {}
        self.tools: dict = {}
        self.skills: list = []

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_tool(self, name, toolset, schema, handler, **rest):
        self.tools[name] = handler

    def register_skill(self, *args, **kwargs):
        self.skills.append(args[0] if args else kwargs)


def sandbox_home(config: str) -> Path:
    home = Path(tempfile.mkdtemp(prefix="vg-home-"))
    (home / "config.yaml").write_text(config, encoding="utf-8")
    os.environ["HERMES_HOME"] = str(home)
    return home


def main() -> int:
    module = load_module("voice_gate_under_test")
    rules = module.rules
    print(f"{PLUGIN.parent.name}/voice-gate")

    # ---- rules
    slop = rules.lint(SLOP)
    clean = rules.lint(CLEAN)
    check("slop produces findings", bool(rules.gate_findings(slop)), str(rules.gate_findings(slop)))
    check("clean prose produces none", not rules.gate_findings(clean), str(rules.gate_findings(clean)))
    quoted = rules.lint("The list forbids `delve` and `tapestry` and `seamless` as examples.")
    check("inline code does not count", not rules.gate_findings(quoted), str(rules.gate_findings(quoted)))
    fence = rules.lint("```text\ndelve tapestry seamless\n```\n")
    check("fenced code does not count", rules.gate_findings(fence) == [], str(rules.gate_findings(fence)))
    three = rules.lint("We delve once, delve twice, and delve a third time in this note.")
    check("three buzzwords stay under the floor", not rules.gate_findings(three), str(rules.gate_findings(three)))

    # ---- the style pack tracks rules.py
    spec = importlib.util.spec_from_file_location("vg_gen", PLUGIN / "scripts" / "gen_style_pack.py")
    gen = importlib.util.module_from_spec(spec)
    sys.modules["vg_gen"] = gen
    spec.loader.exec_module(gen)
    stale = [
        str(path) for path, text in gen.build(rules).items()
        if not (PLUGIN / path).is_file() or (PLUGIN / path).read_text(encoding="utf-8") != text
    ]
    check("style pack matches rules.py", not stale, ", ".join(stale))

    # ---- which bots run the gate
    module._current_profile = lambda: "default"
    sandbox_home("plugins:\n  entries:\n    Voice Gate:\n      settings:\n        apply_hermes: true\n"
                 "        apply_herald: false\n")
    module._current_profile = lambda: "herald"
    check("a bot can be switched off", module._bots_allow() is False)
    module._current_profile = lambda: "default"
    check("the default bot stays on", module._bots_allow() is True)
    sandbox_home("plugins:\n  entries:\n    Voice Gate:\n      settings:\n        mode: warn\n")
    check("no boxes means every bot runs", module._bots_allow() is True)
    sandbox_home("plugins:\n  entries:\n    \"Voice Gate\":\n      settings:\n        apply_tinker: false\n")
    module._current_profile = lambda: "tinker"
    check("a quoted entry key is read", module._bots_allow() is False)

    # ---- settings
    sandbox_home(
        """plugins:
  enabled: []
"""
    )
    module._current_profile = lambda: "default"
    ctx = Ctx({"mode": "improve", "min_words": None, "profile": ""})
    module.register(ctx)
    floor = module._min_words() if not PERSONAL else module._min_words({})
    check("unset floor falls back", floor > 0, str(floor))
    ctx.config["min_words"] = 0
    floor = module._min_words() if not PERSONAL else module._min_words({})
    check("an explicit 0 turns the floor off", floor == 0, str(floor))
    ctx.config["min_words"] = 150
    floor = module._min_words() if not PERSONAL else module._min_words({})
    check("a positive floor is kept", floor == 150, str(floor))

    # ---- tools and hooks
    check("registers both hooks", {"pre_verify", "pre_tool_call"} <= set(ctx.hooks), str(sorted(ctx.hooks)))
    check("registers the check tool", "voice_gate_check" in ctx.tools, str(sorted(ctx.tools)))
    check("registers the vale tool", "voice_gate_vale" in ctx.tools, str(sorted(ctx.tools)))
    payload = ctx.tools["voice_gate_check"]({"text": SLOP})
    parsed = __import__("json").loads(payload)
    first = (parsed.get("checks") or [{}])[0] if "checks" in parsed else parsed
    findings = first.get("findings")
    check("check tool reports findings", bool(parsed.get("ok") and findings), payload[:160])

    # ---- the turn path
    probe = Path(tempfile.mkdtemp(prefix="vg-doc-")) / "note.md"
    probe.write_text(SLOP, encoding="utf-8")
    ctx.config.update({"min_words": 5, "vale_mode": "off"})
    out = ctx.hooks["pre_verify"](attempt=0, changed_paths=[str(probe)])
    message = (out or {}).get("message", "")
    check("a tagged document is nudged", "voice-gate" in message, message[:120])
    check("vale stays out when off", "Vale reports" not in message, message[:120])
    ctx.config["min_words"] = 5000
    check("a short document stays silent",
          ctx.hooks["pre_verify"](attempt=0, changed_paths=[str(probe)]) is None)

    ctx.config.update({"min_words": 5, "vale_mode": "advisory"})
    module._current_profile = lambda: "herald"
    sandbox_home("plugins:\n  entries:\n    Voice Gate:\n      settings:\n        apply_hermes: true\n"
                 "        apply_herald: false\n")
    check("an unticked bot gets no nudge",
          ctx.hooks["pre_verify"](attempt=0, changed_paths=[str(probe)]) is None)

    # ---- exceptions
    dash = "The row loads and the value stays where it was. " * 20 + "One dash — here."
    exc = {"preferences": {"no_em_dash": True}, "exceptions": {"em_dash": ["*.md"]}}
    check("an exception silences its family in the file it names",
          not rules.gate_findings(rules.lint(dash), exc, "README.md"))
    check("the same family still fires in another format",
          bool(rules.gate_findings(rules.lint(dash), exc, "notes.txt")))
    check("an exception without a path applies to nothing",
          bool(rules.gate_findings(rules.lint(dash), exc)))
    shapes = (
        {"em_dash": ["*.md"]},
        {"em_dash": "*.md"},
        ["em dash: *.md"],
        "em_dash: README.md, *.md",
        {"em_dash": {"globs": ["*.md"]}},
    )
    check("every accepted shape parses",
          all(rules.suppressed({"exceptions": shape}, "docs/README.md") for shape in shapes))
    check("a basename glob matches in any directory",
          rules.suppressed({"exceptions": {"em_dash": ["readme.md"]}}, "deep/docs/README.md"))
    check("a wildcard tell silences every family",
          rules.suppressed({"exceptions": {"all": ["*.md"]}}, "x.md") == list(rules.TELL_KEYS))
    check("an unknown tell is ignored", rules.normalise_exceptions({"nonsense": ["*.md"]}) == {})
    check("a semicolon separates globs",
          rules.normalise_exceptions("em_dash: *.md; *.txt")["em_dashes"] == ["*.md", "*.txt"])

    # profile rows and settings rows merge
    profile_rows = {"exceptions": {"em_dash": ["*.md"]}}
    ctx.config["exceptions"] = "bold_lead_bullets: docs/**"
    merged = module._exceptions_block(profile_rows)
    check("profile and settings exceptions merge",
          set(module.rules.normalise_exceptions(merged.get("exceptions"))) == {"em_dashes", "bold_lead_bullets"},
          str(merged.get("exceptions")))
    check("the profile itself is not mutated", "exceptions" in profile_rows and
          module.rules.normalise_exceptions(profile_rows["exceptions"]) == {"em_dashes": ["*.md"]})
    ctx.config["exceptions"] = ""

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
