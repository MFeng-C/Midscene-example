import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import scene_ai_runtime as ai
import test_manager_pure_recording_ios as manager


class SceneAIIntegrationTest(unittest.TestCase):
    def test_ai_start_never_selects_manual_mode(self):
        driver = Mock()
        with patch.object(ai, 'click_ai_control', return_value=True) as button, \
             patch.object(ai, 'node_snapshot', side_effect=[dict(progress=None, signature=False),
                                                          dict(progress=(1, 4))]), \
             patch.object(ai.time, 'sleep'):
            self.assertTrue(ai.start_ai_recording(driver, 1))
        button.assert_called_once_with(driver, '开始（AI）', timeout=30)

    def test_ai_reuses_verified_nodes_with_separate_wait_budget(self):
        driver = Mock()
        with patch.object(ai, 'advance_manual_nodes', return_value=True) as advance:
            self.assertTrue(ai.advance_ai_nodes(driver, 2))
        advance.assert_called_once()
        self.assertIsInstance(advance.call_args.kwargs['snapshot_reader'], ai.AINodeReader)
        self.assertEqual(advance.call_args.kwargs['transition_timeout'], 60)
        self.assertTrue(callable(advance.call_args.kwargs['signature_handler']))

    def run_flow(self, mode):
        common = ['prepare_manager', 'login_manager', 'open_scene_navigation', 'search_scene_order',
                  'step5_scene_confirm_popup', 'step6_scene_click_agree_and_start',
                  'step7_scene_click_start_now', 'step8_scene_click_agree_detection',
                  'step9_scene_wait_detection_result', 'step11_scene_wait_countdown',
                  'exercise_scene_controls', 'step16_scene_review_and_confirm',
                  'step17_scene_confirm_popup', 'wait_upload_success', 'step19_scene_upload_confirm',
                  'return_scene_list', 'logout_customer_ios', 'step24_scene_home']
        specific = ['start_manual_recording', 'step14_scene_manual_qa_node',
                    'step15_scene_manual_reading_node', 'start_ai_recording',
                    'advance_ai_nodes', 'finish_ai_recording']
        calls = []
        with ExitStack() as stack:
            mocks = {}
            for name in common + specific:
                def step(*args, _name=name, **kwargs):
                    calls.append(_name)
                    return 'passed' if _name == 'step9_scene_wait_detection_result' else True
                mocks[name] = stack.enter_context(patch.object(manager, name, side_effect=step))
            self.assertTrue(manager.run_scene_record_cycle(Mock(), 1, record_type=mode))
        for name in common:
            mocks[name].assert_called_once()
        self.assertLess(calls.index('exercise_scene_controls'),
                        calls.index('advance_ai_nodes' if mode == 'ai' else 'step14_scene_manual_qa_node'))
        self.assertLess(calls.index('wait_upload_success'), calls.index('return_scene_list'))
        return mocks

    def test_ai_uses_new_helpers_and_no_manual_start(self):
        mocks = self.run_flow('ai')
        for name in ['start_ai_recording', 'advance_ai_nodes', 'finish_ai_recording']:
            mocks[name].assert_called_once()
        mocks['start_manual_recording'].assert_not_called()
        mocks['step14_scene_manual_qa_node'].assert_not_called()
        for name in ('step16_scene_review_and_confirm', 'step17_scene_confirm_popup',
                     'step19_scene_upload_confirm'):
            self.assertEqual(mocks[name].call_args.kwargs, dict(state_driven=True))
        self.assertEqual(mocks['wait_upload_success'].call_args.kwargs, dict(fail_fast=True))

    def test_ai_and_manual_share_upload_steps_and_order(self):
        ai_calls = self.run_flow('ai')
        manual_calls = self.run_flow('manual')
        for name in ('step16_scene_review_and_confirm', 'step17_scene_confirm_popup',
                     'step19_scene_upload_confirm'):
            self.assertEqual(ai_calls[name].call_args.kwargs, manual_calls[name].call_args.kwargs)

    def test_manual_keeps_existing_entry_and_nodes(self):
        mocks = self.run_flow('manual')
        for name in ['start_manual_recording', 'step14_scene_manual_qa_node', 'step15_scene_manual_reading_node']:
            mocks[name].assert_called_once()
        for name in ['start_ai_recording', 'advance_ai_nodes', 'finish_ai_recording']:
            mocks[name].assert_not_called()
        self.assertNotIn('dom_first', mocks['step16_scene_review_and_confirm'].call_args.kwargs)
        self.assertNotIn('dom_first', mocks['wait_upload_success'].call_args.kwargs)
        self.assertEqual(mocks['wait_upload_success'].call_args.kwargs, dict(fail_fast=True))

    def test_ai_resets_before_session_and_disables_auto_launch(self):
        events, options = [], []
        driver = Mock()
        driver.get_settings.return_value = {}
        def session(*args, **kwargs):
            options.append(kwargs['options'].to_capabilities())
            events.append('session')
            return driver
        with patch.object(manager.sys, 'argv', ['script', 'scene_ai', '2']), \
             patch.object(manager, 'reset_scene_order', side_effect=lambda *_: events.append('reset')), \
             patch.object(manager.webdriver, 'Remote', side_effect=session), \
             patch.object(manager, 'run_scene_record_cycle'), \
             patch.object(manager, 'cleanup_session') as cleanup, \
             patch.object(manager.time, 'sleep'):
            manager.main()
        self.assertEqual(events, ['reset', 'session', 'reset', 'session'])
        self.assertEqual(cleanup.call_count, 2)
        for caps in options:
            self.assertFalse(caps['appium:autoLaunch'])
            self.assertFalse(caps['appium:autoAcceptAlerts'])

    def test_manual_and_ai_use_identical_startup_configuration(self):
        captured = []
        for mode in ('scene_manual', 'scene_ai'):
            driver = Mock()
            driver.get_settings.return_value = {}

            def session(*args, **kwargs):
                captured.append(kwargs['options'].to_capabilities())
                return driver

            with patch.object(manager.sys, 'argv', ['script', mode, '1']), \
                 patch.object(manager, 'reset_scene_order'), \
                 patch.object(manager.webdriver, 'Remote', side_effect=session), \
                 patch.object(manager, 'run_scene_record_cycle'), \
                 patch.object(manager, 'cleanup_session'):
                manager.main()
        ai_caps = dict(captured[1])
        self.assertEqual(ai_caps.pop('appium:wdaConnectionTimeout'), 30000)
        manual_caps = dict(captured[0])
        self.assertEqual(manual_caps.pop('appium:wdaConnectionTimeout'), 60000)
        self.assertEqual(manual_caps, ai_caps)
        self.assertEqual(captured[1]['appium:processArguments'], {'args': []})
        for key in ('autoLaunch', 'autoAcceptAlerts', 'shouldTerminateApp'):
            self.assertFalse(captured[1]['appium:' + key])


if __name__ == '__main__':
    unittest.main()
