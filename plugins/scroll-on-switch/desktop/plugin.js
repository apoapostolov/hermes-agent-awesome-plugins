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
  const states = new Set()

  const scheduleSnap = (el, state) => {
    state.timers.forEach(clearTimeout)
    // Content keeps changing after the switch: long transcripts mount nodes
    // late, and panels (tasks/todos) mount or expand even later. Snap now,
    // then re-snap on every size change via ResizeObserver; the watcher
    // retires 8s after the last change so it never runs forever.
    //
    // The app re-enables scroll anchoring whenever it considers the reader
    // "not following" (data-following=false). A panel whose height oscillates
    // then re-anchors the scroll to a mid-list node on every size change,
    // actively dragging the reader away from the bottom. While the snap
    // session is live, force overflow-anchor:none so nothing fights the snap;
    // restore the app's value when the watcher retires.
    const prevAnchor = el.style.overflowAnchor
    el.style.overflowAnchor = 'none'
    const snapNow = () => {
      if (state.hidden || !document.contains(el)) return false
      snapToBottom(el)
      return true
    }
    snapNow()
    // Re-snap while the transcript (or a panel inside it — task panels mount
    // and expand LATE, well past any fixed ladder) changes size. ResizeObserver
    // sees every growth burst no matter how late or slow; the watcher retires
    // after ~8s of no growth so it never runs forever.
    let ro = null
    let retire = null
    const stop = () => {
      if (ro) ro.disconnect()
      if (retire) clearTimeout(retire)
      ro = retire = null
      el.style.overflowAnchor = prevAnchor
    }
    ro = new ResizeObserver(() => {
      if (state.hidden || !document.contains(el)) { stop(); return }
      snapNow()
      clearTimeout(retire)
      retire = setTimeout(stop, 8000)
    })
    // arm: observe the scroller's content wrapper + first child (panel root)
    const armObserver = () => {
      const target = el.firstElementChild || el
      try { ro.observe(target); if (target.firstElementChild) ro.observe(target.firstElementChild) } catch {}
      clearTimeout(retire)
      retire = setTimeout(stop, 8000)
    }
    armObserver()
    state.stopWatcher = stop
  }

  const observeViewport = el => {
    let state = viewports.get(el)
    if (state) return state
    state = { hidden: isInHiddenPane(el), seen: false, timers: [] }
    viewports.set(el, state)
    states.add(state)
    return state
  }

  const sweep = () => {
    document.querySelectorAll(VIEWPORT).forEach(el => {
      const state = observeViewport(el)
      const hidden = isInHiddenPane(el)
      const becameVisible = state.seen && state.hidden && !hidden
      const firstVisibleMount = !state.seen && !hidden
      state.seen = true
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
    states.forEach(state => { state.timers.forEach(clearTimeout); if (state.stopWatcher) state.stopWatcher() })
    document.querySelectorAll(`[${MARK}]`).forEach(el => el.removeAttribute(MARK))
  }
}

export default {
  id: ID,
  name: 'Scroll on Switch',
  description: 'Always land at the bottom of the transcript when switching to a session, including newly mounted sessions.',
  defaultEnabled: true,
  register(ctx) {
    ctx.onDispose(start())
  }
}
