from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

PLUGIN = Path(__file__).with_name("desktop") / "plugin.js"


def extract_helpers() -> str:
    source = PLUGIN.read_text(encoding="utf-8")
    start_marker = "// DEEPSEEK_HOURS_START"
    end_marker = "// DEEPSEEK_HOURS_END"
    if start_marker not in source or end_marker not in source:
        raise AssertionError("DeepSeek hours markers missing")
    block = source.split(start_marker, 1)[1].split(end_marker, 1)[0]
    block = block.split("function _scheduleDurationText", 1)[0]
    return block


def main() -> None:
    # The authoritative State Council ranges in the plugin are exercised end to
    # end. The current time sits inside a weekday UTC peak window when possible;
    # a holiday check may run at a China-local time outside that UTC window.
    schedule_ranges = [
        ("2025-01-01", "2025-01-01", "New Year's Day"),
        ("2025-01-28", "2025-02-04", "Spring Festival"),
        ("2025-04-04", "2025-04-06", "Qingming Festival"),
        ("2025-05-01", "2025-05-05", "Labour Day"),
        ("2025-05-31", "2025-06-02", "Dragon Boat Festival"),
        ("2025-10-01", "2025-10-08", "National Day and Mid-Autumn Festival"),
        ("2026-01-01", "2026-01-03", "New Year's Day"),
        ("2026-02-15", "2026-02-23", "Spring Festival"),
        ("2026-04-04", "2026-04-06", "Qingming Festival"),
        ("2026-05-01", "2026-05-05", "Labour Day"),
        ("2026-06-19", "2026-06-21", "Dragon Boat Festival"),
        ("2026-09-25", "2026-09-27", "Mid-Autumn Festival"),
        ("2026-10-01", "2026-10-07", "National Day"),
    ]
    cases = [
        ("2026-01-05T01:00:00Z", "peak", None),
        ("2026-01-05T04:00:00Z", "off-peak", None),
        ("2026-01-05T06:00:00Z", "peak", None),
        ("2026-01-05T10:00:00Z", "off-peak", None),
        ("2026-01-05T00:59:59Z", "off-peak", None),
        # Make-up workdays fall on weekends in both notices, so DeepSeek's UTC
        # Monday-Friday rule keeps them off-peak.
        ("2026-10-10T07:00:00Z", "off-peak", None),
        ("2026-09-20T07:00:00Z", "off-peak", None),
        ("2026-02-14T07:00:00Z", "off-peak", None),
    ]
    for start_text, end_text, name in schedule_ranges:
        current = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
        while current <= end:
            iso = f"{current.isoformat()}T07:00:00Z"
            cases.append((iso, "off-peak", name))
            current += timedelta(days=1)
    js = extract_helpers() + f"""
const cases = {json.dumps(cases)};
let failed = 0;
for (const [iso, expectedMode, expectedHoliday] of cases) {{
  const got = _deepseekHoursAt(Date.parse(iso));
  const gotHoliday = got.holiday?.name || null;
  if (got.mode !== expectedMode || gotHoliday !== expectedHoliday) {{
    console.error('FAIL', iso, got.mode, gotHoliday, expectedMode, expectedHoliday);
    failed++;
  }}
}}
const next = new Date(_deepseekNextChange(Date.parse('2026-01-05T07:00:00Z'), 'peak')).toISOString();
if (next !== '2026-01-05T10:00:00.000Z') {{
  console.error('FAIL next-change', next);
  failed++;
}}
process.exit(failed ? 1 : 0);
"""
    temp = Path(__file__).with_name("desktop") / "deepseek_hours_test.mjs"
    temp.write_text(js, encoding="utf-8")
    try:
        result = subprocess.run(["node", str(temp)], capture_output=True, text=True)
        if result.returncode:
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)
    finally:
        temp.unlink(missing_ok=True)
    print(f"DeepSeek hours: {len(cases)} boundary cases + next-change PASS")


if __name__ == "__main__":
    main()
