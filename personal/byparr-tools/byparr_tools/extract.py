"""Domain-agnostic structured extraction from solved HTML.

Keeps site-specific rules out of the transport plugin. Produces JSON-LD,
meta tags, headings and definition/list pairs that any caller can interpret.
Python's html.parser keeps this dependency-free.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any, Dict, List


class _Collector(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jsonld: List[Any] = []
        self.meta: Dict[str, str] = {}
        self.title = ""
        self.headings: List[str] = []
        self.pairs: List[Dict[str, str]] = []
        self._stack: List[str] = []
        self._in_title = False
        self._capture: List[str] | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        tag = tag.lower()
        if tag in self.SKIP:
            return
        if tag == "meta":
            key = a.get("property") or a.get("name") or a.get("itemprop")
            content = a.get("content")
            if key and content:
                self.meta[key] = content
        elif tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3"):
            self._capture = []
        elif tag == "dt":
            self._capture = []
        elif tag == "dd" and self.pairs:
            self._capture = []
        if tag not in ("meta", "link", "br", "img", "input", "hr"):
            self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in ("h1", "h2", "h3") and self._capture is not None:
            text = " ".join("".join(self._capture).split())
            if text:
                self.headings.append(text)
            self._capture = None
        if tag in ("dt", "dd") and self._capture is not None:
            text = " ".join("".join(self._capture).split())
            if tag == "dt":
                self.pairs.append({"term": text, "value": ""})
            elif self.pairs:
                self.pairs[-1]["value"] = text
            self._capture = None
        if tag in self._stack:
            while self._stack:
                popped = self._stack.pop()
                if popped == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._capture is not None:
            self._capture.append(data)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        pass


def extract(html: str, max_pairs: int = 200) -> Dict[str, Any]:
    """Return structured data from a solved HTML document."""
    result: Dict[str, Any] = {
        "title": "", "meta": {}, "jsonld": [], "headings": [], "facts": [],
    }
    if not html:
        return result
    for block in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, flags=re.I | re.S,
    ):
        try:
            result["jsonld"].append(json.loads(block.strip()))
        except (ValueError, TypeError):
            pass
    parser = _Collector()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed HTML must not fail the tool
        pass
    result["title"] = " ".join(parser.title.split())
    result["meta"] = parser.meta
    result["headings"] = parser.headings[:40]
    result["facts"] = [p for p in parser.pairs if p.get("term")][:max_pairs]
    return result
