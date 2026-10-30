"""现场跑批默认输出业务日志，可按需恢复请求级诊断。"""
import os
from contextlib import contextmanager, redirect_stdout


DETAIL_MARKERS = (
    '[耗时细分]', '[启动分段]', '[登录分段]', '[收尾分段]', '[直播清理分段]',
    '[签名定位]', '[AI签名分段]', '[AI签名衔接]', '[签名衔接]', '[AI节点查询]',
    '[AI共性节点]', '[页面衔接]',
)


class ConciseSceneOutput:
    def __init__(self, stream):
        self.stream = stream
        self.pending = ''

    def emit(self, line):
        diagnostic = any(marker in line for marker in DETAIL_MARKERS)
        diagnostic = diagnostic or any(fragment in line for fragment in (
            '签字页面读取及上下文切换耗时', '签字原生触摸执行耗时',
            '现场搜索入口：', '坐标换算及W3C',
        ))
        # 错误信息始终保留，即使出现在诊断阶段。
        if not diagnostic or any(word in line for word in ('失败', '超时', '异常', 'Error', 'ERROR')):
            self.stream.write(line)

    def write(self, text):
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            self.emit(line + '\n')
        return len(text)

    def flush(self):
        if self.pending:
            self.emit(self.pending)
            self.pending = ''
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


@contextmanager
def scene_log_output(enabled=True):
    if not enabled or os.environ.get('IOS_SCENE_VERBOSE_LOG', '0') == '1':
        yield
        return
    import sys
    output = ConciseSceneOutput(sys.stdout)
    try:
        with redirect_stdout(output):
            yield
    finally:
        output.flush()
