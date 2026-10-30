"""
iOS 原生 App UI 自动化测试脚本 - 纯录制业务流程
测试流程：
  1. 客户登录
  2. 点击"纯录制"菜单
  3. 按订单号和客户名称查询订单并点击"录制"按钮
  4. 弹窗确认
  5. 办理提示界面点击"同意并开始录制"
  6. 弹窗点击"立即开始"
  7. 点击"同意检测"
  8. 环境检测界面点击"同意检测"
  9. 分支处理：检测未通过/通过
支持循环执行
"""

import time
import os
import sys
import pymysql
from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from self_service_signature import wait_self_service_completion
from ios_customer_logout import logout_customer_ios
from ios_session_recovery import prepare_login, terminate_previous_app
from pure_recording_controls import ensure_pure_recording_resumed, click_pure_toolbar
from self_service_return import return_and_open_my
from pure_recording_transitions import detect_and_start, wait_upload, return_to_order_list
from pure_recording_search import prepare_search, confirm_keyboard_hidden

from config_pure_recording import (
    WDA_URL, APPIUM_URL, UDID, PLATFORM_VERSION, BUNDLE_ID,
    CUSTOMER_ID, CUSTOMER_PASSWORD, CUSTOMER_CAPTCHA,
    MANAGER_ID, MANAGER_PASSWORD, MANAGER_CAPTCHA,
    ORDER_ID, ORDER_ID_SELF_SERVICE, CUSTOMER_NAME,
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_TABLE, DB_STATE_FIELD,
    TEXT_CUSTOMER_LOGIN, TEXT_MANAGER_LOGIN, TEXT_LOGIN_BTN, TEXT_MY, TEXT_LOGOUT,
    TEXT_SELF_SERVICE, TEXT_PURE_RECORD, TEXT_RECORD_BTN, TEXT_CONFIRM,
    TEXT_AGREE_AND_START, TEXT_AGREE_AND_START_DUAL, TEXT_START_LIVE, TEXT_IMMEDIATELY_START,
    TEXT_AGREE_CHECK, TEXT_START_RECORD, TEXT_PAUSE_RECORD, TEXT_CONTINUE_RECORD,
    TEXT_SCREENSHOT, TEXT_END_RECORD, TEXT_CONFIRM_COMPLETE,
    TEXT_SKIP, TEXT_RECHECK, TEXT_NEXT_STEP, TEXT_FINISH_RECORD,
    TEXT_RETURN, TEXT_END, TEXT_UPLOAD_SUCCESS, TEXT_UPLOAD_SUCCESS2,
    TEXT_END_SERVICE, TEXT_END_SERVICE2, TEXT_SERVICE_ENDED,
    TEXT_ID_PLACEHOLDER, TEXT_PASSWORD_PLACEHOLDER, TEXT_CAPTCHA_PLACEHOLDER,
    APP_LAUNCH_TIMEOUT, LOGIN_FORM_TIMEOUT, LOGIN_BTN_TIMEOUT, PAGE_LOAD_TIMEOUT,
    POPUP_TIMEOUT, AGREE_BTN_TIMEOUT, START_LIVE_TIMEOUT, AGREE_CHECK_TIMEOUT,
    DETECTION_TIMEOUT, RECORD_BTN_TIMEOUT, END_RECORD_TIMEOUT, CONFIRM_TIMEOUT,
    UPLOAD_TIMEOUT, END_TIMEOUT, RETURN_TIMEOUT, LOGOUT_TIMEOUT, CONFIRM_LOGOUT_TIMEOUT,
    BROADCAST_TIMEOUT, BROADCAST_READING_TIMEOUT, BUSINESS_COMPLETE_TIMEOUT,
    POLL_INTERVAL_FAST, POLL_INTERVAL_NORMAL, POLL_INTERVAL_SLOW,
    COUNTDOWN_SECONDS, COUNTDOWN_BUFFER, WAIT_SCREENSHOT_BEFORE_END,
    WEBDRIVER_AGENT_URL, NEW_COMMAND_TIMEOUT, WDA_CONNECTION_TIMEOUT,
    AUTO_ACCEPT_ALERTS, SKIP_LOG_CAPTURE, ENABLE_WEBVIEW_DETAILS,
    AUTO_WEBVIEW, ENSURE_WEBVIEWS_HAVE_PAGES, WEBVIEW_CONNECT_TIMEOUT,
    WEBKIT_DEBUG_PROXY_PORT, SHOW_XCODE_LOG, NEW_COMMAND_TIMEOUT_SHORT,
    WEBVIEW_CONNECT_RETRIES, NATIVE_WEB_TAP,
    SCREENSHOT_DIR, ENABLE_SCREENSHOT,
    CSS_DIALOG_CONFIRM, CSS_DIALOG_CONFIRM_BTN, CSS_AGREE_BTN,
)

# 登录模式：customer 或 manager
LOGIN_MODE = "customer"  # 可通过环境变量 LOGIN_MODE 覆盖

# 环境变量覆盖
ENABLE_SCREENSHOT = os.environ.get("SCREENSHOT", "1" if ENABLE_SCREENSHOT else "0") == "1"
LOGIN_MODE = os.environ.get("LOGIN_MODE", LOGIN_MODE)

# 根据登录模式选择账号
if LOGIN_MODE == "manager":
    LOGIN_TEXT = TEXT_MANAGER_LOGIN
    LOGIN_ID = MANAGER_ID
    LOGIN_PASSWORD = MANAGER_PASSWORD
    LOGIN_CAPTCHA = MANAGER_CAPTCHA
else:
    LOGIN_MODE = "customer"
    LOGIN_TEXT = TEXT_CUSTOMER_LOGIN
    LOGIN_ID = CUSTOMER_ID
    LOGIN_PASSWORD = CUSTOMER_PASSWORD
    LOGIN_CAPTCHA = CUSTOMER_CAPTCHA

# 确保截图目录存在
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def check_and_reset_order_state():
    """检查订单状态，如果state非0则重置为0"""
    print("\n[订单状态检查] 检查订单状态...")
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4'
        )
        cursor = conn.cursor()

        # 查询订单状态
        cursor.execute(f"SELECT {DB_STATE_FIELD} FROM {DB_TABLE} WHERE order_id = %s", (ORDER_ID,))
        result = cursor.fetchone()

        if result is None:
            print(f"    [订单状态检查] 订单 {ORDER_ID} 不存在")
            cursor.close()
            conn.close()
            return False

        current_state = result[0]
        print(f"    [订单状态检查] 订单 {ORDER_ID} 当前状态: {current_state}")

        if current_state != 0:
            print(f"    [订单状态检查] 状态非0，正在重置为0...")
            cursor.execute(f"UPDATE {DB_TABLE} SET {DB_STATE_FIELD} = 0 WHERE order_id = %s", (ORDER_ID,))
            conn.commit()
            print(f"    [订单状态检查] 订单状态已重置为0")
        else:
            print(f"    [订单状态检查] 状态为0，可以继续测试")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"    [订单状态检查] 数据库操作失败: {e}")
        return False


def get_desired_caps():
    """获取 Appium 配置"""
    options = XCUITestOptions()
    options.set_capability("platformName", "iOS")
    options.set_capability("automationName", "XCUITest")
    options.set_capability("deviceName", "iPhone")
    options.set_capability("platformVersion", PLATFORM_VERSION)
    options.set_capability("udid", UDID)
    options.set_capability("bundleId", BUNDLE_ID)
    options.set_capability("webDriverAgentUrl", WEBDRIVER_AGENT_URL)
    options.set_capability("noReset", True)
    options.set_capability("fullReset", False)
    options.set_capability("newCommandTimeout", NEW_COMMAND_TIMEOUT)
    options.set_capability("wdaConnectionTimeout", WDA_CONNECTION_TIMEOUT)
    options.set_capability("autoAcceptAlerts", AUTO_ACCEPT_ALERTS)
    options.set_capability("skipLogCapture", SKIP_LOG_CAPTURE)
    options.set_capability("enableWebviewDetails", ENABLE_WEBVIEW_DETAILS)
    options.set_capability("autoWebview", AUTO_WEBVIEW)
    options.set_capability("ensureWebviewsHavePages", ENSURE_WEBVIEWS_HAVE_PAGES)
    options.set_capability("webviewConnectTimeout", WEBVIEW_CONNECT_TIMEOUT)
    options.set_capability("webkitDebugProxyPort", WEBKIT_DEBUG_PROXY_PORT)
    options.set_capability("showXcodeLog", SHOW_XCODE_LOG)
    options.set_capability("newCommandTimeout", NEW_COMMAND_TIMEOUT_SHORT)
    options.set_capability("webviewConnectRetries", WEBVIEW_CONNECT_RETRIES)
    options.set_capability("nativeWebTap", NATIVE_WEB_TAP)
    options.set_capability("processArguments", {"args": ["-StartInBackground", "YES"]})
    return options


