from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).with_name("desktop") / "plugin.js"


def extract_schedule_helpers() -> str:
    source = PLUGIN.read_text(encoding="utf-8")
    start_marker = "// GLM_HOURS_START"
    end_marker = "// GLM_HOURS_END"
    if start_marker not in source or end_marker not in source:
        raise AssertionError("GLM hours markers missing")
    return source.split(start_marker, 1)[1].split(end_marker, 1)[0]


def test_schedule() -> None:
    cases = [
        ("2026-01-05T05:59:59Z", "off-peak"),  # Monday 13:59:59 Singapore
        ("2026-01-05T06:00:00Z", "peak"),      # Monday 14:00 Singapore
        ("2026-01-05T09:59:59Z", "peak"),      # Monday 17:59:59 Singapore
        ("2026-01-05T10:00:00Z", "off-peak"),  # Monday 18:00 Singapore
        ("2026-01-09T06:00:00Z", "peak"),      # Friday peak
        ("2026-01-10T06:00:00Z", "off-peak"),  # Saturday 14:00 Singapore
        ("2026-01-11T06:00:00Z", "off-peak"),  # Sunday 14:00 Singapore
        ("2026-01-04T16:00:00Z", "off-peak"),  # Monday 00:00 Singapore
        ("2026-09-25T06:00:00Z", "peak"),      # Weekday, no published exception
    ]
    js = extract_schedule_helpers() + f"""
const cases = {json.dumps(cases)};
let failed = 0;
for (const [iso, expected] of cases) {{
  const got = _glmHoursAt(Date.parse(iso)).mode;
  if (got !== expected) {{ console.error('FAIL', iso, got, expected); failed++; }}
}}
const nextCases = [
  ['2026-01-05T07:00:00Z', 'peak', '2026-01-05T10:00:00.000Z'],
  ['2026-01-05T11:00:00Z', 'off-peak', '2026-01-06T06:00:00.000Z'],
  ['2026-01-09T11:00:00Z', 'off-peak', '2026-01-12T06:00:00.000Z'],
  ['2026-01-11T10:00:00Z', 'off-peak', '2026-01-12T06:00:00.000Z'],
];
for (const [iso, mode, expected] of nextCases) {{
  const got = new Date(_glmNextChange(Date.parse(iso), mode)).toISOString();
  if (got !== expected) {{ console.error('FAIL next-change', iso, got, expected); failed++; }}
}}
process.exit(failed ? 1 : 0);
"""
    temp = PLUGIN.with_name("glm_hours_test.mjs")
    temp.write_text(js, encoding="utf-8")
    try:
        result = subprocess.run(["node", str(temp)], capture_output=True, text=True)
        if result.returncode:
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)
    finally:
        temp.unlink(missing_ok=True)


def test_indicator_not_quota_gated() -> None:
    source = PLUGIN.read_text(encoding="utf-8")
    if "id === 'glm' ? jsx(GLMHours, {}) : null" not in source:
        raise AssertionError("GLM schedule indicator must render for every GLM chip")
    if "status?.glm_coding_plan" in source:
        raise AssertionError("GLM schedule indicator must not depend on quota-window metadata")


def main() -> None:
    test_schedule()
    test_indicator_not_quota_gated()
    print("GLM hours: 9 schedule cases + 4 next-change cases + provider-wide indicator PASS")


if __name__ == "__main__":
    main()
