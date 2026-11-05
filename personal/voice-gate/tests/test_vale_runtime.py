"""Run the actual installed Vale pack and verify archive refusal contracts."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vg_vale_runtime', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


class ValeRuntime(unittest.TestCase):
    def test_shipped_pack_runs_with_real_vale(self):
        binary = gate.vale.resolve_binary()
        if not binary: self.skipTest('Vale is not installed on this test host.')
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'test.md'
            file.write_text('We delve into a tapestry of pivotal change.\n', encoding='utf-8')
            report = gate.vale.run([str(file)], binary)
            self.assertTrue(report['ok'], report)
            self.assertTrue(report['counts'], report)

    def test_archive_cannot_escape_by_sibling_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'archive.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('../safe-evil/payload.txt', 'untrusted')
            with self.assertRaises(RuntimeError):
                gate.vale._safe_extract(archive, root / 'safe', 'zip')
            self.assertFalse((root / 'safe-evil' / 'payload.txt').exists())

    def test_wrong_digest_refuses_before_extracting(self):
        with patch.object(gate.vale, 'installed_binary', return_value=None), patch.object(gate.vale, '_download', return_value=b'wrong archive'), patch.object(gate.vale, '_safe_extract') as extract:
            report = gate.vale.install()
            self.assertFalse(report['ok'])
            self.assertIn('checksum mismatch', report['error'])
            extract.assert_not_called()


class ReviewDelta(unittest.TestCase):
    """The three blocking items from the catalog review of 6d5d8f49."""

    def test_child_environment_carries_no_provider_key(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test', 'ANTHROPIC_API_KEY': 'sk-ant'}):
            env = gate.vale.child_env()
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('ANTHROPIC_API_KEY', env)

    def test_the_binary_never_sees_a_key(self):
        seen = {}

        class Proc:
            returncode = 0
            stdout = '{}'
            stderr = ''

        def fake_run(command, **kwargs):
            seen['command'] = command
            seen['env'] = kwargs.get('env')
            return Proc()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = root / 'doc.md'
            document.write_text('A document.\n', encoding='utf-8')
            ini = root / 'vale.ini'
            ini.write_text('StylesPath = styles\n', encoding='utf-8')
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-live'}), \
                    patch.object(gate.vale.subprocess, 'run', fake_run), \
                    patch.object(gate.vale, 'resolve_binary', return_value='vale'), \
                    patch.object(gate.vale, 'approved', return_value=True), \
                    patch.object(gate.vale, 'config_path', return_value=ini):
                report = gate.vale.run([str(document)], approved_only=True)
        self.assertTrue(report['ok'], report)
        self.assertIn('env', seen)
        self.assertNotIn('OPENAI_API_KEY', seen['env'])
        self.assertIn('PATH', seen['env'])

    def test_approval_is_bound_to_the_binary_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / 'fake-vale'
            binary.write_bytes(b'first build')
            gate.vale._DIGESTS.clear()
            with patch.object(gate.vale, 'data_dir', return_value=root):
                gate.vale.record_approval(str(binary))
                self.assertTrue(gate.vale.approved(str(binary)))
                binary.write_bytes(b'a replacement build')
                gate.vale._DIGESTS.clear()
                self.assertFalse(gate.vale.approved(str(binary)))

    def test_advisory_refuses_an_unapproved_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = root / 'doc.md'
            document.write_text('A document.\n', encoding='utf-8')
            with patch.object(gate.vale, 'resolve_binary', return_value='vale'), \
                    patch.object(gate.vale, 'data_dir', return_value=root), \
                    patch.object(gate.vale.subprocess, 'run') as run:
                report = gate.vale.run([str(document)], approved_only=True)
        self.assertFalse(report['ok'])
        self.assertFalse(report['approved'])
        run.assert_not_called()

    def test_home_follows_the_profile_the_host_serves(self):
        served = Path(tempfile.gettempdir()) / 'vg-served-profile'
        launch = Path(tempfile.gettempdir()) / 'vg-launch-profile'
        fake = types.SimpleNamespace(get_hermes_home=lambda: served)
        with patch.dict(sys.modules, {'hermes_constants': fake}), \
                patch.dict(os.environ, {'HERMES_HOME': str(launch)}):
            candidates = gate.profiles.home_candidates()
        self.assertEqual(candidates[0], served)
        self.assertIn(launch, candidates)


if __name__ == '__main__': unittest.main()
