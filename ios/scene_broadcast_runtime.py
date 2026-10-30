"""现场双录的 ReplayKit 遗留会话清理及初始化状态核验。"""
import time
import xml.etree.ElementTree as ET
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoAlertPresentException
from ios_phase_timing import timed_call


def dismiss_stopped_broadcast_alert(driver, timeout=5):
    """只关闭明确的系统直播停止提示，不接受其他系统弹窗。"""
    def alert_text():
        try:
            return driver.switch_to.alert.text
        except NoAlertPresentException:
            return None

    text = timed_call('直播清理/当前系统弹窗读取', alert_text)
    if not isinstance(text, str) or not (
            ('直播屏幕' in text or 'JRecordShare' in text)
            and ('直播已停止' in text or '无效的直播会话' in text)):
        return False
    timed_call('直播清理/点击系统提示好', driver.execute_script,
               'mobile: alert', {'action': 'accept', 'buttonLabel': '好'})
    deadline = time.monotonic() + timeout
    while True:
        current = timed_call('直播清理/核验系统提示关闭', alert_text)
        if current is None:
            print('    [直播清理] 已关闭直播停止提示，无需再次停止录屏')
            return True
        if current != text:
            raise RuntimeError('关闭直播停止提示后出现其他系统弹窗，停止清理')
        if time.monotonic() >= deadline:
            raise RuntimeError('点击好后系统直播停止提示未关闭')
        time.sleep(.15)


def native_state(driver):
    driver.switch_to.context('NATIVE_APP')
    root = ET.fromstring(driver.page_source)
    return ' '.join(e.get(k, '') for e in root.iter() if e.get('visible') != 'false'
                    for k in ('name', 'label', 'value'))


def click_native(driver, label):
    buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
        f"type == 'XCUIElementTypeButton' AND (name == '{label}' OR label == '{label}')")
    for button in buttons:
        if button.is_displayed() and button.is_enabled():
            button.click()
            return True
    return False


def clear_broadcast(driver):
    """先结束系统录屏，再结束宿主进程；仅操作明确的录屏控件。"""
    driver.switch_to.context('NATIVE_APP')
    if dismiss_stopped_broadcast_alert(driver):
        return
    started = time.monotonic()
    # 没有录屏时，只查系统控件；不要每轮序列化包含完整订单列表的 WDA 树。
    markers = driver.find_elements(AppiumBy.IOS_PREDICATE,
        "visible == 1 AND (type == 'XCUIElementTypeAlert' OR "
        "(type == 'XCUIElementTypeButton' AND (name CONTAINS '正在录制屏幕' OR "
        "label CONTAINS '正在录制屏幕' OR name == '停止直播' OR label == '停止直播')))")
    print(f'    [直播清理分段] 系统录屏控件查询: {time.monotonic()-started:.2f}s')
    if not markers:
        return
    text = native_state(driver)
    if '直播已停止' in text or '无效的直播会话' in text:
        print('    [直播清理] 检测到系统直播失败提示，关闭已停止提示')
        if not click_native(driver, '好'):
            raise RuntimeError('系统直播失败提示无法关闭')
        text = native_state(driver)
    if '正在录制屏幕' not in text and '停止直播' not in text:
        return
    if '停止直播' not in text:
        indicators = driver.find_elements(AppiumBy.IOS_PREDICATE,
            "type == 'XCUIElementTypeButton' AND (name CONTAINS '正在录制屏幕' OR label CONTAINS '正在录制屏幕')")
        if not indicators:
            raise RuntimeError('存在遗留屏幕录制，但未找到系统录屏入口')
        indicators[0].click()
    stopped = False
    for _ in range(10):
        for label in ('停止直播', '停止'):
            if click_native(driver, label):
                stopped = True
                break
        text = native_state(driver)
        if '正在录制屏幕' not in text and '停止直播' not in text:
            print('    [直播清理] 已确认系统录屏结束')
            return
        if stopped and '直播已停止' in text:
            click_native(driver, '好')
        time.sleep(.2)
    raise RuntimeError('遗留系统录屏未结束，停止创建新的直播会话')


def wait_detection_ready(driver, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = native_state(driver)
        for reason in ('无效的直播会话', '直播已停止', '初始化失败'):
            if reason in text:
                raise RuntimeError(f'现场直播初始化失败：{reason}')
        if '同意检测' in text and '停止直播' not in text:
            print('    现场直播初始化完成，已确认同意检测页面')
            return True
        time.sleep(.2)
    raise RuntimeError('现场直播初始化超时：未进入同意检测页面；不能仅以停止直播按钮判定成功')
