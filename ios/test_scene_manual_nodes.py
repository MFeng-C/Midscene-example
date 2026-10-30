import unittest
from unittest.mock import Mock, patch

import scene_manual_nodes as nodes


class ManualNodesTest(unittest.TestCase):
    def setUp(self):
        self.signature_patch = patch.object(nodes, 'signature_visible', return_value=False)
        self.signature_patch.start()
        self.addCleanup(self.signature_patch.stop)

    @patch.object(nodes.time, 'sleep')
    def test_all_six_nodes_and_delayed_progress_without_duplicate_click(self, sleep):
        driver = Mock()
        button = Mock()
        progress = [1, 1, 2, 3, 4, 5, 6]
        with patch.object(nodes, 'read_state', side_effect=[(n, 6) for n in progress]), \
             patch.object(nodes, 'visible_control') as control:
            finish_checks = iter([None] * 7 + [button])
            control.side_effect = lambda d, label: next(finish_checks) if label == '完成录制' else button
            self.assertTrue(nodes.advance_manual_nodes(driver, 1))
        self.assertEqual(button.click.call_count, 6)

    @patch.object(nodes.time, 'sleep')
    def test_stuck_progress_fails_without_repeated_click(self, sleep):
        button = Mock()
        with patch.object(nodes.time, 'monotonic', side_effect=range(1000)), \
             patch.object(nodes, 'read_state', return_value=(2, 6)), \
             patch.object(nodes, 'visible_control', side_effect=lambda d, label: button if label == '下一步' else None):
            with self.assertRaisesRegex(RuntimeError, '进度未变化'):
                nodes.advance_manual_nodes(Mock(), 1, transition_timeout=5)
        button.click.assert_called_once()

    @patch.object(nodes.time, 'sleep')
    def test_missing_progress_does_not_blindly_click(self, sleep):
        button = Mock()
        with patch.object(nodes.time, 'monotonic', side_effect=range(1000)), \
             patch.object(nodes, 'read_state', return_value=None), \
             patch.object(nodes, 'visible_control', side_effect=lambda d, label: button if label == '下一步' else None):
            with self.assertRaisesRegex(RuntimeError, '推进超时'):
                nodes.advance_manual_nodes(Mock(), 1, timeout=5)
        button.click.assert_not_called()

    def test_finish_requires_review(self):
        button = Mock()
        with patch.object(nodes, 'visible_control', side_effect=[None, button, Mock()]):
            self.assertTrue(nodes.finish_manual_nodes(Mock(), 1))
        button.click.assert_called_once()

    @patch.object(nodes.time, 'sleep')
    def test_finish_without_review_fails(self, sleep):
        button = Mock()
        with patch.object(nodes.time, 'monotonic', side_effect=range(1000)), \
             patch.object(nodes, 'visible_control', side_effect=lambda d, label: button if label == '完成录制' else None):
            with self.assertRaisesRegex(RuntimeError, '未进入回看'):
                nodes.finish_manual_nodes(Mock(), 1, timeout=3)

    def test_progress_from_accessibility_tree(self):
        driver = Mock()
        driver.page_source = '<App><Text label="进度 2/6" visible="true"/></App>'
        self.assertEqual(nodes.read_state(driver), (2, 6))

    def test_signature_dispatches_three_characters_and_accepts_review(self):
        with patch.object(nodes, 'signature_visible', side_effect=[True, False]), \
             patch.object(nodes, 'sign_scene_name') as sign, \
             patch.object(nodes, 'visible_control', return_value=Mock()):
            self.assertTrue(nodes.advance_manual_nodes(Mock(), 1))
        sign.assert_called_once_with(unittest.mock.ANY, 1, character_count=3)


if __name__ == '__main__':
    unittest.main()
