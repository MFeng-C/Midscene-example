import unittest
from unittest.mock import Mock, patch
import scene_broadcast_runtime as broadcast
from selenium.common.exceptions import NoAlertPresentException


class BroadcastRuntimeTest(unittest.TestCase):
    def test_stopped_alert_fast_path_verifies_close_without_page_query(self):
        driver = Mock()
        type(driver.switch_to.alert).text = property(Mock(side_effect=[
            '直播屏幕 JRecordShare的直播已停止，因为无效的直播会话',
            NoAlertPresentException()]))
        broadcast.clear_broadcast(driver)
        driver.execute_script.assert_called_once_with(
            'mobile: alert', {'action': 'accept', 'buttonLabel': '好'})
        driver.find_elements.assert_not_called()

    def test_unrelated_alert_is_not_accepted(self):
        driver = Mock()
        driver.switch_to.alert.text = '是否允许访问相机'
        self.assertFalse(broadcast.dismiss_stopped_broadcast_alert(driver))
        driver.execute_script.assert_not_called()

    def test_stopped_alert_that_remains_is_failure(self):
        driver = Mock()
        driver.switch_to.alert.text = '直播屏幕 JRecordShare的直播已停止'
        with self.assertRaisesRegex(RuntimeError, '未关闭'):
            broadcast.dismiss_stopped_broadcast_alert(driver, timeout=0)

    def test_no_system_broadcast_does_not_read_whole_page(self):
        driver = Mock()
        driver.find_elements.return_value = []
        with patch.object(broadcast, 'native_state') as snapshot:
            broadcast.clear_broadcast(driver)
        snapshot.assert_not_called()
    def test_invalid_session_fails_before_detection_click(self):
        with patch.object(broadcast, 'native_state', return_value='JRecordShare的直播已停止，因为：尝试开始无效的直播会话'):
            with self.assertRaisesRegex(RuntimeError, '无效的直播会话'):
                broadcast.wait_detection_ready(Mock())

    def test_stop_button_is_not_initialization_success(self):
        with patch.object(broadcast, 'native_state', side_effect=['停止直播', '同意检测']), \
             patch.object(broadcast.time, 'sleep') as sleep:
            self.assertTrue(broadcast.wait_detection_ready(Mock()))
        sleep.assert_called_once()

    def test_stopped_error_is_dismissed_before_new_session(self):
        driver = Mock()
        with patch.object(broadcast, 'native_state', side_effect=['直播已停止 无效的直播会话', '登录']), \
             patch.object(broadcast, 'click_native', return_value=True) as click:
            broadcast.clear_broadcast(driver)
        click.assert_called_once_with(driver, '好')

    def test_active_broadcast_must_be_confirmed_stopped(self):
        driver = Mock()
        with patch.object(broadcast, 'native_state', side_effect=['停止直播', '登录']), \
             patch.object(broadcast, 'click_native', return_value=True) as click:
            broadcast.clear_broadcast(driver)
        click.assert_called_once_with(driver, '停止直播')


if __name__ == '__main__':
    unittest.main()
