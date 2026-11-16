"""Radio Plus: settings page with the launch-autoplay switch."""
from __future__ import annotations

import sys
from pathlib import Path

path = Path("desktop/plugin.js")
s = path.read_text(encoding="utf-8")


def fix(old: str, new: str, label: str) -> None:
    global s
    count = s.count(old)
    if count != 1:
        print(f"MISS {label}: {count}")
        sys.exit(1)
    s = s.replace(old, new)
    print(f"ok {label}")


# ------------------------------------------------------------------ storage key
fix(
    "const ID = 'radio-plus'\n",
    """const ID = 'radio-plus'
// One preference, stored in the plugin's own storage so it travels with the
// plugin's data and never touches app config. Off unless it was switched on.
const AUTOPLAY_KEY = 'local.autoplay'

function autoplayOnLaunch(storage) {
  return storage?.get?.(AUTOPLAY_KEY, false) === true
}
""",
    "autoplay key and reader",
)

# --------------------------------------------------------------------- i18n copy
fix(
    "  noResults: 'No stations found',",
    """  settingsTitle: 'Radio Plus', autoplayLabel: 'Start the last station on launch',
  autoplayDescription: 'Plays the station you listened to last as soon as Hermes opens, so the status bar is live without a click. Off by default; with it off nothing plays until you press play, and a station that cannot be reached reports the reason in the panel instead of retrying.',
  noResults: 'No stations found',""",
    "i18n settings copy",
)

# ------------------------------------------------------------- namespace import
fix(
    "import { useEffect, useRef, useState } from 'react'",
    """// The namespace import is deliberate: a named import of a component this build
// may not export throws at module evaluation and takes the whole plugin down.
import * as pluginSdk from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'""",
    "sdk namespace import",
)

# ------------------------------------------------------------- autoplay on boot
fix(
    "  return { station, stations, favorites, volume, status, meterMode, lastError, open, play, stop, toggle, next, setVolume, mute, favorite, updateStation, removeStation, addStation, waveform }",
    """  // Read once, at launch. A switch flipped mid-session must not start audio
  // behind the user, and a station that was never played must not start either.
  function startIfRequested() {
    if (!autoplayOnLaunch(ctx.storage)) return false
    if (!validStation(restored)) return false
    void play(restored)
    return true
  }

  return { station, stations, favorites, volume, status, meterMode, lastError, open, play, stop, toggle, next, setVolume, mute, favorite, updateStation, removeStation, addStation, waveform, startIfRequested }""",
    "startIfRequested",
)

# ------------------------------------------------------------- settings page
fix(
    "export { artistProfile, resolveArtist, trackCredit }",
    """// Settings ▸ Plugins ▸ Radio Plus. One switch, the sanctioned way to ship an
// optional behaviour: the default stays off and the user opts in.
function RadioSettingsPage({ ctx }) {
  const t = usePluginI18n(ID)
  const [on, setOn] = useState(autoplayOnLaunch(ctx.storage))
  const row = {
    checked: on,
    id: 'radio-plus-autoplay',
    label: t('autoplayLabel'),
    description: t('autoplayDescription'),
    onChange: next => {
      setOn(next)
      ctx.storage.set(AUTOPLAY_KEY, next)
    }
  }
  const ToggleRow = pluginSdk.ToggleRow
  if (ToggleRow) return jsx(ToggleRow, row)
  // An older build without ToggleRow still gets a working control.
  const Switch = pluginSdk.Switch
  const control = Switch
    ? jsx(Switch, { checked: on, 'aria-label': row.label, onCheckedChange: value => row.onChange(value === true) })
    : jsx('input', {
      type: 'checkbox',
      checked: on,
      'aria-label': row.label,
      onChange: event => row.onChange(event.target.checked)
    })
  return jsxs('div', {
    className: 'hermes-radio-plus-setting',
    children: [
      jsxs('div', {
        className: 'hermes-radio-plus-setting-text',
        children: [
          jsx('span', { className: 'hermes-radio-plus-setting-label', children: row.label }),
          jsx('span', { className: 'hermes-radio-plus-setting-note', children: row.description })
        ]
      }),
      control
    ]
  })
}

export { artistProfile, resolveArtist, trackCredit, autoplayOnLaunch, RadioSettingsPage }""",
    "settings page",
)

# --------------------------------------------------------------- registration
fix(
    """    const player = createPlayer(ctx)
    ctx.register({ id: 'player', area: STATUSBAR_AREAS.right, order: 10, render: () => jsx(RadioBar, { player, ctx }) })""",
    """    const player = createPlayer(ctx)
    ctx.register({ id: 'player', area: STATUSBAR_AREAS.right, order: 10, render: () => jsx(RadioBar, { player, ctx }) })
    if (typeof ctx.registerSettingsPage === 'function') {
      ctx.registerSettingsPage({
        id: ID,
        title: 'Radio Plus',
        icon: 'radio-tower',
        order: 70,
        render: () => jsx(RadioSettingsPage, { ctx })
      })
    }
    // After the first paint, so the window is up and the audio element can start
    // without racing the app's own boot.
    setTimeout(() => player.startIfRequested(), 1200)""",
    "registration",
)

# --------------------------------------------------------------------- fallback
css_start = s.index("const CSS = `")
css_end = s.index("\n`", css_start)
fallback = """
.hermes-radio-plus-setting { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 0; }
.hermes-radio-plus-setting-text { display: flex; flex-direction: column; gap: 4px; max-width: 62ch; }
.hermes-radio-plus-setting-label { font-size: 13px; font-weight: 500; }
.hermes-radio-plus-setting-note { font-size: 12px; opacity: .72; line-height: 1.45; }"""
s = s[:css_end] + fallback + s[css_end:]
print("ok settings css")

path.write_text(s, encoding="utf-8")
print("written")