def screenshot(driver, name):
    """截图保存（仅在启用时）"""
    if not ENABLE_SCREENSHOT:
        return
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    try:
        driver.save_screenshot(path)
        print(f"    截图: {path}")
    except Exception as e:
        print(f"    截图失败: {e}")
    return path


def click_element(driver, locators, check_enabled=True, timeout=5):
    """尝试多种方式点击元素"""
    start = time.time()
    while time.time() - start < timeout:
        for loc_type, loc_value in locators:
            try:
                if loc_type == "accessibility id":
                    elem = driver.find_element(AppiumBy.ACCESSIBILITY_ID, loc_value)
                elif loc_type == "xpath":
                    elem = driver.find_element(By.XPATH, loc_value)
                elif loc_type == "class name":
                    elem = driver.find_element(By.CLASS_NAME, loc_value)
                elif loc_type == "predicate":
                    elem = driver.find_element(AppiumBy.IOS_PREDICATE, loc_value)
                else:
                    elem = driver.find_element(By.XPATH, loc_value)

                if not elem.is_displayed():
                    continue
                if check_enabled and not elem.is_enabled():
                    time.sleep(0.1)
                    continue

                elem.click()
                return True, loc_type
            except:
                continue
        time.sleep(0.2)
    return False, None


def input_text(driver, locators, text, clear_first=True, timeout=5, direct=False):
    """清空并输入文本"""
    start = time.time()
    while time.time() - start < timeout:
        for loc_type, loc_value in locators:
            try:
                if loc_type == "accessibility id":
                    elem = driver.find_element(AppiumBy.ACCESSIBILITY_ID, loc_value)
                elif loc_type == "xpath":
                    elem = driver.find_element(By.XPATH, loc_value)
                elif loc_type == "class name":
                    elem = driver.find_element(By.CLASS_NAME, loc_value)
                elif loc_type == "predicate":
                    elem = driver.find_element(AppiumBy.IOS_PREDICATE, loc_value)
                else:
                    elem = driver.find_element(By.XPATH, loc_value)

                if elem and elem.is_displayed():
                    if direct:
                        # 原生 send_keys 自行聚焦；不调用当前客户端已移除的 set_value。
                        if clear_first:
                            elem.clear()
                        elem.send_keys(text)
                        return True
                    # 使用set_value直接设置值，无需先清空（更快）
                    try:
                        elem.set_value(text)
                        return True
                    except:
                        # 兜底：使用传统方式
                        elem.click()
                        time.sleep(0.05)
                        if clear_first:
                            try:
                                elem.clear()
                            except:
                                pass
                        elem.send_keys(text)
                        return True
            except Exception as e:
                continue
        time.sleep(0.1)
    return False


def hide_ios_keyboard(driver, timeout=5):
    """隐藏 iOS 键盘，并验证键盘节点确实消失。"""
    def visible_keyboard():
        try:
            keyboards = driver.find_elements(By.CLASS_NAME, "XCUIElementTypeKeyboard")
            return next((item for item in keyboards if item.is_displayed()), None)
        except Exception:
            return None

    def wait_hidden(seconds=1):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if visible_keyboard() is None:
                return True
            time.sleep(0.1)
        return visible_keyboard() is None

    keyboard = visible_keyboard()
    if keyboard is None:
        return True

    try:
        driver.hide_keyboard()
        if wait_hidden():
            return True
    except Exception:
        pass

    try:
        done_buttons = driver.find_elements(
            AppiumBy.IOS_PREDICATE,
            "type == 'XCUIElementTypeButton' AND "
            "(name == 'Done' OR label == 'Done' OR name == '完成' OR label == '完成')",
        )
        for button in done_buttons:
            if button.is_displayed():
                button.click()
                if wait_hidden():
                    return True
    except Exception:
        pass

    # WebView 键盘的 Done 有时不在当前 App 的可访问树中，使用键盘矩形定位工具栏右侧。
    try:
        keyboard = visible_keyboard()
        if keyboard is not None:
            rect = keyboard.rect
            x = int(rect["x"] + rect["width"] - max(24, rect["width"] * 0.07))
            y = int(rect["y"] + min(24, rect["height"] * 0.10))
            driver.tap([(x, y)])
            if wait_hidden():
                return True
    except Exception:
        pass

    # 最后点击键盘上方的非输入区域，使当前输入框失去焦点。
    try:
        keyboard = visible_keyboard()
        if keyboard is not None:
            rect = keyboard.rect
            size = driver.get_window_size()
            driver.tap([(int(size["width"] * 0.5), max(10, int(rect["y"] - 15)))])
            if wait_hidden(timeout):
                return True
    except Exception:
        pass

    return False


