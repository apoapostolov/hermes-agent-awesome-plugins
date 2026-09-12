/**
 * Scroll on Switch for Hermes.
 *
 * Land on the newest message when the focused session changes. Session list
 * clicks reuse one viewport, so `data-pane-hidden` never flips. Subscribe to
 * `host.state.focusedStoredSessionId` / `focusedSessionId` for that. Keep the
 * pane-hidden watcher for keep-alive tabs.
 *
 * Desktop restore re-applies a saved distance-from-bottom for ~15 frames
 * without resizing. A ResizeObserver misses that. While the snap window is
 * open, write every animation frame and click the native jump control so
 * stick-to-bottom re-arms and restore cancels.
 *
 * Wheel-up yields. Not streaming.
 */

import { host } from '@hermes/plugin-sdk'

const ID = 'scroll-on-switch'
const VIEWPORT = '[data-slot="aui_thread-viewport"]'
const HIDDEN = '[data-pane-hidden]'
const MARK = 'data-sos-armed'
const JUMP_BUTTON = 'button.thread-jump-button'
const NEAR_BOTTOM_PX = 8
const RAF_MS = 2500
const GROW_MS = 8000
const JUMP_THROTTLE_MS = 120

function distanceFromBottom(el) {
  return Math.max(0, el.scrollHeight - el.scrollTop - el.clientHeight)
}

function isInHiddenPane(el) {
  return Boolean(el.closest(HIDDEN))
}

function start() {
  const viewports = new WeakMap()
  const states = new Set()

  const observeViewport = el => {
    let state = viewports.get(el)
    if (state) return state
    state = { hidden: isInHiddenPane(el), seen: false, timers: [] }
    viewports.set(el, state)
    states.add(state)
    return state
  }

  const scheduleSnap = (el, state) => {
    if (state.stopWatcher) state.stopWatcher()
    state.timers.forEach(clearTimeout)

    let ro = null
    let retire = null
    let raf = 0
    let lastJumpAt = 0
    const t0 = performance.now()

    const clickNativeJump = () => {
      const now = performance.now()
      if (now - lastJumpAt < JUMP_THROTTLE_MS) return
      lastJumpAt = now
      const btn = document.querySelector(JUMP_BUTTON)
      if (btn) btn.click()
    }

    const snapNow = () => {
      if (state.hidden || !document.contains(el)) return false
      if (distanceFromBottom(el) > NEAR_BOTTOM_PX) clickNativeJump()
      el.scrollTop = el.scrollHeight
      return true
    }

    const onWheel = e => {
      if (e.deltaY < 0) stop()
    }

    const stop = () => {
      if (ro) ro.disconnect()
      if (retire) clearTimeout(retire)
      if (raf) cancelAnimationFrame(raf)
      ro = retire = null
      raf = 0
      el.removeEventListener('wheel', onWheel)
      state.stopWatcher = null
    }

    const tick = () => {
      if (state.hidden || !document.contains(el)) { stop(); return }
      snapNow()
      if (performance.now() - t0 < RAF_MS) raf = requestAnimationFrame(tick)
    }

    snapNow()
    raf = requestAnimationFrame(tick)

    ro = new ResizeObserver(() => {
      if (state.hidden || !document.contains(el)) { stop(); return }
      snapNow()
      clearTimeout(retire)
      retire = setTimeout(stop, GROW_MS)
    })
    const target = el.firstElementChild || el
    try {
      ro.observe(target)
      if (target.firstElementChild) ro.observe(target.firstElementChild)
    } catch {}
    clearTimeout(retire)
    retire = setTimeout(stop, GROW_MS)
    el.addEventListener('wheel', onWheel, { passive: true })
    state.stopWatcher = stop
  }

  const snapVisible = () => {
    document.querySelectorAll(VIEWPORT).forEach(el => {
      const state = observeViewport(el)
      const hidden = isInHiddenPane(el)
      state.seen = true
      state.hidden = hidden
      el.setAttribute(MARK, hidden ? 'hidden' : 'visible')
      if (!hidden) scheduleSnap(el, state)
    })
  }

  const sweepPanes = () => {
    document.querySelectorAll(VIEWPORT).forEach(el => {
      const state = observeViewport(el)
      const hidden = isInHiddenPane(el)
      const becameVisible = state.seen && state.hidden && !hidden
      const firstVisibleMount = !state.seen && !hidden
      state.seen = true
      state.hidden = hidden
      el.setAttribute(MARK, hidden ? 'hidden' : 'visible')
      if (!hidden && (becameVisible || firstVisibleMount)) scheduleSnap(el, state)
    })
  }

  sweepPanes()

  let paneScheduled = false
  const paneObserver = new MutationObserver(() => {
    if (paneScheduled) return
    paneScheduled = true
    requestAnimationFrame(() => {
      paneScheduled = false
      sweepPanes()
    })
  })
  paneObserver.observe(document.body, {
    attributes: true,
    attributeFilter: ['data-pane-hidden'],
    subtree: true,
    childList: true
  })

  let lastStored = host.state.focusedStoredSessionId.get()
  let lastRuntime = host.state.focusedSessionId.get()
  const unsubStored = host.state.focusedStoredSessionId.subscribe(id => {
    if (id === lastStored) return
    lastStored = id
    snapVisible()
  })
  const unsubRuntime = host.state.focusedSessionId.subscribe(id => {
    if (id === lastRuntime) return
    lastRuntime = id
    snapVisible()
  })

  return () => {
    paneObserver.disconnect()
    unsubStored()
    unsubRuntime()
    states.forEach(state => {
      state.timers.forEach(clearTimeout)
      if (state.stopWatcher) state.stopWatcher()
    })
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
