"""现场 AI 双录专用入口；复用现场通用动作，不改变人工节点实现。"""
import time

from scene_fast_paths import node_snapshot
from scene_manual_nodes import advance_manual_nodes
from scene_ai_ocr import AINodeReader
from scene_ai_signature import sign_ai_name
from scene_ai_pages import click_ai_control


def start_ai_recording(driver, cycle_num, timeout=30):
    # 只点击 AI 入口，不能使用人工入口或以坐标代替模式选择。
    click_ai_control(driver, '开始（AI）', timeout=timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = node_snapshot(driver)
        if state['progress'] is not None or state['signature']:
            print(f'    第{cycle_num}次 - 开始 AI 双录后已确认业务节点就绪')
            return True
        time.sleep(.2)
    raise RuntimeError('开始 AI 双录后未出现业务节点')


def advance_ai_nodes(driver, cycle_num):
    """等 AI 播报/采集结束且按钮启用后推进，遇签名复用三字签名。"""
    print(f'    第{cycle_num}次 - 逐步核验 AI 节点、进度及三字签名')
    # 每次推进仍核验进度；不假定问答、朗读之后便已完成。
    # AI 播报和回答采集可能较长，使用独立等待预算，不修改人工默认值。
    reader = AINodeReader()

    def signature(driver, cycle_num, **kwargs):
        reader.invalidate()
        try:
            return sign_ai_name(driver, cycle_num, ocr_closed_at=reader.last_ocr_closed_at, **kwargs)
        finally:
            reader.invalidate()

    try:
        return advance_manual_nodes(driver, cycle_num, batch=True,
                                    timeout=300, transition_timeout=60,
                                    snapshot_reader=reader,
                                    signature_handler=signature, eager_advance=True,
                                    post_signature_timeout=30)
    except Exception as error:
        raise RuntimeError(f'现场 AI 节点推进失败：{error}') from error
    finally:
        driver.switch_to.context('NATIVE_APP')
        print(f'    [AI节点查询] DOM读取 {reader.reads} 次，进入WebView {reader.switches} 次，'
              f'读取及OCR处理累计 {reader.elapsed:.2f}s')


def finish_ai_recording(driver, cycle_num):
    state = node_snapshot(driver)
    if state['review']:
        return True
    if not state['finish']:
        raise RuntimeError('AI 双录未到达完成录制节点')
    click_ai_control(driver, '完成录制')
    deadline = time.monotonic() + 30
    while True:
        if node_snapshot(driver)['review']:
            return True
        if time.monotonic() >= deadline:
            raise RuntimeError('AI 点击完成录制后未进入回看界面')
        time.sleep(.2)
