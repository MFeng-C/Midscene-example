import unittest
from unittest.mock import Mock, patch

import scene_ai_recovery as recovery
import test_manager_pure_recording_ios as manager
import scene_manual_nodes as nodes


class AIRecoveryTest(unittest.TestCase):
    def test_client_requests_are_bounded_and_not_retried(self):
        config = recovery.ai_client_config('http://localhost:4723')
        self.assertEqual(config.timeout, 40)
        self.assertEqual(config.init_args_for_pool_manager['init_args_for_pool_manager']['retries'], 0)

    def test_failed_termination_still_releases_session(self):
        driver = Mock()
        driver.terminate_app.side_effect = TimeoutError()
        recovery.end_failed_ai_cycle(driver, 'test.bundle')
        self.assertEqual(driver.command_executor._client_config.timeout, 3)
        driver.quit.assert_called_once()

    def test_failed_sixth_cycle_ends_and_seventh_starts_in_new_session(self):
        drivers = [Mock() for _ in range(7)]
        for driver in drivers:
            driver.get_settings.return_value = {}
        calls = []

        def cycle(driver, number, **kwargs):
            calls.append(number)
            if number == 6:
                raise TimeoutError('signature transition stalled')

        with patch.object(manager.sys, 'argv', ['script', 'scene_ai', '7']), \
             patch.object(manager, 'reset_scene_order'), \
             patch.object(manager.webdriver, 'Remote', side_effect=drivers) as remote, \
             patch.object(manager, 'run_scene_record_cycle', side_effect=cycle), \
             patch.object(manager, 'capture_failure'), \
             patch.object(manager, 'cleanup_session') as cleanup, \
             patch.object(manager.time, 'sleep'):
            with self.assertRaises(SystemExit) as result:
                manager.main()
        self.assertEqual(result.exception.code, 1)  # 仍如实报告有失败轮。
        self.assertEqual(calls, list(range(1, 8)))
        self.assertEqual(remote.call_count, 7)
        self.assertEqual(cleanup.call_count, 6)
        drivers[5].terminate_app.assert_called_once_with(manager.BUNDLE_ID)
        drivers[5].quit.assert_called_once()
        self.assertEqual(drivers[5].command_executor._client_config.timeout, 3)
        self.assertEqual(remote.call_args.kwargs['client_config'].timeout, 40)
        self.assertEqual(remote.call_args.kwargs['options'].get_capability('wdaConnectionTimeout'), 30000)

    def test_post_signature_does_not_get_another_300_second_budget(self):
        driver = Mock()
        reader = Mock(side_effect=[dict(signature=True)] + [
            dict(signature=False, review=False, finish=False, next=False, progress=(4, 4))] * 100)
        handler = Mock(return_value=dict(progress=(4, 4), clicked=True))
        clock = [0]

        def now():
            clock[0] += 1
            return clock[0]

        with patch.object(nodes.time, 'monotonic', side_effect=now), \
             patch.object(nodes.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, '进度未变化|节点推进超时'):
                nodes.advance_manual_nodes(driver, 1, timeout=300, transition_timeout=60,
                    batch=True, snapshot_reader=reader, signature_handler=handler,
                    post_signature_timeout=30)
        self.assertLess(clock[0], 50)


if __name__ == '__main__':
    unittest.main()
