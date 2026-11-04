"""Wide format tests: every text-bearing document type the gate should judge.

    python tests/test_wide_formats.py

No third-party packages: the PDFs are built here with the standard library, so
this proves the extractor rather than a library that happens to be installed.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import zlib
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []

SLOP = ("In today's fast-paced world we delve into the tapestry of a pivotal platform. "
        "It plays a crucial role and serves as a testament to the team. "
        "Moreover, it is seamless. Furthermore, it is robust. In conclusion, this is a turning point.")
CLEAN = ("The release adds a settings page and fixes the blank row on load. "
         "Install it with the command below, then open Plugins and check the row.")
FILLER = "The page opens, the row loads, and the value stays where it was. " * 22
CODE = ("def main():\n"
        "    total = 0\n"
        "    for index in range(200):\n"
        "        total += index\n"
        "    return total\n\n")


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
        return
    FAILURES.append(name)
    print(f"  FAIL {name}{': ' + detail if detail else ''}")


def load():
    spec = importlib.util.spec_from_file_location(
        "voice_gate_wide", PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["voice_gate_wide"] = module
    spec.loader.exec_module(module)
    return module


def make_pdf(path: Path, text: str, compress: bool) -> None:
    body = ("BT /F1 12 Tf 72 720 Td (" +
            text.replace("(", r"\(").replace(")", r"\)") + ") Tj ET").encode()
    stream = zlib.compress(body) if compress else body
    filt = b" /Filter /FlateDecode" if compress else b""
    path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length " + str(len(stream)).encode() + filt + b" >>\nstream\n" +
        stream + b"\nendstream endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"trailer << /Root 1 0 R >>\n%%EOF\n"
    )


def build(root: Path) -> dict[str, Path]:
    files = {
        "doc.md": f"# Notes\n\n{SLOP}\n\n{FILLER}\n\n```python\nprint('x')\n```\n",
        "doc.markdown": f"Notes\n\n{SLOP}\n\n{FILLER}\n",
        "doc.txt": f"Notes\n\n{SLOP}\n\n{FILLER}\n",
        "doc.rst": (f"Notes\n=====\n\n{SLOP}\n\n{FILLER}\n\n"
                    ".. code-block:: python\n\n   for i in range(3):\n      print(i)\n"),
        "doc.adoc": (f"= Notes\n\n{SLOP}\n\n{FILLER}\n\n[source,python]\n----\n"
                     "for i in range(3):\n  print(i)\n----\n"),
        "doc.org": (f"* Notes\n\n{SLOP}\n\n{FILLER}\n\n#+BEGIN_SRC python\n"
                    "for i in range(3):\n  print(i)\n#+END_SRC\n"),
        "doc.tex": (f"\\documentclass{{article}}\n\\begin{{document}}\n{SLOP}\n\n{FILLER}\n"
                    "\\begin{verbatim}\nprint(1)\n\\end{verbatim}\n\\end{document}\n"),
        "doc.html": ("<html><head><style>p{color:red}</style></head><body><h1>Notes</h1><p>" + SLOP +
                     "</p><pre>print(1)</pre><p>" + FILLER + "</p></body></html>\n"),
        "clean.md": f"# Notes\n\n{CLEAN}\n\n{FILLER}\n",
        "clean.txt": f"Notes\n\n{CLEAN}\n\n{FILLER}\n",
        "clean.rst": f"Notes\n=====\n\n{CLEAN}\n\n{FILLER}\n",
        "clean.html": f"<html><body><p>{CLEAN}</p><p>{FILLER}</p></body></html>\n",
        "code.txt": CODE * 40,
        "code.py": CODE * 40,
    }
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    make_pdf(root / "doc.pdf", SLOP + " " + FILLER, compress=False)
    make_pdf(root / "doc-flate.pdf", SLOP + " " + FILLER, compress=True)
    make_pdf(root / "clean.pdf", CLEAN + " " + FILLER, compress=True)
    make_pdf(root / "blank.pdf", "", compress=True)
    return {name: root / name for name in
            [*files, "doc.pdf", "doc-flate.pdf", "clean.pdf", "blank.pdf"]}


def main() -> int:
    module = load()
    extract = module.extract
    root = Path(tempfile.mkdtemp(prefix="vg-wide-"))
    files = build(root)
    print(f"{PLUGIN.parent.name}/voice-gate — wide formats")

    flagged = ["doc.md", "doc.markdown", "doc.txt", "doc.rst", "doc.adoc", "doc.org",
               "doc.tex", "doc.html", "doc.pdf", "doc-flate.pdf"]
    silent = ["clean.md", "clean.txt", "clean.rst", "clean.html", "clean.pdf"]

    for name in flagged:
        text = extract.read(files[name])
        found = module.rules.gate_findings(module.rules.lint(text or "")) if text else []
        check(f"{name} is judged and reports tells", bool(found), f"words={len((text or '').split())}")

    for name in silent:
        text = extract.read(files[name]) or ""
        found = module.rules.gate_findings(module.rules.lint(text))
        check(f"{name} stays silent", not found, str(found))

    code_words = len((extract.read(files["code.txt"]) or "").split())
    check("a source-code .txt carries no prose", code_words == 0, f"{code_words} words")
    check("a .py file is not prose", not extract.is_prose_path(files["code.py"]))
    check("a blank PDF has nothing to judge", not (extract.read(files["blank.pdf"]) or "").strip())
    check("the compressor is exercised", "delve" in (extract.read(files["doc-flate.pdf"]) or ""))

    # a README that shows code stays prose: the fence must not be counted
    fenced = root / "fenced.md"
    fenced.write_text(f"# Notes\n\n{CLEAN}\n\n```\ndelve tapestry seamless\n```\n\n{FILLER}\n", encoding="utf-8")
    fenced_text = extract.read(fenced) or ""
    check("code inside a README is not counted", not module.rules.gate_findings(module.rules.lint(fenced_text)))

    # the same words in a sentence still fire
    inline = root / "inline.md"
    inline.write_text(
        f"# Notes\n\nWe delve into the tapestry of a seamless yet pivotal testament.\n\n{FILLER}\n",
        encoding="utf-8",
    )
    check("the same words in prose still fire",
          bool(module.rules.gate_findings(module.rules.lint(extract.read(inline) or ""))))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
