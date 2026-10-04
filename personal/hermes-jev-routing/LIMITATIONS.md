# Public edition

This edition stays inside the plugin SDK. It classifies the turn and can rewrite the model id when the pick stays on the provider already bound to the request. It does not look up the gateway agent cache and does not call `switch_model`, so a pick on another provider is recorded and left alone.

The personal edition does that switch. Read `personal/hermes-jev-routing/LIMITATIONS.md` before copying the switch into this tree.
