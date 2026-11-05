"""Exercise storage limits, competing writers, failure isolation and privacy."""
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vg_diagnostics', ROOT / 'diagnostics.py')
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def writer(home):
    diag.MAX_BYTES = 2048
    for number in range(80):
        diag.emit(home, 'concurrent', number=number)


class DiagnosticsTests(unittest.TestCase):
    def test_rotation_is_bounded_and_parseable_across_processes(self):
        with tempfile.TemporaryDirectory() as home:
            workers = [multiprocessing.Process(target=writer, args=(home,)) for _ in range(4)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(20)
                self.assertEqual(worker.exitcode, 0)
            files = list((Path(home) / 'logs' / 'voice-gate').glob('events.jsonl*'))
            self.assertEqual(len(files), 5)
            self.assertEqual((Path(home) / 'logs' / 'voice-gate' / 'events.lock').stat().st_size, 1)
            self.assertLessEqual(sum(file.stat().st_size for file in files), 5 * 2048)
            for file in files:
                for line in file.read_text().splitlines():
                    self.assertEqual(json.loads(line)['event'], 'concurrent')

    def test_record_limit_preserves_json(self):
        with tempfile.TemporaryDirectory() as home:
            diag.emit(home, 'large', details={str(i): ['x' * 500] * 48 for i in range(128)})
            raw = (Path(home) / 'logs' / 'voice-gate' / 'events.jsonl').read_bytes()
            self.assertLessEqual(len(raw), diag.MAX_RECORD_BYTES)
            self.assertTrue(json.loads(raw)['details_dropped'])

    def test_logging_failure_does_not_change_return_or_exception(self):
        def broken_home():
            raise OSError('unavailable')
        wrapped = diag.traced('test', broken_home)(lambda: 42)
        self.assertEqual(wrapped(), 42)
        def failure():
            raise ValueError('original')
        with self.assertRaisesRegex(ValueError, 'original'):
            diag.traced('test', broken_home)(failure)()
        with patch.object(Path, 'mkdir', side_effect=OSError('disk full')):
            diag.emit('.', 'unwritable')

    def test_tool_logs_correlate_without_prose_paths_or_errors(self):
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / 'config.yaml').touch()
            spec = importlib.util.spec_from_file_location('vg_diagnostic_integration', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
            plugin = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = plugin
            spec.loader.exec_module(plugin)
            with patch.dict(os.environ, {'HERMES_HOME': home}):
                handler = plugin._as_handler(lambda args: {'ok': False, 'error': 'PRIVATE_ERROR', 'checks': []}, 'test')
                payload = json.loads(handler({'text': 'PRIVATE_PROSE', 'paths': ['PRIVATE_PATH'], 'assessment': 'PRIVATE_ASSESSMENT'}))
                self.assertEqual(payload['error'], 'PRIVATE_ERROR')
            raw = (Path(home) / 'logs' / 'voice-gate' / 'events.jsonl').read_text()
            self.assertNotIn('PRIVATE_', raw)
            records = [json.loads(line) for line in raw.splitlines()]
            self.assertEqual(len({row['operation'] for row in records}), 1)
            self.assertTrue(records[0]['operation'])
            self.assertEqual(records[-1]['event'], 'tool.test.finish')
            self.assertEqual(records[1]['text_chars'], len('PRIVATE_PROSE'))


if __name__ == '__main__':
    unittest.main()
