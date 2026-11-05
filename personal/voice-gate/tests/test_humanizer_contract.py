"""Regression checks for the humanizer comparison and gate's editorial contract."""
import importlib.util
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vg_contract_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


class Context:
    def __init__(self, **config): self.config = config
    def get_config(self, key, default=None): return self.config.get(key, default)


class HumanizerContract(unittest.TestCase):
    def setUp(self):
        self.ctx = Context(mode='improve', min_words=0, vale_mode='off')
        gate._CTX = self.ctx
        gate._root_settings = lambda: {}
        gate._current_profile = lambda: 'default'
        gate._TURN_RECORDS.clear()
        gate._REVIEWED.clear()

    def issues(self, text, profile=None, path=None):
        return gate.rules.gate_findings(gate.rules.lint(text, profile, path), profile, path, structured=True)

    def test_word_boundaries_and_overlap(self):
        profile = {'rules': {'banned_words': ['begin', 'begins']}}
        self.assertEqual(gate.rules.lint('The beginning is documented.', profile)['tells']['banned_words']['count'], 0)
        self.assertEqual(gate.rules.lint('The job begins here.', profile)['tells']['banned_words']['count'], 1)

    def test_catalog_exposes_every_rule_with_carveouts(self):
        plan = gate._tool_review({'action': 'plan'})
        self.assertEqual({item['id'] for item in plan['patterns']}, set(range(1, 111)))
        full = gate._tool_review({'action': 'plan', 'pattern_ids': [74, 96, 97, 110]})
        self.assertTrue(all('Carve-outs' in item['guidance'] or 'Judgment-only' in item['guidance'] for item in full['patterns']))

    def test_protected_examples_are_not_rewritten_as_prose(self):
        text = '---\nname: delve tapestry robust\n---\n\n> Great question.\n\n"As an AI, delve tapestry."\n\n~~~text\n```\nAs an AI, I cannot browse.\n~~~\n'
        self.assertEqual(self.issues(text), [])

    def test_format_extractors_do_not_leak_code(self):
        for suffix, source in [('.adoc', '[source,text]\n----\nAs an AI, delve tapestry.\n----\n'), ('.org', '#+BEGIN_SRC text\nAs an AI, delve tapestry.\n#+END_SRC\n')]:
            self.assertEqual(self.issues(gate.extract.prose_lines(gate.extract.to_prose(source, suffix))), [])

    def test_tier2_cluster_is_paragraph_local(self):
        together = gate.rules.lint('We foster change and bolster adoption.')['tells']['tier2']
        apart = gate.rules.lint('We foster change.\n\nWe bolster adoption.')['tells']['tier2']
        self.assertGreaterEqual(together['count'], 2)
        self.assertEqual(apart['count'], 0)
        self.assertEqual(len(gate.rules.paragraphs(gate.extract.prose_lines('A complete paragraph.\n\nAnother complete paragraph.'))), 2)

    def test_tier3_uses_one_word_density(self):
        mixed = gate.rules.lint('Effective dynamic scalable compelling sophisticated.')['tells']['tier3']
        repeated = gate.rules.lint('Effective effective effective.')['tells']['tier3']
        self.assertEqual(mixed['count'], 0)
        self.assertEqual(repeated['count'], 3)

    def test_clarity_is_separate_from_markers(self):
        hits = self.issues('We utilize a tool to delve into the topic.')
        self.assertTrue({'tier1a', 'tier1b'} <= {item['rule'] for item in hits})
        self.assertTrue(all(item['requires_review'] for item in hits))

    def test_literal_technical_carveouts(self):
        self.assertFalse(any(item['rule'] == 'load_bearing_metaphor' for item in self.issues('The load-bearing wall supports the roof.')))
        self.assertTrue(any(item['rule'] == 'load_bearing_metaphor' for item in self.issues('It is a load-bearing assumption.')))
        self.assertFalse(any(item['rule'] == 'template_phrases' for item in self.issues('A first step towards the full API. A small step towards a lower bill.')))
        self.assertFalse(any(item['rule'] == 'unnecessary_hyphenation' for item in self.issues('The real-time analytics use high-quality data.')))

    def test_new_mechanical_families_and_positions(self):
        text = 'The release notes say citeturn0search0.\nWe changed the code-base in real-time.\n'
        hits = self.issues(text)
        self.assertTrue({'citation_residue', 'unnecessary_hyphenation'} <= {item['rule'] for item in hits})
        self.assertTrue(all(item['positions'] for item in hits))
        self.assertFalse(any(item['rule'] == 'tool_fingerprints' for item in self.issues('Read https://example.org/?page=2&v=4.')))

    def test_profile_validation_rejects_poisoned_thresholds(self):
        self.assertTrue(gate.profiles.validate({'name': 'bad', 'thresholds': {'hedges': 'NaN'}}))
        self.assertTrue(gate.profiles.validate({'name': 'bad', 'preferences': 'wrong'}))
        self.assertEqual(gate.profiles.validate({'name': 'ok', 'context': 'docs', 'rules': {'hedges': []}, 'thresholds': {'min_words': 0}}), [])
        draft = gate.profiles.draft(['A complete source sentence.'])
        self.assertEqual(gate.profiles.validate(draft), [])
        self.assertEqual(draft['preferences'], {})
        self.assertEqual(gate._min_words({'thresholds': {'min_words': 0}}), 0)

    def test_directory_exceptions_work_on_absolute_paths(self):
        self.assertTrue(gate.rules.suppressed({'exceptions': {'all': 'docs/**'}}, 'C:/repo/docs/page.md'))

    def test_review_loop_is_bounded_and_preserves_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'notes.md'
            file.write_text('Great question.\n\n```python\nprint(1)\n```\n')
            self.assertIsNotNone(gate._on_pre_verify(attempt=0, session_id='test', changed_paths=[str(file)]))
            self.assertIsNone(gate._on_pre_verify(attempt=2, session_id='test', changed_paths=[str(file)]))
            file.write_text('The job finished.\n\n```python\nprint(2)\n```\n')
            result = gate._tool_review({'action': 'record', 'paths': [str(file)], 'assessment': 'Reviewed meaning, voice, structure, and delivery.'})
            self.assertFalse(result['ok'])
            self.assertIn('fenced_code', result['preservation']['errors'])

    def test_noop_review_is_tied_to_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'notes.md'
            file.write_text('The job finished successfully and returned the expected value.\n')
            gate._on_pre_verify(attempt=0, session_id='review', changed_paths=[str(file)])
            result = gate._tool_review({'action': 'record', 'paths': [str(file)], 'assessment': 'No edit is justified; the operation, result and scope are already clear.'})
            self.assertTrue(result['ok'])
            self.assertIsNone(gate._on_pre_verify(attempt=1, session_id='review', changed_paths=[str(file)]))
            file.write_text('As an AI, I cannot browse.\n')
            self.assertIsNotNone(gate._on_pre_verify(attempt=1, session_id='review', changed_paths=[str(file)]))

    def test_profile_name_cannot_escape_destination(self):
        self.assertFalse(gate._tool_learn({'name': '../escape', 'text': 'A source sentence.', 'save': True})['ok'])

    def test_program_paths_request_the_declared_approval(self):
        with patch.object(gate.vale, 'resolve_binary', return_value='C:/tools/vale.exe'):
            for action in ('status', 'check', 'install'):
                result = gate._on_pre_tool_call(tool_name='voice_gate_vale', args={'action': action, 'paths': ['README.md']})
                self.assertEqual(result['action'], 'approve')
                self.assertIn('vale', result['message'].lower())
            self.assertIsNone(gate._on_pre_tool_call(tool_name='someone_elses_tool', args={'action': 'install'}))

    def test_vale_cannot_bypass_exceptions_or_family_switches(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'notes.txt'
            file.write_text('Robust robust robust.')
            report = {'ok': True, 'report': {str(file.resolve()): [{'Check': 'VoiceGate.Marketing', 'Severity': 'warning', 'Match': 'robust', 'Line': 1}] * 3}}
            self.ctx.config.update({'vale_mode': 'advisory', 'exceptions': 'all: *.txt'})
            with patch.object(gate.vale, 'resolve_binary', return_value='vale'), patch.object(gate.vale, 'run', return_value=report):
                self.assertIsNone(gate._on_pre_verify(attempt=0, changed_paths=[str(file)]))
                self.ctx.config.update({'exceptions': '', 'tell_marketing_adjectives': False, 'tell_tier1a': False})
                result = gate._on_pre_verify(attempt=0, changed_paths=[str(file)])
                self.assertNotIn('Vale reports', (result or {}).get('message', ''))

    def test_model_review_uses_all_references_and_validates_quotes(self):
        gate.model_review._CACHE.clear()
        captured = {}
        source = 'The decision emerged after the meeting.'
        def complete(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(parsed={'assessment': 'The accountable actor is unclear.', 'issues': [
                {'path': 'doc.md', 'pattern_id': 74, 'quote': 'The decision emerged', 'explanation': 'The text describes a consequential decision without identifying its owner.', 'repair': 'Ask who decided; do not invent an actor.', 'severity': 'P2'},
                {'path': 'doc.md', 'pattern_id': 74, 'quote': 'An invented quote', 'explanation': 'Wrong.', 'repair': 'Wrong.', 'severity': 'P1'}]})
        ctx = SimpleNamespace(llm=SimpleNamespace(complete_structured=complete))
        result = gate.model_review.analyze(ctx, {'doc.md': source}, {}, True)
        self.assertEqual(len(result['issues']), 1)
        self.assertEqual(result['rejected_findings'], 1)
        self.assertEqual(captured['task'], gate.model_review.TASK)
        self.assertEqual(len(json.loads(captured['input'])['references']), 10)
        excluded = gate.model_review.analyze(ctx, {'doc.md': source}, {}, True, {'doc.md': [74]})
        self.assertEqual(excluded['issues'], [])

    def test_model_review_is_opt_in_and_handles_bad_responses(self):
        self.assertFalse(gate._tool_review({'action': 'analyze', 'paths': ['not-read.md']})['ok'])
        gate.model_review._CACHE.clear()
        ctx = SimpleNamespace(llm=SimpleNamespace(complete_structured=lambda **kwargs: SimpleNamespace(parsed=None)))
        result = gate.model_review.analyze(ctx, {'doc.md': 'A complete sentence.'}, {})
        self.assertFalse(result['ok'])
        self.assertEqual(result['not_reviewed'], ['doc.md'])


if __name__ == '__main__': unittest.main()
