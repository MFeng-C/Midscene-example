import unittest
from unittest.mock import Mock, patch

import scene_manual_runtime as runtime
import test_manager_pure_recording_ios as manager


class CycleRecoveryTest(unittest.TestCase):
    def test_cleanup_policy_tracks_full_cycle_result_in_both_modes(self):
        for mode in ('scene_manual', 'scene_ai'):
            with self.subTest(mode=mode):
                driver = Mock()
                driver.get_settings.return_value = {}
                with patch.object(manager.sys, 'argv', ['script', mode, '4']), \
                     patch.object(manager, 'reset_scene_order'), \
                     patch.object(manager.webdriver, 'Remote', return_value=driver), \
                     patch.object(manager, 'run_scene_record_cycle',
                                  side_effect=[True, RuntimeError('failed'), True, True]) as run, \
                     patch.object(manager, 'capture_failure'), \
                     patch.object(manager, 'end_failed_ai_cycle'), \
                     patch.object(manager, 'cleanup_session'), \
                     patch.object(manager.time, 'sleep'):
                    with self.assertRaises(SystemExit):
                        manager.main()
                self.assertEqual([c.kwargs['cleanup_broadcast'] for c in run.call_args_list],
                                 [True, False, True, False])

    def test_successful_previous_cycle_skips_special_query(self):
        driver = Mock()
        driver.query_app_state.return_value = 4
        with patch.object(runtime, 'clear_broadcast') as clear, \
             patch.object(runtime, 'terminate_previous_app'), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'startup_snapshot', return_value=dict(form=True)):
            runtime.prepare_manager(driver, 2, 'test.bundle', Mock(), cleanup_broadcast=False)
        clear.assert_not_called()

    def test_skipped_query_still_clears_delayed_alert(self):
        driver = Mock()
        driver.query_app_state.return_value = 4
        with patch.object(runtime, 'clear_broadcast') as clear, \
             patch.object(runtime, 'terminate_previous_app'), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'startup_snapshot', side_effect=[dict(replayStopped=True), dict(form=True)]):
            runtime.prepare_manager(driver, 2, 'test.bundle', Mock(), cleanup_broadcast=False)
        clear.assert_called_once_with(driver)

    def test_delayed_system_alert_after_logout_is_cleared_before_login(self):
        driver = Mock()
        driver.query_app_state.return_value = 4
        states = [dict(form=False, entry=False, loggedIn=True, canBack=False),
                  dict(replayStopped=True), dict(form=True, entry=False, loggedIn=False)]
        with patch.object(runtime, 'clear_broadcast') as clear, \
             patch.object(runtime, 'terminate_previous_app'), \
             patch.object(runtime, 'startup_snapshot', side_effect=states), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'logout_customer_ios') as logout:
            self.assertTrue(runtime.prepare_manager(driver, 5, 'test.bundle', Mock()))
        self.assertEqual(clear.call_count, 2)
        logout.assert_called_once()
        driver.activate_app.assert_called_once_with('test.bundle')
        self.assertTrue(driver.__dict__['_scene_login_snapshot'][1]['form'])

    def run_login(self, current):
        driver = Mock()
        fields = [Mock(), Mock(), Mock()]
        for field, value in zip(fields, ('test-manager', 'test-password', 'test-captcha')):
            state = {'value': current if field is fields[0] else ''}
            field.get_attribute.side_effect = lambda key, state=state: state['value']
            field.clear.side_effect = lambda state=state: state.update(value='')
            field.send_keys.side_effect = lambda text, state=state: state.update(value=state['value'] + text)
        with patch.object(runtime, 'manager_login_fields', return_value=fields), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'wait_control', return_value=Mock()), \
             patch.object(runtime, 'scene_navigation', return_value=dict(ready=True)):
            runtime.login_manager(driver, 1, 'test-manager', 'test-password', 'test-captcha')
        return fields

    def test_matching_manager_id_is_also_cleared_and_reentered(self):
        fields = self.run_login('test-manager')
        fields[0].clear.assert_called_once()
        fields[0].send_keys.assert_called_once_with('test-manager')
        fields[1].send_keys.assert_called_once_with('test-password')
        fields[2].send_keys.assert_called_once_with('test-captcha')

    def test_wrong_manager_id_is_replaced(self):
        fields = self.run_login('other-manager')
        fields[0].clear.assert_called_once()
        fields[0].send_keys.assert_called_once_with('test-manager')

    def test_manual_default_does_not_reuse_manager_id(self):
        fields = self.run_login('test-manager')
        self.assertTrue(fields[0].get_attribute.called)
        fields[0].clear.assert_called_once()
        fields[0].send_keys.assert_called_once_with('test-manager')


if __name__ == '__main__':
    unittest.main()
