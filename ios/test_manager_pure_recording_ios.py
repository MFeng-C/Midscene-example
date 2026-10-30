"""
iOS 原生 App UI 自动化测试脚本 - 客户经理纯录制业务流程
WDA: http://172.16.2.134:8100
Appium: http://172.16.2.134:4723
iOS UDID: 7720cc4ebea57931c047c2cdc0a9fbc5f6cf0c5c
Bundle ID: com.juphoon.record.ios
测试流程：
  1. 客户经理登录（点击"客户经理登录"菜单，输入10001/Aa123456/0000）
  2. 点击"纯录制"菜单
  3. 订单列表点击"录制"按钮
  4. 弹窗确认
  5. 办理提示界面点击"同意并开始录制"
  6. 直播屏幕弹窗点击"开始直播"
  7. 3s倒计时后再次点击"同意并开始录制"
  8. 环境检测界面点击"同意检测"
  9. 分支处理：检测未通过/通过
  10. 录制流程（结束录制、确认完成）
  11. 文件上传
  12. 点击"结束"按钮
  13. 点击"返回"按钮
  14. 进入我的页面并退出登录
  15. 点击 Home 键返回桌面
支持循环执行
"""

import time
import os
import sys
from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scene_manual_nodes import advance_manual_nodes, finish_manual_nodes
from scene_record_controls import exercise_scene_controls
from scene_fast_paths import search_scene_order
from scene_broadcast_runtime import wait_detection_ready
from scene_ai_runtime import start_ai_recording, advance_ai_nodes, finish_ai_recording
from scene_ai_pages import click_ai_control
from scene_ai_recovery import ai_client_config, limit_failure_requests, end_failed_ai_cycle
from scene_ai_upload_failure import close_failed_upload
from scene_manual_runtime import SceneUploadFailed
from scene_manual_runtime import (reset_scene_order, prepare_manager, login_manager,
    return_scene_list, wait_upload_success, timed_step, capture_failure, open_scene_navigation,
    start_manual_recording, cleanup_session, wait_scene_transition, configure_scene_startup)
from ios_customer_logout import logout_customer_ios
from test_pure_recording_ios import (
    click_record_control as customer_click_record_control,
    switch_to_webview as customer_switch_to_webview,
    click_record_result as customer_click_record_result,
    step3_click_record_in_list as search_customer_order,
    step6_click_start_live as start_system_broadcast,
)


# 配置
WDA_URL = "http://172.16.2.134:8100"
APPIUM_URL = "http://172.16.2.134:4723"
UDID = "7720cc4ebea57931c047c2cdc0a9fbc5f6cf0c5c"
BUNDLE_ID = "com.juphoon.record.ios"
PLATFORM_VERSION = "17"
SCENE_ORDER_ID = "OD2109575721056833536"
SCENE_CUSTOMER_NAME = "郇伟"

# 截图保存目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(SCRIPT_DIR, "screenshots_manager_pure_recording")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# 是否截图（默认关闭）
ENABLE_SCREENSHOT = os.environ.get("SCREENSHOT", "0") == "1"


def get_desired_caps():
    """获取 Appium 配置"""
    options = XCUITestOptions()
    options.set_capability("platformName", "iOS")
    options.set_capability("automationName", "XCUITest")
    options.set_capability("deviceName", "iPhone")
    options.set_capability("platformVersion", PLATFORM_VERSION)
    options.set_capability("udid", UDID)
    options.set_capability("bundleId", BUNDLE_ID)
    options.set_capability("webDriverAgentUrl", WDA_URL)
    options.set_capability("noReset", True)
    options.set_capability("fullReset", False)
    options.set_capability("newCommandTimeout", 300)
    options.set_capability("wdaConnectionTimeout", 60000)
    options.set_capability("autoAcceptAlerts", True)
    options.set_capability("skipLogCapture", True)
    options.set_capability("enableWebviewDetails", True)
    options.set_capability("autoWebview", False)
    options.set_capability("ensureWebviewsHavePages", True)
    options.set_capability("webviewConnectTimeout", 30000)
    options.set_capability("webkitDebugProxyPort", 9221)
    options.set_capability("showXcodeLog", True)
    options.set_capability("newCommandTimeout", 60)
    options.set_capability("webviewConnectRetries", 30)
    options.set_capability("nativeWebTap", True)
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
                    time.sleep(0.2)
                    continue

                elem.click()
                return True, loc_type
            except:
                continue
        time.sleep(0.2)
    return False, None


def input_text(driver, locators, text, clear_first=True, timeout=5):
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
                else:
                    elem = driver.find_element(By.XPATH, loc_value)

                if elem and elem.is_displayed():
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
        time.sleep(0.2)
    return False


def clear_input_field(driver, locators, timeout=5):
    """清空输入框"""
    start = time.time()
    while time.time() - start < timeout:
        for loc_type, loc_value in locators:
            try:
                if loc_type == "xpath":
                    elem = driver.find_element(By.XPATH, loc_value)
                elif loc_type == "accessibility id":
                    elem = driver.find_element(AppiumBy.ACCESSIBILITY_ID, loc_value)
                else:
                    elem = driver.find_element(By.XPATH, loc_value)

                if elem and elem.is_displayed():
                    elem.click()
                    time.sleep(0.2)
                    # 全选并删除
                    elem.send_keys("")  # Ctrl+A
                    elem.send_keys("3")  # Delete
                    return True
            except:
                continue
        time.sleep(0.2)
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


def wait_countdown(driver, seconds=3):
    """等待倒计时"""
    print(f"   等待 {seconds}s 倒计时...")
    time.sleep(seconds + 0.5)  # 倒计时 + 缓冲


# ============================================================================
# 测试步骤函数
# ============================================================================

