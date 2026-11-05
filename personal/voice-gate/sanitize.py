"""Mask protected Markdown spans without destroying line or paragraph boundaries."""
from __future__ import annotations
import re

FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
INLINE = re.compile(r'(`+)(?!`)([^\n]*?)(?<!`)\1(?!`)')
URL = re.compile(r'https?://[^\s<>\])]+')
PATH = re.compile(r'(?<!\w)(?:[A-Za-z]:[/\\]|(?:\.{0,2}/|~/))[\w./\\-]+')
QUOTES = re.compile(r'"[^"\n]+"|“[^”\n]+”')


def blank(text: str) -> str:
    return ''.join('\n' if char == '\n' else ' ' for char in text)


def protected_spans(text: str) -> dict[str, list[str]]:
    groups = {key: [] for key in ('frontmatter', 'fenced_code', 'inline_code', 'blockquotes', 'tables', 'quotes', 'urls', 'paths', 'headings')}
    lines = text.splitlines(keepends=True)
    index = 0
    if lines and lines[0].strip() == '---':
        for end in range(1, len(lines)):
            if lines[end].strip() in ('---', '...'):
                groups['frontmatter'].append(''.join(lines[:end + 1]))
                index = end + 1
                break
    while index < len(lines):
        line = lines[index]
        match = FENCE.match(line)
        if match:
            fence = match[1]
            end = index + 1
            closing = re.compile(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*$')
            while end < len(lines) and not closing.match(lines[end]):
                end += 1
            end = min(end + 1, len(lines))
            groups['fenced_code'].append(''.join(lines[index:end]))
            index = end
            continue
        if line.lstrip().startswith('>'):
            groups['blockquotes'].append(line)
        elif line.lstrip().startswith('|') and '|' in line.lstrip()[1:]:
            groups['tables'].append(line)
        elif re.match(r'^ {0,3}#{1,6}\s', line):
            groups['headings'].append(line)
        else:
            inline = INLINE.findall(line)
            groups['inline_code'].extend(''.join((fence, body, fence)) for fence, body in inline)
            prose = INLINE.sub(lambda m: blank(m[0]), line)
            groups['quotes'].extend(QUOTES.findall(prose))
            groups['urls'].extend(URL.findall(prose))
            groups['paths'].extend(PATH.findall(prose))
        index += 1
    return groups


def prose(text: str, keep_tables: bool = False, keep_headings: bool = False, keep_urls: bool = False) -> str:
    groups = protected_spans(text)
    for category, spans in groups.items():
        if category == 'tables' and keep_tables or category == 'headings' and keep_headings:
            continue
        if category == 'urls' and keep_urls:
            continue
        for span in spans:
            text = text.replace(span, blank(span))
    # Keep a link's reader-facing label; do not count its destination as prose.
    text = re.sub(r'\[([^]\n]+)\]\([^\n)]*\)', r'\1', text)
    return text