def find_and_click_button(driver, name_pattern, timeout=15):
    """查找并点击按钮，支持多种匹配方式"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            # 尝试 Predicate 方式
            buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                f"name CONTAINS '{name_pattern}' AND type == 'XCUIElementTypeButton'")
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        except:
            pass

        # 兜底：遍历所有按钮
        try:
            all_buttons = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeButton')
            for btn in all_buttons:
                name = btn.get_attribute('name') or ''
                if name_pattern in name and btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        except:
            pass
        time.sleep(0.2)
    return False


def wait_for_page_element(driver, check_func, timeout=30):
    """等待页面满足条件"""
    start = time.time()
    while time.time() - start < timeout:
        if check_func(driver.page_source):
            return True
        time.sleep(0.3)
    return False


def switch_to_webview(driver):
    """切换到 WebView 并返回是否成功"""
    try:
        for ctx in driver.contexts:
            if 'WEBVIEW' in ctx:
                driver.switch_to.context(ctx)
                return True
    except:
        pass
    return False


def switch_to_native(driver):
    """切换回原生"""
    try:
        driver.switch_to.context("NATIVE_APP")
    except:
        pass


def webview_click(driver, selectors):
    """在 WebView 中点击元素"""
    if not switch_to_webview(driver):
        return False

    for selector in selectors:
        try:
            if selector[0] == "css":
                btn = driver.find_element(By.CSS_SELECTOR, selector[1])
            elif selector[0] == "xpath":
                btn = driver.find_element(By.XPATH, selector[1])
            else:
                continue

            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                switch_to_native(driver)
                return True
        except:
            continue

    switch_to_native(driver)
    return False


def wait_countdown(driver, seconds=None):
    """等待倒计时"""
    if seconds is None:
        seconds = COUNTDOWN_SECONDS
    print(f"    等待 {seconds}s 倒计时...")
    time.sleep(seconds + COUNTDOWN_BUFFER)


# ============================================================================
# 测试步骤函数
# ============================================================================

def step1_login(driver, cycle_num, fast_input=False, direct_input=False):
    """Step 1: 客户登录"""
    print(f"\n[Step 1] {LOGIN_TEXT}...")

    prepare_login(driver, cycle_num, BUNDLE_ID, screenshot)

    # 用更高效的轮询等待"客户登录"按钮出现
    btn_found = False
    max_polls = int(APP_LAUNCH_TIMEOUT / POLL_INTERVAL_FAST)
    for wait_idx in range(max_polls):
        try:
            buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                f"name == '{LOGIN_TEXT}' AND type == 'XCUIElementTypeButton'")
            for btn in buttons:
                if btn.is_displayed():
                    btn_found = True
                    print(f"    第{cycle_num}次 - {LOGIN_TEXT}按钮出现(iter {wait_idx})")
                    break
        except:
            pass
        if btn_found:
            break
        time.sleep(POLL_INTERVAL_FAST)
    screenshot(driver, f"step1_launch_{cycle_num}")

    # 使用 Predicate 定位登录按钮
    login_btn = None
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            f"name == '{LOGIN_TEXT}' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                login_btn = btn
                break
    except:
        pass

    if login_btn is None:
        success, loc_type = click_element(driver, [
            ("xpath", f'//XCUIElementTypeButton[@name="{LOGIN_TEXT}"]'),
            ("xpath", f'//*[contains(@name,"{LOGIN_TEXT}")]'),
            ("accessibility id", LOGIN_TEXT),
        ])
        if success:
            print(f"    第{cycle_num}次 - 已点击{LOGIN_TEXT}({loc_type})")
        else:
            screenshot(driver, f"error_step1_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'{LOGIN_TEXT}'按钮")
    else:
        login_btn.click()
        print(f"    第{cycle_num}次 - 已点击{LOGIN_TEXT}(Predicate)")

    # 等待登录表单出现
    max_polls = int(LOGIN_FORM_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        try:
            text_fields = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeTextField')
            if len(text_fields) >= 2:
                print(f"    第{cycle_num}次 - 登录表单出现(iter {wait_idx})")
                break
        except:
            pass
        time.sleep(POLL_INTERVAL_NORMAL)
    screenshot(driver, f"step1_login_form_{cycle_num}")

    # 输入账号
    success = input_text(driver, [
        *([('predicate', "type == 'XCUIElementTypeTextField' AND (value CONTAINS '身份证' OR name CONTAINS '身份证')")] if fast_input else []),
        ("xpath", f'//XCUIElementTypeTextField[@value="{TEXT_ID_PLACEHOLDER}"]'),
        ("xpath", '//XCUIElementTypeTextField[contains(@value,"身份证")]'),
        ("xpath", '//XCUIElementTypeTextField[1]'),
    ], LOGIN_ID, clear_first=True, direct=direct_input)
    if not success:
        screenshot(driver, f"error_step1_id_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到账号输入框")
    print(f"    第{cycle_num}次 - 已输入账号")

    # 输入密码
    success = input_text(driver, [
        *([('predicate', "type == 'XCUIElementTypeSecureTextField'")] if fast_input else []),
        ("xpath", f'//XCUIElementTypeSecureTextField[@value="{TEXT_PASSWORD_PLACEHOLDER}"]'),
        ("xpath", '//XCUIElementTypeSecureTextField[1]'),
    ], LOGIN_PASSWORD, clear_first=False, direct=direct_input)
    if not success:
        screenshot(driver, f"error_step1_pwd_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    print(f"    第{cycle_num}次 - 已输入密码")

    # 输入验证码
    success = input_text(driver, [
        *([('predicate', "type == 'XCUIElementTypeTextField' AND (value CONTAINS '验证码' OR name CONTAINS '验证码')")] if fast_input else []),
        ("xpath", f'//XCUIElementTypeTextField[@value="{TEXT_CAPTCHA_PLACEHOLDER}"]'),
        ("xpath", '//XCUIElementTypeTextField[2]'),
    ], LOGIN_CAPTCHA, clear_first=True, direct=direct_input)
    if not success:
        screenshot(driver, f"error_step1_captcha_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    print(f"    第{cycle_num}次 - 已输入验证码")

    # 使用 Predicate 定位登录按钮
    login_btn = None
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            f"name == '{TEXT_LOGIN_BTN}' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                login_btn = btn
                break
    except:
        pass

    if login_btn:
        login_btn.click()
        print(f"    第{cycle_num}次 - 已点击{TEXT_LOGIN_BTN}(Predicate)")
    else:
        success, loc_type = click_element(driver, [
            ("xpath", f'//XCUIElementTypeButton[@name="{TEXT_LOGIN_BTN}"]'),
            ("xpath", f'//XCUIElementTypeButton[contains(@name,"{TEXT_LOGIN_BTN}")]'),
        ])
        if success:
            print(f"    第{cycle_num}次 - 已点击{TEXT_LOGIN_BTN}({loc_type})")
        else:
            screenshot(driver, f"error_step1_login_btn_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_LOGIN_BTN}'按钮")

    return True


def step2_click_self_service(driver, cycle_num):
    """Step 2: 点击"自助"菜单"""
    print(f"\n[Step 2] 点击'{TEXT_SELF_SERVICE}'菜单...")

    # 等待页面加载完成
    max_polls = int(PAGE_LOAD_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if TEXT_SELF_SERVICE in source or TEXT_MY in source:
            print(f"    第{cycle_num}次 - 页面已加载(iter {wait_idx})")
            break
        time.sleep(POLL_INTERVAL_NORMAL)

    # 使用 Predicate 定位
    btn_found = False
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            f"name CONTAINS '{TEXT_SELF_SERVICE}' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"    第{cycle_num}次 - 已点击'{TEXT_SELF_SERVICE}'(Predicate)")
                btn_found = True
                break
    except:
        pass

    if not btn_found:
        success = find_and_click_button(driver, TEXT_SELF_SERVICE, timeout=10)
        if success:
            print(f"    第{cycle_num}次 - 已点击'{TEXT_SELF_SERVICE}'")
        else:
            screenshot(driver, f"error_step2_self_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_SELF_SERVICE}'按钮")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step2_self_service_{cycle_num}")
    return True


def step2_click_pure_recording(driver, cycle_num):
    """Step 2: 点击"纯录制"菜单"""
    print(f"\n[Step 2] 点击'{TEXT_PURE_RECORD}'菜单...")

    source = driver.page_source
    if '高级搜索' in source:
        driver.back()
        time.sleep(POLL_INTERVAL_SLOW)
        source = driver.page_source
    if '纯录制双录' in source and '订单状态' in source:
        print(f"    第{cycle_num}次 - 当前已在纯录制订单列表，跳过重复导航")
        screenshot(driver, f"step2_pure_recording_{cycle_num}")
        return True

    # 等待页面加载完成
    max_polls = int(PAGE_LOAD_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if TEXT_PURE_RECORD in source or TEXT_MY in source:
            print(f"    第{cycle_num}次 - 页面已加载(iter {wait_idx})")
            break
        time.sleep(POLL_INTERVAL_NORMAL)

    # 使用 Predicate 定位
    btn_found = False
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            f"name CONTAINS '{TEXT_PURE_RECORD}' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"    第{cycle_num}次 - 已点击'{TEXT_PURE_RECORD}'(Predicate)")
                btn_found = True
                break
    except:
        pass

    if not btn_found:
        success = find_and_click_button(driver, TEXT_PURE_RECORD, timeout=15)
        if success:
            print(f"    第{cycle_num}次 - 已点击'{TEXT_PURE_RECORD}'")
        else:
            screenshot(driver, f"error_step2_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_PURE_RECORD}'按钮")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step2_pure_recording_{cycle_num}")
    return True


def record_confirmation_visible(driver):
    """只接受可见确认按钮，不能用列表中的“录制”文字判断弹窗。"""
    buttons = driver.find_elements(
        AppiumBy.IOS_PREDICATE,
        "type == 'XCUIElementTypeButton' AND "
        "(name == '确认' OR label == '确认' OR name == '确定' OR label == '确定')",
    )
    return any(button.is_displayed() and button.is_enabled() for button in buttons)


def click_record_result(driver):
    """精确点击查询结果中的录制按钮，并确认页面已经响应。"""
    def wait_confirmation():
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if record_confirmation_visible(driver):
                return True
            time.sleep(0.2)
        return False

    for use_tap in (False, True):
        if record_confirmation_visible(driver):
            return True
        buttons = driver.find_elements(
            AppiumBy.IOS_PREDICATE,
            "type == 'XCUIElementTypeButton' AND (name == '录制' OR label == '录制')",
        )
        buttons = [button for button in buttons if button.is_displayed() and button.is_enabled()]
        if len(buttons) > 1:
            raise RuntimeError('查询结果包含多个录制按钮，无法确定目标订单')
        if not buttons:
            continue
        button = buttons[0]
        if use_tap:
            rect = button.rect
            driver.tap([(int(rect['x'] + rect['width'] / 2),
                         int(rect['y'] + rect['height'] / 2))])
        else:
            button.click()
        if wait_confirmation():
            return True

    # 保留 WebView 兼容路径，同样只匹配完整按钮文本。
    if webview_click(driver, [("xpath", "//button[normalize-space(.)='录制']")]):
        return wait_confirmation()
    return False


def step3_click_record_in_list(driver, cycle_num, fast_search=False, dom_search=False,
                               order_id=None, customer_name=None):
    """Step 3: 使用全局搜索精确查询目标订单，再点击录制。"""
    # 调用方可指定现场订单；不修改客户场景的配置和默认订单。
    target_order = order_id if order_id is not None else ORDER_ID
    target_customer = customer_name if customer_name is not None else CUSTOMER_NAME
    return search_and_record_order(driver, cycle_num, target_order, target_customer,
                                   fast_search, dom_search)


def search_and_record_order(driver, cycle_num, ORDER_ID, CUSTOMER_NAME,
                            fast_search=False, dom_search=False):
    print(f"\n[搜索订单] 按订单号和客户名称查询订单...")

    input_started = time.monotonic()
    prepared = dom_search and prepare_search(
        driver, ORDER_ID, CUSTOMER_NAME, switch_to_webview)
    order_entered = customer_entered = prepared
    if not prepared:
        # 快速路径可能已打开表单；兜底时不能再次点击搜索入口而关闭表单。
        opened = False
        if dom_search:
            fields = driver.find_elements(AppiumBy.IOS_PREDICATE,
                "type == 'XCUIElementTypeTextField' AND (name CONTAINS '订单号' OR value CONTAINS '订单号')")
            opened = any(field.is_displayed() for field in fields)
        if not opened:
            opened = find_and_click_button(driver, "全局搜索", timeout=2)
        if not opened:
            opened = find_and_click_button(driver, "高级搜索", timeout=2)
        if not opened:
            size = driver.get_window_size()
            driver.tap([(int(size["width"] * 0.90), int(size["height"] * 0.07))])
        time.sleep(POLL_INTERVAL_SLOW)
    
        order_locators = [
            ("xpath", '//XCUIElementTypeTextField[contains(@name,"订单号") or contains(@value,"订单号")]'),
            ("xpath", '(//XCUIElementTypeTextField)[1]'),
        ]
        customer_locators = [
            ("xpath", '//XCUIElementTypeTextField[contains(@name,"客户名称") or contains(@value,"客户名称")]'),
            ("xpath", '(//XCUIElementTypeTextField)[2]'),
        ]
        if fast_search:
            # 原生 XPath 需要生成整棵可访问树；优先使用 WDA 原生 predicate。
            order_locators.insert(0, ('predicate',
                "type == 'XCUIElementTypeTextField' AND (name CONTAINS '订单号' OR value CONTAINS '订单号')"))
            customer_locators.insert(0, ('predicate',
                "type == 'XCUIElementTypeTextField' AND (name CONTAINS '客户名称' OR value CONTAINS '客户名称')"))
        input_started = time.monotonic()
        order_entered = input_text(driver, order_locators, ORDER_ID, timeout=5, direct=dom_search)
        customer_entered = input_text(driver, customer_locators, CUSTOMER_NAME, timeout=5, direct=dom_search)
    
        if not order_entered or not customer_entered:
            if switch_to_webview(driver):
                try:
                    fields = [field for field in driver.find_elements(By.CSS_SELECTOR, "input") if field.is_displayed()]
                    if len(fields) >= 2:
                        driver.execute_script(
                            "arguments[0].value=''; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
                            fields[0],
                        )
                        fields[0].send_keys(ORDER_ID)
                        driver.execute_script(
                            "arguments[0].value=''; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
                            fields[1],
                        )
                        fields[1].send_keys(CUSTOMER_NAME)
                        order_entered = customer_entered = True
                finally:
                    switch_to_native(driver)

    if not order_entered or not customer_entered:
        screenshot(driver, f"error_step3_search_form_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到订单号或客户名称输入框")

    print(f"    第{cycle_num}次 - 已输入订单号 {ORDER_ID}，客户名称 {CUSTOMER_NAME}")
    print(f"    第{cycle_num}次 - 搜索输入耗时 {time.monotonic() - input_started:.2f}s")
    keyboard_started = time.monotonic()
    keyboard_hidden = (confirm_keyboard_hidden(driver, hide_ios_keyboard) if prepared
                       else hide_ios_keyboard(driver))
    if not keyboard_hidden:
        screenshot(driver, f"error_step3_keyboard_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - iOS 键盘未能隐藏")
    print(f"    第{cycle_num}次 - iOS 键盘已隐藏")
    print(f"    第{cycle_num}次 - 收键盘耗时 {time.monotonic() - keyboard_started:.2f}s")

    queried = False
    for _ in range(2):
        try:
            query_buttons = driver.find_elements(
                AppiumBy.IOS_PREDICATE,
                "type == 'XCUIElementTypeButton' AND name == '查询'",
            )
            for button in query_buttons:
                if button.is_displayed() and button.is_enabled():
                    button.click()
                    queried = True
                    break
        except Exception:
            pass
        if queried:
            break
        try:
            driver.execute_script("mobile: scroll", {"direction": "down"})
        except Exception:
            pass
        time.sleep(POLL_INTERVAL_NORMAL)

    if not queried:
        queried = webview_click(driver, [
            ("xpath", "//button[normalize-space(.)='查询']"),
            ("xpath", "//*[contains(@class,'button') and normalize-space(.)='查询']"),
        ])
    if not queried:
        screenshot(driver, f"error_step3_query_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'查询'按钮")

    result_ready = wait_for_page_element(
        driver,
        lambda source: '高级搜索' not in source and ORDER_ID in source and TEXT_RECORD_BTN in source,
        timeout=15,
    )
    if not result_ready:
        screenshot(driver, f"error_step3_search_result_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 查询结果未出现订单 {ORDER_ID}")

    screenshot(driver, f"step3_search_result_{cycle_num}")
    if not click_record_result(driver):
        screenshot(driver, f"error_step3_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 录制按钮未出现或点击后确认弹窗未出现")

    print(f"    第{cycle_num}次 - 已点击目标订单的'{TEXT_RECORD_BTN}'，确认弹窗已出现")
    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step3_record_btn_{cycle_num}")
    return True


def step4_confirm_popup(driver, cycle_num):
    """Step 4: 弹窗确认"""
    print(f"\n[Step 4] 弹窗点击'{TEXT_CONFIRM}'...")

    # 动态等待弹窗出现
    max_polls = int(POPUP_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if record_confirmation_visible(driver):
            print(f"    第{cycle_num}次 - 弹窗元素检测到(iter {wait_idx})")
            break
        time.sleep(POLL_INTERVAL_NORMAL)

    # 精确文字优先：通用弹窗 footer 选择器可能首先匹配左侧“取消”。
    if webview_click(driver, [
        ("xpath", f"//button[normalize-space(.)='{TEXT_CONFIRM}']"),
        ("xpath", "//button[normalize-space(.)='确定']"),
    ]):
        print(f"    第{cycle_num}次 - WebView点击'{TEXT_CONFIRM}'成功")
        time.sleep(POLL_INTERVAL_SLOW)
        screenshot(driver, f"step4_confirm_{cycle_num}")
        return True

    # 尝试 Appium mobile alert 命令
    try:
        driver.execute_script("mobile: alert", {"action": "accept"})
        print(f"    第{cycle_num}次 - mobile:alert accept 成功")
        time.sleep(POLL_INTERVAL_SLOW)
        screenshot(driver, f"step4_confirm_{cycle_num}")
        return True
    except:
        pass

    # 尝试原生 Alert
    try:
        WebDriverWait(driver, 2).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        alert.accept()
        print(f"    第{cycle_num}次 - 原生Alert确认成功")
        time.sleep(POLL_INTERVAL_SLOW)
        screenshot(driver, f"step4_confirm_{cycle_num}")
        return True
    except:
        pass

    # 尝试原生 iOS 按钮
    try:
        alert_buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            f"type == 'XCUIElementTypeButton' AND (name == '{TEXT_CONFIRM}' OR name == '确定')")
        for btn in alert_buttons:
            if btn.is_displayed():
                btn.click()
                print(f"    第{cycle_num}次 - iOS原生按钮点击成功")
                time.sleep(POLL_INTERVAL_SLOW)
                screenshot(driver, f"step4_confirm_{cycle_num}")
                return True
    except:
        pass

    # 兜底：遍历所有按钮找"确定"或"确认"
    try:
        all_buttons = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeButton')
        for btn in all_buttons:
            name = btn.get_attribute('name') or ''
            if (TEXT_CONFIRM in name or '确定' in name) and btn.is_displayed():
                btn.click()
                print(f"    第{cycle_num}次 - 兜底点击'{TEXT_CONFIRM}'成功")
                time.sleep(POLL_INTERVAL_SLOW)
                screenshot(driver, f"step4_confirm_{cycle_num}")
                return True
    except:
        pass

    screenshot(driver, f"error_step4_{cycle_num}")
    raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_CONFIRM}'按钮")


def step5_click_agree_and_start(driver, cycle_num):
    """Step 5: 点击'同意并开始录制'"""
    print(f"\n[Step 5] 点击'{TEXT_AGREE_AND_START}'...")

    # 等待按钮出现并可点击
    btn_found = False
    max_polls = int(AGREE_BTN_TIMEOUT / POLL_INTERVAL_SLOW)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if TEXT_AGREE_AND_START in source or TEXT_AGREE_AND_START_DUAL in source:
            print(f"    第{cycle_num}次 - 检测到按钮元素(iter {wait_idx})")

            # 尝试找到按钮并点击
            try:
                buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                    f"(name CONTAINS '{TEXT_AGREE_AND_START}' OR name CONTAINS '{TEXT_AGREE_AND_START_DUAL}') AND type == 'XCUIElementTypeButton'")
                for btn in buttons:
                    if btn.is_displayed():
                        # 如果按钮不可用，尝试滚动
                        if not btn.is_enabled():
                            print(f"    第{cycle_num}次 - 按钮禁用，尝试滚动...")
                            driver.execute_script("mobile: scroll", {"direction": "up"})
                            time.sleep(POLL_INTERVAL_SLOW)
                            continue
                        btn.click()
                        print(f"    第{cycle_num}次 - 点击'{TEXT_AGREE_AND_START}'成功")
                        btn_found = True
                        break
            except:
                pass

            if btn_found:
                break

        time.sleep(POLL_INTERVAL_SLOW)

    if not btn_found:
        # 最后尝试：使用 WebView 或 JS 点击
        if webview_click(driver, [
            ("xpath", f"//button[contains(text(),'{TEXT_AGREE_AND_START}')]"),
            ("xpath", f"//button[contains(text(),'{TEXT_AGREE_AND_START_DUAL}')]"),
            ("css", CSS_AGREE_BTN),
        ]):
            print(f"    第{cycle_num}次 - WebView点击'{TEXT_AGREE_AND_START}'成功")
            btn_found = True

    if not btn_found:
        screenshot(driver, f"error_step5_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_AGREE_AND_START}'按钮")

    # 系统直播弹窗可能已经出现，立即交给下一步处理，避免截图阻塞点击。
    return True


def visible_ios_text(driver, text):
    """系统弹窗和 H5 文本可能不是 Button，按可见的精确文字查找。"""
    elements = driver.find_elements(
        AppiumBy.IOS_PREDICATE,
        f"name == '{text}' OR label == '{text}' OR value == '{text}'",
    )
    return next((element for element in elements if element.is_displayed()), None)


def tap_ios_text(driver, text):
    element = visible_ios_text(driver, text)
    if element is None or not element.is_enabled():
        return False
    rect = element.rect
    if rect['width'] <= 0 or rect['height'] <= 0:
        return False
    driver.tap([(int(rect['x'] + rect['width'] / 2),
                 int(rect['y'] + rect['height'] / 2))])
    return True


def click_pure_recording_broadcast(driver, text):
    """纯录制横屏系统弹窗：使用元素原生点击，避免屏幕坐标旋转偏移。"""
    elements = driver.find_elements(
        AppiumBy.IOS_PREDICATE,
        f"name CONTAINS '{text}' OR label CONTAINS '{text}' OR value CONTAINS '{text}'",
    )
    # 系统弹窗文字可能带换行；只接受完整按钮文案，不能误点底层业务按钮。
    for element in elements:
        labels = [element.get_attribute(key) for key in ('name', 'label', 'value')]
        if not any(''.join(str(label or '').split()) == text for label in labels):
            continue
        if element.is_displayed() and element.is_enabled():
            element.click()
            return True
    return False


def step6_click_start_live(driver, cycle_num, pure_recording=False):
    """ReplayKit 弹窗在 SpringBoard，必须允许 WDA 优先识别系统弹窗。"""
    driver.switch_to.context('NATIVE_APP')
    previous = driver.get_settings()
    keys = ('defaultActiveApplication', 'activeAppDetectionPoint', 'waitForIdleTimeout',
            'respectSystemAlerts', 'autoAcceptAlerts')
    defaults = dict(defaultActiveApplication='auto', activeAppDetectionPoint='64.00,64.00',
                    waitForIdleTimeout=10, respectSystemAlerts=False,
                    autoAcceptAlerts=AUTO_ACCEPT_ALERTS)
    restore = {key: previous.get(key, defaults[key]) for key in keys}
    size = driver.get_window_size()
    try:
        driver.update_settings({
            'defaultActiveApplication': 'auto',
            'activeAppDetectionPoint': f"{size['width'] / 2:.2f},{size['height'] / 2:.2f}",
            'waitForIdleTimeout': 0,
            # 否则即使弹窗可见，WDA 仍查询底层业务 App，检测点/进程设置无效。
            'respectSystemAlerts': True,
            'autoAcceptAlerts': False,
        })
        if pure_recording:
            return start_live_in_active_app(driver, cycle_num,
                                            start_tap=click_pure_recording_broadcast)
        return start_live_in_active_app(driver, cycle_num)
    finally:
        driver.update_settings(restore)


def start_live_in_active_app(driver, cycle_num, start_tap=None):
    """Step 6: 点击 iOS 开始直播，并确认启动状态。"""
    print(f"\n[Step 6] 点击'{TEXT_START_LIVE}'...")

    driver.switch_to.context('NATIVE_APP')
    started = time.monotonic()
    deadline = started + 30
    clicked = False
    start_tap = start_tap or tap_ios_text
    last_process = None
    while time.monotonic() < deadline:
        # 弹窗出现后优先点击，不先查询尚未出现的检测页或执行截图。
        if not clicked:
            lookup_started = time.monotonic()
            if start_tap(driver, TEXT_START_LIVE):
                clicked = True
                print(f"    第{cycle_num}次 - 已点击'开始直播'，"
                      f"本轮定位及点击耗时 {time.monotonic() - lookup_started:.2f}s，"
                      f"本步骤累计 {time.monotonic() - started:.2f}s")
            else:
                active = driver.execute_script('mobile: activeAppInfo')
                process = active.get('bundleId')
                if process != last_process:
                    print(f"    直播按钮暂未找到，当前活动应用: {process}，"
                          f"本轮查询耗时 {time.monotonic() - lookup_started:.2f}s")
                    last_process = process
        if visible_ios_text(driver, TEXT_AGREE_CHECK) is not None:
            screenshot(driver, f"step6_detection_ready_{cycle_num}")
            return True
        if visible_ios_text(driver, '停止直播') is not None:
            print(f"    第{cycle_num}次 - 直播已启动，等待倒计时结束")
            return True
        if not clicked:
            for label in (TEXT_IMMEDIATELY_START,):
                if start_tap(driver, label):
                    clicked = True
                    print(f"    第{cycle_num}次 - 已点击'{label}'，等待启动状态")
                    break
        # 此处不能重点击底层“同意并开始双录”：系统弹窗漏检时会误点遮罩。
        time.sleep(0.1)

    # 截图调试：最终失败截图
    screenshot(driver, f"error_step6_{cycle_num}")
    raise Exception(f"第{cycle_num}次 - 直播未启动或同意检测页面未出现")


def step7_wait_countdown_and_agree(driver, cycle_num):
    """Step 7: 3s倒计时后点击'同意检测'
    注意：如果界面已显示检测未通过（有"跳过"按钮），则跳过此步骤
    """
    print(f"\n[Step 7] 等待{COUNTDOWN_SECONDS}s倒计时后点击'{TEXT_AGREE_CHECK}'...")

    wait_countdown(driver, COUNTDOWN_SECONDS)

    # 先检查当前界面是否已经是检测未通过界面（有"跳过"按钮）
    page_source = driver.page_source
    if TEXT_SKIP in page_source and TEXT_RECHECK in page_source:
        print(f"    第{cycle_num}次 - 已是检测未通过界面，跳过等待")
        screenshot(driver, f"step7_skip_{cycle_num}")
        return True

    # 点击"同意检测"按钮
    deadline = time.monotonic() + max(30, AGREE_CHECK_TIMEOUT)
    while time.monotonic() < deadline:
        # 倒计时/系统弹窗未结束时等待，绝不点击“停止直播”。
        if visible_ios_text(driver, '停止直播') is not None:
            time.sleep(0.3)
            continue
        clicked = tap_ios_text(driver, TEXT_AGREE_CHECK)
        if not clicked:
            clicked = webview_click(driver, [
                ('xpath', "//button[normalize-space(.)='同意检测']"),
            ])
        if clicked:
            # 点击不等于生效；等待提示按钮消失再继续检测结果步骤。
            transition_deadline = time.monotonic() + 5
            while time.monotonic() < transition_deadline:
                source = driver.page_source
                if TEXT_AGREE_CHECK not in source:
                    print(f"    第{cycle_num}次 - 已点击'{TEXT_AGREE_CHECK}'并离开检测提示")
                    screenshot(driver, f"step7_agree_{cycle_num}")
                    return True
                time.sleep(0.3)
        time.sleep(0.3)

    screenshot(driver, f"error_step7_{cycle_num}")
    raise Exception(f"第{cycle_num}次 - 同意检测未出现或点击后未进入检测流程")

def step8_self_service_detection(driver, cycle_num):
    """Step 8: 自助业务 - 检测结果分支处理
    逻辑：
    1. 等待页面判断是"检测未通过"还是"检测通过"
    2. 如果检测未通过 → 点击"跳过" → 自动跳转到播报节点
    3. 如果检测通过，自动跳转到播报节点
    4. 播报/朗读后逐字输入测试签字并提交
    5. 严格等待业务办理完成界面
    注意：自助业务流程没有"完成录制"按钮
    """
    print("\n[Step 8] 自助业务检测结果分支处理...")

    # 先等待判断当前页面状态
    page_state = None
    detection_deadline = time.monotonic() + DETECTION_TIMEOUT
    while time.monotonic() < detection_deadline:
        source = driver.page_source
        if '请客户进行签字' in source or '业务办理完成' in source:
            break
        if TEXT_RECHECK in source or TEXT_SKIP in source:
            page_state = 'detect_fail'
            print(f"    第{cycle_num}次 - 检测未通过界面")
            break
        if TEXT_START_RECORD in source:
            page_state = 'detect_pass'
            print(f"    第{cycle_num}次 - 检测通过界面")
            break
        time.sleep(POLL_INTERVAL_SLOW)

    if page_state == 'detect_fail':
        # 分支1：检测未通过 → 点击"跳过" → 自动跳转到播报节点
        print(f"    第{cycle_num}次 - [分支1] 检测未通过，点击跳过")

        success = find_and_click_button(driver, TEXT_SKIP, timeout=10)
        if success:
            print(f"    第{cycle_num}次 - 已点击'{TEXT_SKIP}'")
        else:
            screenshot(driver, f"error_step8_skip_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_SKIP}'按钮")

        time.sleep(POLL_INTERVAL_SLOW)
        screenshot(driver, f"step8_skip_{cycle_num}")

        # 风险提示弹窗 - 点击确认
        if webview_click(driver, [
            ("css", CSS_DIALOG_CONFIRM),
            ("css", CSS_DIALOG_CONFIRM_BTN),
            ("xpath", f"//button[contains(text(),'{TEXT_CONFIRM}')]"),
        ]):
            print(f"    第{cycle_num}次 - 风险提示弹窗点击'{TEXT_CONFIRM}'成功")
        else:
            success, _ = click_element(driver, [
                ("predicate", f"name CONTAINS '{TEXT_CONFIRM}' AND type == 'XCUIElementTypeButton'"),
                ("xpath", f'//XCUIElementTypeButton[@name="{TEXT_CONFIRM}"]'),
            ], timeout=5)
            if success:
                print(f"    第{cycle_num}次 - 原生点击'{TEXT_CONFIRM}'成功")

        time.sleep(POLL_INTERVAL_SLOW)
        screenshot(driver, f"step8_risk_confirm_{cycle_num}")

    else:
        print(f"    第{cycle_num}次 - 等待播报、测试签字及业务完成")

    return wait_self_service_completion(driver, cycle_num, screenshot, CUSTOMER_NAME)


def step8_pure_record_detection(driver, cycle_num):
    """检测结果、跳过/风险确认、开始录制分别核验。"""
    print("\n[Step 8] 纯录制业务检测结果处理...")
    return detect_and_start(driver, cycle_num, screenshot, timeout=DETECTION_TIMEOUT)


def step8_click_agree_detection(driver, cycle_num):
    """Step 8: 点击'开始录制'（根据检测结果分支处理）- 兼容性别名，实际分发到具体业务"""
    # 根据当前业务类型选择对应的处理函数
    # 此处默认走纯录制逻辑，自助业务会直接调用step8_self_service_detection
    return step8_pure_record_detection(driver, cycle_num)


def step9_detection_not_pass(driver, cycle_num):
    """Step 9: 检测未通过分支"""
    print("\n[Step 9] 检测未通过分支...")

    # 等待检测结果界面
    max_polls = int(DETECTION_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if TEXT_RECHECK in source or TEXT_SKIP in source:
            print(f"    第{cycle_num}次 - 检测结果界面出现(iter {wait_idx})")
            break
        time.sleep(POLL_INTERVAL_NORMAL)

    screenshot(driver, f"step9_detection_result_{cycle_num}")

    # 点击"跳过"按钮
    success = find_and_click_button(driver, TEXT_SKIP, timeout=10)
    if success:
        print(f"    第{cycle_num}次 - 已点击'{TEXT_SKIP}'")
    else:
        screenshot(driver, f"error_step9_skip_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_SKIP}'按钮")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step9_skip_{cycle_num}")

    # 风险提示弹窗 - 点击确认
    if webview_click(driver, [
        ("css", CSS_DIALOG_CONFIRM),
        ("css", CSS_DIALOG_CONFIRM_BTN),
        ("xpath", f"//button[contains(text(),'{TEXT_CONFIRM}')]"),
    ]):
        print(f"    第{cycle_num}次 - 风险提示弹窗点击'{TEXT_CONFIRM}'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", f"name CONTAINS '{TEXT_CONFIRM}' AND type == 'XCUIElementTypeButton'"),
            ("xpath", f'//XCUIElementTypeButton[@name="{TEXT_CONFIRM}"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'{TEXT_CONFIRM}'成功")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step9_risk_confirm_{cycle_num}")

    # 等待"开始录制"按钮
    success = find_and_click_button(driver, TEXT_START_RECORD, timeout=RECORD_BTN_TIMEOUT)
    if success:
        print(f"    第{cycle_num}次 - 已点击'{TEXT_START_RECORD}'")
    else:
        screenshot(driver, f"error_step9_start_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_START_RECORD}'按钮")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step9_start_record_{cycle_num}")

    return True


def step9_detection_pass(driver, cycle_num):
    """Step 9.1: 检测通过分支"""
    print("\n[Step 9.1] 检测通过分支...")

    # 等待倒计时
    wait_countdown(driver, COUNTDOWN_SECONDS)

    # 点击"开始录制"按钮
    success = find_and_click_button(driver, TEXT_START_RECORD, timeout=RECORD_BTN_TIMEOUT)
    if success:
        print(f"    第{cycle_num}次 - 已点击'{TEXT_START_RECORD}'")
    else:
        screenshot(driver, f"error_step9_1_start_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_START_RECORD}'按钮")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step9_1_start_record_{cycle_num}")

    return True


def click_record_control(driver, label, timeout=10, toolbar=False, web_first=False):
    """录制控件可暴露为 StaticText/Other；按精确文本及实际位置点击。"""
    if web_first and toolbar and click_pure_toolbar(driver, label, switch_to_webview):
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        driver.switch_to.context('NATIVE_APP')
        size = driver.get_window_size()
        candidates = driver.find_elements(
            AppiumBy.IOS_PREDICATE,
            f"name == '{label}' OR label == '{label}' OR value == '{label}'",
        )
        for element in candidates:
            if not element.is_displayed() or not element.is_enabled():
                continue
            rect = element.rect
            x = rect['x'] + rect['width'] / 2
            y = rect['y'] + rect['height'] / 2
            if rect['width'] <= 0 or rect['height'] <= 0:
                continue
            if not (0 <= x < size['width'] and 0 <= y < size['height']):
                continue
            if toolbar and y > size['height'] * 0.25:
                continue
            driver.tap([(int(x), int(y))])
            return True

        # H5 工具栏通常由 span/div 构成，不限定为 HTML button。
        if switch_to_webview(driver):
            try:
                elements = driver.find_elements(
                    By.XPATH,
                    f"//*[normalize-space(.)='{label}' and not(*[normalize-space(.)='{label}'])]",
                )
                for element in elements:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    eligible = driver.execute_script(
                        "const e=arguments[0], r=e.getBoundingClientRect();"
                        "return !e.closest('[disabled], [aria-disabled=\"true\"], .van-button--disabled')"
                        " && r.width>0 && r.height>0 && r.top>=0"
                        " && (!arguments[1] || r.bottom<=window.innerHeight*0.25);",
                        element, toolbar,
                    )
                    if eligible:
                        element.click()
                        return True
            finally:
                driver.switch_to.context('NATIVE_APP')
        time.sleep(0.3)
    return False


def exercise_customer_record_controls(driver, cycle_num):
    """同步 Android 已跑通流程：暂停、继续录制并截图。"""
    print(f"    第{cycle_num}次 - 点击'{TEXT_PAUSE_RECORD}'")
    if not click_record_control(driver, TEXT_PAUSE_RECORD, toolbar=True, web_first=True):
        screenshot(driver, f"error_record_pause_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_PAUSE_RECORD}'按钮")

    print(f"    第{cycle_num}次 - 等待'{TEXT_CONTINUE_RECORD}'恢复可点击")
    try:
        ensure_pure_recording_resumed(driver, cycle_num, switch_to_webview)
    except Exception:
        screenshot(driver, f"error_record_continue_{cycle_num}")
        raise
    wait_countdown(driver, COUNTDOWN_SECONDS)

    print(f"    第{cycle_num}次 - 点击'{TEXT_SCREENSHOT}'")
    if not click_record_control(driver, TEXT_SCREENSHOT, toolbar=True, web_first=True):
        screenshot(driver, f"error_record_screenshot_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_SCREENSHOT}'按钮")
    screenshot(driver, f"step10_record_controls_{cycle_num}")
    time.sleep(WAIT_SCREENSHOT_BEFORE_END)
    # 截图/切换前后台后可能再次弹出“流程暂停中”，结束录制前重新确认。
    ensure_pure_recording_resumed(driver, cycle_num, switch_to_webview)


def step10_record_flow(driver, cycle_num):
    """Step 10: 录制流程（结束录制、确认完成）"""
    print("\n[Step 10] 录制流程...")

    # 等待倒计时
    wait_countdown(driver, COUNTDOWN_SECONDS)

    exercise_customer_record_controls(driver, cycle_num)

    # 点击"结束录制"按钮
    success = find_and_click_button(driver, TEXT_END_RECORD, timeout=END_RECORD_TIMEOUT)
    if success:
        print(f"    第{cycle_num}次 - 已点击'{TEXT_END_RECORD}'")
    else:
        screenshot(driver, f"error_step10_end_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_END_RECORD}'按钮")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step10_record_end_{cycle_num}")

    # 点击"确认完成"按钮
    success = find_and_click_button(driver, TEXT_CONFIRM_COMPLETE, timeout=CONFIRM_TIMEOUT)
    if success:
        print(f"    第{cycle_num}次 - 已点击'{TEXT_CONFIRM_COMPLETE}'")
    else:
        screenshot(driver, f"error_step10_confirm_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_CONFIRM_COMPLETE}'按钮")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step10_confirm_{cycle_num}")

    # 业务完成弹窗 - 点击确认
    if webview_click(driver, [
        ("css", CSS_DIALOG_CONFIRM),
        ("css", CSS_DIALOG_CONFIRM_BTN),
        ("xpath", f"//button[contains(text(),'{TEXT_CONFIRM}')]"),
    ]):
        print(f"    第{cycle_num}次 - 业务完成弹窗点击'{TEXT_CONFIRM}'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", f"name CONTAINS '{TEXT_CONFIRM}' AND type == 'XCUIElementTypeButton'"),
            ("xpath", f'//XCUIElementTypeButton[@name="{TEXT_CONFIRM}"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'{TEXT_CONFIRM}'成功")

    time.sleep(1)
    screenshot(driver, f"step10_business_complete_{cycle_num}")

    return True


def step10_self_service_flow(driver, cycle_num):
    """Step 10: 自助业务播报+朗读流程"""
    print("\n[Step 10] 自助业务播报+朗读流程...")

    # 等待播报节点出现
    max_polls = int(BROADCAST_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if '播报' in source or TEXT_NEXT_STEP in source:
            print(f"    第{cycle_num}次 - 播报节点出现(iter {wait_idx})")
            break
        time.sleep(POLL_INTERVAL_NORMAL)
    screenshot(driver, f"step10_broadcast_{cycle_num}")

    # 等待播报完成（等待"下一步"按钮可点击）
    print(f"    第{cycle_num}次 - 等待播报完成...")
    max_polls = int(BROADCAST_READING_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        try:
            buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                f"name == '{TEXT_NEXT_STEP}' AND type == 'XCUIElementTypeButton'")
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    print(f"    第{cycle_num}次 - 已点击'{TEXT_NEXT_STEP}'(播报->朗读)")
                    time.sleep(POLL_INTERVAL_SLOW)
                    break
        except:
            pass
        time.sleep(POLL_INTERVAL_NORMAL)
    screenshot(driver, f"step10_broadcast_done_{cycle_num}")

    # 等待朗读节点出现并点击"完成录制"
    max_polls = int(BUSINESS_COMPLETE_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if TEXT_FINISH_RECORD in source or '朗读' in source:
            print(f"    第{cycle_num}次 - 朗读节点出现(iter {wait_idx})")
            break
        time.sleep(POLL_INTERVAL_NORMAL)
    screenshot(driver, f"step10_reading_{cycle_num}")

    # 点击"完成录制"按钮
    success = find_and_click_button(driver, TEXT_FINISH_RECORD, timeout=CONFIRM_TIMEOUT)
    if success:
        print(f"    第{cycle_num}次 - 已点击'{TEXT_FINISH_RECORD}'")
    else:
        screenshot(driver, f"error_step10_reading_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_FINISH_RECORD}'按钮")

    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step10_reading_done_{cycle_num}")

    # 业务完成弹窗 - 点击确认
    if webview_click(driver, [
        ("css", CSS_DIALOG_CONFIRM),
        ("css", CSS_DIALOG_CONFIRM_BTN),
        ("xpath", f"//button[contains(text(),'{TEXT_CONFIRM}')]"),
    ]):
        print(f"    第{cycle_num}次 - 业务完成弹窗点击'{TEXT_CONFIRM}'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", f"name CONTAINS '{TEXT_CONFIRM}' AND type == 'XCUIElementTypeButton'"),
            ("xpath", f'//XCUIElementTypeButton[@name="{TEXT_CONFIRM}"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'{TEXT_CONFIRM}'成功")

    time.sleep(1)
    screenshot(driver, f"step10_business_complete_{cycle_num}")

    return True


def step11_upload_file(driver, cycle_num):
    """上传成功必须明确出现，确认后须进入后续页面。"""
    print("\n[Step 11] 文件上传...")
    return wait_upload(driver, cycle_num, screenshot, timeout=UPLOAD_TIMEOUT)


def step12_click_end(driver, cycle_num):
    """Step 12: 点击'结束'按钮"""
    print(f"\n[Step 12] 点击'{TEXT_END}'按钮...")

    source = driver.page_source
    if '业务办理完成' in source or TEXT_RETURN in source:
        print(f"    第{cycle_num}次 - 已进入业务办理完成页，跳过'{TEXT_END}'")
        screenshot(driver, f"step12_business_complete_{cycle_num}")
        return True

    # 先等待文件上传成功弹窗消失
    max_polls = int(RETURN_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if TEXT_UPLOAD_SUCCESS not in source and TEXT_UPLOAD_SUCCESS2 not in source:
            print(f"    第{cycle_num}次 - 上传成功弹窗已消失(iter {wait_idx})")
            break
        time.sleep(POLL_INTERVAL_NORMAL)

    time.sleep(POLL_INTERVAL_SLOW)  # 短暂等待后点击结束按钮

    end_clicked = False

    # 切换到 WebView，点击"结束"按钮
    if switch_to_webview(driver):
        try:
            btn = driver.find_element(By.XPATH, f"//*[contains(text(),'{TEXT_END}')]")
            if btn.is_displayed():
                driver.execute_script("arguments[0].scrollIntoViewIfNeeded(); arguments[0].click();", btn)
                switch_to_native(driver)
                print(f"    第{cycle_num}次 - WebView XPath点击'{TEXT_END}'成功")
                time.sleep(POLL_INTERVAL_SLOW)
                screenshot(driver, f"step12_end_{cycle_num}")
                end_clicked = True
        except Exception as e:
            print(f"    WebView XPath点击失败: {e}")
            switch_to_native(driver)

    # 兜底：原生按钮（仅当WebView方式失败时）
    if not end_clicked:
        success = find_and_click_button(driver, TEXT_END, timeout=END_TIMEOUT)
        if success:
            print(f"    第{cycle_num}次 - 已点击'{TEXT_END}'")
        else:
            screenshot(driver, f"error_step12_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_END}'按钮")

        time.sleep(POLL_INTERVAL_SLOW)
        screenshot(driver, f"step12_end_{cycle_num}")

    # 等待"结束办理"弹窗出现并点击"确认"
    max_polls = int(CONFIRM_LOGOUT_TIMEOUT / POLL_INTERVAL_NORMAL)
    for wait_idx in range(max_polls):
        source = driver.page_source
        if TEXT_END_SERVICE in source or TEXT_END_SERVICE2 in source or TEXT_SERVICE_ENDED in source:
            print(f"    第{cycle_num}次 - 结束办理弹窗出现(iter {wait_idx})")
            # 使用H5 webview方式点击"确认"
            if webview_click(driver, [
                ("css", CSS_DIALOG_CONFIRM),
                ("css", CSS_DIALOG_CONFIRM_BTN),
                ("xpath", f"//button[contains(text(),'{TEXT_CONFIRM}')]"),
            ]):
                print(f"    第{cycle_num}次 - H5点击'{TEXT_CONFIRM}'成功")
                time.sleep(POLL_INTERVAL_SLOW)
                screenshot(driver, f"step12_end_confirm_{cycle_num}")
                return True
            time.sleep(POLL_INTERVAL_NORMAL)
        else:
            time.sleep(POLL_INTERVAL_NORMAL)

    # 弹窗未出现但流程继续
    print(f"    第{cycle_num}次 - 结束办理弹窗未出现，继续流程")
    return True


def step13_click_return(driver, cycle_num):
    """点击返回后必须核验纯录制订单列表，不能仅凭点击成功继续登出。"""
    print("\n[Step 13] 返回纯录制订单列表...")
    return return_to_order_list(driver, cycle_num, screenshot, timeout=RETURN_TIMEOUT)


def step14_go_to_my_and_logout(driver, cycle_num):
    """Step 14: 进入我的页面并退出登录"""
    print("\n[Step 14] 进入我的页面并退出登录...")
    return logout_customer_ios(driver, cycle_num, screenshot)


def step13_self_service_return_and_open_my(driver, cycle_num):
    print("\n[Step 13] 自助完成页返回列表并进入我的页面...")
    return return_and_open_my(driver, cycle_num, screenshot, timeout=RETURN_TIMEOUT)


def step15_home_button(driver, cycle_num):
    """Step 15: 点击 Home 键返回桌面"""
    print("\n[Step 15] 点击 Home 键返回桌面...")
    try:
        driver.execute_script("mobile: pressButton", {"name": "home"})
        print(f"    第{cycle_num}次 - 已点击 Home 键")
    except Exception as e:
        print(f"    Home 键点击失败: {e}")
    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step15_home_{cycle_num}")
    return True


def run_test_cycle(driver, cycle_num, detect_mode="auto"):
    """执行一次测试循环

    Args:
        driver: WebDriver 实例
        cycle_num: 循环编号
        detect_mode: "auto" 自动判断, "not_pass" 强制未通过分支, "pass" 强制通过分支
    """
    print(f"\n{'='*60}")
    print(f"开始第 {cycle_num} 次测试 (检测模式: {detect_mode})")
    print(f"{'='*60}")

    previous_settings = driver.get_settings()
    cycle_started = time.monotonic()
    try:
        # 录制画面持续变化，默认 idle 等待会反复拖慢输入、键盘和工具栏操作。
        # 仅纯录制周期生效，直播步骤仍自行管理系统弹窗设置。
        driver.update_settings({'waitForIdleTimeout': 0})
        # Step 1: 客户登录
        step1_login(driver, cycle_num, fast_input=True, direct_input=True)

        # Step 2: 点击"纯录制"菜单
        step2_click_pure_recording(driver, cycle_num)

        # Step 3: 订单列表点击"录制"按钮
        step3_click_record_in_list(driver, cycle_num, fast_search=True, dom_search=True)

        # Step 4: 弹窗确认
        step4_confirm_popup(driver, cycle_num)

        # Step 5: 点击"同意并开始录制"
        step5_click_agree_and_start(driver, cycle_num)

        # Step 6: 点击"开始直播"
        step6_click_start_live(driver, cycle_num, pure_recording=True)

        # Step 7: 3s倒计时后再次点击"同意并开始录制"
        step7_wait_countdown_and_agree(driver, cycle_num)

        # Step 8: 点击"同意检测"
        step8_click_agree_detection(driver, cycle_num)

        # Step 9: Step 8 已内部分支处理检测结果，此处直接进入 Step 10
        # Step 10: 录制流程
        step10_record_flow(driver, cycle_num)

        # Step 11: 文件上传
        step11_upload_file(driver, cycle_num)

        # Step 12: 点击"结束"按钮
        step12_click_end(driver, cycle_num)

        # Step 13: 点击"返回"按钮
        step13_click_return(driver, cycle_num)

        # Step 14: 进入我的页面并退出登录
        step14_go_to_my_and_logout(driver, cycle_num)

        # Step 15: 点击 Home 键
        step15_home_button(driver, cycle_num)

        print(f"\n第 {cycle_num} 次测试完成！")
        return True

    except Exception as e:
        screenshot(driver, f"error_cycle_{cycle_num}")
        print(f"\n[第 {cycle_num} 次测试失败] {str(e)}")
        raise
    finally:
        driver.update_settings({'waitForIdleTimeout': previous_settings.get('waitForIdleTimeout', 10)})
        print(f"    第{cycle_num}次 - 纯录制周期耗时 {time.monotonic() - cycle_started:.2f}s")


def run_self_service_cycle(driver, cycle_num, detect_mode="auto"):
    """执行一次自助业务测试循环

    Args:
        driver: WebDriver 实例
        cycle_num: 循环编号
        detect_mode: "auto" 自动判断, "not_pass" 强制未通过分支, "pass" 强制通过分支
    """
    print(f"\n{'='*60}")
    print(f"开始第 {cycle_num} 次自助业务测试 (检测模式: {detect_mode})")
    print(f"{'='*60}")

    previous_settings = driver.get_settings()
    cycle_started = time.monotonic()
    try:
        # 自助双录同样持续播放/采集画面，使用状态核验代替 WDA 的空闲等待。
        driver.update_settings({'waitForIdleTimeout': 0})
        # Step 1: 客户登录
        step1_login(driver, cycle_num, fast_input=True)

        # Step 2: 点击"自助"菜单
        step2_click_self_service(driver, cycle_num)

        # Step 3: 订单列表点击"录制"按钮
        step3_click_record_in_list(driver, cycle_num, fast_search=True)

        # Step 4: 弹窗确认
        step4_confirm_popup(driver, cycle_num)

        # Step 5: 点击"同意并开始双录"
        step5_click_agree_and_start(driver, cycle_num)

        # Step 6: 点击"开始直播"
        step6_click_start_live(driver, cycle_num)

        # Step 7: 3s倒计时后点击"同意检测"
        step7_wait_countdown_and_agree(driver, cycle_num)

        # Step 8: 检测结果分支处理（播报+朗读自动完成约24s）
        step8_self_service_detection(driver, cycle_num)

        # 连续处理完成页返回和列表导航，不在两次点击之间读取原生树或截图。
        step13_self_service_return_and_open_my(driver, cycle_num)

        # Step 13: 进入我的页面并退出登录
        step14_go_to_my_and_logout(driver, cycle_num)

        # Step 14: 点击 Home 键
        step15_home_button(driver, cycle_num)

        print(f"\n第 {cycle_num} 次自助业务测试完成！")
        return True

    except Exception as e:
        screenshot(driver, f"error_self_cycle_{cycle_num}")
        print(f"\n[第 {cycle_num} 次自助业务测试失败] {str(e)}")
        raise
    finally:
        driver.update_settings({'waitForIdleTimeout': previous_settings.get('waitForIdleTimeout', 10)})
        print(f"    第{cycle_num}次 - 自助双录周期耗时 {time.monotonic() - cycle_started:.2f}s")


def main():
    global ORDER_ID
    from config_pure_recording import ORDER_ID as pure_record_order_id

    loop_count = 1
    detect_mode = "auto"  # 默认自动判断检测结果
    test_type = "pure_record"  # 默认纯录制测试

    if len(sys.argv) > 1:
        if sys.argv[1] == "self":
            test_type = "self_service"
            if len(sys.argv) > 2:
                try:
                    loop_count = int(sys.argv[2])
                except ValueError:
                    loop_count = 1
        elif sys.argv[1] == "self_service":
            test_type = "self_service"
            if len(sys.argv) > 2:
                try:
                    loop_count = int(sys.argv[2])
                except ValueError:
                    loop_count = 1
        else:
            try:
                loop_count = int(sys.argv[1])
            except ValueError:
                loop_count = 1
            if len(sys.argv) > 2:
                detect_mode = sys.argv[2]  # not_pass, pass, auto

    ORDER_ID = ORDER_ID_SELF_SERVICE if test_type == "self_service" else pure_record_order_id
    test_name = "自助业务" if test_type == "self_service" else "纯录制"
    print("=" * 60)
    print(f"iOS App {test_name}业务流程自动化测试")
    print(f"登录模式: {LOGIN_MODE}")
    print(f"Appium 地址: {APPIUM_URL}")
    print(f"WDA 地址: {WDA_URL}")
    print(f"UDID: {UDID}")
    print(f"Bundle ID: {BUNDLE_ID}")
    print(f"iOS 版本: {PLATFORM_VERSION}")
    print(f"循环次数: {loop_count} 次")
    print(f"检测模式: {detect_mode}")
    print(f"截图功能: {'开启' if ENABLE_SCREENSHOT else '关闭'}")
    print(f"订单号: {ORDER_ID}")
    print("=" * 60)

    # 检查并重置订单状态
    if not check_and_reset_order_state():
        print("[错误] 订单状态检查失败，退出测试")
        sys.exit(1)

    success_count = 0
    fail_count = 0

    for i in range(1, loop_count + 1):
        driver = None
        try:
            # 每次循环前检查并重置订单状态
            if not check_and_reset_order_state():
                print(f"[第 {i} 次] 订单状态检查失败，跳过本次测试")
                fail_count += 1
                continue

            options = get_desired_caps()
            # 由 Step 1 控制“结束旧进程 -> 冷启动 -> 登出旧账号”的顺序。
            options.set_capability('autoLaunch', False)
            driver = webdriver.Remote(APPIUM_URL, options=options)

            if test_type == "self_service":
                run_self_service_cycle(driver, i, detect_mode)
            else:
                run_test_cycle(driver, i, detect_mode)
            success_count += 1

        except Exception as e:
            fail_count += 1
            print(f"\n[第 {i} 次测试失败] {str(e)}")
            if driver:
                try:
                    terminate_previous_app(driver, BUNDLE_ID)
                    print(f"    第{i}次 - 异常业务 App 进程已结束")
                except Exception as cleanup_error:
                    print(f"    第{i}次 - 进程清理未完成，下轮启动前将重新强制清理: {cleanup_error}")
            print("    继续执行下一次测试...")

        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

        time.sleep(2)

    # 打印汇总结果
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    print(f"总循环次数: {loop_count}")
    print(f"成功次数: {success_count}")
    print(f"失败次数: {fail_count}")
    print(f"成功率: {success_count/loop_count*100:.1f}%")
    print("=" * 60)

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
