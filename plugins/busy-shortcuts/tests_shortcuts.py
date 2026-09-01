import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).parent


def load_plugin():
    spec = importlib.util.spec_from_file_location("busy_shortcuts_test", ROOT / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeCLI:
    def __init__(self):
        self.calls = []

    def _handle_busy_command(self, command):
        self.calls.append(command)

    def process_command(self, command):
        self.calls.append(command)
        return True


class FakeContext:
    def __init__(self):
        self.commands = {}

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = (handler, kwargs)


class BusyShortcutsTests(unittest.TestCase):
    def setUp(self):
        self.cli_mod = types.ModuleType("cli")
        self.cli_mod.HermesCLI = FakeCLI
        self.cli_mod.save_config_value = lambda *_args: True
        self.old_cli = sys.modules.get("cli")
        sys.modules["cli"] = self.cli_mod
        self.plugin = load_plugin()
        self.plugin._cli_patched = False
        self.plugin._active_cli = None

    def tearDown(self):
        if self.old_cli is None:
            sys.modules.pop("cli", None)
        else:
            sys.modules["cli"] = self.old_cli

    def test_registers_i_and_s(self):
        ctx = FakeContext()
        self.plugin.register(ctx)
        self.assertEqual(set(ctx.commands), {"i", "s"})

    def test_i_sets_interrupt_mode(self):
        self.plugin._patch_cli()
        cli = FakeCLI()
        cli.process_command("/i")
        self.assertEqual(cli.calls, ["/busy interrupt"])

    def test_s_without_prompt_sets_steer_mode(self):
        self.plugin._patch_cli()
        cli = FakeCLI()
        cli.process_command("/s")
        self.assertEqual(cli.calls, ["/busy steer"])

    def test_s_with_prompt_forwards_to_steer(self):
        self.plugin._patch_cli()
        cli = FakeCLI()
        cli.process_command("/s focus on the failing test")
        self.assertEqual(cli.calls, ["/steer focus on the failing test"])

    def test_other_commands_are_unchanged(self):
        self.plugin._patch_cli()
        cli = FakeCLI()
        cli.process_command("/q next turn")
        self.assertEqual(cli.calls, ["/q next turn"])


if __name__ == "__main__":
    unittest.main()
