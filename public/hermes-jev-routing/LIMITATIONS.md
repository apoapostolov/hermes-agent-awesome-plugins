# Reach-in

This edition switches providers the same way the personal edition does. It walks the caller stack, and if that misses, the live agent cache, then calls `switch_model`. The desktop half also asks the session to adopt the pick when the tier is not held for confirm.

That cache walk is outside the plugin SDK. It is here because the session model has to move with the pick.