def step1_manager_login(driver, cycle_num):
    """Step 1: 客户经理登录"""
    print("\n[Step 1] 客户经理登录...")

    try:
        driver.activate_app(BUNDLE_ID)
        print(f"    第{cycle_num}次 - 已启动 App")
    except Exception as e:
        print(f"    第{cycle_num}次 - 启动 App: {e}")

    try:
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.XPATH, '//XCUIElementTypeButton[@name="客户经理登录"]')))
        print(f"    第{cycle_num}次 - 客户经理登录按钮出现")
    except:
        pass
    screenshot(driver, f"step1_launch_{cycle_num}")

    # 点击"客户经理登录"菜单
    success, loc_type = click_element(driver, [
        ("xpath", '//XCUIElementTypeButton[@name="客户经理登录"]'),
        ("xpath", '//*[contains(@name,"客户经理登录")]'),
        ("accessibility id", "客户经理登录"),
    ])
    if success:
        print(f"    第{cycle_num}次 - 已点击客户经理登录({loc_type})")
    else:
        screenshot(driver, f"error_step1_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'客户经理登录'按钮")

    try:
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.XPATH, '//XCUIElementTypeTextField[contains(@value,"工号")]')))
        print(f"    第{cycle_num}次 - 登录表单出现")
    except:
        pass
    screenshot(driver, f"step1_login_form_{cycle_num}")

    # 输入工号（先清空）
    success = input_text(driver, [
        ("xpath", '//XCUIElementTypeTextField[@value="请输入工号"]'),
        ("xpath", '//XCUIElementTypeTextField[contains(@value,"工号")]'),
        ("xpath", '//XCUIElementTypeTextField[1]'),
    ], "10001", clear_first=True)
    if not success:
        screenshot(driver, f"error_step1_id_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到工号输入框")
    print(f"    第{cycle_num}次 - 已输入工号")

    # 输入密码
    success = input_text(driver, [
        ("xpath", '//XCUIElementTypeSecureTextField[@value="请输入登录密码"]'),
        ("xpath", '//XCUIElementTypeSecureTextField[1]'),
    ], "Aa123456", clear_first=False)
    if not success:
        screenshot(driver, f"error_step1_pwd_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    print(f"    第{cycle_num}次 - 已输入密码")

    # 输入验证码
    success = input_text(driver, [
        ("xpath", '//XCUIElementTypeTextField[@value="请输入验证码"]'),
        ("xpath", '//XCUIElementTypeTextField[2]'),
    ], "0000", clear_first=True)
    if not success:
        screenshot(driver, f"error_step1_captcha_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    print(f"    第{cycle_num}次 - 已输入验证码")

    # 点击登录按钮
    success, loc_type = click_element(driver, [
        ("xpath", '//XCUIElementTypeButton[@name="登录"]'),
        ("xpath", '//XCUIElementTypeButton[contains(@name,"登录")]'),
    ])
    if not success:
        screenshot(driver, f"error_step1_login_btn_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'登录'按钮")
    print(f"    第{cycle_num}次 - 已点击登录按钮({loc_type})")

    return True


def step2_click_pure_recording(driver, cycle_num):
    """Step 2: 点击"纯录制"菜单"""
    print("\n[Step 2] 点击'纯录制'菜单...")

    # 等待页面加载完成
    for wait_idx in range(20):
        source = driver.page_source
        if '纯录制' in source or '我的' in source:
            print(f"    第{cycle_num}次 - 页面已加载(iter {wait_idx})")
            break
        time.sleep(0.3)

    success = find_and_click_button(driver, '纯录制', timeout=15)
    if success:
        print(f"    第{cycle_num}次 - 已点击'纯录制'")
    else:
        screenshot(driver, f"error_step2_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'纯录制'按钮")

    time.sleep(0.5)
    screenshot(driver, f"step2_pure_recording_{cycle_num}")
    return True


def step3_click_record_in_list(driver, cycle_num):
    """Step 3: 订单列表点击'录制'按钮"""
    print("\n[Step 3] 订单列表点击'录制'按钮...")

    # 等待订单列表加载
    for wait_idx in range(20):
        source = driver.page_source
        if '录制' in source and '订单' in source:
            print(f"    第{cycle_num}次 - 订单列表已加载(iter {wait_idx})")
            break
        time.sleep(0.3)

    # 优先使用原生 Predicate 定位"录制"按钮
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            "name == '录制' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"    第{cycle_num}次 - 原生Predicate点击'录制'成功")
                time.sleep(0.5)
                screenshot(driver, f"step3_record_btn_{cycle_num}")
                return True
    except:
        pass

    # 兜底：遍历所有按钮找"录制"
    try:
        all_buttons = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeButton')
        for btn in all_buttons:
            name = btn.get_attribute('name') or ''
            if name == '录制' and btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"    第{cycle_num}次 - 原生遍历点击'录制'成功")
                time.sleep(0.5)
                screenshot(driver, f"step3_record_btn_{cycle_num}")
                return True
    except:
        pass

    # 最后尝试 WebView
    if webview_click(driver, [
        ("xpath", "//button[contains(text(),'录制')]"),
        ("xpath", "//*[contains(@class,'btn') and contains(text(),'录制')]"),
    ]):
        print(f"    第{cycle_num}次 - WebView点击'录制'成功")
        time.sleep(0.5)
        screenshot(driver, f"step3_record_btn_{cycle_num}")
        return True

    screenshot(driver, f"error_step3_{cycle_num}")
    raise Exception(f"第{cycle_num}次 - 未找到'录制'按钮")


def step4_confirm_popup(driver, cycle_num):
    """Step 4: 弹窗确认"""
    print("\n[Step 4] 弹窗点击'确定'...")

    # 动态等待弹窗出现（最多等待3s）
    popup_found = False
    for wait_idx in range(10):  # 10 * 0.3 = 3s
        source = driver.page_source
        if '确定' in source or '确认' in source or '录制' in source:
            print(f"    第{cycle_num}次 - 弹窗元素检测到(iter {wait_idx})")
            popup_found = True
            break
        time.sleep(0.3)

    # 直接尝试最高效的方式：WebView 点击
    if webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'确认')]"),
        ("xpath", "//button[contains(text(),'确定')]"),
    ]):
        print(f"    第{cycle_num}次 - WebView点击'确认'成功")
        time.sleep(0.3)
        screenshot(driver, f"step4_confirm_{cycle_num}")
        return True

    # 尝试 Appium mobile alert 命令
    try:
        driver.execute_script("mobile: alert", {"action": "accept"})
        print(f"    第{cycle_num}次 - mobile:alert accept 成功")
        time.sleep(0.3)
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
        time.sleep(0.3)
        screenshot(driver, f"step4_confirm_{cycle_num}")
        return True
    except:
        pass

    # 尝试原生 iOS 按钮
    try:
        alert_buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            "type == 'XCUIElementTypeButton' AND (name == '确定' OR name == '确认')")
        for btn in alert_buttons:
            if btn.is_displayed():
                btn.click()
                print(f"    第{cycle_num}次 - iOS原生按钮点击成功")
                time.sleep(0.3)
                screenshot(driver, f"step4_confirm_{cycle_num}")
                return True
    except:
        pass

    # 兜底：遍历所有按钮找"确定"或"确认"
    try:
        all_buttons = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeButton')
        for btn in all_buttons:
            name = btn.get_attribute('name') or ''
            if ('确定' in name or '确认' in name) and btn.is_displayed():
                btn.click()
                print(f"    第{cycle_num}次 - 兜底点击'确定'成功")
                time.sleep(0.3)
                screenshot(driver, f"step4_confirm_{cycle_num}")
                return True
    except:
        pass

    screenshot(driver, f"error_step4_{cycle_num}")
    raise Exception(f"第{cycle_num}次 - 未找到'确定'按钮")


def step5_click_agree_and_start(driver, cycle_num):
    """Step 5: 点击'同意并开始录制'"""
    print("\n[Step 5] 点击'同意并开始录制'...")

    # 等待按钮出现并可点击
    btn_found = False
    for wait_idx in range(30):
        source = driver.page_source
        if '同意并开始双录' in source or '同意并开始录制' in source:
            print(f"    第{cycle_num}次 - 检测到按钮元素(iter {wait_idx})")

            # 尝试找到按钮并点击
            try:
                buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                    "(name CONTAINS '同意并开始双录' OR name CONTAINS '同意并开始录制') AND type == 'XCUIElementTypeButton'")
                for btn in buttons:
                    if btn.is_displayed():
                        # 如果按钮不可用，尝试滚动
                        if not btn.is_enabled():
                            print(f"    第{cycle_num}次 - 按钮禁用，尝试滚动...")
                            # 向上滚动
                            driver.execute_script("mobile: scroll", {"direction": "up"})
                            time.sleep(0.5)
                            continue
                        btn.click()
                        print(f"    第{cycle_num}次 - 点击'同意并开始录制'成功")
                        btn_found = True
                        break
            except:
                pass

            if btn_found:
                break

        time.sleep(0.5)

    if not btn_found:
        # 最后尝试：使用 WebView 或 JS 点击
        if webview_click(driver, [
            ("xpath", "//button[contains(text(),'同意并开始双录')]"),
            ("xpath", "//button[contains(text(),'同意并开始录制')]"),
            ("css", "button.agree-btn"),
        ]):
            print(f"    第{cycle_num}次 - WebView点击'同意并开始录制'成功")
            btn_found = True

    if not btn_found:
        screenshot(driver, f"error_step5_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'同意并开始录制'按钮")

    time.sleep(0.3)
    screenshot(driver, f"step5_agree_{cycle_num}")
    return True


