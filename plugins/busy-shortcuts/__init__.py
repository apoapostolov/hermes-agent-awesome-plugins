"""Short slash commands for Hermes busy-input modes.

The built-in ``/q`` already queues a prompt, so this plugin keeps that
behavior for ``/q <prompt>``. Bare ``/q`` remains the built-in queue command.
The added shortcuts are:

- ``/i`` -> ``/busy interrupt``
- ``/s <prompt>`` -> ``/steer <prompt>``

The CLI patch makes the aliases execute against the live CLI instance instead
of entering the normal pending-input path while a turn is running. Gateway
invocations persist the selected mode for the next session when no CLI object
is available in the plugin process.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_active_cli: Any | None = None
_cli_patched = False


def _persist_mode(mode: str) -> str:
    """Persist a busy mode when the command runs outside the classic CLI."""
    try:
        from cli import save_config_value

        if save_config_value("display.busy_input_mode", mode):
            return f"Busy input mode set to '{mode}'"
    except Exception:
        logger.debug("Could not persist busy input mode", exc_info=True)
    return f"Busy input mode set to '{mode}' for the next session"


def _set_mode(mode: str) -> str:
    cli = _active_cli
    if cli is not None and hasattr(cli, "_handle_busy_command"):
        cli._handle_busy_command(f"/busy {mode}")
        return ""
    return _persist_mode(mode)


def _handle_interrupt(_raw_args: str) -> str:
    return _set_mode("interrupt")


def _handle_steer(raw_args: str) -> str:
    """Dispatch /s as /steer in the classic CLI, or explain the mapping."""
    cli = _active_cli
    if cli is not None:
        prompt = (raw_args or "").strip()
        if prompt:
            cli.process_command(f"/steer {prompt}")
            return ""
        return _set_mode("steer")
    return "Use /steer <prompt> to inject a message, or /busy steer to set Enter mode"


def _patch_cli() -> None:
    global _cli_patched
    if _cli_patched:
        return
    try:
        import cli as cli_mod
    except Exception:
        return

    cls = getattr(cli_mod, "HermesCLI", None)
    original = getattr(cls, "process_command", None)
    if cls is None or original is None:
        return

    def wrapped(self: Any, command: str) -> bool:
        global _active_cli
        text = (command or "").strip()
        parts = text.split(None, 1)
        base = parts[0].lower().lstrip("/") if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        if base == "i":
            _active_cli = self
            _set_mode("interrupt")
            return True
        if base == "s":
            _active_cli = self
            if args:
                self.process_command(f"/steer {args}")
            else:
                _set_mode("steer")
            return True

        # /q is already a built-in alias for /queue. Keep it untouched so
        # /q <prompt> remains useful and compatible with Hermes core.
        _active_cli = self
        return original(self, command)

    cls.process_command = wrapped
    _cli_patched = True


def register(ctx: Any) -> None:
    ctx.register_command(
        "i",
        handler=_handle_interrupt,
        description="Set busy input to interrupt the current run.",
    )
    ctx.register_command(
        "s",
        handler=_handle_steer,
        description="Steer a prompt into the current run, or set steer mode.",
        args_hint="[prompt]",
    )
    _patch_cli()
