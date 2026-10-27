<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Better Capabilities</h1>
  <strong>Delete and package skills, browse their files, save on/off presets.</strong>
  <p>A Settings ▸ Plugins page for the capability work the Capabilities page does not cover.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.1.0-2ea44f" alt="Version 1.1.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Better Capabilities" />
</div>

## What it adds

A page of its own under **Settings → Plugins → Better Capabilities**, with three entries: an
overview, **Skills**, and **Presets**. It is also reachable from the gear on the plugin's row in
**Capabilities → Plugins**, and from the Settings rail.

- **Skills.** Filter the list, flip a skill on or off, and read the other markdown files in its
  folder (`references/`, `docs/`, and so on) without leaving the page. Each row also offers
  Package (zip), Open folder, and Delete.
- **Package (zip).** Saves `SKILL.md` plus `references/` and the rest of the folder. `__pycache__`,
  `.git`, virtualenvs and compiled files stay out, and symlinks are skipped.
- **Delete.** The folder goes to the Recycle Bin. When the bin is unavailable — a non-Windows host,
  or a locked folder — it is moved to `<hermes home>/better-capabilities-trash/` and the page says
  which happened.
- **Presets.** Save the current on/off set for skills, toolsets, or agent plugins under a name, then
  apply, overwrite, rename, reorder, or delete it. The page snapshots and applies the switches
  itself through the plugin SDK, so preset state is saved per profile and applied to the profile
  the page is showing.

The plugin draws that page itself. It adds nothing to the Capabilities page, which gives plugins no
slot to contribute to.

## Install

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/better-capabilities
```

Then enable **Better Capabilities** under **Capabilities → Plugins**; the page appears under
Settings → Plugins. Zip, delete and the skill file list need the plugin's Python routes, and those
mount when the Desktop backend starts — after adding or updating this plugin, fully quit and reopen
Hermes Desktop once so they exist.

## What it touches

No network calls, no telemetry, no credentials. Inside this Hermes home's `skills/` folder it reads
markdown, exports zips, and deletes folders (Recycle Bin, or a moved-aside folder). On Windows the
Recycle Bin delete runs `powershell.exe` once with a fixed script that only calls the .NET recycle
API on the path the server already resolved.

Bundled and hub skills live outside that tree; the page leaves them alone.

## Limits

See [LIMITATIONS.md](LIMITATIONS.md) for what this edition does not have — the `/preset` chat
command and the personal edition's sidebar glyphs — and why.

## License

[MIT](../../LICENSE)