def step6_click_start_live(driver, cycle_num):
    """Step 6: 点击'开始直播'"""
    print("\n[Step 6] 点击'开始直播'...")

    # 尝试 WebView
    if webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'开始直播')]"),
    ]):
        print(f"    第{cycle_num}次 - WebView点击'开始直播'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", "name CONTAINS '开始直播' AND type == 'XCUIElementTypeButton'"),
            ("xpath", '//XCUIElementTypeButton[@name="开始直播"]'),
            ("xpath", '//XCUIElementTypeButton[contains(@name,"开始直播")]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'开始直播'成功")
        else:
            screenshot(driver, f"error_step6_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'开始直播'按钮")

    time.sleep(0.5)
    screenshot(driver, f"step6_start_live_{cycle_num}")
    return True


def step7_wait_countdown_and_agree(driver, cycle_num):
    """Step 7: 3s倒计时后点击'同意检测'"""
    print("\n[Step 7] 等待3s倒计时后点击'同意检测'...")

    wait_countdown(driver, 3)

    # 点击"同意检测"按钮
    success = find_and_click_button(driver, '同意检测', timeout=15)
    if success:
        print(f"    第{cycle_num}次 - 已点击'同意检测'")
    else:
        screenshot(driver, f"error_step7_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'同意检测'按钮")

    time.sleep(0.3)
    screenshot(driver, f"step7_agree_{cycle_num}")
    return True


def step8_pure_record_detection(driver, cycle_num):
    """Step 8: 纯录制业务 - 点击'开始录制'（检测结果分支处理）"""
    print("\n[Step 8] 纯录制业务检测结果处理...")

    # 先等待判断当前页面状态
    page_state = None
    for wait_idx in range(15):
        source = driver.page_source
        if '重新检测' in source or '跳过' in source:
            page_state = 'detect_fail'
            print(f"    第{cycle_num}次 - 检测未通过界面(iter {wait_idx})")
            break
        if '开始录制' in source:
            page_state = 'detect_pass'
            print(f"    第{cycle_num}次 - 检测通过界面(iter {wait_idx})")
            break
        time.sleep(0.5)

    if page_state == 'detect_fail':
        # 检测未通过分支 - 点击"跳过"
        success = find_and_click_button(driver, '跳过', timeout=10)
        if success:
            print(f"    第{cycle_num}次 - 已点击'跳过'")
        else:
            screenshot(driver, f"error_step8_skip_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'跳过'按钮")

        time.sleep(0.3)
        screenshot(driver, f"step8_skip_{cycle_num}")

        # 风险提示弹窗 - 点击确认
        if webview_click(driver, [
            ("css", '.van-dialog__confirm'),
            ("css", 'button.van-dialog__confirm'),
            ("xpath", "//button[contains(text(),'确认')]"),
        ]):
            print(f"    第{cycle_num}次 - 风险提示弹窗点击'确认'成功")
        else:
            success, _ = click_element(driver, [
                ("predicate", "name CONTAINS '确认' AND type == 'XCUIElementTypeButton'"),
                ("xpath", '//XCUIElementTypeButton[@name="确认"]'),
            ], timeout=5)
            if success:
                print(f"    第{cycle_num}次 - 原生点击'确认'成功")

        time.sleep(0.5)
        screenshot(driver, f"step8_risk_confirm_{cycle_num}")

        # 等待"开始录制"按钮
        success = find_and_click_button(driver, '开始录制', timeout=20)
        if success:
            print(f"    第{cycle_num}次 - 已点击'开始录制'")
        else:
            screenshot(driver, f"error_step8_start_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'开始录制'按钮")

        time.sleep(0.3)
        screenshot(driver, f"step8_start_record_{cycle_num}")
    else:
        # 检测通过分支 - 直接点击"开始录制"
        success = find_and_click_button(driver, '开始录制', timeout=15)
        if success:
            print(f"    第{cycle_num}次 - 已点击'开始录制'")
        else:
            screenshot(driver, f"error_step8_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'开始录制'按钮")

        time.sleep(0.3)
        screenshot(driver, f"step8_start_record_{cycle_num}")

    return True


def step10_record_flow(driver, cycle_num):
    """Step 10: 录制流程（结束录制、确认完成）"""
    print("\n[Step 10] 录制流程...")

    # 等待3s倒计时
    wait_countdown(driver, 3)

    # 点击"结束录制"按钮
    success = find_and_click_button(driver, '结束录制', timeout=15)
    if success:
        print(f"    第{cycle_num}次 - 已点击'结束录制'")
    else:
        screenshot(driver, f"error_step10_end_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'结束录制'按钮")

    time.sleep(0.5)
    screenshot(driver, f"step10_record_end_{cycle_num}")

    # 点击"确认完成"按钮
    success = find_and_click_button(driver, '确认完成', timeout=15)
    if success:
        print(f"    第{cycle_num}次 - 已点击'确认完成'")
    else:
        screenshot(driver, f"error_step10_confirm_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'确认完成'按钮")

    time.sleep(0.3)
    screenshot(driver, f"step10_confirm_{cycle_num}")

    # 业务完成弹窗 - 点击确认
    if webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'确认')]"),
    ]):
        print(f"    第{cycle_num}次 - 业务完成弹窗点击'确认'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", "name CONTAINS '确认' AND type == 'XCUIElementTypeButton'"),
            ("xpath", '//XCUIElementTypeButton[@name="确认"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'确认'成功")

    time.sleep(1)
    screenshot(driver, f"step10_business_complete_{cycle_num}")

    return True


def step11_upload_file(driver, cycle_num):
    """Step 11: 文件上传"""
    print("\n[Step 11] 文件上传...")

    # 等待上传成功弹窗
    for wait_idx in range(30):
        source = driver.page_source
        if '文件上传成功' in source or '上传成功' in source:
            print(f"    第{cycle_num}次 - 文件上传成功(iter {wait_idx})")
            break
        time.sleep(0.5)

    screenshot(driver, f"step11_upload_{cycle_num}")

    # 点击上传成功弹窗的"确认"
    if webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'确认')]"),
    ]):
        print(f"    第{cycle_num}次 - 上传成功弹窗点击'确认'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", "name CONTAINS '确认' AND type == 'XCUIElementTypeButton'"),
            ("xpath", '//XCUIElementTypeButton[@name="确认"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'确认'成功")

    time.sleep(0.5)
    screenshot(driver, f"step11_upload_confirm_{cycle_num}")

    return True


def step12_click_end(driver, cycle_num):
    """Step 12: 点击'结束'按钮"""
    print("\n[Step 12] 点击'结束'按钮...")

    # 先等待文件上传成功弹窗消失
    for wait_idx in range(20):
        source = driver.page_source
        if '文件上传成功' not in source and '上传成功' not in source:
            print(f"    第{cycle_num}次 - 上传成功弹窗已消失(iter {wait_idx})")
            break
        time.sleep(0.3)

    time.sleep(0.5)  # 短暂等待后点击结束按钮

    end_clicked = False

    # 切换到 WebView，点击"结束"按钮
    if switch_to_webview(driver):
        try:
            btn = driver.find_element(By.XPATH, "//*[contains(text(),'结束')]")
            if btn.is_displayed():
                driver.execute_script("arguments[0].scrollIntoViewIfNeeded(); arguments[0].click();", btn)
                switch_to_native(driver)
                print(f"    第{cycle_num}次 - WebView XPath点击'结束'成功")
                time.sleep(0.3)
                screenshot(driver, f"step12_end_{cycle_num}")
                end_clicked = True
        except Exception as e:
            print(f"    WebView XPath点击失败: {e}")
            switch_to_native(driver)

    # 兜底：原生按钮（仅当WebView方式失败时）
    if not end_clicked:
        success = find_and_click_button(driver, '结束', timeout=10)
        if success:
            print(f"    第{cycle_num}次 - 已点击'结束'")
        else:
            screenshot(driver, f"error_step12_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'结束'按钮")

        time.sleep(0.3)
        screenshot(driver, f"step12_end_{cycle_num}")

    # 等待"结束办理"弹窗出现并点击"确认"
    for wait_idx in range(10):
        source = driver.page_source
        if '结束办理' in source or '结束服务' in source or '本次服务已结束' in source:
            print(f"    第{cycle_num}次 - 结束办理弹窗出现(iter {wait_idx})")
            # 使用H5 webview方式点击"确认"
            if webview_click(driver, [
                ("css", '.van-dialog__confirm'),
                ("css", 'button.van-dialog__confirm'),
                ("xpath", "//button[contains(text(),'确认')]"),
            ]):
                print(f"    第{cycle_num}次 - H5点击'确认'成功")
                time.sleep(0.3)
                screenshot(driver, f"step12_end_confirm_{cycle_num}")
                return True
            time.sleep(0.2)
        else:
            time.sleep(0.2)

    # 弹窗未出现但流程继续
    print(f"    第{cycle_num}次 - 结束办理弹窗未出现，继续流程")
    return True


def step13_click_return(driver, cycle_num):
    """Step 13: 点击'返回'按钮"""
    print("\n[Step 13] 点击'返回'按钮...")

    # 等待返回按钮出现
    for wait_idx in range(10):
        source = driver.page_source
        if '返回' in source:
            print(f"    第{cycle_num}次 - 返回按钮出现(iter {wait_idx})")
            break
        time.sleep(0.2)

    # 使用原生iOS Predicate定位"返回"按钮
    btn_found = False
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            "name == '返回' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"    第{cycle_num}次 - 原生Predicate点击'返回'成功")
                btn_found = True
                break
    except:
        pass

    if not btn_found:
        # 兜底：遍历所有按钮找"返回"
        try:
            all_buttons = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeButton')
            for btn in all_buttons:
                name = btn.get_attribute('name') or ''
                if name == '返回' and btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    print(f"    第{cycle_num}次 - 原生遍历点击'返回'成功")
                    btn_found = True
                    break
        except:
            pass

    if not btn_found:
        # 最后尝试 WebView 方式
        if webview_click(driver, [
            ("xpath", "//button[contains(text(),'返回')]"),
            ("xpath", "//*[contains(text(),'返回')]"),
        ]):
            print(f"    第{cycle_num}次 - WebView点击'返回'成功")
            btn_found = True

    if not btn_found:
        screenshot(driver, f"error_step13_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'返回'按钮")

    time.sleep(0.3)
    screenshot(driver, f"step13_return_{cycle_num}")

    return True


def step14_go_to_my_and_logout(driver, cycle_num):
    """Step 14: 进入我的页面并退出登录"""
    print("\n[Step 14] 进入我的页面并退出登录...")

    # 点击"我的"菜单
    success = find_and_click_button(driver, '我的', timeout=15)
    if success:
        print(f"    第{cycle_num}次 - 已点击'我的'")
    else:
        screenshot(driver, f"error_step14_my_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'我的'按钮")

    time.sleep(0.5)
    screenshot(driver, f"step14_my_{cycle_num}")

    # 点击"退出登录"按钮
    success = find_and_click_button(driver, '退出登录', timeout=10)
    if success:
        print(f"    第{cycle_num}次 - 已点击'退出登录'")
    else:
        screenshot(driver, f"error_step14_logout_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")

    time.sleep(0.3)
    screenshot(driver, f"step14_logout_{cycle_num}")

    # 确认退出登录
    if webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'确认')]"),
    ]):
        print(f"    第{cycle_num}次 - 退出登录确认成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", "name CONTAINS '确认' AND type == 'XCUIElementTypeButton'"),
            ("xpath", '//XCUIElementTypeButton[@name="确认"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'确认'成功")

    time.sleep(1)
    screenshot(driver, f"step14_logout_confirm_{cycle_num}")

    return True


def step15_home_button(driver, cycle_num):
    """Step 15: 点击 Home 键返回桌面"""
    print("\n[Step 15] 点击 Home 键返回桌面...")
    try:
        driver.execute_script("mobile: pressButton", {"name": "home"})
        print(f"    第{cycle_num}次 - 已点击 Home 键")
    except Exception as e:
        print(f"    Home 键点击失败: {e}")
    time.sleep(0.5)
    screenshot(driver, f"step15_home_{cycle_num}")
    return True


# ============================================================================
# 客户经理现场双录业务流程 Step 函数
# ============================================================================

def step1_scene_launch_app(driver, cycle_num):
    """Step 1: 启动 App"""
    print("\n[Step 1] 启动 App...")

    try:
        driver.activate_app(BUNDLE_ID)
        print(f"    第{cycle_num}次 - 已启动 App")
    except Exception as e:
        print(f"    第{cycle_num}次 - 启动 App: {e}")

    try:
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.XPATH, '//XCUIElementTypeButton[@name="客户经理登录"]')))
        print(f"    第{cycle_num}次 - 客户经理登录按钮出现")
    except:
        pass
    screenshot(driver, f"scene_step1_launch_{cycle_num}")
    return True


