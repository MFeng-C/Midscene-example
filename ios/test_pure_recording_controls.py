import unittest
from unittest.mock import Mock, patch

import pure_recording_controls as controls


def state(paused=True, recording=False, clicked=False):
    return dict(paused=paused, recording=recording, clicked=clicked)


class ResumeRecordingTest(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.webview = Mock(return_value=True)
        self.now = 0

    def sleep(self, seconds):
        self.now += seconds

    def run_resume(self, timeout=3):
        with patch.object(controls.time, 'monotonic', side_effect=lambda: self.now), \
                patch.object(controls.time, 'sleep', side_effect=self.sleep):
            return controls.ensure_pure_recording_resumed(self.driver, 1, self.webview, timeout)

    def test_click_requires_later_recording_confirmation(self):
        self.driver.execute_script.side_effect = [state(clicked=True), state(),
                                                  state(paused=False, recording=True)]
        self.assertTrue(self.run_resume())
        self.assertEqual(self.driver.execute_script.call_count, 3)
        self.driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_click_that_does_not_dismiss_popup_fails_and_retries_are_bounded(self):
        def execute(script, click):
            return state(clicked=click)
        self.driver.execute_script.side_effect = execute
        with self.assertRaisesRegex(RuntimeError, '未确认暂停弹窗关闭'):
            self.run_resume(timeout=5)
        self.assertEqual(sum(call.args[1] for call in self.driver.execute_script.call_args_list), 3)

    def test_no_popup_without_recording_toolbar_is_not_success(self):
        self.driver.execute_script.return_value = state(paused=False)
        with self.assertRaisesRegex(RuntimeError, '录制恢复'):
            self.run_resume()

    def test_already_recording_succeeds_without_retry(self):
        self.driver.execute_script.return_value = state(paused=False, recording=True)
        self.assertTrue(self.run_resume())
        self.assertEqual(self.driver.execute_script.call_count, 1)

    def test_missing_webview_fails_and_restores_native(self):
        self.webview.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'WebView'):
            self.run_resume()
        self.driver.execute_script.assert_not_called()
        self.driver.switch_to.context.assert_called_with('NATIVE_APP')


if __name__ == '__main__':
    unittest.main()
