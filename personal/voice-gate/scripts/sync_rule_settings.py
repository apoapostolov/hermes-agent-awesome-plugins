"""Maintain one generated settings switch per new mechanical or vocabulary family."""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = '  # Generated humanizer families: scripts/sync_rule_settings.py\n'


def main():
    spec = importlib.util.spec_from_file_location('vg_settings_gen', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    families = {key: spec[4] for key, spec in module.rules.mechanics.SPECS.items()}
    families.update({'tier1a': 'Frequency-band vocabulary markers; inspect context, never infer authorship.', 'tier1b': 'Clarity and formality suggestions, separate from authorship markers.', 'tier2': 'Two or more Tier 2 occurrences in the same paragraph.', 'tier3': 'Repetition of one Tier 3 word at the documented per-word density.', 'tier3_phrases': 'Repeated Tier 3 phrases or a cluster of three distinct phrases.'})
    path = ROOT / 'plugin.yaml'
    current = path.read_text(encoding='utf-8')
    head, marker, tail = current.partition(MARKER)
    following = re.search(r'^\S', tail, re.M) if marker else None
    before = (head + (tail[following.start():] if following else '')).rstrip() + '\n' if marker else current
    rows = [MARKER.rstrip()]
    copy_path = ROOT / 'settings_copy.json'
    copy = json.loads(copy_path.read_text(encoding='utf-8')) if copy_path.exists() else {}
    for key, description in families.items():
        label, description = copy.get(f'tell_{key}', [key.replace('_', ' ').capitalize(), description])
        rows.extend([f'  tell_{key}:', '    type: bool', '    default: true', f'    label: {json.dumps(label, ensure_ascii=False)}', f'    description: {json.dumps(description, ensure_ascii=False)}'])
    start = before.index('config_schema:\n') + len('config_schema:\n')
    suffix = before[start:]
    next_section = re.search(r'^\S', suffix, re.M)
    position = start + next_section.start() if next_section else len(before)
    path.write_text(before[:position].rstrip() + '\n' + '\n'.join(rows) + '\n' + before[position:], encoding='utf-8')
    print(f'{len(families)} family settings synchronized.')


if __name__ == '__main__': main()
