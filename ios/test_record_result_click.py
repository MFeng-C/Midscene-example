"""离线回归：录制按钮与纯录制导航不能混淆。"""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from appium.webdriver.common.appiumby import AppiumBy


class RecordClickTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).with_name('test_pure_recording_ios.py').read_text(encoding='utf-8'))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in ('record_confirmation_visible', 'click_record_result')]
        self.clock = Mock()
        self.clock.monotonic.side_effect = range(1000)
        self.namespace = {'AppiumBy': AppiumBy, 'time': self.clock, 'webview_click': Mock(return_value=False)}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<record-click>', 'exec'), self.namespace)
        self.driver = Mock()
        self.record = Mock()
        self.record.rect = {'x': 100, 'y': 200, 'width': 80, 'height': 40}
        self.confirmed = False

        def find(by, predicate):
            if "name == '确认'" in predicate:
                return [Mock()] if self.confirmed else []
            self.assertNotIn('CONTAINS', predicate)
            self.assertIn("name == '录制'", predicate)
            return [self.record]
        self.driver.find_elements.side_effect = find

    def test_exact_click_requires_confirmation(self):
        self.record.click.side_effect = lambda: setattr(self, 'confirmed', True)
        self.assertTrue(self.namespace['click_record_result'](self.driver))
        self.record.click.assert_called_once()
        self.driver.tap.assert_not_called()

    def test_ineffective_click_retries_at_button_center(self):
        self.driver.tap.side_effect = lambda points: setattr(self, 'confirmed', True)
        self.assertTrue(self.namespace['click_record_result'](self.driver))
        self.driver.tap.assert_called_once_with([(140, 220)])

    def test_no_confirmation_is_failure(self):
        self.assertFalse(self.namespace['click_record_result'](self.driver))


if __name__ == '__main__':
    unittest.main()
