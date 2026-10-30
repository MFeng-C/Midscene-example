"""离线回归：上传弹窗晚到、确认未生效、节点失效及超时。"""
import ast
from pathlib import Path
import unittest


class Clock:
    now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Device:
    def __init__(self, clock, delay=20, required_clicks=1, stale=False):
        self.clock, self.delay = clock, delay
        self.required_clicks, self.stale = required_clicks, stale
        self.clicks = 0
        self.done = False
        self.screenshots = []

    def __call__(self, **selector):
        return Node(self, selector.get("text", selector.get("description")))

    def xpath(self, expression):
        return Node(self, expression.split('"')[1])

    def screenshot(self, name):
        self.screenshots.append(name)


class Node:
    def __init__(self, device, label):
        self.device, self.label = device, label

    @property
    def exists(self):
        d = self.device
        if self.label == "确认":
            return not d.done  # 无上传标题时即使存在其他确认也不能点击。
        if self.label == "文件上传成功":
            return not d.done and d.clock.now >= d.delay
        return d.done and self.label in ("业务办理完成", "返回")

    def click(self):
        d = self.device
        d.clicks += 1
        if d.stale:
            d.stale = False
            raise RuntimeError("stale node")
        d.done = d.clicks >= d.required_clicks


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        source = Path(__file__).with_name("test_jdualrecord_app.py").read_text(encoding="utf-8-sig")
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "wait_scene_upload_completion")
        namespace = dict(time=self.clock, TEXT_CONFIRM="确认", TEXT_RETURN="返回", print=lambda *args: None)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<upload-helper>", "exec"), namespace)
        self.wait = namespace[node.name]

    def test_delayed_dialog(self):
        d = Device(self.clock)
        self.wait(d, 5, "ai", timeout=30)
        self.assertTrue(d.done)
        self.assertGreaterEqual(self.clock.now, 20)

    def test_ineffective_click_and_stale_node(self):
        for stale in (False, True):
            with self.subTest(stale=stale):
                d = Device(self.clock, delay=0, required_clicks=2, stale=stale)
                self.wait(d, 5, "ai", timeout=15)
                self.assertEqual(d.clicks, 2)
                self.assertTrue(d.done)

    def test_timeout_does_not_click_unrelated_confirmation(self):
        d = Device(self.clock, delay=100)
        with self.assertRaisesRegex(Exception, "超时"):
            self.wait(d, 5, "ai", timeout=10)
        self.assertEqual(d.clicks, 0)
        self.assertEqual(len(d.screenshots), 1)

    def test_unclosed_dialog_is_not_success(self):
        d = Device(self.clock, delay=0, required_clicks=100)
        with self.assertRaisesRegex(Exception, "超时"):
            self.wait(d, 5, "ai", timeout=15)
        self.assertEqual(d.clicks, 3)

    def test_already_completed(self):
        d = Device(self.clock)
        d.done = True
        self.wait(d, 5, "manual", timeout=10)
        self.assertEqual(d.clicks, 0)


if __name__ == "__main__":
    unittest.main()
