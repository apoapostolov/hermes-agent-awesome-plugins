#!/usr/bin/env python3
"""Mechanical half of the catalog review gate.

    python admission_check.py <plugin-dir> [--entry plugin-catalog/<name>.yaml]

Prints FAIL / WARN / INFO per finding with file:line, then a summary. Exit 1 on
any FAIL. This is a floor: the reviewer reads the whole tree, so a clean run is
permission to open the PR, never evidence it will land. Every pattern here came
from a real finding in a NousResearch/hermes-agent catalog review; the checklist
that explains each one is maintained in the hermes-plugin-desk-ops skill at
references/catalog-review-bar.md.

Context matters more than the pattern, so each check looks at its neighbourhood:
an `env=` on the call, a guard line above an extraction, a scoped selector, a
test harness writing sys.modules. A naive grep on this list would fail our own
listed plugins, and a gate that cries wolf gets ignored.

No third-party imports (the host python has no PyYAML), so YAML is read as flat
keys by regex.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".git", "node_modules", "dist", "build", ".venv", "venv"}

# Hermes measures a plugin's system-prompt section against its own cap and skips an
# oversized one instead of truncating it, so the section is lost whole at session
# start. The cap is applied to the text, not to the max_chars a plugin declares.
HOST_PROMPT_CAP = 2_200


def nearby(text: str, pos: int, window: int, needle: str) -> bool:
    return needle in text[max(0, pos - window): pos + window]


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


class Findings:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str, int]] = []

    def add(self, severity: str, rule: str, path: Path, line: int, message: str) -> None:
        self.rows.append((severity, rule, str(path), message, line))

    def count(self, severity: str) -> int:
        return sum(1 for row in self.rows if row[0] == severity)


# ---------------------------------------------------------------- desktop JS
# (severity, rule, pattern, message, predicate)
def js_rules():
    def observer_is_body(text, match):
        tail = text[match.start(): match.start() + 400]
        return ".observe(document.body" in tail or "childList" in tail or "subtree: true" in tail

    def selector_is_scoped(text, match):
        # Judge the selector that carries the banned attribute, not the whole
        # template string: a stylesheet can scope one rule and leave the next
        # global, which is exactly what #129250 rejected.
        line_start = text.rfind(chr(10), 0, match.start()) + 1
        line_end = text.find(chr(10), match.start())
        segment = text[line_start: line_end if line_end > 0 else match.start() + 200]
        own = re.search(r"\[data-(?!slot|testid|tour|sidebar|tree|state|orientation|highlighted|disabled|selected|align|side)[a-z][\w-]*", segment)
        return not own

    def click_app_node(text, match):
        return "querySelector" in text[max(0, match.start() - 200): match.start()]

    return [
        ("FAIL", "rule-8", r"window\.hermesDesktop", "raw app bridge; use host.request or a host.<area> door", None),
        ("FAIL", "rule-8", r"localStorage\.(get|set|remove)Item\(\s*['\"]hermes\.desktop", "app storage key; use ctx.storage or host.pluginDecisions", None),
        ("FAIL", "rule-8", r"__reactFiber\$|__reactProps\$|_reactProps", "React internals; use a registered slot or host.sessions", None),
        ("FAIL", "rule-8", r"\[data-(slot|testid|tour|sidebar|tree|state|orientation|highlighted|disabled|selected|align|side)", "app-owned DOM selector; use a ctx.register area", selector_is_scoped),
        ("FAIL", "rule-8", r"new MutationObserver", "app-wide observer; re-register on your own state", observer_is_body),
        ("FAIL", "rule-8", r"document\.execCommand", "composer write; use host.composer", None),
        ("FAIL", "rule-8", r"\bnew Function\s*\(|\beval\s*\(", "code eval is refused outright", None),
        ("FAIL", "rule-8", r"Object\.defineProperty\(\s*[A-Za-z_.]+\s*,?\s*|Storage\.prototype", "prototype patching is refused", None),
        ("FAIL", "rule-8", r"<webview|createElement\(['\"]webview", "app-partition webview; use <SandboxedFrame>", None),
        ("WARN", "rule-8", r"document\.querySelector", "app DOM query needs a justification in the PR body", None),
        ("WARN", "rule-8", r"insertAdjacentElement|insertAdjacentHTML|\.appendChild\s*\(", "node injection; confirm the parent is your own", None),
        ("WARN", "rule-8", r"dangerouslySetInnerHTML", "innerHTML sink; sanitize and justify", None),
        ("WARN", "rule-8", r"\.click\s*\(\s*\)", "synthetic click on an app node; use your own control", click_app_node),
        ("INFO", "rule-8", r"import\s*\(", "dynamic import must resolve to @hermes/plugin-sdk or react only", None),
    ]


# --------------------------------------------------------------------- python
CORE_MODULE = re.compile(r"['\"](hermes_cli|tui_gateway|agent|tools|gateway|hermes_constants)[.\w]*['\"]")


def py_rules():
    def unguarded(text, match):
        guarded = nearby(text, match.start(), 500, "is_relative_to") or nearby(text, match.start(), 500, "relative_to(")
        return not guarded

    def modules_assignment(text, match):
        return bool(CORE_MODULE.search(text[match.start(): match.start() + 240]))

    return [
        ("FAIL", "rule-9", r"_agent_cache|reasoning_config\s*=|agent\.switch_model|_preflight_request_tokens|agent\.usage_anchor", "private agent internals; use llm_request middleware", None),
        ("FAIL", "rule-9", r"^\s*subprocess\.Popen\s*=", "process-wide Popen patch; refused", None),
        ("FAIL", "rule-9", r"sys\.modules\[[^\]]+\]\s*=", "overrides a core module entry; refused", modules_assignment),
        ("FAIL", "rule-9", r"tui_gateway\.server\._|from\s+tui_gateway\.server\s+import\s+_", "private gateway import; use broadcast_plugin_event", None),
        ("FAIL", "rule-11", r"os\.environ\[[^\]]+\]\s*=|os\.environ\.setdefault|os\.environ\.update", "os.environ write; allowed only inside a test fixture", None),
        ("FAIL", "rule-11", r"\.grok/|(?<![\w-])auth\.json|\.codex/auth|\.claude/\.credentials", "vendor credential store; you may not read or refresh it", None),
        ("FAIL", "rule-11", r"library\.env", "secret mirror into the plugin tree; refused", None),
        ("FAIL", "rule-12", r"shell\s*=\s*True", "shell=True; pass an argv list", None),
        ("FAIL", "scanner", r"/etc/passwd", "trips the install scanner to dangerous; use ../../victim in fixtures", None),
        ("WARN", "rule-11", r"(open|read_text)\s*\([^)]*['\"][^'\"]*\.env['\"]", "reads Hermes .env; use agent.secret_scope.get_secret", None),
        ("WARN", "rule-11", r"(write_text|open)\([^\n]*\.env['\"]?\s*,\s*['\"]w", "writes .env; only as a separate explicit user action", None),
        ("WARN", "rule-12", r"subprocess\.(run|Popen|call|check_output|check_call)\s*\(", "no env= here; pass a minimal env unless the child is the user's own app", None),
        ("WARN", "security", r"\.extractall\s*\(", "extraction needs a member-path and sibling-prefix guard", unguarded),
        ("WARN", "security", r"\.unlink\s*\(", "deletion: confirm the id is shape-gated or resolve().relative_to(base)", unguarded),
        ("WARN", "rule-14", r"confirm_expensive_model\s*:\s*True", "never answer a core confirmation guard for the user", None),
        ("INFO", "network", r"urlopen\s*\(|requests\.(get|post)|httpx\.|aiohttp\.", "third-party network call; the listing needs a disclosure sentence", None),
    ]


def files(root: Path, suffixes: set[str]) -> list[Path]:
    out = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if SKIP_DIRS & set(path.parts):
            continue
        out.append(path)
    return out


def is_test(path: Path) -> bool:
    return ("tests" in path.parts or path.name.startswith(("test_", "tests_"))
            or path.name.endswith("_test.py"))


JS_TOOLING = {"tests", "scripts", "docs", "node_modules", "dist"}


def scan(path: Path, root: Path, found: Findings, text: str, is_js: bool) -> None:
    if is_js and (is_test(path) or JS_TOOLING & set(path.relative_to(root).parts)):
        return
    rules = js_rules() if is_js else py_rules()
    for severity, rule, pattern, message, predicate in rules:
        for match in re.finditer(pattern, text, re.M):
            if predicate is not None and not predicate(text, match):
                continue
            if is_test(path) and severity == "FAIL" and rule != "scanner":
                severity = "INFO"
            if not is_js and pattern.startswith("subprocess") and ("env=" in text[max(0, match.start() - 120): match.start() + 240]):
                continue
            found.add(severity, rule, path.relative_to(root), line_of(text, match.start()), message)


def flat(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def key(text: str, name: str) -> str:
    match = re.search(rf"^{name}:\s*(.+)$", text, re.M)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def prompt_variants(root: Path) -> list[tuple[str, str]] | None:
    """Every prompt-section variant a plugin publishes, or None when it publishes none.

    A plugin makes its own section measurable by defining `prompt_texts()` in
    `prompt_section.py`, returning `[[label, text], ...]` for each shape the host can
    receive. None means the plugin ships no such module; an empty list means it ships
    one without the hook, which is a warning rather than a finding.
    """
    module = root / "prompt_section.py"
    if not module.is_file():
        return None
    code = (
        "import importlib.util, json, sys\n"
        "spec = importlib.util.spec_from_file_location('prompt_section', sys.argv[1])\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "hook = getattr(mod, 'prompt_texts', None)\n"
        "print(json.dumps([[str(a), str(b)] for a, b in hook()] if hook else []))\n"
    )
    try:
        run = subprocess.run([sys.executable, "-c", code, str(module)],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    if run.returncode != 0 or not run.stdout.strip():
        return []
    try:
        pairs = json.loads(run.stdout.strip().splitlines()[-1])
        return [(str(a), str(b)) for a, b in pairs]
    except (ValueError, TypeError):
        return []


def prompt_findings(root: Path, found: Findings, manifest: str, prod_py: str) -> None:
    declared = key(manifest, "max_chars")
    if declared.isdigit() and int(declared) > HOST_PROMPT_CAP:
        found.add("FAIL", "prompt-cap", Path("plugin.yaml"), 1,
                  f"max_chars {declared} is over the host's {HOST_PROMPT_CAP}; the section is dropped whole")
    variants = prompt_variants(root)
    if variants is None:
        return
    if not variants:
        if "register_system_prompt_section" in prod_py:
            found.add("WARN", "prompt-cap", Path("prompt_section.py"), 1,
                      "registers a prompt section but no prompt_texts(); the size cannot be measured, and an oversized section is skipped whole")
        return
    for label, text in variants:
        if len(text) > HOST_PROMPT_CAP:
            found.add("FAIL", "prompt-cap", Path("prompt_section.py"), 1,
                      f"prompt section {label!r} is {len(text)} chars, over the host's {HOST_PROMPT_CAP}; it is skipped, not truncated")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="plugin directory (one edition, not the repo)")
    parser.add_argument("--entry", help="catalog entry yaml to cross-check")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    manifest_path = root / "plugin.yaml"
    portable = not manifest_path.is_file()
    if portable:
        manifest_path = root / "plugin.json"
        if not manifest_path.is_file():
            print(f"no plugin.yaml or plugin.json in {root}")
            return 2

    found = Findings()
    js = files(root, {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"})
    py = files(root, {".py"})
    for path in js:
        scan(path, root, found, path.read_text(encoding="utf-8", errors="replace"), True)
    for path in py:
        scan(path, root, found, path.read_text(encoding="utf-8", errors="replace"), False)

    if portable:
        # A portable Agent Plugins v1 package has no plugin.yaml, so the rules that
        # read one (declared requires_env, pre_tool_call, max_chars) have nothing to
        # read. Its server declaration lives in mcp.json; the rest of the floor still
        # applies: source scan, sha and version cross-check, image pin, platforms,
        # disclosure.
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace"))
        except ValueError as exc:
            print(f"{manifest_path.name} is not valid JSON: {exc}")
            return 1
        manifest = ""
        version = str(data.get("version") or "")
        found.add("INFO", "portable", manifest_path.name, 0,
                  "portable package: the plugin.yaml-only checks (requires_env, pre_tool_call, prompt cap) do not apply")
    else:
        manifest = flat(manifest_path)
        version = key(manifest, "version")
    prod_py = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in py if not is_test(p))
    all_js = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in js if not is_test(p))

    for match in re.finditer(r"^\s*(?:from|import)\s+hermes_cli[.\w]*", prod_py, re.M):
        line = prod_py.splitlines()[line_of(prod_py, match.start()) - 1]
        if "plugin_events" in line or "secret_scope" in line:
            continue
        found.add("FAIL", "rule-9", Path("."), 0, f"private hermes_cli import: {line.strip()[:70]}")
    schema_text = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                            for p in py if "schema" in p.name.lower())
    if re.search(r"https?://[^\"'\s]*\{version\}", prod_py) and re.search(r'''["']version["']\s*:''', schema_text):
        found.add("FAIL", "rule-17", Path("."), 0, "a tool-supplied version reaches a download URL; pin digests and refuse unpinned versions")
    if not portable and "get_secret(" in prod_py and "requires_env" not in manifest:
        found.add("FAIL", "rule-11", Path("plugin.yaml"), 1, "get_secret() used but requires_env is not declared")
    if not portable and re.search(r"subprocess\.(run|Popen|call|check_output)", prod_py):
        if "pre_tool_call" not in manifest:
            found.add("WARN", "rule-12", Path("plugin.yaml"), 1, "starts a program and declares no pre_tool_call; fine only if no tool argument reaches it")

    if not portable:
        prompt_findings(root, found, manifest, prod_py)

    if args.entry:
        entry_path = Path(args.entry)
        entry = flat(entry_path)
        sha = key(entry, "sha")
        entry_version = key(entry, "version")
        if sha and not re.fullmatch(r"[0-9a-f]{40}", sha):
            found.add("FAIL", "rule-2", entry_path.name, 1, f"sha {sha!r} is not 40 lowercase hex")
        if version and entry_version and entry_version != version:
            found.add("FAIL", "rule-14", entry_path.name, 1, f"entry version {entry_version} != {manifest_path.name} {version}")
        for url in set(re.findall(r"https://raw\.githubusercontent\.com/[^/]+/[^/]+/([0-9a-f]{40})/", entry)):
            if sha and url != sha:
                found.add("FAIL", "rule-2", entry_path.name, 1, f"an image is pinned to {url[:8]} but the entry sha is {sha[:8]}")
        if re.search(r"CREATE_NO_WINDOW|winreg|%LOCALAPPDATA%|AppData\\\\Local", prod_py + all_js) and not re.search(r"platforms:\s*\[?\s*windows", entry):
            found.add("FAIL", "rule-14", entry_path.name, 1, "Windows-only code but platforms does not say windows")
        if re.search(r"urlopen|requests\.|httpx\.|aiohttp\.", prod_py) and "Disclosure" not in entry:
            found.add("FAIL", "rule-13", entry_path.name, 1, "network calls with no Disclosure sentence in the description")
        if re.search(r"Desktop 0\.\d|hides the|0\.\d+\.\d+ \+?and? newer", key(entry, "description")):
            found.add("WARN", "rule-14", entry_path.name, 1, "description claims host behaviour; verify it exists in the pinned Hermes")

    order = {"FAIL": 0, "WARN": 1, "INFO": 2}
    found.rows.sort(key=lambda row: (order[row[0]], row[2], row[4]))
    print(f"{root.name} {version}".strip())
    if not found.rows:
        print("  clean: no mechanical finding")
    for severity, rule, path, message, line in found.rows:
        where = f"{path}:{line}" if line else path
        print(f"  {severity:4s} {rule:9s} {where:52s} {message}")
    print(f"\nsummary: {found.count('FAIL')} FAIL, {found.count('WARN')} WARN, {found.count('INFO')} INFO")
    print("floor only: the catalog checklist is references/catalog-review-bar.md in the desk-ops skill")
    return 1 if found.count("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
