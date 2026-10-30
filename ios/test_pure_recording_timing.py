"""纯录制性能设置及搜索定位的回归测试。"""
import ast
from pathlib import Path
import time
import unittest
from unittest.mock import Mock

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.by import By


class PureRecordingTimingTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).with_name('test_pure_recording_ios.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('run_test_cycle', 'run_self_service_cycle', 'input_text')]
        self.scope = dict(time=time, AppiumBy=AppiumBy, By=By, screenshot=Mock())
        for cycle in nodes:
            for node in ast.walk(cycle):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith('step'):
                    self.scope[node.func.id] = Mock()
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<timing>', 'exec'), self.scope)
        self.driver = Mock()
        self.driver.get_settings.return_value = {'waitForIdleTimeout': 7}

    def test_pure_cycle_restores_idle_setting_after_success(self):
        self.assertTrue(self.scope['run_test_cycle'](self.driver, 1))
        self.assertEqual([c.args[0] for c in self.driver.update_settings.call_args_list],
                         [{'waitForIdleTimeout': 0}, {'waitForIdleTimeout': 7}])
        self.scope['step3_click_record_in_list'].assert_called_once_with(self.driver, 1, fast_search=True, dom_search=True)
        self.scope['step1_login'].assert_called_once_with(self.driver, 1, fast_input=True, direct_input=True)

    def test_pure_cycle_restores_idle_setting_after_failure(self):
        self.scope['step3_click_record_in_list'].side_effect = RuntimeError('搜索失败')
        with self.assertRaisesRegex(RuntimeError, '搜索失败'):
            self.scope['run_test_cycle'](self.driver, 1)
        self.assertEqual(self.driver.update_settings.call_args.args[0], {'waitForIdleTimeout': 7})
        self.scope['step6_click_start_live'].assert_not_called()

    def test_input_predicate_uses_native_locator_instead_of_xpath(self):
        self.assertTrue(self.scope['input_text'](self.driver, [('predicate', 'field predicate')], 'test'))
        self.driver.find_element.assert_called_once_with(AppiumBy.IOS_PREDICATE, 'field predicate')
        self.driver.find_element.return_value.set_value.assert_called_once_with('test')

    def test_direct_input_skips_click_and_removed_set_value(self):
        self.assertTrue(self.scope['input_text'](self.driver, [('predicate', 'field')], 'test', direct=True))
        element = self.driver.find_element.return_value
        element.clear.assert_called_once_with()
        element.send_keys.assert_called_once_with('test')
        element.click.assert_not_called()
        element.set_value.assert_not_called()

    def test_direct_password_input_does_not_clear_when_not_requested(self):
        self.assertTrue(self.scope['input_text'](self.driver, [('predicate', 'field')], 'test',
                                                direct=True, clear_first=False))
        self.driver.find_element.return_value.clear.assert_not_called()

    def test_self_cycle_uses_fast_inputs_and_restores_settings(self):
        self.assertTrue(self.scope['run_self_service_cycle'](self.driver, 1))
        self.scope['step1_login'].assert_called_once_with(self.driver, 1, fast_input=True)
        self.scope['step3_click_record_in_list'].assert_called_once_with(self.driver, 1, fast_search=True)
        self.scope['step6_click_start_live'].assert_called_once_with(self.driver, 1)
        self.assertEqual([c.args[0] for c in self.driver.update_settings.call_args_list],
                         [{'waitForIdleTimeout': 0}, {'waitForIdleTimeout': 7}])

    def test_self_cycle_restores_settings_after_failure(self):
        self.scope['step8_self_service_detection'].side_effect = RuntimeError('签字失败')
        with self.assertRaisesRegex(RuntimeError, '签字失败'):
            self.scope['run_self_service_cycle'](self.driver, 1)
        self.assertEqual(self.driver.update_settings.call_args.args[0], {'waitForIdleTimeout': 7})


if __name__ == '__main__':
    unittest.main()
