"""Run the actual installed Vale pack and verify archive refusal contracts."""
import importlib.util
import sys
import tempfile
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


if __name__ == '__main__': unittest.main()
