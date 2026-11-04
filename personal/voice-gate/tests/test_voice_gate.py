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

    # the settings copy feeds the same machinery
    ctx.config["exceptions"] = "em_dash: *.md"
    block = module._exceptions_block()
    check("the settings carry exceptions", block.get("exceptions") == {"em_dashes": ["*.md"]}, str(block))
    ctx.config["exceptions"] = ""
    check("an empty setting means none", module._exceptions_block() == {})


    # ---- a host that inherits no HERMES_HOME must still find the profile
    saved = os.environ.pop("HERMES_HOME", None)
    try:
        home = module._home()
        check("the home resolves without HERMES_HOME", home.is_dir(), str(home))
        check("the home resolves to a directory", home.is_dir(), str(home))
    finally:
        if saved is not None:
            os.environ["HERMES_HOME"] = saved


    # ---- the extended families: each one fires on its own shape
    def fires(text, path=None, profile=None):
        return rules.gate_findings(rules.lint(text, profile), profile, path)

    def fires_family(text, family):
        return any(item.startswith(family) or family in item for item in fires(text))

    cases = [
        ("narrated candor", "To be fully transparent, the numbers are bad.\n", "narrated candor"),
        ("objection nobody raised", "Some might say this is obvious.\n", "objection nobody raised"),
        ("rhetorical setup", "Think about it. Full stop.\n", "rhetorical setup"),
        ("emphasis crutch", "This matters because it does, and it is a feature, not a bug.\n",
         "emphasis crutch"),
        ("slogan instead of a property", "Batteries included. Zero config.\n",
         "slogan instead of a property"),
        ("template phrase", "A step towards the world of better tools.\n", "template phrase"),
        ("copula avoidance", "It serves as a base and boasts a cache.\n", "copula avoidance"),
        ("wh- opener", "What makes this hard is time. Why this matters is trust.\n", "wh- opener"),
        ("stacked hedge", "It could potentially work and may eventually ship.\n", "stacked hedge"),
        ("parenthetical hedge", "The cost (arguably the real one) stays, and the rest (increasingly the norm) follows.\n", "parenthetical hedge"),
        ("future-narrative closer", "It will become one of the most important tools.\n",
         "future-narrative closer"),
        ("vague attribution", "Experts say it works. Studies show the same.\n", "vague attribution"),
        ("real/actual inflation", "The real value shows in the real problem.\n", "real/actual"),
        ("endorsement closer", "Bookmark this and thank me later.\n", "endorsement closer"),
        ("launch-copy introduction", "Say hello to Notes, your new editor.\n", "launch-copy"),
        ("assistant residue", "As an AI, I cannot browse.\n", "assistant residue"),
        ("template residue", "[Insert your name here] and TBD.\n", "template residue"),
        ("tool fingerprint in a URL", "See example.com/?utm_source=chatgpt for the copy.\n",
         "tool fingerprint"),
        ("numbered-list inflation", "Three key takeaways follow.\n", "numbered-list inflation"),
        ("stacked questions", "Is it fast? Is it safe?\n", "stacked questions"),
    ]
    for name, text, expected in cases:
        check(f"fires: {name}", expected in " ".join(fires(text)), " ".join(fires(text)))

    check("fires: negative listing",
          any(i.startswith("negative listing") for i in
              fires("Not a dashboard. Not a portal. Not a tool. It was different.\n")))
    check("fires: hashtag block",
          any(i.startswith("hashtag block") for i in
              fires("#AI #Tech #Build #Ship #Code #Tools here.\n")))
    check("fires: over-compressed shorthand",
          any(i.startswith("over-compressed") for i in
              fires(" ".join(["a \u2192 b"] * 6) + "\n")))
    check("fires: bare noun-phrase bullets",
          any(i.startswith("bare noun-phrase") for i in
              fires("- speed\n- scale\n- safety\n- cost\n- risk\n\n")))

    # A repeated article is not a repeated opener, and a list is not a paragraph.
    check("silent: repeated articles",
          not any(i.startswith("same-opener") for i in
                  fires("The gate reads it. The gate writes it. The gate stops there.\n")))
    check("fires: repeated real opener",
          any(i.startswith("same-opener") for i in
              fires("Gates open early. Gates close late. Gates stay shut after dark. Gates rust.\n")))
    check("silent: short bullets are not staccato",
          not any(i.startswith("staccato") for i in
                  fires("- one\n- two\n- three\n- four\n- five\n\n")))

    # Register: a README keeps its bold labels, a note does not.
    readme = "**Install** the plugin.\n\n- **Mode:** warn\n- **Floor:** 200\n- **Profile:** base\n"
    check("register: docs keeps bold labels", not any("bold lead-in" in i for i in fires(readme, "README.md")),
          " ".join(fires(readme, "README.md")))
    check("register: a plain note does not",
          any("bold lead-in" in i for i in fires(readme, "notes.txt")),
          " ".join(fires(readme, "notes.txt")))
    check("register: an explicit context relaxes",
          not any("em dash" in i for i in
                  fires("One \u2014 two \u2014 three \u2014 four \u2014 five.\n",
                        "notes.txt", {"preferences": {"no_em_dash": True}, "context": "casual"})))
    check("register: docs is inferred from a path",
          rules.context_for_path("public/x/LIMITATIONS.md") == "docs")
    check("register: chat keeps the strict rules", rules.context_for_path("") == "")


    # ---- one switch per family, and it wins over the profile
    ctx.config["tell_hedges"] = False
    check("a family switch turns that family off", "hedges" in module._disabled_families(),
          str(module._disabled_families()[:4]))
    hedge_text = "Perhaps this is arguably fine. Maybe it is somewhat unclear. It could be argued."
    off = module._disabled_families()
    check("a disabled family stays silent",
          not any("hedge" in item for item in rules.gate_findings(rules.lint(hedge_text), None, "notes.txt", disabled=off)))
    check("the other families still fire",
          bool(rules.gate_findings(rules.lint(SLOP), None, "notes.txt", disabled=off)))
    ctx.config["tell_hedges"] = True
    check("switching it back restores the family", "hedges" not in module._disabled_families())


    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