def step2_scene_manager_login(driver, cycle_num):
    """Step 2: 客户经理登录"""
    print("\n[Step 2] 客户经理登录...")

    # 点击"客户经理登录"菜单
    success, loc_type = click_element(driver, [
        ("xpath", '//XCUIElementTypeButton[@name="客户经理登录"]'),
        ("xpath", '//*[contains(@name,"客户经理登录")]'),
        ("accessibility id", "客户经理登录"),
    ])
    if success:
        print(f"    第{cycle_num}次 - 已点击客户经理登录({loc_type})")
    else:
        screenshot(driver, f"scene_error_step2_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'客户经理登录'按钮")

    try:
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.XPATH, '//XCUIElementTypeTextField[contains(@value,"工号")]')))
        print(f"    第{cycle_num}次 - 登录表单出现")
    except:
        pass
    screenshot(driver, f"scene_step2_login_form_{cycle_num}")

    # 输入工号
    success = input_text(driver, [
        ("xpath", '//XCUIElementTypeTextField[@value="请输入工号"]'),
        ("xpath", '//XCUIElementTypeTextField[contains(@value,"工号")]'),
        ("xpath", '//XCUIElementTypeTextField[1]'),
    ], "10001", clear_first=True)
    if not success:
        screenshot(driver, f"scene_error_step3_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到工号输入框")
    print(f"    第{cycle_num}次 - 已输入工号")

    # 输入密码
    success = input_text(driver, [
        ("xpath", '//XCUIElementTypeSecureTextField[@value="请输入登录密码"]'),
        ("xpath", '//XCUIElementTypeSecureTextField[1]'),
    ], "Aa123456", clear_first=False)
    if not success:
        screenshot(driver, f"scene_error_step4_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    print(f"    第{cycle_num}次 - 已输入密码")

    # 输入验证码
    success = input_text(driver, [
        ("xpath", '//XCUIElementTypeTextField[@value="请输入验证码"]'),
        ("xpath", '//XCUIElementTypeTextField[2]'),
    ], "0000", clear_first=True)
    if not success:
        screenshot(driver, f"scene_error_step5_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    print(f"    第{cycle_num}次 - 已输入验证码")

    # 点击登录按钮
    success, loc_type = click_element(driver, [
        ("xpath", '//XCUIElementTypeButton[@name="登录"]'),
        ("xpath", '//XCUIElementTypeButton[contains(@name,"登录")]'),
    ])
    if not success:
        screenshot(driver, f"scene_error_step6_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'登录'按钮")
    print(f"    第{cycle_num}次 - 已点击登录按钮({loc_type})")

    return True


def step3_scene_click_on_site_menu(driver, cycle_num):
    """Step 3: 点击'现场'菜单"""
    print("\n[Step 3] 点击'现场'菜单...")

    # 等待页面加载完成
    for wait_idx in range(20):
        source = driver.page_source
        if '现场' in source or '我的' in source:
            print(f"    第{cycle_num}次 - 页面已加载(iter {wait_idx})")
            break
        time.sleep(0.3)

    success = find_and_click_button(driver, '现场', timeout=15)
    if success:
        print(f"    第{cycle_num}次 - 已点击'现场'")
    else:
        screenshot(driver, f"scene_error_step7_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'现场'按钮")

    time.sleep(0.5)
    screenshot(driver, f"scene_step7_{cycle_num}")
    return True


def step4_scene_click_record_in_list(driver, cycle_num):
    """Step 4: 全局搜索现场目标订单，并核验录制确认弹窗。"""
    return search_customer_order(
        driver, cycle_num, fast_search=True, dom_search=True,
        order_id=SCENE_ORDER_ID, customer_name=SCENE_CUSTOMER_NAME)




def step5_scene_confirm_popup(driver, cycle_num):
    """Step 5: 弹窗点击'确认'按钮"""
    print("\n[Step 5] 弹窗点击'确认'...")

    # 动态等待弹窗出现
    popup_found = False
    for wait_idx in range(10):
        source = driver.page_source
        if '确定' in source or '确认' in source:
            print(f"    第{cycle_num}次 - 弹窗元素检测到(iter {wait_idx})")
            popup_found = True
            break
        time.sleep(0.3)

    # 直接尝试 WebView 点击
    if webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'确认')]"),
        ("xpath", "//button[contains(text(),'确定')]"),
    ]):
        print(f"    第{cycle_num}次 - WebView点击'确认'成功")
        time.sleep(0.3)
        screenshot(driver, f"scene_step9_{cycle_num}")
        return True

    # 尝试 Appium mobile alert 命令
    try:
        driver.execute_script("mobile: alert", {"action": "accept"})
        print(f"    第{cycle_num}次 - mobile:alert accept 成功")
        time.sleep(0.3)
        screenshot(driver, f"scene_step9_{cycle_num}")
        return True
    except:
        pass

    # 尝试原生 Alert
    try:
        WebDriverWait(driver, 2).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        alert.accept()
        print(f"    第{cycle_num}次 - 原生Alert确认成功")
        time.sleep(0.3)
        screenshot(driver, f"scene_step9_{cycle_num}")
        return True
    except:
        pass

    # 尝试原生 iOS 按钮
    try:
        alert_buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            "type == 'XCUIElementTypeButton' AND (name == '确定' OR name == '确认')")
        for btn in alert_buttons:
            if btn.is_displayed():
                btn.click()
                print(f"    第{cycle_num}次 - iOS原生按钮点击成功")
                time.sleep(0.3)
                screenshot(driver, f"scene_step9_{cycle_num}")
                return True
    except:
        pass

    screenshot(driver, f"scene_error_step9_{cycle_num}")
    raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")


