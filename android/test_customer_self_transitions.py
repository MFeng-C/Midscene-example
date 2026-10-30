import unittest
from unittest.mock import Mock, patch
from PIL import Image, ImageDraw
import customer_self_transitions as transitions


def page(*labels, title=None):
    nodes = [({'text': s}, [10, 1800 + i * 20, 100, 1820 + i * 20]) for i, s in enumerate(labels)]
    if title:
        nodes.append(({'text': title}, [10, 10, 500, 100]))
    return nodes


HOME = page('我的', '自助', '纯录制', title='远程双录')
SELF = page('我的', '自助', '纯录制', title='自助双录') + page('订单状态')
LOGIN = page('客户登录') + [({'class': 'android.widget.EditText'}, [10, 300, 500, 400])]
DONE = page('业务办理完成', '返回')


class TransitionTests(unittest.TestCase):
    def run_transition(self, action, states, on_tap=None, timeout=8):
        clock = [0]
        index = [0]
        d = Mock()
        d.screenshot.return_value = Image.new('RGB', (1080, 2340), 'white')

        def snapshot(device):
            state = states[min(index[0], len(states) - 1)]
            index[0] += 1
            if isinstance(state, Exception):
                raise state
            return state

        def sleep(seconds):
            clock[0] += seconds

        with patch.object(transitions, 'snapshot', side_effect=snapshot), \
             patch.object(transitions.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(transitions.time, 'sleep', side_effect=sleep), \
             patch.object(transitions, 'tap', side_effect=on_tap) as tap:
            transitions.transition(d, 25, action, timeout)
            return tap

    def test_login_waits_through_loading(self):
        tap = self.run_transition('login', [LOGIN] * 10 + [HOME + page('加载中...')] * 5 + [HOME])
        tap.assert_not_called()

    def test_navigation_retries_ignored_tap_and_verifies_title(self):
        tap = self.run_transition('self', [HOME] * 9 + [SELF])
        self.assertEqual(tap.call_count, 2)

    def test_card_self_label_never_used_as_navigation(self):
        card = ({'text': '自助'}, [500, 500, 700, 600])
        tap = self.run_transition('self', [[card] + HOME, [card] + SELF])
        self.assertEqual(tap.call_count, 1)
        self.assertEqual(tap.call_args.args[1], transitions.bottom_navigation(HOME, '自助'))
        self.assertNotEqual(tap.call_args.args[1], card)

    def test_card_label_does_not_replace_missing_navigation(self):
        nodes = [n for n in HOME if n[0].get('text') != '自助']
        nodes.insert(0, ({'text': '自助'}, [500, 500, 700, 600]))
        self.assertFalse(transitions.order_page(nodes))
        self.assertIsNone(transitions.bottom_navigation(nodes, '自助'))

    def test_detail_page_stops_without_further_click(self):
        with self.assertRaisesRegex(RuntimeError, '进入订单详情'):
            self.run_transition('self', [page(title='订单详情')])

    def test_self_list_without_navigation_is_recognized(self):
        nodes = page('订单状态', '产品类型', '查询日期', title='自助双录')
        self.run_transition('self', [nodes]).assert_not_called()
        self.assertTrue(transitions.order_page(nodes))

    def test_self_card_on_remote_page_is_not_target_page(self):
        nodes = page('订单状态', '自助', title='远程双录')
        self.assertFalse(transitions.order_list_header(nodes, '自助双录'))

    def test_title_without_list_controls_is_not_success(self):
        self.assertFalse(transitions.order_list_header(page(title='自助双录'), '自助双录'))

    def test_stale_remote_tree_with_selected_self_continues(self):
        nodes = page('订单状态', title='远程双录')
        with patch.object(transitions, 'self_navigation_selected', return_value=True):
            self.run_transition('self', [nodes]).assert_not_called()

    def test_stale_complete_remote_navigation_with_selected_self_continues(self):
        with patch.object(transitions, 'self_navigation_selected', return_value=True):
            self.run_transition('self', [HOME]).assert_not_called()

    def test_missing_navigation_clicks_only_bottom_self_region(self):
        nodes = page('订单状态', title='远程双录')
        with patch.object(transitions, 'self_navigation_selected', side_effect=[False, True]), \
             patch.object(Mock, 'window_size', create=True, return_value=(1080, 2340)):
            tap = self.run_transition('self', [nodes])
        self.assertEqual(tap.call_count, 1)
        self.assertGreater(tap.call_args.args[1][1][1], 2100)

    def test_visual_selection_distinguishes_customer_tabs(self):
        for selected in range(4):
            screen = Image.new('RGB', (1080, 2340), 'white')
            ImageDraw.Draw(screen).rectangle(
                (selected * 270 + 80, 2240, selected * 270 + 180, 2300), fill=(25, 140, 250))
            d = Mock()
            d.screenshot.return_value = screen
            self.assertEqual(transitions.self_navigation_selected(d), selected == 1)

    def test_return_retries_until_order_list(self):
        tap = self.run_transition('return', [DONE] * 9 + [HOME])
        self.assertEqual(tap.call_count, 2)

    def test_logout_already_completed_never_clicks_confirm(self):
        self.run_transition('logout', [LOGIN]).assert_not_called()

    def test_logout_confirm_disappears_during_click(self):
        tap = self.run_transition('logout', [page('确认'), LOGIN],
                                  on_tap=RuntimeError('UiObjectNotFoundException'))
        self.assertEqual(tap.call_count, 1)

    def test_login_timeout_does_not_proceed_to_navigation(self):
        with self.assertRaisesRegex(RuntimeError, 'login页面切换超时'):
            self.run_transition('login', [LOGIN], timeout=1)


if __name__ == '__main__':
    unittest.main()
