"""Keep authored settings labels and hints in the manifest without reformatting it."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    copy = json.loads((ROOT / 'settings_copy.json').read_text(encoding='utf-8'))
    path = ROOT / 'plugin.yaml'
    lines = path.read_text(encoding='utf-8').splitlines()
    key = None
    seen = set()
    for index, line in enumerate(lines):
        match = re.match(r'^  ([\w_]+):$', line)
        if match: key = match[1]
        elif line and not line.startswith((' ', '#')): key = None
        if key in copy:
            if line.startswith('    label:'):
                lines[index] = '    label: ' + json.dumps(copy[key][0], ensure_ascii=False)
                seen.add(key)
            elif line.startswith('    description:'):
                lines[index] = '    description: ' + json.dumps(copy[key][1], ensure_ascii=False)
    missing = set(copy) - seen
    if missing: raise ValueError(f'Copy has no matching settings: {sorted(missing)}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'{len(seen)} settings labels and hints updated.')


if __name__ == '__main__': main()
