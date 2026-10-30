"""离线验证自助双录每轮启动时的账号恢复。"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class Device:
    def __init__(self, state, stuck=False, switch_stuck=False):
        self.state, self.stuck = state, stuck
        self.switch_stuck = switch_stuck
        self.actions, self.screenshots = [], []

    def __call__(self, **selector):
        device = self
        label = selector.get('text', selector.get('description'))

        class Exists:
            def __bool__(self):
                if selector.get('selected'):
                    return label == '客户登录' and device.state == 'form'
                return label in {
                    'home': ('我的',), 'profile': ('我的', '退出登录'),
                    'confirm': ('我的', '确认'), 'entry': ('客户登录',),
                    'form': ('客户登录',), 'manager': ('客户登录',), 'unknown': (),
                }[device.state]

            def __call__(self, **kwargs):
                return bool(self)

        class Node:
            exists = Exists()

            @property
            def count(self):
                return 3 if device.state in ('form', 'manager') else 0

            def click(self):
                device.actions.append(label)
                if label == '退出登录':
                    device.state = 'confirm'
                elif label == '确认' and not device.stuck:
                    device.state = 'entry'
                elif label == '客户登录' and not device.switch_stuck:
                    device.state = 'form'

        return Node()

    def screenshot(self, name):
        self.screenshots.append(name)

    def xpath(self, expression):
        return self(text='客户登录', selected='@selected="true"' in expression)


class RecoveryTests(unittest.TestCase):
    def recover(self, device):
        clock = SimpleNamespace(now=0)

        def sleep(seconds):
            clock.now += seconds

        def navigation(d, label, timeout):
            d.actions.append(label)
            d.state = 'profile'
            return True

        def logout(d, cycle, action):
            navigation(d, '我的', 3)
            d(text='退出登录').click()
            d(text='确认').click()
            if d.stuck:
                d.screenshot('logout_timeout.png')
                raise Exception('未能恢复到客户登录表单')

        tree = ast.parse(Path(__file__).with_name('test_jdualrecord_app.py').read_text(encoding='utf-8-sig'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'ensure_customer_self_login_form')
        namespace = dict(time=SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep),
                         TEXT_MY='我的', TEXT_LOGOUT='退出登录', TEXT_CONFIRM='确认',
                         click_bottom_navigation=navigation, customer_self_transition=logout)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<recovery>', 'exec'), namespace)
        namespace['ensure_customer_self_login_form'](device, 25, timeout=3)

    def test_logged_in_account_is_logged_out_before_login(self):
        d = Device('home')
        self.recover(d)
        self.assertEqual(d.actions, ['我的', '退出登录', '确认', '客户登录'])
        self.assertEqual(d.state, 'form')

    def test_selected_customer_form_continues_without_repeated_click(self):
        d = Device('form')
        self.recover(d)
        self.assertEqual(d.actions, [])

    def test_manager_three_fields_do_not_skip_customer_entry(self):
        d = Device('manager')
        self.recover(d)
        self.assertEqual(d.actions, ['客户登录'])
        self.assertEqual(d.state, 'form')

    def test_ignored_role_switch_does_not_accept_manager_form(self):
        d = Device('manager', switch_stuck=True)
        with self.assertRaisesRegex(Exception, '未能恢复到客户登录表单'):
            self.recover(d)
        self.assertEqual(d.state, 'manager')

    def test_login_entry_opens_form(self):
        d = Device('entry')
        self.recover(d)
        self.assertEqual(d.actions, ['客户登录'])

    def test_failed_logout_does_not_proceed_to_login(self):
        d = Device('home', stuck=True)
        with self.assertRaisesRegex(Exception, '未能恢复到客户登录表单'):
            self.recover(d)
        self.assertNotIn('客户登录', d.actions)
        self.assertTrue(d.screenshots)


if __name__ == '__main__':
    unittest.main()
