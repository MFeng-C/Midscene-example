import unittest
from unittest.mock import Mock, patch

import ios_session_recovery as recovery


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.driver.query_app_state.return_value = 1
        self.driver.get_settings.return_value = {'waitForIdleTimeout': 5}
        self.driver.contexts = ['NATIVE_APP', 'WEBVIEW_1']
        self.shot = Mock()

    def test_kill_before_launch_then_verify_logged_out(self):
        events = []
        self.driver.terminate_app.side_effect = lambda b: events.append('kill')
        self.driver.query_app_state.side_effect = lambda b: events.append('verify') or 1
        self.driver.activate_app.side_effect = lambda b: events.append('launch')
        self.driver.execute_script.return_value = dict(loggedOut=True, my=False, logout=False)
        with patch.object(recovery, 'logout_customer_ios') as logout:
            self.assertTrue(recovery.prepare_login(self.driver, 1, 'app', self.shot))
        self.assertEqual(events, ['kill', 'verify', 'launch'])
        logout.assert_not_called()
        self.assertEqual(self.driver.update_settings.call_args.args[0], {'waitForIdleTimeout': 5})

    def test_logged_in_must_logout_instead_of_reusing_account(self):
        self.driver.execute_script.return_value = dict(loggedOut=False, my=True, logout=False)
        with patch.object(recovery, 'logout_customer_ios') as logout:
            self.assertTrue(recovery.prepare_login(self.driver, 2, 'app', self.shot))
        logout.assert_called_once_with(self.driver, 2, self.shot)

    def test_failed_termination_never_launches(self):
        self.driver.query_app_state.return_value = 4
        with self.assertRaisesRegex(RuntimeError, '进程未结束'):
            recovery.prepare_login(self.driver, 1, 'app', self.shot)
        self.driver.activate_app.assert_not_called()

    def test_logout_failure_is_not_ignored(self):
        self.driver.execute_script.return_value = dict(loggedOut=False, my=True, logout=False)
        with patch.object(recovery, 'logout_customer_ios', side_effect=RuntimeError('logout failed')):
            with self.assertRaisesRegex(RuntimeError, 'logout failed'):
                recovery.prepare_login(self.driver, 2, 'app', self.shot)
        self.shot.assert_called_once()

    def test_deep_page_returns_to_list_before_logout(self):
        states = iter([dict(loggedOut=False, my=False, logout=False),
                       dict(loggedOut=False, my=True, logout=False)])
        self.driver.execute_script.side_effect = lambda script, arg: (
            next(states) if script == recovery.LOGOUT_SCRIPT else '')
        with patch.object(recovery, 'logout_customer_ios') as logout, \
                patch.object(recovery.time, 'sleep'):
            self.assertTrue(recovery.prepare_login(self.driver, 2, 'app', self.shot))
        self.driver.back.assert_called_once()
        logout.assert_called_once()


if __name__ == '__main__':
    unittest.main()
