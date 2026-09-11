/**
 * Scroll on Switch for Hermes.
 *
 * Switching to a session should land on the newest message. The desktop now
 * windows older turns, restores a saved distance-from-bottom, and re-applies
 * that offset while pages prepend. The app's own jump control is the snap
 * path: `button.thread-jump-button` runs `requestScrollToBottom` (re-arm
 * stick-to-bottom and cancel restore). `scrollTop` only covers growth after
 * that click, or a missing button.
 *
 * Trigger: `[data-slot="aui_thread-viewport"]` leaving a `data-pane-hidden`
 * ancestor, or mounting already visible. Not streaming. Wheel-up yields.
 */

const ID = 'scroll-on-switch'
const VIEWPORT = '[data-slot="aui_thread-viewport"]'
const HIDDEN = '[data-pane-hidden]'
const MARK = 'data-sos-armed'
const JUMP_BUTTON = 'button.thread-jump-button'
const NEAR_BOTTOM_PX = 8
const YANK_PX = 64

function distanceFromBottom(el) {
  return Math.max(0, el.scrollHeight - el.scrollTop - el.clientHeight)
}

function clickNativeJump() {
  const btn = document.querySelector(JUMP_BUTTON)
  if (btn) btn.click()
}

function snapToBottom(el) {
  el.scrollTop = el.scrollHeight
}

function isInHiddenPane(el) {
  return Boolean(el.closest(HIDDEN))
}

function start() {
  const viewports = new WeakMap()
  const states = new Set()

  const scheduleSnap = (el, state) => {
    state.timers.forEach(clearTimeout)
    let jumped = false
    let ro = null
    let retire = null

    const snapNow = () => {
      if (state.hidden || !document.contains(el)) return false
      const dist = distanceFromBottom(el)
      if (dist > NEAR_BOTTOM_PX && !jumped) {
        jumped = true
        clickNativeJump()
      } else if (dist > YANK_PX) {
        clickNativeJump()
      }
      snapToBottom(el)
      return true
    }

    const onWheel = e => {
      if (e.deltaY < 0) stop()
    }

    const stop = () => {
      if (ro) ro.disconnect()
      if (retire) clearTimeout(retire)
      ro = retire = null
      el.removeEventListener('wheel', onWheel)
    }

    snapNow()

    ro = new ResizeObserver(() => {
      if (state.hidden || !document.contains(el)) { stop(); return }
      snapNow()
      clearTimeout(retire)
      retire = setTimeout(stop, 8000)
    })

    const target = el.firstElementChild || el
    try {
      ro.observe(target)
      if (target.firstElementChild) ro.observe(target.firstElementChild)
    } catch {}
    clearTimeout(retire)
    retire = setTimeout(stop, 8000)
    el.addEventListener('wheel', onWheel, { passive: true })
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
