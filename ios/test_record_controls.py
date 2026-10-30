"""录制工具栏定位的离线回归。"""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.by import By


class RecordControlsTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).with_name('test_pure_recording_ios.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'click_record_control')
        clock = Mock()
        clock.monotonic.side_effect = range(100)
        self.webview = Mock(return_value=False)
        self.fast_click = Mock(return_value=False)
        scope = dict(time=clock, AppiumBy=AppiumBy, By=By, switch_to_webview=self.webview,
                     click_pure_toolbar=self.fast_click)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<controls>', 'exec'), scope)
        self.click = scope['click_record_control']
        self.driver = Mock()
        self.driver.get_window_size.return_value = {'width': 736, 'height': 414}
        self.element = Mock()
        self.element.rect = dict(x=510, y=5, width=50, height=24)
        self.driver.find_elements.return_value = [self.element]

    def test_static_text_uses_landscape_center(self):
        self.assertTrue(self.click(self.driver, '暂停', toolbar=True))
        predicate = self.driver.find_elements.call_args.args[1]
        self.assertNotIn('XCUIElementTypeButton', predicate)
        self.assertIn("label == '暂停'", predicate)
        self.driver.tap.assert_called_once_with([(535, 17)])

    def test_disabled_and_non_toolbar_nodes_are_not_clicked(self):
        self.element.is_enabled.return_value = False
        self.assertFalse(self.click(self.driver, '暂停', timeout=2, toolbar=True))
        self.driver.tap.assert_not_called()

    def test_bottom_text_is_not_toolbar(self):
        self.element.rect['y'] = 350
        self.assertFalse(self.click(self.driver, '截图', timeout=2, toolbar=True))
        self.driver.tap.assert_not_called()

    def test_webview_click_restores_native_context(self):
        self.driver.find_elements.side_effect = [[], [self.element]]
        self.webview.return_value = True
        self.driver.execute_script.return_value = True
        self.assertTrue(self.click(self.driver, '截图', toolbar=True))
        self.element.click.assert_called_once()
        self.driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_fast_toolbar_avoids_native_discovery_when_successful(self):
        self.fast_click.return_value = True
        self.assertTrue(self.click(self.driver, '截图', toolbar=True, web_first=True))
        self.driver.find_elements.assert_not_called()
        self.driver.tap.assert_not_called()

    def test_fast_toolbar_failure_preserves_native_fallback(self):
        self.assertTrue(self.click(self.driver, '暂停', toolbar=True, web_first=True))
        self.fast_click.assert_called_once_with(self.driver, '暂停', self.webview)
        self.driver.tap.assert_called_once_with([(535, 17)])


if __name__ == '__main__':
    unittest.main()
