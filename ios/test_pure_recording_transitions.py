import unittest
from unittest.mock import Mock, patch

import pure_recording_transitions as flow


def state(**updates):
    result = dict(clicked=False, skip=False, risk=False, start=False, recording=False,
                  uploadSuccess=False, uploadConfirm=False, end=False, complete=False,
                  list=False, text='test page')
    result.update(updates)
    return result


class PureTransitionsTest(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.driver.contexts = ['NATIVE_APP', 'WEBVIEW_1']
        self.shot = Mock()
        self.now = 0

    def run_flow(self, function, states):
        responses = iter(states)
        last = states[-1]
        self.driver.execute_script.side_effect = lambda *args: next(responses, last)
        def sleep(seconds):
            self.now += seconds
        with patch.object(flow.time, 'monotonic', side_effect=lambda: self.now), \
                patch.object(flow.time, 'sleep', side_effect=sleep):
            return function(self.driver, 1, self.shot, timeout=1)

    def actions(self):
        return [c.args[1] for c in self.driver.execute_script.call_args_list]

    def test_upload_timeout_never_clicks_confirmation(self):
        with self.assertRaisesRegex(RuntimeError, '文件上传超时'):
            self.run_flow(flow.wait_upload, [state(end=True)])
        self.assertNotIn('上传确认', self.actions())
        self.shot.assert_called_once()
        self.driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_upload_confirmation_and_following_page_required(self):
        self.assertTrue(self.run_flow(flow.wait_upload, [
            state(uploadSuccess=True, uploadConfirm=True),
            state(clicked=True, uploadSuccess=True, uploadConfirm=True),
            state(complete=True)]))
        self.assertEqual(self.actions(), [None, '上传确认', None])

    def test_upload_confirmation_stuck_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, '弹窗关闭'):
            self.run_flow(flow.wait_upload, [
                state(uploadSuccess=True, uploadConfirm=True),
                state(clicked=True, uploadSuccess=True, uploadConfirm=True),
                state(uploadSuccess=True, uploadConfirm=True)])
        self.assertEqual(self.actions().count('上传确认'), 1)

    def test_success_page_without_modal_is_accepted_with_explicit_success(self):
        self.assertTrue(self.run_flow(flow.wait_upload, [state(uploadSuccess=True, end=True)]))

    def test_return_click_without_order_list_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, '返回订单列表超时'):
            self.run_flow(flow.return_to_order_list, [state(complete=True), state(clicked=True), state()])
        self.assertEqual(self.actions().count('返回'), 1)

    def test_return_waits_for_order_list(self):
        self.assertTrue(self.run_flow(flow.return_to_order_list, [
            state(complete=True), state(clicked=True, complete=True), state(), state(list=True)]))
        self.assertEqual(self.actions(), [None, '返回', None, None])

    def test_detection_pass_must_transition_to_recording(self):
        self.assertTrue(self.run_flow(flow.detect_and_start, [
            state(start=True), state(clicked=True, start=True), state(recording=True)]))
        self.assertEqual(self.actions(), [None, '开始录制', None])

    def test_detection_failed_skip_risk_start_recording(self):
        self.assertTrue(self.run_flow(flow.detect_and_start, [
            state(skip=True), state(clicked=True, skip=True), state(risk=True),
            state(clicked=True, risk=True), state(start=True),
            state(clicked=True, start=True), state(recording=True)]))
        self.assertEqual([a for a in self.actions() if a], ['跳过', '风险确认', '开始录制'])

    def test_risk_confirmation_not_effective_cannot_proceed(self):
        with self.assertRaisesRegex(RuntimeError, '等待开始录制'):
            self.run_flow(flow.detect_and_start, [
                state(skip=True), state(clicked=True, risk=True),
                state(clicked=True, risk=True), state(risk=True, start=True)])
        self.assertNotIn('开始录制', self.actions())

    def test_no_detection_result_is_not_assumed_passed(self):
        with self.assertRaisesRegex(RuntimeError, '等待检测结果'):
            self.run_flow(flow.detect_and_start, [state()])
        self.assertNotIn('开始录制', self.actions())

    def test_start_click_without_recording_toolbar_fails(self):
        with self.assertRaisesRegex(RuntimeError, '等待录制工具栏'):
            self.run_flow(flow.detect_and_start, [state(start=True), state(clicked=True), state()])
        self.assertEqual(self.actions().count('开始录制'), 1)


if __name__ == '__main__':
    unittest.main()
