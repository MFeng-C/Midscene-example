import io
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from scene_log_output import scene_log_output


class SceneLogTest(unittest.TestCase):
    def test_concise_keeps_business_and_errors(self):
        target = io.StringIO()
        with patch.dict('os.environ', {'IOS_SCENE_VERBOSE_LOG': '0'}), redirect_stdout(target):
            with scene_log_output():
                print('[Step 14] 业务节点')
                print('[耗时细分] OCR/读取: 0.05s（完成）')
                print('[AI OCR] 已点击跳过')
                print('[AI签名衔接] 发起节点读取请求')
                print('[耗时细分] 请求: 20s（失败）')
                print('成功次数: 3')
        self.assertNotIn('0.05s', target.getvalue())
        self.assertNotIn('发起节点', target.getvalue())
        for text in ('[Step 14]', '已点击跳过', '失败', '成功次数: 3'):
            self.assertIn(text, target.getvalue())

    def test_verbose_and_other_scenarios_keep_details(self):
        for enabled, verbose in ((True, '1'), (False, '0')):
            target = io.StringIO()
            with patch.dict('os.environ', {'IOS_SCENE_VERBOSE_LOG': verbose}), redirect_stdout(target):
                with scene_log_output(enabled):
                    print('[耗时细分] detail')
            self.assertIn('detail', target.getvalue())


if __name__ == '__main__':
    unittest.main()
