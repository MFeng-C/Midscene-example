import unittest
from unittest.mock import Mock, patch

import scene_manual_signature as signature


def state(ink=None, text='请客户经理进行签字', label='确定'):
    return dict(text=text, canvas=None if ink is None else dict(ink=ink),
                controls=[dict(text=label, enabled=True, rect={})])


class SignatureTest(unittest.TestCase):
    def run_states(self, states):
        driver = Mock()
        driver.get_settings.return_value = {'waitForIdleTimeout': 7, 'animationCoolOffTimeout': 1}
        with patch.object(signature, 'signature_snapshot', side_effect=states) as snapshot, \
             patch.object(signature, 'draw_test_signature') as draw, \
             patch.object(signature, 'native_point', return_value=(100, 100)), \
             patch.object(signature.time, 'sleep'):
            result = signature.sign_scene_name(driver, 1)
            for call in snapshot.call_args_list:
                self.assertEqual(call.kwargs['signature_prompt'], '请客户经理进行签字')
        return result, driver, draw

    def test_three_characters_then_review(self):
        result, driver, draw = self.run_states([
            state('blank1'), state('ink1'), state('blank2'), state('ink2'),
            state('blank3'), state('ink3'), state(text='录制回看', label='确认完成')])
        self.assertTrue(result)
        self.assertEqual(draw.call_count, 3)
        self.assertEqual(driver.tap.call_count, 3)
        driver.update_settings.assert_called_with(
            {'waitForIdleTimeout': 7, 'animationCoolOffTimeout': 1})

    def test_early_exit_fails(self):
        with self.assertRaisesRegex(RuntimeError, '提前结束'):
            self.run_states([state('blank'), state('ink'), state(text='回看', label='确认完成')])

    def test_missing_ink_fails(self):
        with self.assertRaisesRegex(RuntimeError, '未生成笔迹'):
            self.run_states([state('blank'), state('blank')])

    def test_fourth_character_fails(self):
        with self.assertRaisesRegex(RuntimeError, '额外签名'):
            self.run_states([state('b1'), state('i1'), state('b2'), state('i2'),
                             state('b3'), state('i3'), state('b4')])

    def test_manager_prompt_without_canvas_must_not_count_as_finished(self):
        with patch.object(signature.time, 'monotonic', side_effect=range(1000)), \
             patch.object(signature, 'signature_snapshot', return_value=state(label='下一步')), \
             patch.object(signature.time, 'sleep'):
            driver = Mock()
            driver.get_settings.return_value = {}
            with self.assertRaisesRegex(RuntimeError, '提前结束'):
                signature.sign_scene_name(driver, 1)
            driver.tap.assert_not_called()


if __name__ == '__main__':
    unittest.main()
