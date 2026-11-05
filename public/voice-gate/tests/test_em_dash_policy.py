"""Behavior of the prose-only em-dash policy, through the real extraction path."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('voice_gate_dash_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)
POLICY = {'preferences': {'no_em_dash': True}}


class EmDashPolicy(unittest.TestCase):
    def test_formatting_and_prose_are_distinct(self):
        cases = {
            '- Status — Ready\n- **Owner** — Apostol\n': 0,
            '| Item | Value |\n| --- | --- |\n| Owner | — |\n': 0,
            'The request failed — retry it.': 1,
            '- The server is ready — retry it.': 1,
            '- Status — The request failed — retry it.': 1,
            '| Item | Value |\n| --- | --- |\n| Status | Failed — retry it. |': 1,
            'Use `left — right` as the example.': 0,
            '```text\nThe request failed — retry it.\n```\n': 0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            for text, count in cases.items():
                with self.subTest(text=text):
                    file = Path(tmp) / 'README.md'
                    file.write_text(text, encoding='utf-8')
                    result = gate.rules.lint(gate.extract.read(file) or '', POLICY)
                    self.assertEqual(result['tells']['em_dashes']['count'], count)
                    found = gate.rules.gate_findings(result, POLICY, str(file))
                    self.assertEqual(any('em dash' in item for item in found), count > 0)

    def test_explicit_policy_survives_register_relaxation(self):
        for context in ('docs', 'technical-blog', 'casual', 'linkedin'):
            profile = {**POLICY, 'context': context}
            result = gate.rules.lint('The request failed — retry it.', profile)
            self.assertTrue(gate.rules.gate_findings(result, profile))


if __name__ == '__main__':
    unittest.main()
