/**
 * Drag to Pin Session, catalog-safe interim edition.
 *
 * The desktop SDK exposes session pin actions and row-decoration slots, but
 * does not yet expose a supported drag/drop target for the Pinned section.
 * This edition keeps direct pin and unpin actions in the trailing row slot
 * until that drop-target hook is available.
 */

import { host, SESSION_ROW_AREAS } from '@hermes/plugin-sdk'
import { jsxs, jsx } from 'react/jsx-runtime'

const ID = 'drag-to-pin-session'

function stopRowGesture(event) {
  event.stopPropagation()
}

function setPinned(sessionId, pinned) {
  try {
    host.sessions.pin(sessionId, pinned)
  } catch (err) {
    console.warn(`[${ID}] ${pinned ? 'pin' : 'unpin'} failed`, err)
  }
}

function SessionPinActions({ sessionId }) {
  const buttonStyle = {
    appearance: 'none',
    background: 'transparent',
    border: 0,
    color: 'var(--ui-text-tertiary)',
    cursor: 'pointer',
    font: 'inherit',
    fontSize: '0.625rem',
    lineHeight: 1.25,
    padding: '2px 4px',
  }

  return jsxs('span', {
    style: { display: 'inline-flex', alignItems: 'center', gap: '2px' },
    children: [
      jsx('button', {
        type: 'button',
        'aria-label': 'Pin session',
        title: 'Pin session',
        style: buttonStyle,
        onPointerDown: stopRowGesture,
        onClick: event => {
          event.stopPropagation()
          setPinned(sessionId, true)
        },
        children: 'Pin',
      }),
      jsx('button', {
        type: 'button',
        'aria-label': 'Unpin session',
        title: 'Unpin session',
        style: buttonStyle,
        onPointerDown: stopRowGesture,
        onClick: event => {
          event.stopPropagation()
          setPinned(sessionId, false)
        },
        children: 'Unpin',
      }),
    ],
  })
}

export default {
  id: ID,
  name: 'Session Pin Controls',
  description: 'Pin or unpin a session from its row using supported desktop SDK actions.',
  defaultEnabled: true,
  register(ctx) {
    ctx.register({
      id: 'pin-actions',
      area: SESSION_ROW_AREAS.trailing,
      data: {
        render: ({ sessionId }) => jsx(SessionPinActions, { sessionId }),
      },
    })
  },
}
