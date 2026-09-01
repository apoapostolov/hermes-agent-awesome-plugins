/**
 * Scroll on Switch for Hermes.
 *
 * Keep-alive session tabs deliberately keep their scroll position while
 * hidden, so switching back to a tab reopens it wherever you left it.
 * This plugin snaps a pane back to the bottom the moment it becomes the
 * visible pane, instead of restoring the stale position.
 *
 * The transcript viewport is `[data-slot="aui_thread-viewport"]`. An
 * inactive keep-alive tab sits inside an element carrying
 * `data-pane-hidden`. Watching for that attribute to disappear from a
 * viewport's ancestors gives the exact switch-to moment; one
 * `scrollTop = scrollHeight` snap then lands the reader at the newest
 * message.
 */

const ID = 'scroll-on-switch'
const VIEWPORT = '[data-slot="aui_thread-viewport"]'
const HIDDEN = '[data-pane-hidden]'
const MARK = 'data-sos-armed'

function snapToBottom(el) {
  el.scrollTop = el.scrollHeight
}

/**
 * Is this viewport inside a currently-hidden keep-alive pane?
 */
function isInHiddenPane(el) {
  return Boolean(el.closest(HIDDEN))
}

/**
 * React can mount a session directly as visible, or finish rendering messages
 * after the viewport becomes visible. Track both cases and retry while the
 * transcript is still growing.
 */
function start() {
  const viewports = new WeakMap()
  const contentObserver = new MutationObserver(records => {
    const touched = new Set()
    records.forEach(record => {
      if (!record.addedNodes.length) return
      const node = record.target.nodeType === Node.TEXT_NODE
        ? record.target.parentElement
        : record.target
      const viewport = node?.closest?.(VIEWPORT)
      if (viewport) touched.add(viewport)
    })
    touched.forEach(el => {
      const state = viewports.get(el)
      if (state && !isInHiddenPane(el)) {
        state.hidden = false
        scheduleSnap(el, state)
      }
    })
  })
  const resizeObserver = new ResizeObserver(entries => {
    entries.forEach(({ target }) => {
      const state = viewports.get(target)
      if (state && !state.hidden && state.followUntil > Date.now()) {
        scheduleSnap(target, state)
      }
    })
  })

  const scheduleSnap = (el, state) => {
    state.timers.forEach(clearTimeout)
    state.timers = [0, 50, 150, 400, 900].map(delay => setTimeout(() => {
      if (!state.hidden && document.contains(el)) snapToBottom(el)
    }, delay))
    state.followUntil = Date.now() + 1500
  }

  const observeViewport = el => {
    let state = viewports.get(el)
    if (state) return state
    state = { hidden: isInHiddenPane(el), followUntil: 0, timers: [] }
    viewports.set(el, state)
    contentObserver.observe(el, { childList: true, subtree: true })
    resizeObserver.observe(el)
    return state
  }

  const sweep = () => {
    document.querySelectorAll(VIEWPORT).forEach(el => {
      const state = observeViewport(el)
      const hidden = isInHiddenPane(el)
      const becameVisible = state.hidden && !hidden
      const firstVisibleMount = state.followUntil === 0 && !hidden
      state.hidden = hidden
      el.setAttribute(MARK, hidden ? 'hidden' : 'visible')

      if (!hidden && (becameVisible || firstVisibleMount)) {
        scheduleSnap(el, state)
      }
    })
  }

  // The active session may be mounted already, so treat every visible
  // viewport in the initial pass as an activation too.
  sweep()

  let scheduled = false
  const observer = new MutationObserver(() => {
    if (scheduled) return
    scheduled = true
    requestAnimationFrame(() => {
      scheduled = false
      sweep()
    })
  })
  observer.observe(document.body, {
    attributes: true,
    attributeFilter: ['data-pane-hidden'],
    subtree: true,
    childList: true
  })

  return () => {
    observer.disconnect()
    contentObserver.disconnect()
    resizeObserver.disconnect()
    document.querySelectorAll(`[${MARK}]`).forEach(el => el.removeAttribute(MARK))
    document.querySelectorAll(VIEWPORT).forEach(el => {
      const state = viewports.get(el)
      if (state) state.timers.forEach(clearTimeout)
    })
  }
}

export default {
  id: ID,
  name: 'Scroll on Switch',
  description: 'Always land at the bottom of the transcript when a session becomes active, including newly mounted sessions.',
  defaultEnabled: true,
  register(ctx) {
    ctx.onDispose(start())
  }
}
