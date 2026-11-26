"""Validate editable startup inputs and recovery before Qwen takes over."""

import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ax3l.activity.ViewConfiguration import apply_values, view_values
from ax3l.app.experiment.ExperimentLoop import ExperimentLoop
from ax3l.entities.ExperimentView import VIEWS
from ax3l.interface.SimulationConfiguration import SimulationConfiguration
from ax3l.interface.SyntheticExperimentConfiguration import SyntheticExperimentConfiguration
from view_cycle_fixtures import FakeSnake, LocalLLM, MemoryEvents, MemoryLog, MemoryStore


SOURCE = Path(__file__).resolve().parents[1] / 'conf/synthetic'


class SyntheticConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(TemporaryDirectory())
        self.directory = Path(temporary) / 'synthetic'
        shutil.copytree(SOURCE, self.directory)

    def write_config(self, config):
        (self.directory / 'config.json').write_text(json.dumps(config))

    def test_edits_are_loaded_as_the_actual_per_view_choices(self):
        config = json.loads((self.directory / 'config.json').read_text())
        config['model']['hidden_size'] = 80
        self.write_config(config)
        (self.directory / 'architecture.md').write_text('A wider model should improve the high score.\n')
        proposals = SyntheticExperimentConfiguration.load(self.directory)
        self.assertEqual(set(proposals), set(VIEWS))
        for name, view in VIEWS.items():
            self.assertEqual(proposals[name].values, view_values(view, config))
        self.assertEqual(proposals['architecture'].hypothesis, 'A wider model should improve the high score.')
        proposals['architecture'].values['model.hidden_size'] = 88
        self.assertEqual(SyntheticExperimentConfiguration.load(self.directory)['architecture'].values[
            'model.hidden_size'], 80)

    def test_invalid_or_unchanged_configuration_identifies_its_file_and_field(self):
        default = SimulationConfiguration.defaults()
        valid = json.loads((self.directory / 'config.json').read_text())
        cases = [
            (default, 'change at least one'),
            (dict(valid, seed=1971), 'seed'),
            (apply_values(valid, {'model.hidden_size': 73}), 'hidden_size'),
            (apply_values(valid, {'game.rewards.closer_to_food': 5}), 'rewards'),
            (dict(valid, epochs=100), 'epochs'),
        ]
        for config, field in cases:
            with self.subTest(field=field):
                self.write_config(config)
                with self.assertRaisesRegex(ValueError, field) as caught:
                    SyntheticExperimentConfiguration.load(self.directory)
                self.assertIn(str(self.directory / 'config.json'), str(caught.exception))
        for text in ('{', '{"seed": NaN}', '{"seed": Infinity}'):
            with self.subTest(text=text):
                (self.directory / 'config.json').write_text(text)
                with self.assertRaisesRegex(ValueError, 'config.json'):
                    SyntheticExperimentConfiguration.load(self.directory)

    def test_all_four_hypotheses_are_required_nonblank_and_short(self):
        for name in VIEWS:
            path = self.directory / f'{name}.md'
            original = path.read_text()
            for text in ('   \n', 'x' * 281):
                path.write_text(text)
                with self.assertRaisesRegex(ValueError, name):
                    SyntheticExperimentConfiguration.load(self.directory)
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                SyntheticExperimentConfiguration.load(self.directory)
            path.write_text(original)


