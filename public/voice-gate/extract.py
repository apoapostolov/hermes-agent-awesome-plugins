"""Pull the prose out of whatever a turn or a commit changed.

The gate judges text, so it needs text from more than Markdown: a plain
``.txt`` note, a reStructuredText page, an AsciiDoc or Org document, a
generated PDF. Two decisions follow from that.

Markup is removed before the rules see the file, because a README that shows
code inside a fence is prose plus a code sample, and counting the sample
would flag the documentation for quoting what it discusses.

PDFs are decoded here rather than behind a library. The backend's interpreter
ships no PDF package, and a gate that needs an install is a gate that quietly
stops running on the next machine.
"""

from __future__ import annotations

import html
import re
import zlib
from pathlib import Path
from typing import Optional

TEXT_SUFFIXES = {
    ".md", ".markdown", ".mdx",
    ".txt", ".text", ".rst", ".rest",
    ".adoc", ".asciidoc", ".asc",
    ".org", ".tex", ".html", ".htm",
}
PDF_SUFFIXES = {".pdf"}

MAX_BYTES = 8_000_000

_RST_DIRECTIVE = re.compile(r"(?m)^[ \t]*\.\.[ \t]+\S.*$")
_RST_INLINE = re.compile(r"``([^`]+)``|:[a-z:+-]+:`([^`]+)`")
_ADOC_FENCE = re.compile(r"(?ms)^(/[-=.*_+]{4,})\s*$.*?^\1\s*$")
_ADOC_INLINE = re.compile(r"\+([^+\n]+)\+")
_ORG_BLOCK = re.compile(r"(?ms)^[ \t]*#\+(begin_src|begin_example|begin_export)\b.*?^[ \t]*#\+end_\1[ \t]*$")
_TEX_BLOCK = re.compile(r"(?ms)^[ \t]*\\begin\{(verbatim|lstlisting|minted|equation\*?)\}.*?^[ \t]*\\end\{\1\}")
_TEX_COMMAND = re.compile(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?")
_HTML_DROP = re.compile(r"(?is)<(script|style|pre|code|svg)\b.*?</\1\s*>")
_HTML_TAG = re.compile(r"(?s)<[^>]+>")
_PDF_OBJECT = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_PDF_LITERAL = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)
_PDF_HEX = re.compile(rb"<([0-9A-Fa-f\s]+)>")
_PDF_ESCAPES = {
    b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
    b"(": b"(", b")": b")", b"\\": b"\\",
}


def is_prose_path(path: Path) -> bool:
    """Whether the gate should look inside this file at all."""
    suffix = path.suffix.lower()
    return suffix in TEXT_SUFFIXES or suffix in PDF_SUFFIXES


def read(path: Path) -> Optional[str]:
    """The file's prose, or None when there is nothing to judge."""
    try:
        suffix = path.suffix.lower()
        if suffix in PDF_SUFFIXES:
            return prose_lines(pdf_text(path)) or None
        if suffix not in TEXT_SUFFIXES:
            return None
        if path.stat().st_size > MAX_BYTES:
            return None
        raw = path.read_bytes()
    except Exception:
        return None
    return prose_lines(to_prose(_decode(raw), suffix))


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def to_prose(text: str, suffix: str) -> str:
    """Drop the markup and code a document carries, keeping its sentences."""
    if suffix in {".html", ".htm"}:
        text = _HTML_DROP.sub(chr(10), text)
        text = _HTML_TAG.sub(chr(10), text)
        return html.unescape(text)
    if suffix in {".rst", ".rest"}:
        text = _RST_DIRECTIVE.sub("", text)
        text = _strip_indented_blocks(text)
        return _RST_INLINE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    if suffix in {".adoc", ".asciidoc", ".asc"}:
        text = _ADOC_FENCE.sub("", text)
        return _ADOC_INLINE.sub(lambda m: m.group(1), text)
    if suffix == ".org":
        return _ORG_BLOCK.sub("", text)
    if suffix == ".tex":
        text = _TEX_BLOCK.sub("", text)
        text = re.sub(r"(?m)%.*$", "", text)
        return _TEX_COMMAND.sub("", text)
    return text


CODE_CHARS = set("{}[]();=<>$#|&*/\\")
CODE_STARTS = (
    "def ", "class ", "import ", "from ", "function ", "const ", "let ", "var ",
    "return ", "if ", "for ", "while ", "public ", "private ", "protected ",
    "package ", "use ", "fn ", "impl ", "SELECT ", "INSERT ", "UPDATE ", "DELETE ",
    "#include", "<?", "<!", "curl ", "$ ", ">>> ", "... ", "npm ", "pip ",
)


