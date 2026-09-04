/**
 * UI Polish for Hermes.
 *
 * Session-list channel group headers: moves the platform/channel icon from
 * the left edge (before the name) to the right side of the same header
 * line, after the session count. Pure flex-order CSS, no DOM changes —
 * the app keeps managing its own nodes.
 */

const ID = 'ui-polish-for-hermes'
const STYLE_ID = 'ui-polish-for-hermes-style'

const CSS = `
  /* Header buttons render [chevron, icon, label, spacer, count, (warn)];
     flex order moves the icon to the far right without touching the DOM. */
  [data-sessions-mode] button > :nth-child(2) {
    order: 9;
  }
  /* Keep the disconnect warning next to the count, not after the icon. */
  [data-sessions-mode] button > :nth-child(6) {
    order: 8;
  }
`

export default {
  id: ID,
  name: 'UI Polish for Hermes',
  description: 'Session-list polish: channel group headers show their platform icon right-aligned after the session count instead of before the name.',
  defaultEnabled: true,
  register(ctx) {
    let style = document.getElementById(STYLE_ID)
    if (!style) {
      style = document.createElement('style')
      style.id = STYLE_ID
      style.textContent = CSS
      document.head.appendChild(style)
    }
    ctx.onDispose(() => document.getElementById(STYLE_ID)?.remove())
  }
}
