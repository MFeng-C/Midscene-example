import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import ios_phase_timing as timing


class PhaseTimingTest(unittest.TestCase):
    def test_result_and_secret_arguments_are_preserved_without_logging(self):
        action = Mock(return_value='private-result')
        output = io.StringIO()
        with redirect_stdout(output), patch.object(timing, 'perf_counter', side_effect=[10, 10.125]):
            result = timing.timed_call('登录/密码/send_keys请求', action, 'private-password')
        self.assertEqual(result, 'private-result')
        action.assert_called_once_with('private-password')
        self.assertIn('0.125s', output.getvalue())
        self.assertNotIn('private-password', output.getvalue())
        self.assertNotIn('private-result', output.getvalue())

    def test_exception_is_rethrown_and_failure_duration_is_logged(self):
        error = RuntimeError('private-error-content')
        output = io.StringIO()
        with redirect_stdout(output), patch.object(timing, 'perf_counter', side_effect=[5, 7]):
            with self.assertRaises(RuntimeError) as caught:
                timing.timed_call('OCR/跳过点击请求', Mock(side_effect=error))
        self.assertIs(caught.exception, error)
        self.assertIn('2.000s（失败）', output.getvalue())
        self.assertNotIn('private-error-content', output.getvalue())

    def test_flow_decorator_preserves_function_name(self):
        @timing.timed_flow('阶段总计')
        def step(value):
            return value
        with redirect_stdout(io.StringIO()):
            self.assertEqual(step(42), 42)
        self.assertEqual(step.__name__, 'step')


if __name__ == '__main__':
    unittest.main()