class SyntheticStartupTests(unittest.TestCase):
    def setUp(self):
        self.log = MemoryLog()
        self.store = MemoryStore(self.log)
        self.snake = FakeSnake()
        self.model = LocalLLM()
        self.addCleanup(self.model.close)
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.ExperimentDb', return_value=self.store))
        self.enterContext(patch('ax3l.app.experiment.ExperimentLoop.EventLogDb',
                               return_value=MemoryEvents(self.log)))

    def loop(self):
        return ExperimentLoop(self.log, self.model.llm, self.snake)

    def test_baseline_then_synthetic_complete_before_any_inference(self):
        respond = self.model.respond
        def first_request(request):
            self.assertEqual(len(self.snake.submissions), 2)
            self.assertTrue(self.store.load().synthetic)
            return respond(request)
        self.model.respond = first_request
        save = self.store.save
        def stop(state):
            save(state)
            if state.synthetic and state.phase == 'completed':
                raise KeyboardInterrupt()
        with patch.object(self.store, 'save', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                self.loop().run(cycles=1)
        baseline, synthetic = self.snake.results
        self.assertEqual(self.snake.submissions[0], SimulationConfiguration.defaults())
        self.assertEqual(self.snake.submissions[1], json.loads((SOURCE / 'config.json').read_text()))
        state = self.store.load()
        self.assertEqual(state.reference_run_id, baseline)
        self.assertEqual(state.latest_run_id, synthetic)
        self.assertEqual(state.golden_run_id, baseline)
        self.assertEqual(len(self.model.requests), 4)
        for name, request in zip(VIEWS, self.model.requests):
            text = request['messages'][0]['content'][0]['text']
            self.assertIn((SOURCE / f'{name}.md').read_text().strip(), text)
            self.assertIn(f'Golden reference: {baseline}', text)
            self.assertIn(f'Latest simulation: {synthetic}', text)
        accepted = [json.loads(e['content']) for e in self.log.events if e['name'] == 'proposal_accepted']
        self.assertEqual(accepted[0]['origin'], 'synthetic')
        self.model.respond = respond
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 3)
        self.assertEqual(len(self.model.requests), 12)
        self.assertFalse(self.store.load().synthetic)

    def test_synthetic_promotion_retains_original_baseline_for_evaluation(self):
        self.snake = FakeSnake((10, 12, 7))
        self.loop().run(cycles=1)
        baseline, synthetic, candidate = self.snake.results
        self.assertEqual(self.store.load().golden_run_id, synthetic)
        for request in self.model.requests[:4]:
            self.assertIn(f'Golden reference: {baseline}', request['messages'][0]['content'][0]['text'])
        self.assertEqual(self.store.comparison(candidate)['golden_run_id'], synthetic)

    def test_old_snakelab_history_does_not_replace_fresh_baseline_and_synthetic_runs(self):
        old_config = apply_values(SimulationConfiguration.defaults(), {'model.hidden_size': 128})
        old_config['seed'] = 8123
        old = self.snake.submit_simulation(old_config)
        self.snake.results[old]['high_score'] = 999
        self.loop().run(cycles=1)
        old, baseline, synthetic, candidate = self.snake.results
        self.assertEqual(self.snake.submissions[1], SimulationConfiguration.defaults())
        self.assertEqual(self.snake.submissions[2], json.loads((SOURCE / 'config.json').read_text()))
        self.assertEqual(self.snake.results[old]['high_score'], 999)
        self.assertEqual(self.snake.results[old]['config'], old_config)
        for request in self.model.requests[:4]:
            text = request['messages'][0]['content'][0]['text']
            self.assertIn(f'Golden reference: {baseline}', text)
            self.assertIn(f'Latest simulation: {synthetic}', text)
            self.assertNotIn(old, text)
        self.assertEqual(self.store.load().golden_run_id, synthetic)
        self.assertEqual(self.store.load().latest_run_id, candidate)

    def test_restart_uses_saved_inputs_and_does_not_repeat_either_startup_run(self):
        save = self.store.save
        def stop(state):
            save(state)
            if state.baseline and state.phase == 'running':
                raise KeyboardInterrupt()
        initial = SyntheticExperimentConfiguration.load()
        with patch.object(self.store, 'save', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                self.loop().run(cycles=1)
        self.assertEqual(self.store.load().proposals, initial)
        self.assertEqual(self.model.requests, [])
        with patch.object(SyntheticExperimentConfiguration, 'load', side_effect=AssertionError('Reloaded files')):
            self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 3)
        self.assertEqual(len(self.model.requests), 12)

    def test_lost_synthetic_acknowledgement_is_reconciled_without_resubmission(self):
        submit = self.snake.submit_simulation
        def lost_reply(config):
            run_id = submit(config)
            if len(self.snake.submissions) == 2:
                raise TimeoutError('Lost acknowledgement')
            return run_id
        with patch.object(self.snake, 'submit_simulation', side_effect=lost_reply):
            with self.assertRaises(TimeoutError):
                self.loop().run(cycles=1)
        self.assertTrue(self.store.load().synthetic)
        self.assertFalse(self.store.load().baseline)
        self.assertEqual(self.model.requests, [])
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 3)
        self.assertEqual(len(self.model.requests), 12)

    def test_restart_after_startup_promotions_does_not_repeat_runs_or_events(self):
        for boundary in ('baseline', 'synthetic'):
            with self.subTest(boundary=boundary):
                self.log.events.clear()
                self.store.state = None
                self.model.requests.clear()
                self.snake = FakeSnake((10, 12, 7))
                save = self.store.save
                def stop(state):
                    if state.synthetic and not state.baseline and state.phase == (
                            'ready' if boundary == 'baseline' else 'evaluating'):
                        raise KeyboardInterrupt()
                    save(state)
                with patch.object(self.store, 'save', side_effect=stop):
                    with self.assertRaises(KeyboardInterrupt):
                        self.loop().run(cycles=1)
                self.assertEqual(self.model.requests, [])
                self.loop().run(cycles=1)
                names = [event['name'] for event in self.log.events]
                self.assertEqual(len(self.snake.submissions), 3)
                self.assertEqual(names.count('golden_config_created'), 2)
                self.assertEqual(names.count('configuration_compared'), 2)
                self.assertEqual(names.count('simulation_submitted'), 3)

    def test_failed_synthetic_run_blocks_inference_and_can_resume(self):
        submit = self.snake.submit_simulation
        def failed(config):
            run_id = submit(config)
            if len(self.snake.submissions) == 2:
                self.snake.results[run_id]['status'] = 'failed'
            return run_id
        with patch.object(self.snake, 'submit_simulation', side_effect=failed):
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                self.loop().run(cycles=1)
        state = self.store.load()
        self.assertTrue(state.synthetic)
        self.assertEqual(self.model.requests, [])
        self.snake.results[state.run_id]['status'] = 'completed'
        self.loop().run(cycles=1)
        self.assertEqual(len(self.snake.submissions), 3)
        self.assertEqual(len(self.model.requests), 12)

    def test_invalid_inputs_fail_before_the_baseline_is_submitted(self):
        with patch.object(SyntheticExperimentConfiguration, 'load', side_effect=ValueError('Invalid hypothesis')):
            with self.assertRaisesRegex(ValueError, 'Invalid hypothesis'):
                self.loop().run(cycles=1)
        self.assertIsNone(self.store.load())
        self.assertEqual(self.snake.submissions, [])
        self.assertEqual(self.model.requests, [])