def step6_scene_click_agree_and_start(driver, cycle_num):
    """Step 6: 点击'同意并开始双录'"""
    print("\n[Step 6] 点击'同意并开始双录'...")

    # 等待按钮出现
    btn_found = False
    for wait_idx in range(30):
        source = driver.page_source
        if '同意并开始双录' in source or '同意并开始录制' in source:
            print(f"    第{cycle_num}次 - 检测到按钮元素(iter {wait_idx})")

            try:
                buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                    "(name CONTAINS '同意并开始双录' OR name CONTAINS '同意并开始录制') AND type == 'XCUIElementTypeButton'")
                for btn in buttons:
                    if btn.is_displayed():
                        if not btn.is_enabled():
                            print(f"    第{cycle_num}次 - 按钮禁用，尝试滚动...")
                            driver.execute_script("mobile: scroll", {"direction": "up"})
                            time.sleep(0.5)
                            continue
                        btn.click()
                        print(f"    第{cycle_num}次 - 点击'同意并开始双录'成功")
                        btn_found = True
                        break
            except:
                pass

            if btn_found:
                break
        time.sleep(0.5)

    if not btn_found:
        if webview_click(driver, [
            ("xpath", "//button[contains(text(),'同意并开始双录')]"),
            ("xpath", "//button[contains(text(),'同意并开始录制')]"),
            ("css", "button.agree-btn"),
        ]):
            print(f"    第{cycle_num}次 - WebView点击'同意并开始双录'成功")
            btn_found = True

    if not btn_found:
        screenshot(driver, f"scene_error_step10_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'同意并开始双录'按钮")

    # 系统弹窗弹出后立即交给下一步，避免截图或固定等待阻塞点击。
    return True


def step7_scene_click_start_now(driver, cycle_num):
    """Step 7: 复用纯录制的系统弹窗原生点击和启动状态核验。"""
    start_system_broadcast(driver, cycle_num, pure_recording=True)
    return wait_detection_ready(driver)




def step8_scene_click_agree_detection(driver, cycle_num):
    """Step 8: 点击'同意检测'"""
    print("\n[Step 8] 点击'同意检测'...")

    success = find_and_click_button(driver, '同意检测', timeout=15)
    if success:
        print(f"    第{cycle_num}次 - 已点击'同意检测'")
    else:
        screenshot(driver, f"scene_error_step12_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'同意检测'按钮")

    time.sleep(0.3)
    screenshot(driver, f"scene_step12_{cycle_num}")
    return True


def step9_scene_wait_detection_result(driver, cycle_num, timeout=120):
    """Step 9: 等待检测结果"""
    print(f"\n[Step 9] 等待检测结果（最多 {timeout} 秒）...")

    start_time = time.time()
    last_screenshot_time = start_time

    while time.time() - start_time < timeout:
        source = driver.page_source

        if '已通过' in source:
            elapsed = int(time.time() - start_time)
            print(f"    第{cycle_num}次 - 环境检测已通过！（耗时 {elapsed} 秒）")
            screenshot(driver, f"scene_passed_{cycle_num}")
            return "passed"

        if '未通过' in source or '重新检测' in source:
            elapsed = int(time.time() - start_time)
            print(f"    第{cycle_num}次 - 环境检测未通过！（耗时 {elapsed} 秒）")
            screenshot(driver, f"scene_failed_{cycle_num}")
            return "failed"

        # 每10秒截一次图记录进度
        if time.time() - last_screenshot_time >= 10:
            screenshot(driver, f"scene_detecting_{cycle_num}_{int(time.time()-start_time)}s")
            last_screenshot_time = time.time()

        time.sleep(1)

    print(f"    第{cycle_num}次 - 检测超时（超过 {timeout} 秒）")
    screenshot(driver, f"scene_timeout_{cycle_num}")
    return "timeout"


def step10_scene_handle_detection_result(driver, cycle_num, record_type="ai"):
    """Step 10: 处理检测结果，选择 AI 或 人工模式"""
    print(f"\n[Step 10] 处理检测结果，选择双录方式：{'开始(AI)' if record_type == 'ai' else '开始(人工)'}...")

    # 先等待业务办理界面加载
    time.sleep(3)
    screenshot(driver, f"scene_step14_before_{cycle_num}")

    if record_type == "ai":
        # AI 模式 - 等待"开始（AI）"按钮可点击
        btn_found = False
        for attempt in range(30):
            source = driver.page_source
            if '开始（AI）' in source:
                try:
                    buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                        "name CONTAINS '开始（AI）' AND type == 'XCUIElementTypeButton'")
                    for btn in buttons:
                        if btn.is_displayed() and btn.is_enabled():
                            btn.click()
                            print(f"    第{cycle_num}次 - 已点击【开始（AI）】")
                            btn_found = True
                            break
                except:
                    pass
            if btn_found:
                break
            print(f"    第{cycle_num}次 - 等待'开始（AI）'按钮可点击...（已等待{attempt+1}s）")
            time.sleep(1)

        if not btn_found:
            # 尝试 WebView 点击
            if webview_click(driver, [
                ("xpath", "//button[contains(text(),'开始（AI）')]"),
                ("xpath", "//*[contains(text(),'开始（AI）')]"),
            ]):
                print(f"    第{cycle_num}次 - WebView点击'开始（AI）'成功")
                btn_found = True

        if not btn_found:
            screenshot(driver, f"scene_error_step14_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'开始（AI）'按钮")
    else:
        # 人工模式
        btn_found = False
        for attempt in range(30):
            source = driver.page_source
            if '开始（人工）' in source:
                try:
                    buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                        "name CONTAINS '开始（人工）' AND type == 'XCUIElementTypeButton'")
                    for btn in buttons:
                        if btn.is_displayed() and btn.is_enabled():
                            btn.click()
                            print(f"    第{cycle_num}次 - 已点击【开始（人工）】")
                            btn_found = True
                            break
                except:
                    pass
            if btn_found:
                break
            time.sleep(1)

        if not btn_found:
            if webview_click(driver, [
                ("xpath", "//button[contains(text(),'开始（人工）')]"),
                ("xpath", "//*[contains(text(),'开始（人工）')]"),
            ]):
                print(f"    第{cycle_num}次 - WebView点击'开始（人工）'成功")
                btn_found = True

        if not btn_found:
            screenshot(driver, f"scene_error_step14_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'开始（人工）'按钮")

    time.sleep(2)
    screenshot(driver, f"scene_step14_{cycle_num}")
    return True


