/**
 * Dropdown clipping guard.
 *
 * The setup dialog's body is a scroll container (`overflow-auto max-h-[70vh]`)
 * and the provider rows sit inside another `overflow-hidden` box. A menu
 * positioned inside either one is cropped at the dialog edge instead of
 * spilling past it, which is exactly how the renewal-day and add-provider
 * dropdowns used to behave: 266px of list, 123px of it visible.
 *
 * The fix is structural, not cosmetic — both menus go through the house Popover
 * (exported by @hermes/plugin-sdk), which portals into the dialog shell: the
 * one node DialogContent deliberately leaves unclipped. So the assertions below
 * check the structure, not a colour or a pixel value.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(join(here, 'desktop/plugin.js'), 'utf8')

let pass = 0
const fails = []
const ok = (name, cond, detail) => {
  if (cond) { pass++; return }
  fails.push(name + (detail ? ' — ' + detail : ''))
}

// 1. The clipper that causes the bug is still there. If this stops being true
//    the reasoning above changed and the rest of this file should be revisited.
ok('setup body still owns scroll + max height',
  /bodyClassName: 'gap-3 overflow-auto max-h-\[70vh\]'/.test(src))

// 2. Both dropdowns are house Popovers, so both portal out of that clipper.
const popoverContent = src.match(/jsx\(PopoverContent,/g) || []
ok('both dropdowns render through PopoverContent', popoverContent.length === 2,
  'found ' + popoverContent.length)
ok('both triggers are PopoverTrigger asChild',
  (src.match(/jsx\(PopoverTrigger, \{\s*\n\s*asChild: true,/g) || []).length === 2)

// 3. No menu is positioned in the flow. These are the exact class strings the
//    clipped versions used.
for (const cls of ['absolute right-0 top-7', 'absolute left-0 top-8']) {
  ok('no in-flow menu positioned with "' + cls + '"', !src.includes(cls))
}

// 4. The old workaround is gone. It mutated every scroll ancestor's inline
//    overflow while a menu was open, which also could not help the row list
//    that clips with `overflow-hidden`.
ok('ancestor overflow lift hack removed', !/st\.maxHeight = 'none'/.test(src))
ok('capture-phase mousedown dismiss removed',
  !/document\.addEventListener\('mousedown', close, true\)/.test(src))

// 5. The user-facing controls survived the rewrite.
for (const marker of ["'data-day-button': ''", "'data-add-picker': ''", "'data-day-menu': ''"]) {
  ok('kept ' + marker, src.includes(marker))
}

// 6. The renewal-day menu still lists None + 31 days, and picking one persists.
ok('day list still builds 31 days', /length: 31/.test(src))
ok('day pick still persists reset_days', /persist\(undefined, undefined, \{ reset_days: days \}\)/.test(src))

// 7. Menus size to the trigger rather than a hardcoded width (add-provider).
ok('add-provider menu matches trigger width',
  src.includes("width: 'var(--radix-popover-trigger-width)'"))

console.log('popover-clip: ' + pass + ' checks PASS')
if (fails.length) {
  console.error('FAILED:')
  for (const f of fails) console.error('  - ' + f)
  process.exit(1)
}
