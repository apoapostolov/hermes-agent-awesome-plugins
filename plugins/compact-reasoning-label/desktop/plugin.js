// Compact Reasoning Label
// The composer's model pill renders "Model Name Medium" (effort word baked into
// the label). This plugin strips that trailing effort word from the model pill
// so it reads just the model name; the reasoning pill beside it keeps showing
// the level ("Medium") as usual.
const STYLE_ID = 'hermes-compact-reasoning-label'

// Short + full effort labels (mirrors reasoning-effort SHORT_LABELS).
const EFFORT_WORDS = ['Off', 'Min', 'Minimal', 'Low', 'Med', 'Medium', 'High', 'XHigh', 'Extra High', 'Max', 'Ultra']
const TRAILING_EFFORT = new RegExp('\\s+(' + EFFORT_WORDS.join('|') + ')$')

function pillSpans(root) {
  // Model pill = button span.truncate that is NOT the reasoning pill's label.
  const spans = root.querySelectorAll('[data-slot="composer-root"] button span.truncate')
  const out = []
  for (const span of spans) {
    const pill = span.closest('button')
    if (pill && pill.dataset.testid === 'reasoning-pill') continue
    out.push(span)
  }
  return out
}

function stripOne(span) {
  const text = span.textContent
  if (!text) return
  const m = text.match(TRAILING_EFFORT)
  if (!m) return
  const stripped = text.slice(0, m.index)
  if (!stripped.trim()) return // never blank the whole pill
  if (span.textContent === stripped) return // idempotent: no write, no loop
  span.textContent = stripped
}

function sweep() {
  for (const span of pillSpans(document)) stripOne(span)
}

export default {
  id: 'compact-reasoning-label',
  name: 'Compact Reasoning Label',
  description: 'Model pill shows just the model name; the effort level lives only in the reasoning pill beside it.',
  defaultEnabled: true,
  register(ctx) {
    document.getElementById(STYLE_ID)?.remove()
    const style = document.createElement('style')
    style.id = STYLE_ID
    style.textContent = `
      /* keep the reasoning pill label visible (it carries the level word) */
      [data-slot="composer-root"] [data-testid="reasoning-pill"] > span:first-child {
        display: inline !important;
      }
    `
    document.head.appendChild(style)

    sweep()
    // React rewrites the label on model/effort changes; re-strip idempotently.
    const observer = new MutationObserver(() => sweep())
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    const t = setInterval(sweep, 1000)

    ctx.onDispose(() => {
      observer.disconnect()
      clearInterval(t)
      style.remove()
    })
  }
}