def step11_scene_wait_countdown(driver, cycle_num):
    """Step 11: 等待 3s 倒计时"""
    print("\n[Step 11] 等待 3s 倒计时...")
    wait_countdown(driver, 3)
    screenshot(driver, f"scene_step15_{cycle_num}")
    return True


def step12_scene_ai_qa_node(driver, cycle_num):
    """Step 12: AI 问答节点 - 等待'下一步'按钮可点击"""
    print("\n[Step 12] AI问答节点，等待'下一步'按钮可点击...")

    screenshot(driver, f"scene_step16_{cycle_num}")

    # 等待"下一步"按钮可点击（话术播报结束后AI采集回答约4s）
    btn_found = False
    for attempt in range(60):
        source = driver.page_source
        if '下一步' in source:
            try:
                buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                    "name CONTAINS '下一步' AND type == 'XCUIElementTypeButton'")
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        print(f"    第{cycle_num}次 - 已点击【下一步】(问答->朗读)")
                        btn_found = True
                        break
            except:
                pass
        if btn_found:
            break
        print(f"    第{cycle_num}次 - '下一步'按钮不可点击，等待1秒...(已等待{attempt+1}s)")
        time.sleep(1)

    if not btn_found:
        # 尝试 WebView 点击
        if webview_click(driver, [
            ("xpath", "//button[contains(text(),'下一步')]"),
            ("xpath", "//*[contains(text(),'下一步')]"),
        ]):
            print(f"    第{cycle_num}次 - WebView点击'下一步'成功")
            btn_found = True

    if not btn_found:
        screenshot(driver, f"scene_error_step16_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - '下一步'按钮始终不可点击")

    time.sleep(3)
    screenshot(driver, f"scene_step16_after_{cycle_num}")
    return True


def step13_scene_reading_node(driver, cycle_num):
    """Step 13: 朗读节点 - 等待'完成录制'可点击"""
    print("\n[Step 13] 朗读节点，等待'完成录制'可点击...")

    screenshot(driver, f"scene_step17_{cycle_num}")

    # 先确保在朗读节点界面上
    time.sleep(3)

    btn_clicked = False

    # 方式1: 原生 Predicate 定位
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            "name CONTAINS '完成录制' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"    第{cycle_num}次 - 已点击【完成录制】(Predicate方式)")
                btn_clicked = True
                break
    except:
        pass

    # 方式2: WebView XPath
    if not btn_clicked:
        if webview_click(driver, [
            ("xpath", "//button[contains(text(),'完成录制')]"),
            ("xpath", "//*[contains(text(),'完成录制')]"),
        ]):
            print(f"    第{cycle_num}次 - 已点击【完成录制】(WebView方式)")
            btn_clicked = True

    # 方式3: 坐标定位（右下角区域）
    if not btn_clicked:
        try:
            window_size = driver.get_window_size()
            width = window_size['width']
            height = window_size['height']
            click_x = int(width * 0.85)
            click_y = int(height * 0.85)
            driver.execute_script("mobile: tap", {"x": click_x, "y": click_y})
            print(f"    第{cycle_num}次 - 已点击【完成录制】(坐标方式: {click_x}, {click_y})")
            btn_clicked = True
        except Exception as e:
            print(f"    第{cycle_num}次 - 坐标方式失败: {e}")

    if btn_clicked:
        time.sleep(2)
    else:
        screenshot(driver, f"scene_error_step17_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未能点击'完成录制'按钮")

    time.sleep(2)
    screenshot(driver, f"scene_step17_{cycle_num}")
    return True


def step14_scene_manual_qa_node(driver, cycle_num):
    """Step 14: 逐节点点击下一步，直到完成录制按钮出现。"""
    print("\n[Step 14] 逐步推进人工双录节点...")
    try:
        return advance_manual_nodes(driver, cycle_num, batch=True)
    except Exception:
        screenshot(driver, f"scene_error_step16_{cycle_num}")
        raise


def step15_scene_manual_reading_node(driver, cycle_num):
    """Step 15: 完成录制，并确认进入回看界面。"""
    print("\n[Step 15] 点击完成录制并核验回看界面...")
    try:
        return finish_manual_nodes(driver, cycle_num)
    except Exception:
        screenshot(driver, f"scene_error_step17_{cycle_num}")
        raise


def step16_scene_review_and_confirm(driver, cycle_num, state_driven=False, dom_first=False):
    """Step 16: 录制回看界面 - 点击'确认完成'"""
    print("\n[Step 16] 录制回看界面，点击'确认完成'...")

    success = (click_ai_control(driver, '确认完成', timeout=15) if dom_first
               else find_and_click_button(driver, '确认完成', timeout=15))
    if success:
        print(f"    第{cycle_num}次 - 已点击【确认完成】")
    else:
        if webview_click(driver, [
            ("xpath", "//button[contains(text(),'确认完成')]"),
            ("xpath", "//*[contains(text(),'确认完成')]"),
        ]):
            print(f"    第{cycle_num}次 - WebView点击'确认完成'成功")
        else:
            screenshot(driver, f"scene_error_step18_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'确认完成'按钮")

    if state_driven:
        wait_scene_transition(driver, 'confirm')
    else:
        time.sleep(2)
    screenshot(driver, f"scene_step18_{cycle_num}")
    return True


