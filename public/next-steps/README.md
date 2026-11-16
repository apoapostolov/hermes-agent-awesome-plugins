<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Next Steps</h1>
  <strong>End a reply with options instead of a promise.</strong>
  <p>Clickable next steps under every reply. Tick several and one send delivers them together.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.3-2ea44f" alt="Version 1.0.3" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Next Steps" />
</div>

## Screenshot

<div align="center">
  <img src="docs/screenshot.png" alt="Three answers left unanswered, carried under a later reply with age labels, a dismiss cross and Clean Old Proposals" />
</div>

## What You Can Do

- End a reply with up to six steps instead of "say the word and I'll push it". A click sends that step back as a normal user turn, so the next message is already written.
- Tick several and send once. With two or more options the row is multi-select and the send button carries a count, so three picks become one message with three lines rather than three queued turns. A block registered with `multi="0"` sends on the first click.
- See which options are worth taking now. A decision classifier tags them **Recommended** in the accent tint and they start ticked; several can carry the tag when they belong together, never all of them, and never beside "leave it as it is".
- See which options could cost you something. An option the classifier reads as able to damage files, a build or money carries an amber **RISKY** pill. Off by default.
- Read a label that would otherwise mislead. The agent can attach a dim second line to any chip, clipped at two wrapped lines with the full text on hover.
- Let two options exclude each other. Alternating options are drawn next to each other and picking one greys the other; the option that means leaving things alone closes the row.
- Pick up what earlier replies left unanswered. With carry on, every reply lists those options youngest reply first, each with how many replies back it was offered and an X to drop it, and the queue caps at thirty.
- Answer mid-turn. A step clicked while a turn is working joins the queue as the next turn; with steer on it also reaches the live turn so the text lands mid-request, and a refused steer still becomes that queued turn.

The plugin has two halves. The agent half registers the options through the `next_steps` tool, or writes a `::nextsteps` directive when tool calling is off, and a bundled prompt rule asks it to end a choice that way. The renderer half draws the row under the reply and sends the text back as a normal user turn. Every chip in a block shares one width, set by the longest option, and per-block state survives a reload.

## Settings

Open Settings, Plugins, Next Steps.

| Setting | Default | What it does |
| --- | --- | --- |
| Ask the decision classifier which steps to pick | on | Asks for recommendations before the options are written, one classifier call per reply that offers a choice. |
| Accent the recommended options | on | Keeps the accent tint on a recommended chip that is not ticked. |
| Mark risky options | off | Adds the amber RISKY pill to options that could damage something. |
| Carry unanswered options forward | off | Lists earlier replies' unanswered options under every reply, youngest first. |
| Send a chip result as a steer | off | A step clicked mid-turn steers the running answer instead of queueing behind it. |
| Turn a written offer into options | off | Rewrites a closing offer written in prose into the same row before the reply is stored. |

Recommendations and the RISKY pill need a decision classifier plugin loaded, nerve or jev. Without one the chips work exactly the same and are simply never marked.

## What the agent writes

The tool takes `options`, `multi`, `recommend`, `alternates`, `risky` and `subtitles`. Without tool calling the same row is a directive:

```
::nextsteps{multi="1" rec="1" risky="2" q1="Push the branch and open the PR" q2="Force-push over the review commit" q3="Write the release note first" d2="Rewrites origin, discarding the commit already there"}
```

`q` attributes are the labels, `dN` a subtitle for option N, `rec` the recommended indexes, `alt` pairs that exclude each other, `risky` the indexes that carry the pill, `carry="1"` records the reply's options for later ones, and `steer="1"` asks a click to steer the live turn. `next_steps_recommend` returns the classifier's pick without drawing anything.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.22.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Or this plugin alone:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/next-steps
```

Enable **Next Steps** under **Capabilities → Plugins**, then `Ctrl+K` and **Reload window** so the renderer half loads. The agent half is live immediately; the chips appear only after the reload.

Follow-up Chips and Next Steps draw the same slot under a reply, so disable one before enabling the other.

## Requirements / Limits

Desktop plus gateway, and the same per-chat state through `ctx.storage`. A step is a sentence, so a vague option sends a vague request; the plugin does not rewrite what the agent wrote. Ticks are per block, so two blocks open in one reply keep separate picks. The carry queue is stored per chat, and clearing a chat clears its queue. A subtitle is authored by the agent and nothing checks it against the label. The RISKY pill is a classifier's opinion about consequences, not a reading of your repository.

This is the catalog edition and stays inside the plugin SDK. It drops the two surfaces that reach into the app's own DOM: the chip border no longer runs Hermes' arc while a reply works, and a carried label does not jump back to the reply that offered it. The personal edition has both, and `personal/next-steps/LIMITATIONS.md` names the hooks they need before this edition can carry them too.

## Where this comes from

An extended edition of **Follow-up Chips** ([nuonrg/hermes-plugin-followup-chips](https://github.com/nuonrg/hermes-plugin-followup-chips)), which it grew out of and still shares the idea with: a reply ends with clickable options, and a click sends one back as the next turn. Next Steps carries that further with the classifier marks, subtitles, the alternating and deferral ordering, the carry-forward queue, and the steer setting.

## License

[MIT](../../LICENSE)
