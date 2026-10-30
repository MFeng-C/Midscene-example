"""只记录固定阶段名和时长，不输出动作参数、页面内容或账号信息。"""
from functools import wraps
from time import perf_counter


def timed_call(label, action, *args, **kwargs):
    started = perf_counter()
    status = '失败'
    try:
        result = action(*args, **kwargs)
        status = '完成'
        return result
    finally:
        print(f'    [耗时细分] {label}: {perf_counter()-started:.3f}s（{status}）')


def timed_flow(label):
    def decorate(action):
        @wraps(action)
        def measured(*args, **kwargs):
            return timed_call(label, action, *args, **kwargs)
        return measured
    return decorate
