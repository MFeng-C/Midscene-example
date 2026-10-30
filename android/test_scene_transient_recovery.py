"""离线回归：登录连接重置与签名提交节点刷新。"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def load_function(name, **namespace):
    tree = ast.parse(Path(__file__).with_name('test_jdualrecord_app.py').read_text(encoding='utf-8-sig'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<recovery>', 'exec'), namespace)
    return namespace[name]


class Device:
    def __init__(self, state, stale=False):
        self.state, self.stale = state, stale

    def __call__(self, **selector):
        device = self
        label = selector.get('text')

        class Node:
            @property
            def exists(self):
                return label in {
                    'login': (), 'home': ('远程',),
                    'submit': ('提交签名',), 'next': ('下一步',),
                }[device.state]

            @property
            def info(self):
                if device.stale:
                    device.state = 'next'
                    raise RuntimeError('StaleObjectException')
                return {'bounds': dict(left=10, right=20, top=10, bottom=20)}

        return Node()


class RecoveryTests(unittest.TestCase):
    def login(self, device, submit, connect):
        return load_function(
            'submit_manager_login', _submit_manager_login=submit,
            time=SimpleNamespace(sleep=lambda _: None), DEVICE_ID='device',
            u2=SimpleNamespace(connect=connect),
        )(device, 47, 'manual')

    def signature(self, device, tap):
        return load_function(
            'submit_scene_signature', TEXT_NEXT_STEP='下一步', DEVICE_ID='device',
            time=SimpleNamespace(sleep=lambda _: None), subprocess=SimpleNamespace(run=tap),
        )(device, 80)

    def test_reset_after_login_does_not_submit_twice(self):
        d = Device('login')
        submit = Mock(side_effect=ConnectionResetError(10054, 'reset'))
        recovered = Device('home')
        self.assertIs(self.login(d, submit, Mock(return_value=recovered)), recovered)
        self.assertEqual(submit.call_count, 1)

    def test_reset_before_login_retries_on_reconnected_device(self):
        d, recovered = Device('login'), Device('login')
        submit = Mock(side_effect=[ConnectionResetError(10054, 'reset'), None])
        self.assertIs(self.login(d, submit, Mock(return_value=recovered)), recovered)
        self.assertIs(submit.call_args.args[0], recovered)

    def test_connection_retry_is_bounded(self):
        d = Device('login')
        submit = Mock(side_effect=ConnectionResetError(10054, 'reset'))
        with self.assertRaises(ConnectionResetError):
            self.login(d, submit, Mock(return_value=d))
        self.assertEqual(submit.call_count, 3)

    def test_unrelated_login_error_is_not_retried(self):
        submit, connect = Mock(side_effect=ValueError('bad login')), Mock()
        with self.assertRaises(ValueError):
            self.login(Device('login'), submit, connect)
        connect.assert_not_called()

    def test_stale_signature_recognizes_next_without_tapping(self):
        tap = Mock()
        self.assertTrue(self.signature(Device('submit', stale=True), tap))
        tap.assert_not_called()

    def test_signature_tap_is_confirmed_by_next_step(self):
        d = Device('submit')
        tap = Mock(side_effect=lambda *args, **kwargs: setattr(d, 'state', 'next'))
        self.assertTrue(self.signature(d, tap))
        self.assertEqual(tap.call_count, 1)

    def test_absent_signature_is_not_assumed_success(self):
        self.assertFalse(self.signature(Device('login'), Mock()))


if __name__ == '__main__':
    unittest.main()
