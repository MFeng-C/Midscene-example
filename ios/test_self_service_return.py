import unittest
from unittest.mock import Mock, patch

import self_service_return as navigation


def state(clicked=None, complete=False, myReady=False):
    return dict(clicked=clicked, complete=complete, myReady=myReady)


class ReturnNavigationTest(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.driver.contexts = ['NATIVE_APP', 'WEBVIEW_1']
        self.shot = Mock()
        self.now = 0

    def sleep(self, seconds):
        self.now += seconds

    def run_navigation(self, timeout=1):
        with patch.object(navigation.time, 'monotonic', side_effect=lambda: self.now), \
                patch.object(navigation.time, 'sleep', side_effect=self.sleep):
            return navigation.return_and_open_my(self.driver, 1, self.shot, timeout)

    def test_return_wait_for_list_then_my_and_verify(self):
        self.driver.execute_script.side_effect = [
            state('返回', complete=True), state(), state('我的'), state(myReady=True)]
        self.assertTrue(self.run_navigation())
        self.assertEqual([c.args[1:] for c in self.driver.execute_script.call_args_list],
                         [(False, False), (True, False), (True, False), (True, True)])
        self.shot.assert_not_called()
        self.driver.find_elements.assert_not_called()
        self.driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_clicking_my_without_profile_confirmation_cannot_pass(self):
        self.driver.execute_script.side_effect = [state('我的')] + [state()] * 20
        with self.assertRaisesRegex(RuntimeError, '进入我的页面超时'):
            self.run_navigation()
        self.shot.assert_called_once()

    def test_already_on_profile_does_not_require_more_clicks(self):
        self.driver.execute_script.return_value = state(myReady=True)
        self.assertTrue(self.run_navigation())
        self.assertEqual(self.driver.execute_script.call_count, 1)

    def test_missing_webview_fails_and_restores_native(self):
        self.driver.contexts = ['NATIVE_APP']
        with self.assertRaisesRegex(RuntimeError, 'WebView'):
            self.run_navigation()
        self.driver.execute_script.assert_not_called()
        self.driver.switch_to.context.assert_called_with('NATIVE_APP')


if __name__ == '__main__':
    unittest.main()
