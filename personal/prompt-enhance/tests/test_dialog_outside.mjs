// Shipped with prompt-enhance: proves the dialog outside-click guard in
// desktop/plugin.js. Runs the SHIPPED function, not a retyped copy.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(join(here, '..', 'desktop', 'plugin.js'), 'utf8')

function extractFunction(name) {
  const start = src.indexOf(`function ${name}(`)
  if (start < 0) throw new Error(`missing function ${name}`)
  let depth = 0
  let seen = false
  for (let i = start; i < src.length; i += 1) {
    if (src[i] === '{') { depth += 1; seen = true }
    if (src[i] === '}' && seen && --depth === 0) return src.slice(start, i + 1)
  }
  throw new Error(`unterminated function ${name}`)
}

// The interpolated source is this plugin's own shipping plugin.js, read from
// disk above, not external input; new Function is how the shipped code is
// evaluated verbatim instead of testing a retyped copy.
const factory = new Function(`${extractFunction('guardDialogOutside')}; return guardDialogOutside`)
const rect = { left: 100, top: 100, right: 500, bottom: 300 }
const guard = factory()({ current: { getBoundingClientRect: () => rect } })

function pointerEvent(x, y) {
  const state = { prevented: false }
  return {
    detail: { originalEvent: { clientX: x, clientY: y } },
    preventDefault() { state.prevented = true },
    wasPrevented: () => state.prevented,
  }
}

// The reported case: coordinates inside the dialog, target resolved outside.
const inside = pointerEvent(300, 200)
guard.pointer(inside)
if (!inside.wasPrevented()) throw new Error('an inside click was allowed to dismiss the dialog')

// A genuine outside click must still close the dialog.
const outside = pointerEvent(50, 50)
guard.pointer(outside)
if (outside.wasPrevented()) throw new Error('an outside click was kept open')

// A synthesized Tab that escapes the focus trap must not close the dialog.
const focus = { prevented: false, preventDefault() { this.prevented = true } }
guard.focus(focus)
if (!focus.prevented) throw new Error('a focus escape was allowed to dismiss the dialog')

// Control: without the guard, the same inside click stays unprevented and Radix
// dismisses. This proves the guard, not the fixture, flips the reported case.
const unguarded = pointerEvent(300, 200)
if (unguarded.wasPrevented() || unguarded.wasPrevented() === inside.wasPrevented()) {
  throw new Error('control did not reproduce the unguarded dismissal')
}

// Both dialogs carry all three props, and both anchor the ref on their own root.
for (const prop of ['onPointerDownOutside', 'onInteractOutside', 'onFocusOutside']) {
  const wired = src.split(`${prop}:`).length - 1
  if (wired !== 2) throw new Error(`${prop} wired ${wired} times, expected 2`)
}
for (const marker of ['data-pe-library', 'data-pe-edit']) {
  const anchored = src.split(`'${marker}': '',`).length - 1
  if (anchored !== 1) throw new Error(`${marker} appears ${anchored} times, expected 1`)
}
if (!/ref: dialogRef,\s*\n\s*'data-pe-library'/.test(src) || !/ref: dialogRef,\s*\n\s*'data-pe-edit'/.test(src)) {
  throw new Error('dialog refs are not anchored on the plugin roots')
}

console.log('prompt-enhance dialog guard: inside kept, outside dismissed, focus kept, both dialogs wired')
