"""客户经理现场人工双录：按实际节点进度推进，不假定只有问答和朗读两页。"""

import re
import time
import xml.etree.ElementTree as ET

from appium.webdriver.common.appiumby import AppiumBy
from scene_manual_signature import sign_scene_name
from scene_fast_paths import node_snapshot


def read_state(driver):
    root = ET.fromstring(driver.page_source)
    texts = []
    for element in root.iter():
        if element.get('visible') == 'false':
            continue
        texts.extend(element.get(key, '') for key in ('name', 'label', 'value'))
    match = re.search(r'进度\s*[:：]?\s*(\d+)\s*/\s*(\d+)', ' '.join(texts))
    progress = tuple(map(int, match.groups())) if match else None
    return progress


def visible_control(driver, label):
    elements = driver.find_elements(
        AppiumBy.IOS_PREDICATE,
        f"name == '{label}' OR label == '{label}' OR value == '{label}'")
    return next((element for element in elements
                 if element.is_displayed() and element.is_enabled()), None)


def signature_visible(driver):
    elements = driver.find_elements(
        AppiumBy.IOS_PREDICATE,
        "name CONTAINS '请客户经理进行签字' OR label CONTAINS '请客户经理进行签字' "
        "OR value CONTAINS '请客户经理进行签字'")
    return any(element.is_displayed() for element in elements)


def advance_manual_nodes(driver, cycle_num, timeout=180, transition_timeout=30, batch=False,
                         snapshot_reader=None, signature_handler=None, eager_advance=False,
                         post_signature_timeout=None):
    """每次点击后必须观察进度变化；出现完成录制才交给下一步。"""
    driver.switch_to.context('NATIVE_APP')
    snapshot_reader = snapshot_reader or node_snapshot
    signature_handler = signature_handler or sign_scene_name
    deadline = time.monotonic() + timeout
    pending = None
    pending_deadline = None
    clicks = 0
    signature_done = False
    signature_finished = None
    while time.monotonic() < deadline:
        state = (snapshot_reader(driver, advance=pending is None) if batch and eager_advance
                 else snapshot_reader(driver) if batch else None)
        if (state['signature'] if batch else signature_visible(driver)):
            if signature_done:
                raise RuntimeError('现场签名完成后再次出现签名节点')
            print(f'    第{cycle_num}次 - 已识别客户经理签字节点，开始三字签名')
            signature_result = signature_handler(driver, cycle_num, character_count=3)
            signature_done = True
            signature_finished = time.monotonic()
            pending = None
            if isinstance(signature_result, dict) and signature_result.get('clicked'):
                pending = signature_result['progress']
                pending_deadline = time.monotonic() + transition_timeout
                clicks += 1
                signature_finished = None
                print(f'    第{cycle_num}次 - 签名内已校验并点击下一步，当前进度 {pending[0]}/{pending[1]}')
            # 签名独立计时，后续节点保留完整的推进窗口。
            deadline = time.monotonic() + (post_signature_timeout or timeout)
            if pending is not None:
                pending_deadline = min(pending_deadline, deadline)
            continue
        if signature_done and (state['review'] if batch else visible_control(driver, '确认完成') is not None):
            return True
        if (state['finish'] if batch else visible_control(driver, '完成录制') is not None):
            print(f'    第{cycle_num}次 - 已到达完成录制节点，共点击下一步 {clicks} 次')
            return True
        progress = state['progress'] if batch else read_state(driver)
        if pending is not None:
            if progress is not None and progress != pending:
                if progress[1] != pending[1] or progress[0] <= pending[0]:
                    raise RuntimeError(f'人工双录进度异常：{pending} -> {progress}')
                print(f'    第{cycle_num}次 - 节点已推进到 {progress[0]}/{progress[1]}')
                pending = None
            elif time.monotonic() >= pending_deadline:
                raise RuntimeError(f'点击下一步后进度未变化：{pending[0]}/{pending[1]}')
            else:
                time.sleep(.2)
                continue
        button = state['next'] if batch else visible_control(driver, '下一步')
        if progress is not None and (bool(button) if batch else button is not None):
            if not 1 <= progress[0] <= progress[1]:
                raise RuntimeError(f'人工双录进度无效：{progress}')
            if clicks >= 50:
                raise RuntimeError('人工双录下一步点击次数超出上限')
            if batch:
                if not (eager_advance and state.get('clicked')) and not snapshot_reader(
                        driver, click=True, progress=progress)['clicked']:
                    time.sleep(.2)
                    continue
            else:
                button.click()
            clicks += 1
            if signature_finished is not None:
                print(f'    [签名衔接] 签名结束至下一步点击: {time.monotonic()-signature_finished:.2f}s')
                signature_finished = None
            pending = progress
            pending_deadline = min(deadline, time.monotonic() + transition_timeout)
            print(f'    第{cycle_num}次 - 已点击下一步，当前进度 {progress[0]}/{progress[1]}')
        time.sleep(.2)
    if signature_done and post_signature_timeout is not None:
        raise RuntimeError(f'签名后节点推进超时（{post_signature_timeout}s），结束当前轮次')
    raise RuntimeError('人工双录节点推进超时，未出现完成录制按钮')


def finish_manual_nodes(driver, cycle_num, timeout=30):
    """精确点击完成录制，核验回看页，不点击顶栏结束或盲点坐标。"""
    driver.switch_to.context('NATIVE_APP')
    if visible_control(driver, '确认完成') is not None:
        return True
    button = visible_control(driver, '完成录制')
    if button is None:
        raise RuntimeError('人工双录未到达完成录制节点')
    button.click()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if visible_control(driver, '确认完成') is not None:
            print(f'    第{cycle_num}次 - 已点击完成录制，回看确认按钮已出现')
            return True
        time.sleep(.2)
    raise RuntimeError('点击完成录制后未进入回看确认界面')
