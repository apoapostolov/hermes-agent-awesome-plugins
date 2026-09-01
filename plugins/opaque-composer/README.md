# Opaque Composer

Keep the Hermes Desktop composer solid while you scroll through a conversation.
This prevents earlier message text from showing through the input area.

## Install

Install the pack from:

```text
https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

After installation, enable **Opaque Composer** under **Settings → Plugins**, then
run **Ctrl+K → Reload desktop plugins**.

## How it works

The plugin adds a small namespaced stylesheet to the desktop window. It replaces
the composer's translucent fill in both its normal and scrolled states with the
active theme's card color. It uses Hermes' stable `data-slot="composer-root"`
hook and removes the stylesheet when the plugin is disabled.

Desktop-only. No gateway or Python runtime is required.
