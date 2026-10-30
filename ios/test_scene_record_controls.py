import unittest
from unittest.mock import Mock, patch, call
import scene_record_controls as controls


def state(paused=False, recording=True, clicked=False):
    return dict(paused=paused, recording=recording, clicked=clicked)


class SceneControlsTest(unittest.TestCase):
    @patch.object(controls.time, 'sleep')
    def test_pause_wait_three_seconds_resume_then_screenshot(self, sleep):
        driver = Mock()
        events = []
        states = iter([state(), state(True, False), state(True, False, True), state(), state()])
        def execute(script, click):
            events.append(('read', click))
            return next(states)
        driver.execute_script.side_effect = execute
        click = Mock(side_effect=lambda d, label, **kw: events.append(('click', label)) or True)
        sleep.side_effect = lambda seconds: events.append(('sleep', seconds))
        self.assertTrue(controls.exercise_scene_controls(driver, 1, click, Mock(return_value=True)))
        self.assertEqual(click.call_args_list, [call(driver, '暂停', toolbar=True, web_first=True),
                                               call(driver, '截图', toolbar=True, web_first=True)])
        self.assertLess(events.index(('sleep', 3)), events.index(('read', True)))
        self.assertLess(events.index(('read', True)), events.index(('click', '截图')))
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    @patch.object(controls.time, 'sleep')
    def test_unconfirmed_pause_fails_without_screenshot(self, sleep):
        driver = Mock()
        driver.execute_script.return_value = state()
        click = Mock(return_value=True)
        with patch.object(controls.time, 'monotonic', side_effect=range(1000)):
            with self.assertRaisesRegex(RuntimeError, '未出现暂停弹窗'):
                controls.exercise_scene_controls(driver, 1, click, Mock(return_value=True), timeout=3)
        self.assertEqual(click.call_count, 1)

    @patch.object(controls.time, 'sleep')
    def test_resume_timeout_cannot_proceed_to_screenshot(self, sleep):
        driver = Mock()
        driver.execute_script.side_effect = [state()] + [state(True, False, True)] * 50
        click = Mock(return_value=True)
        with patch.object(controls.time, 'monotonic', side_effect=range(1000)):
            with self.assertRaisesRegex(RuntimeError, '未恢复录制'):
                controls.exercise_scene_controls(driver, 1, click, Mock(return_value=True), timeout=3)
        self.assertEqual(click.call_count, 1)

    def test_missing_webview_fails_and_restores_native(self):
        driver = Mock()
        with self.assertRaisesRegex(RuntimeError, '未找到业务 WebView'):
            controls.exercise_scene_controls(driver, 1, Mock(), Mock(return_value=False))
        driver.switch_to.context.assert_called_with('NATIVE_APP')


if __name__ == '__main__':
    unittest.main()