def step17_scene_confirm_popup(driver, cycle_num, state_driven=False, dom_first=False):
    """Step 17: 弹窗点击'确认'按钮"""
    print("\n[Step 17] 弹窗点击'确认'...")

    if dom_first:
        click_ai_control(driver, '确认', dialog=True, timeout=15)
        print(f"    第{cycle_num}次 - DOM 精确点击提交弹窗确认成功")
    elif webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'确认')]"),
    ]):
        print(f"    第{cycle_num}次 - WebView点击'确认'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", "name CONTAINS '确认' AND type == 'XCUIElementTypeButton'"),
            ("xpath", '//XCUIElementTypeButton[@name="确认"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'确认'成功")
        else:
            screenshot(driver, f"scene_error_step19_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")

    # 人工流程下一步 wait_upload_success 负责等待并核验上传，避免额外固定等待。
    if not state_driven:
        time.sleep(2)
    screenshot(driver, f"scene_step19_{cycle_num}")
    return True


def step18_scene_wait_upload(driver, cycle_num):
    """Step 18: 等待上传成功"""
    print("\n[Step 18] 等待录制文件上传成功...")
    time.sleep(3)
    screenshot(driver, f"scene_step20_{cycle_num}")
    return True


def step19_scene_upload_confirm(driver, cycle_num, state_driven=False, dom_first=False):
    """Step 19: 上传成功弹窗点击'确认'"""
    print("\n[Step 19] 上传成功弹窗点击'确认'...")

    if dom_first:
        click_ai_control(driver, '确认', dialog=True, timeout=15)
        print(f"    第{cycle_num}次 - DOM 精确点击上传成功弹窗确认成功")
    elif webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'确认')]"),
    ]):
        print(f"    第{cycle_num}次 - WebView点击'确认'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", "name CONTAINS '确认' AND type == 'XCUIElementTypeButton'"),
            ("xpath", '//XCUIElementTypeButton[@name="确认"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'确认'成功")
        else:
            if state_driven:
                raise RuntimeError('已上传成功但未能点击确认，停止返回操作')
            print(f"    第{cycle_num}次 - 未找到上传成功弹窗，继续...")

    if state_driven:
        wait_scene_transition(driver, 'completed')
    else:
        time.sleep(2)
    screenshot(driver, f"scene_step21_{cycle_num}")
    return True


def step20_scene_click_return(driver, cycle_num):
    """Step 20: 业务办理完成界面 - 点击'返回'"""
    print("\n[Step 20] 业务办理完成界面，点击'返回'...")

    btn_found = False

    # 方式1: 原生 Predicate
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
            "name == '返回' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"    第{cycle_num}次 - 原生Predicate点击'返回'成功")
                btn_found = True
                break
    except:
        pass

    # 方式2: 遍历原生按钮
    if not btn_found:
        try:
            all_buttons = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeButton')
            for btn in all_buttons:
                name = btn.get_attribute('name') or ''
                if name == '返回' and btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    print(f"    第{cycle_num}次 - 原生遍历点击'返回'成功")
                    btn_found = True
                    break
        except:
            pass

    # 方式3: WebView
    if not btn_found:
        if webview_click(driver, [
            ("xpath", "//button[contains(text(),'返回')]"),
            ("xpath", "//*[contains(text(),'返回')]"),
        ]):
            print(f"    第{cycle_num}次 - WebView点击'返回'成功")
            btn_found = True

    if not btn_found:
        screenshot(driver, f"scene_error_step22_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'返回'按钮")

    time.sleep(2)
    screenshot(driver, f"scene_step22_{cycle_num}")
    return True


def step21_scene_click_my(driver, cycle_num):
    """Step 21: 点击'我的'菜单"""
    print("\n[Step 21] 点击'我的'菜单...")

    success = find_and_click_button(driver, '我的', timeout=15)
    if success:
        print(f"    第{cycle_num}次 - 已点击'我的'")
    else:
        screenshot(driver, f"scene_error_step23_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'我的'按钮")

    time.sleep(2)
    screenshot(driver, f"scene_step23_{cycle_num}")
    return True


def step22_scene_click_logout(driver, cycle_num):
    """Step 22: 点击'退出登录'"""
    print("\n[Step 22] 点击'退出登录'...")

    success = find_and_click_button(driver, '退出登录', timeout=10)
    if success:
        print(f"    第{cycle_num}次 - 已点击'退出登录'")
    else:
        screenshot(driver, f"scene_error_step24_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")

    time.sleep(1)
    return True


def step23_scene_confirm_logout(driver, cycle_num):
    """Step 23: 弹窗点击'确认'"""
    print("\n[Step 23] 弹窗点击'确认'...")

    if webview_click(driver, [
        ("css", '.van-dialog__confirm'),
        ("css", 'button.van-dialog__confirm'),
        ("xpath", "//button[contains(text(),'确认')]"),
    ]):
        print(f"    第{cycle_num}次 - WebView点击'确认'成功")
    else:
        success, _ = click_element(driver, [
            ("predicate", "name CONTAINS '确认' AND type == 'XCUIElementTypeButton'"),
            ("xpath", '//XCUIElementTypeButton[@name="确认"]'),
        ], timeout=5)
        if success:
            print(f"    第{cycle_num}次 - 原生点击'确认'成功")
        else:
            screenshot(driver, f"scene_error_step25_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")

    time.sleep(2)
    screenshot(driver, f"scene_step25_{cycle_num}")
    return True


def step24_scene_home(driver, cycle_num):
    """Step 24: 点击 Home 键返回桌面"""
    print("\n[Step 24] 点击 Home 键返回桌面...")

    try:
        driver.execute_script("mobile: pressButton", {"name": "home"})
        print(f"    第{cycle_num}次 - 已点击 Home 键")
    except Exception as e:
        print(f"    Home 键点击失败: {e}")

    time.sleep(1)
    screenshot(driver, f"scene_step26_home_{cycle_num}")
    return True


def run_scene_record_cycle(driver, cycle_num, record_type="ai", cleanup_broadcast=True):
    """执行客户经理现场双录测试循环

    Args:
        driver: WebDriver 实例
        cycle_num: 循环编号
        record_type: "ai" - AI双录流程, "manual" - 人工双录流程
    """
    print(f"\n{'='*60}")
    print(f"开始第 {cycle_num} 次客户经理现场双录测试 ({'AI' if record_type == 'ai' else '人工'}双录)")
    print(f"{'='*60}")

    try:
        # Step 1: 启动 App
        timed_step(prepare_manager, driver, cycle_num, BUNDLE_ID, screenshot,
                   cleanup_broadcast=cleanup_broadcast)

        # Step 2: 客户经理登录
        timed_step(login_manager, driver, cycle_num, "10001", "Aa123456", "0000")

        # Step 3: 点击"现场"菜单
        timed_step(open_scene_navigation, driver, cycle_num)

        # Step 4: 订单列表点击"录制"按钮
        timed_step(search_scene_order, driver, cycle_num, SCENE_ORDER_ID, SCENE_CUSTOMER_NAME,
                   customer_switch_to_webview, search_customer_order, customer_click_record_result)

        # Step 5: 弹窗点击"确认"
        timed_step(step5_scene_confirm_popup, driver, cycle_num)

        # Step 6: 点击"同意并开始双录"
        timed_step(step6_scene_click_agree_and_start, driver, cycle_num)

        # Step 7: 弹窗点击"立即开始"
        timed_step(step7_scene_click_start_now, driver, cycle_num)

        # Step 8: 点击"同意检测"
        timed_step(step8_scene_click_agree_detection, driver, cycle_num)

        # Step 9: 等待检测结果
        result = timed_step(step9_scene_wait_detection_result, driver, cycle_num, timeout=120)

        if result == "passed":
            print(f"    第{cycle_num}次 - 检测通过，等待3s后自动跳转...")
        elif result == "failed":
            print(f"    第{cycle_num}次 - 检测未通过，点击'跳过'")
            if find_and_click_button(driver, '跳过', timeout=10):
                print(f"    第{cycle_num}次 - 已点击'跳过'")
            time.sleep(2)

            # 风险提示弹窗点击"确认"
            print(f"    第{cycle_num}次 - 风险提示弹窗，点击'确认'")
            if webview_click(driver, [
                ("css", '.van-dialog__confirm'),
                ("css", 'button.van-dialog__confirm'),
                ("xpath", "//button[contains(text(),'确认')]"),
            ]):
                print(f"    第{cycle_num}次 - 风险提示弹窗点击'确认'成功")

            # 等待跳转到等待录制界面
            print(f"    第{cycle_num}次 - 等待界面加载...")
            time.sleep(3)
        else:
            print(f"    第{cycle_num}次 - 检测超时，继续执行...")
            time.sleep(2)

        screenshot(driver, f"scene_step13_{cycle_num}")

        # Step 10: 选择双录方式（AI 或 人工）
        if record_type == 'manual':
            timed_step(start_manual_recording, driver, cycle_num)
        else:
            timed_step(start_ai_recording, driver, cycle_num)

        # Step 11: 等待 3s 倒计时
        timed_step(step11_scene_wait_countdown, driver, cycle_num)

        if record_type == "ai":
            # AI 双录流程
            print(f"\n[AI双录流程]")

            timed_step(exercise_scene_controls, driver, cycle_num,
                       customer_click_record_control, customer_switch_to_webview)
            timed_step(advance_ai_nodes, driver, cycle_num)
            timed_step(finish_ai_recording, driver, cycle_num)
        else:
            # 人工双录流程
            print(f"\n[人工双录流程]")

            timed_step(exercise_scene_controls, driver, cycle_num,
                       customer_click_record_control, customer_switch_to_webview)

            # Step 14: 人工问答节点 - 点击"下一步"
            timed_step(step14_scene_manual_qa_node, driver, cycle_num)

            # Step 15: 人工朗读节点 - 点击"完成录制"
            timed_step(step15_scene_manual_reading_node, driver, cycle_num)

        # Step 16: 录制回看界面 - 点击"确认完成"
        # AI 上传链路与人工共用：回看确认、提交、原生结果核验和成功确认。
        timed_step(step16_scene_review_and_confirm, driver, cycle_num, state_driven=True)

        # Step 17: 弹窗点击"确认"
        timed_step(step17_scene_confirm_popup, driver, cycle_num, state_driven=True)

        # Step 18: 等待上传成功
        # AI 与人工共用明确上传失败后的界面退出；退出成功仍保留失败结果。
        try:
            timed_step(wait_upload_success, driver, fail_fast=True)
        except SceneUploadFailed as upload_error:
            try:
                timed_step(close_failed_upload, driver, cycle_num,
                    lambda: timed_step(return_scene_list, driver, cycle_num),
                    lambda: timed_step(logout_customer_ios, driver, cycle_num,
                                       screenshot, login_marker='客户经理登录'))
            except Exception as recovery_error:
                raise SceneUploadFailed(
                    f'{upload_error}；界面退出未完成：{recovery_error}') from recovery_error
            raise

        # Step 19: 上传成功弹窗点击"确认"
        timed_step(step19_scene_upload_confirm, driver, cycle_num, state_driven=True)

        # Step 20: 业务办理完成界面 - 点击"返回"
        timed_step(return_scene_list, driver, cycle_num)

        # Step 21: 点击"我的"菜单
        timed_step(logout_customer_ios, driver, cycle_num, screenshot, login_marker="客户经理登录")

        # Step 24: 点击 Home 键返回桌面
        timed_step(step24_scene_home, driver, cycle_num)

        print(f"\n第 {cycle_num} 次客户经理现场双录测试完成！")
        return True

    except Exception as e:
        if record_type != 'ai':
            screenshot(driver, f"scene_error_cycle_{cycle_num}")
        print(f"\n[第 {cycle_num} 次测试失败] {str(e)}")
        raise


def run_test_cycle(driver, cycle_num, detect_mode="auto"):
    """执行一次测试循环

    Args:
        driver: WebDriver 实例
        cycle_num: 循环编号
        detect_mode: "auto" 自动判断, "not_pass" 强制未通过分支, "pass" 强制通过分支
    """
    print(f"\n{'='*60}")
    print(f"开始第 {cycle_num} 次客户经理纯录制测试 (检测模式: {detect_mode})")
    print(f"{'='*60}")

    try:
        # Step 1: 客户经理登录
        step1_manager_login(driver, cycle_num)

        # Step 2: 点击"纯录制"菜单
        step2_click_pure_recording(driver, cycle_num)

        # Step 3: 订单列表点击"录制"按钮
        step3_click_record_in_list(driver, cycle_num)

        # Step 4: 弹窗确认
        step4_confirm_popup(driver, cycle_num)

        # Step 5: 点击"同意并开始录制"
        step5_click_agree_and_start(driver, cycle_num)

        # Step 6: 点击"开始直播"
        step6_click_start_live(driver, cycle_num)

        # Step 7: 3s倒计时后再次点击"同意并开始录制"
        step7_wait_countdown_and_agree(driver, cycle_num)

        # Step 8: 点击"同意检测"
        step8_pure_record_detection(driver, cycle_num)

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

        print(f"\n第 {cycle_num} 次客户经理纯录制测试完成！")
        return True

    except Exception as e:
        screenshot(driver, f"error_cycle_{cycle_num}")
        print(f"\n[第 {cycle_num} 次测试失败] {str(e)}")
        raise


def _main():
    loop_count = 1
    detect_mode = "auto"  # 默认自动判断检测结果
    test_type = "pure_recording"  # 默认客户经理纯录制
    record_type = "ai"  # 默认 AI 双录

    if len(sys.argv) > 1:
        if sys.argv[1] == "scene":
            test_type = "scene"
            # 检查第二个参数是否为 ai 或 manual
            if len(sys.argv) > 2:
                if sys.argv[2] == "manual":
                    record_type = "manual"
                # 检查是否有循环次数参数
                if len(sys.argv) > 3:
                    try:
                        loop_count = int(sys.argv[3])
                    except ValueError:
                        loop_count = 1
            else:
                record_type = "ai"  # scene 默认 AI
        elif sys.argv[1] == "scene_ai":
            test_type = "scene"
            record_type = "ai"
            if len(sys.argv) > 2:
                try:
                    loop_count = int(sys.argv[2])
                except ValueError:
                    loop_count = 1
        elif sys.argv[1] == "scene_manual":
            test_type = "scene"
            record_type = "manual"
            if len(sys.argv) > 2:
                try:
                    loop_count = int(sys.argv[2])
                except ValueError:
                    loop_count = 1
        else:
            # 纯录制测试
            try:
                loop_count = int(sys.argv[1])
            except ValueError:
                loop_count = 1

            if len(sys.argv) > 2:
                detect_mode = sys.argv[2]  # not_pass, pass, auto

    print("=" * 60)
    print(f"iOS App 客户经理{'现场双录（' + ('AI' if record_type == 'ai' else '人工') + '）' if test_type == 'scene' else '纯录制'}业务流程自动化测试")
    print('登录模式: manager')
    print(f"Appium 地址: {APPIUM_URL}")
    print(f"WDA 地址: {WDA_URL}")
    print(f"UDID: {UDID}")
    print(f"Bundle ID: {BUNDLE_ID}")
    print(f"iOS 版本: {PLATFORM_VERSION}")
    print(f"测试类型: {'客户经理现场双录(' + ('AI' if record_type == 'ai' else '人工') + ')' if test_type == 'scene' else '客户经理纯录制'}")
    print(f"循环次数: {loop_count} 次")
    print(f"截图功能: {'开启' if ENABLE_SCREENSHOT else '关闭'}")
    if test_type == 'scene':
        print(f'订单号: {SCENE_ORDER_ID}')
    if test_type == "pure_recording":
        print(f"检测模式: {detect_mode}")
    print("=" * 60)

    success_count = 0
    fail_count = 0
    previous_cycle_succeeded = False

    for i in range(1, loop_count + 1):
        driver = None
        previous_settings = None
        ai_failed = False
        cycle_started = time.monotonic()
        try:
            if test_type == "scene":
                timed_step(reset_scene_order, SCENE_ORDER_ID)
            options = get_desired_caps()
            if test_type == "scene":
                # 人工和 AI 使用相同的会话配置及 prepare_manager 启动入口。
                configure_scene_startup(options)
            client_kwargs = {}
            if test_type == 'scene' and record_type == 'ai':
                options.set_capability('wdaConnectionTimeout', 30000)
                client_kwargs['client_config'] = ai_client_config(APPIUM_URL)
            driver = webdriver.Remote(APPIUM_URL, options=options, **client_kwargs)
            if test_type == "scene":
                previous_settings = driver.get_settings()
                driver.update_settings({'waitForIdleTimeout': 0, 'animationCoolOffTimeout': 0})

            if test_type == "scene":
                cleanup_broadcast = not previous_cycle_succeeded
                # 先标记未完成；任何中途异常均要求下一轮重新检查。
                previous_cycle_succeeded = False
                run_scene_record_cycle(driver, i, record_type=record_type,
                                       cleanup_broadcast=cleanup_broadcast)
                previous_cycle_succeeded = True
            else:
                run_test_cycle(driver, i, detect_mode)
            success_count += 1

        except Exception as e:
            previous_cycle_succeeded = False
            fail_count += 1
            print(f"\n[第 {i} 次测试失败] {str(e)}")
            if driver and test_type == "scene":
                ai_failed = record_type == 'ai'
                if ai_failed:
                    limit_failure_requests(driver)
                    print('    AI本轮失败，限时保存现场后结束 App，继续下一循环')
                else:
                    print('    保留失败现场，不主动结束 App；下轮启动时再清理')
                capture_failure(driver, BUNDLE_ID, SCREENSHOT_DIR, i)
            print("    继续执行下一次测试...")

        finally:
            if driver:
                if ai_failed:
                    end_failed_ai_cycle(driver, BUNDLE_ID)
                elif test_type == 'scene':
                    cleanup_session(driver, previous_settings or {})
                elif previous_settings is not None:
                    try:
                        driver.update_settings({key: previous_settings.get(key, default)
                            for key, default in [('waitForIdleTimeout', 10), ('animationCoolOffTimeout', 2)]})
                    except Exception as error:
                        print(f"    恢复设备等待设置失败: {error}")
                try:
                    if test_type != 'scene':
                        driver.quit()
                except:
                    pass

            scene_label = f"现场双录（{'AI' if record_type == 'ai' else '人工'}）" if test_type == 'scene' else '客户经理纯录制'
            print(f"    第{i}次 - {scene_label}周期耗时 {time.monotonic() - cycle_started:.2f}s（含会话创建及收尾）")

        if i < loop_count:
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


def main():
    from scene_log_output import scene_log_output
    scene_mode = len(sys.argv) > 1 and sys.argv[1] in ('scene', 'scene_ai', 'scene_manual')
    with scene_log_output(enabled=scene_mode):
        return _main()


if __name__ == "__main__":
    main()
