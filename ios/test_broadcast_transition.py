import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from types import SimpleNamespace


class BroadcastTransitionTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).with_name('test_pure_recording_ios.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('step6_click_start_live', 'start_live_in_active_app',
                                'click_pure_recording_broadcast', 'step7_wait_countdown_and_agree')]
        clock = Mock()
        clock.monotonic.side_effect = range(500)
        self.scope = dict(time=clock, screenshot=Mock(), wait_countdown=Mock(),
                          AppiumBy=SimpleNamespace(IOS_PREDICATE='predicate'),
                          visible_ios_text=Mock(return_value=None), tap_ios_text=Mock(return_value=False),
                          webview_click=Mock(return_value=False), COUNTDOWN_SECONDS=3,
                          AGREE_CHECK_TIMEOUT=15, AUTO_ACCEPT_ALERTS=True,
                          TEXT_AGREE_CHECK='同意检测', TEXT_SKIP='跳过',
                          TEXT_RECHECK='重新检测', TEXT_START_LIVE='开始直播',
                          TEXT_IMMEDIATELY_START='立即开始', TEXT_AGREE_AND_START='同意并开始录制',
                          TEXT_AGREE_AND_START_DUAL='同意并开始双录')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<transition>', 'exec'), self.scope)
        self.driver = Mock()
        self.driver.page_source = '环境检测中'
        self.driver.get_settings.return_value = {}
        self.driver.get_window_size.return_value = {'width': 736, 'height': 414}
        self.driver.execute_script.return_value = {'bundleId': 'com.juphoon.record.ios'}

    def test_missing_broadcast_does_not_report_success(self):
        with self.assertRaisesRegex(Exception, '直播未启动'):
            self.scope['step6_click_start_live'](self.driver, 1)
        self.driver.tap.assert_not_called()
        self.assertEqual(self.driver.update_settings.call_args.args[0]['waitForIdleTimeout'], 10)

    def test_system_popup_detection_uses_landscape_center(self):
        self.scope['visible_ios_text'].return_value = object()
        self.assertTrue(self.scope['step6_click_start_live'](self.driver, 1))
        settings = self.driver.update_settings.call_args_list[0].args[0]
        self.assertEqual(settings['activeAppDetectionPoint'], '368.00,207.00')
        self.assertEqual(settings['defaultActiveApplication'], 'auto')
        self.assertEqual(settings['waitForIdleTimeout'], 0)
        self.assertTrue(settings['respectSystemAlerts'])
        self.assertFalse(settings['autoAcceptAlerts'])

    def test_system_settings_are_restored_on_failure_without_underlying_clicks(self):
        previous = dict(respectSystemAlerts=False, autoAcceptAlerts=True,
                        defaultActiveApplication='com.juphoon.record.ios',
                        waitForIdleTimeout=3, activeAppDetectionPoint='10.00,20.00')
        self.driver.get_settings.return_value = previous
        with self.assertRaisesRegex(Exception, '直播未启动'):
            self.scope['step6_click_start_live'](self.driver, 1)
        self.assertEqual(self.driver.update_settings.call_args.args[0], previous)
        labels = [call.args[1] for call in self.scope['tap_ios_text'].call_args_list]
        self.assertNotIn('同意并开始双录', labels)
        self.assertNotIn('同意并开始录制', labels)

    def test_broadcast_countdown_is_observed_without_stopping(self):
        self.scope['visible_ios_text'].side_effect = lambda d, t: object() if t == '停止直播' else None
        self.assertTrue(self.scope['step6_click_start_live'](self.driver, 1))
        self.scope['tap_ios_text'].assert_called_once_with(self.driver, '开始直播')

    def test_start_live_is_clicked_before_status_queries_or_screenshots(self):
        events = []
        def tap(driver, text):
            events.append(('tap', text))
            return True
        def visible(driver, text):
            events.append(('status', text))
            return object() if text == '停止直播' else None
        self.scope['tap_ios_text'].side_effect = tap
        self.scope['visible_ios_text'].side_effect = visible
        self.assertTrue(self.scope['step6_click_start_live'](self.driver, 1))
        self.assertEqual(events[0], ('tap', '开始直播'))
        self.scope['screenshot'].assert_not_called()
        self.scope['time'].sleep.assert_not_called()

    def test_detection_waits_for_overlay_then_clicks(self):
        self.scope['visible_ios_text'].side_effect = [object(), None]
        self.scope['tap_ios_text'].return_value = True
        self.assertTrue(self.scope['step7_wait_countdown_and_agree'](self.driver, 1))
        self.scope['tap_ios_text'].assert_called_once_with(self.driver, '同意检测')

    def test_pure_recording_uses_native_element_click_without_coordinate_tap(self):
        button = Mock()
        button.get_attribute.side_effect = lambda key: '开始\n直播' if key == 'label' else None
        self.driver.find_elements.return_value = [button]
        self.scope['visible_ios_text'].side_effect = lambda d, t: object() if t == '停止直播' else None
        self.assertTrue(self.scope['step6_click_start_live'](self.driver, 1, pure_recording=True))
        button.click.assert_called_once_with()
        self.driver.tap.assert_not_called()
        self.scope['tap_ios_text'].assert_not_called()
        self.scope['screenshot'].assert_not_called()

    def test_pure_recording_rejects_underlying_business_button(self):
        button = Mock()
        button.get_attribute.return_value = '同意并开始直播'
        self.driver.find_elements.return_value = [button]
        self.assertFalse(self.scope['click_pure_recording_broadcast'](self.driver, '开始直播'))
        button.click.assert_not_called()

    def test_pure_recording_ignores_hidden_or_disabled_buttons(self):
        hidden, disabled = Mock(), Mock()
        for button in (hidden, disabled):
            button.get_attribute.return_value = '开始直播'
        hidden.is_displayed.return_value = False
        disabled.is_enabled.return_value = False
        self.driver.find_elements.return_value = [hidden, disabled]
        self.assertFalse(self.scope['click_pure_recording_broadcast'](self.driver, '开始直播'))
        hidden.click.assert_not_called()
        disabled.click.assert_not_called()

    def test_only_pure_recording_cycle_selects_special_click(self):
        tree = ast.parse(Path(__file__).with_name('test_pure_recording_ios.py').read_text(encoding='utf-8'))
        for function_name, expected in [('run_test_cycle', True), ('run_self_service_cycle', False)]:
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function_name)
            calls = [n for n in ast.walk(function) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == 'step6_click_start_live']
            self.assertEqual(len(calls), 1)
            options = {kw.arg: ast.literal_eval(kw.value) for kw in calls[0].keywords}
            self.assertEqual(options.get('pure_recording', False), expected)

    def test_ineffective_detection_click_fails(self):
        self.driver.page_source = '同意检测'
        self.scope['tap_ios_text'].return_value = True
        with self.assertRaisesRegex(Exception, '点击后未进入'):
            self.scope['step7_wait_countdown_and_agree'](self.driver, 1)


if __name__ == '__main__':
    unittest.main()
