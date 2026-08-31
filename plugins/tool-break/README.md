# tool-break

Never let a stalled tool call force you to cancel a long task. Abort an in-flight call with `/break`, instruct with `/break {message}`, or force it to repeat with `/again`.

- **`/break`** kills the newest in-flight spawn tree and keeps the turn alive.
- **`/break --id <id> <hint>`** kills that specific spawn; hint rides in the broken tool result.
- **`/again`** same kill, then reissue the exact call (max 2 per fingerprint).
- **`/again <hint>`** same with a tweak.
- **`/break-status`** JSON payload for the desktop strip.
- Desktop strip: name + time pill, Break / Message / Again / gear per spawn. Elapsed color grades, auto-break thresholds, per-tool hide list (all in `localStorage` under `tool-break.*`).

Previously published as `hermes-break`. Same commands.

## Files

- `plugin.yaml`: hooks `pre_tool_call`, `post_tool_call`, `transform_tool_result`, `on_session_start/end` plus slash commands
- `__init__.py`: spawn tracking, descendant tree, `taskkill`/`kill -9`, Popen hook
- `desktop/plugin.js`: composer strip (`COMPOSER_AREAS.top`), palette + keybind (`mod+shift+b`)
- `tests_break.py`: local checks for rewrite helpers

## How it works

Tracks every `terminal`/`process` spawn via a Popen hook and a descendant sweep. `/break-status` exposes the killable list. `/break` and `/again` kill the tree (`taskkill /F /T` on Windows, `kill -9` on POSIX) and rewrite the tool result so the model can continue.
