"""Snapshot the reviewed humanizer skill, with a source manifest and all 110 rules.

Run explicitly with the source skill directory. No runtime network or dependency.
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(source):
    source = Path(source).resolve()
    destination = ROOT / 'references' / 'humanizer'
    files = [source / 'SKILL.md', *sorted((source / 'references').glob('*.md'))]
    manifest = []
    for file in files:
        target = destination / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = file.read_text(encoding='utf-8')
        # The published review contract never ships a private person's binding.
        if file.name == 'apo-voice-profile.md':
            content = '# Approved author profile\n\nUse the approved author profile supplied by the current user or host. The explicit brief or writing sample wins over generic editorial preferences. Preserve meaning, attribution, conditions, uncertainty, obligations, and exact syntax. Do not invent a profile, identity, experience, or personal preference when no approved source is available. Profile learning is a separate workflow; corpus text is not automatically approved evidence.\n'
        else:
            content = content.replace("Apostol's profile", 'the approved author profile')
            content = content.replace('the private profile binding', 'the approved profile contract')
            content = content.replace('writing for Apo or when he asks for his voice. It includes register routing,', 'applying a user-approved voice. It includes register routing,')
        target.write_text(content, encoding='utf-8')
        manifest.append({'path': file.relative_to(source).as_posix(), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    catalog = (source / 'references' / 'pattern-catalog.md').read_text(encoding='utf-8')
    entries = []
    matches = list(re.finditer(r'^### (\d+)\. (.+)$', catalog, re.M))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(catalog)
        body = catalog[match.end():end].split('\n## ')[0].strip()
        entries.append({'id': int(match[1]), 'title': match[2], 'guidance': body})
    if {entry['id'] for entry in entries} != set(range(1, 111)):
        raise ValueError('Expected the complete 110-pattern catalog')
    (destination / 'catalog.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (destination / 'SOURCE.json').write_text(json.dumps({'skill_version': '1.11.0', 'source': 'Hermes writing/humanizer', 'adaptations': ['Private author binding replaced with a generic approved-profile contract.'], 'original_files': manifest}, indent=2) + '\n', encoding='utf-8')
    print(f'Snapshotted {len(files)} source files and {len(entries)} catalog patterns.')


if __name__ == '__main__':
    main(sys.argv[1])
