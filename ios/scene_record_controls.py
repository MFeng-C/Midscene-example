"""现场双录工具栏测试，不修改客户纯录制行为。"""
import time
from pure_recording_controls import RESUME_SCRIPT

SCENE_RESUME_SCRIPT = RESUME_SCRIPT.replace(
    "const resume=find('继续录制');",
    "const resume=[...find('继续双录'),...find('继续录制')];")


def exercise_scene_controls(driver, cycle_num, click_control, switch_to_webview, timeout=20):
    def read(click=False):
        if not switch_to_webview(driver):
            raise RuntimeError('现场录制控件：未找到业务 WebView')
        return driver.execute_script(SCENE_RESUME_SCRIPT, click)

    def wait_state(predicate, message):
        deadline = time.monotonic() + timeout
        while True:
            state = read()
            if predicate(state):
                return state
            if time.monotonic() >= deadline:
                raise RuntimeError(message)
            time.sleep(.2)

    try:
        wait_state(lambda s: s['recording'] and not s['paused'], '现场录制工具栏未就绪')
        if not click_control(driver, '暂停', toolbar=True, web_first=True):
            raise RuntimeError('现场双录未找到暂停按钮')
        wait_state(lambda s: s['paused'], '点击暂停后未出现暂停弹窗')
        print(f'    第{cycle_num}次 - 已确认现场双录暂停，等待 3 秒后继续')
        time.sleep(3)
        deadline = time.monotonic() + timeout
        attempts, next_click = 0, 0
        while True:
            now = time.monotonic()
            state = read(attempts < 3 and now >= next_click)
            if not state['paused'] and state['recording']:
                break
            if state['clicked']:
                attempts += 1
                next_click = time.monotonic() + 1
            if time.monotonic() >= deadline:
                raise RuntimeError('现场双录继续操作后未恢复录制')
            time.sleep(.2)
        print(f'    第{cycle_num}次 - 已确认现场双录恢复，点击业务截图')
        if not click_control(driver, '截图', toolbar=True, web_first=True):
            raise RuntimeError('现场双录未找到截图按钮')
        wait_state(lambda s: s['recording'] and not s['paused'], '业务截图后录制状态异常')
        print(f'    第{cycle_num}次 - 已执行业务截图，录制状态正常')
        return True
    finally:
        driver.switch_to.context('NATIVE_APP')