def prose_lines(text: str) -> str:
    """The lines that read as prose, so a code sample cannot pass as a document.

    A file of source code is not a document to judge: its lines start with a
    keyword or carry code punctuation on most characters. Dropping those lines
    leaves the word count that the floor already measures, which is how a
    README with code blocks stays prose while a `.txt` of Python does not.

    Fenced regions go whole, delimiters included, because leaving the content
    behind would read a YAML example as a paragraph: a profile that lists the
    phrases it refuses must not be flagged for listing them.
    """
    kept: list[str] = []
    fenced = False
    for raw in text.splitlines():
        head = raw.lstrip()
        if not head:
            continue
        if head.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        indent = len(raw) - len(head)
        is_item = head.startswith(("- ", "* ", "+ ", "> ")) or head[:2].strip().isdigit()
        if (
            indent >= 4
            and not is_item
            and (":" in head or "=" in head or head.startswith(("{", "[", '"', "'")))
        ):
            continue  # an indented config or code block, never a paragraph
        if head.startswith(CODE_STARTS):
            continue
        density = sum(char in CODE_CHARS for char in head) / len(head)
        if density > 0.12:
            continue
        if len(head.split()) <= 3 and not head.endswith((".", "!", "?", ":", ";", ",")):
            continue  # a heading or a label, not a sentence
        kept.append(head)
    return "\n".join(kept)


def _strip_indented_blocks(text: str) -> str:
    """Remove the indented body under a reST literal marker (``::``)."""
    lines = text.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        out.append(line)
        if line.rstrip().endswith("::") and index + 1 < len(lines):
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index][:1] in " \t"):
                index += 1
            continue
        index += 1
    return "\n".join(out)


def pdf_text(path: Path) -> str:
    """Text from a PDF's content streams, using only the standard library.

    Covers what generated documents use: uncompressed and Flate streams with
    ``Tj`` and ``TJ`` operators. A scanned page carries no text at all and
    returns "", which the caller treats as nothing to judge.
    """
    try:
        raw = path.read_bytes()
    except Exception:
        return ""
    if b"%PDF" not in raw[:1024]:
        return ""
    pieces: list[str] = []
    for block in _PDF_OBJECT.findall(raw):
        for stream in _inflate(block):
            pieces.extend(_content_strings(stream))
    return " ".join(piece for piece in pieces if piece).strip()


def _inflate(block: bytes) -> list[bytes]:
    out = [block]
    try:
        out.append(zlib.decompress(block))
    except Exception:
        try:
            out.append(zlib.decompressobj().decompress(block))
        except Exception:
            pass
    return out


def _content_strings(stream: bytes) -> list[str]:
    """Every text string in a content stream, in page order."""
    found: list[str] = []
    for match in _PDF_LITERAL.finditer(stream):
        value = _unescape_literal(match.group(0)[1:-1])
        if value.strip():
            found.append(value)
    for match in _PDF_HEX.finditer(stream):
        try:
            digits = re.sub(rb"\s+", b"", match.group(1))
            if len(digits) % 2:
                digits += b"0"
            value = bytes.fromhex(digits.decode("ascii")).decode("utf-16-be", "ignore")
        except Exception:
            continue
        if value.strip():
            found.append(value)
    # A TJ array splits one string into kerning pieces; joining above is close
    # enough for word counting, and the newline marker keeps sentences apart.
    return found


def _unescape_literal(body: bytes) -> str:
    out = bytearray()
    index = 0
    while index < len(body):
        char = body[index:index + 1]
        if char != b"\\":
            out.extend(char)
            index += 1
            continue
        index += 1
        if index >= len(body):
            break
        nxt = body[index:index + 1]
        if nxt in _PDF_ESCAPES:
            out.extend(_PDF_ESCAPES[nxt])
            index += 1
        elif nxt.isdigit():
            octal = body[index:index + 3]
            keep = 0
            while keep < len(octal) and octal[keep:keep + 1].isdigit() and keep < 3:
                keep += 1
            try:
                out.append(int(octal[:keep], 8) & 0xFF)
            except ValueError:
                pass
            index += keep
        elif nxt in (b"\n", b"\r"):
            index += 1
        else:
            out.extend(nxt)
            index += 1
    return bytes(out).decode("utf-8", "replace")
