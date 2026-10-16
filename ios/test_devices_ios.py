"""
iOS 原生 App UI 自动化测试脚本
测试流程：客户登录 -> 我的 -> 退出登录
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

from config import (
    WDA_URL, APPIUM_URL, UDID, PLATFORM_VERSION, BUNDLE_ID,
    CUSTOMER_ID, CUSTOMER_PASSWORD, CUSTOMER_CAPTCHA,
    MANAGER_ID, MANAGER_PASSWORD, MANAGER_CAPTCHA,
    TEXT_CUSTOMER_LOGIN, TEXT_MANAGER_LOGIN, TEXT_LOGIN_BTN, TEXT_MY, TEXT_LOGOUT,
    TEXT_CAPTCHA_PLACEHOLDER, TEXT_ID_PLACEHOLDER, TEXT_PASSWORD_PLACEHOLDER, TEXT_MANAGER_ID_PLACEHOLDER,
    APP_LAUNCH_TIMEOUT, LOGIN_FORM_TIMEOUT, LOGIN_BTN_TIMEOUT, PAGE_LOAD_TIMEOUT, LOGOUT_CONFIRM_TIMEOUT,
    POLL_INTERVAL_FAST, POLL_INTERVAL_NORMAL, POLL_INTERVAL_SLOW,
    WEBDRIVER_AGENT_URL, NEW_COMMAND_TIMEOUT, WDA_CONNECTION_TIMEOUT,
    AUTO_ACCEPT_ALERTS, SKIP_LOG_CAPTURE, ENABLE_WEBVIEW_DETAILS,
    AUTO_WEBVIEW, ENSURE_WEBVIEWS_HAVE_PAGES, WEBVIEW_CONNECT_TIMEOUT,
    WEBKIT_DEBUG_PROXY_PORT, SHOW_XCODE_LOG, NEW_COMMAND_TIMEOUT_SHORT,
    WEBVIEW_CONNECT_RETRIES, NATIVE_WEB_TAP,
    SCREENSHOT_DIR, ENABLE_SCREENSHOT,
)

# 登录模式：customer 或 manager
LOGIN_MODE = "manager"  # 可通过环境变量 LOGIN_MODE 覆盖

# 确保截图目录存在
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

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


def find_element(driver, locators, timeout=15):
    """查找单个元素，支持多种定位方式

    Args:
        driver: WebDriver 实例
        locators: [(loc_type, loc_value), ...] 列表
        timeout: 超时时间（秒）

    Returns:
        找到的元素，否则返回 None
    """
    start = time.time()
    last_error = None

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

                if elem.is_displayed():
                    return elem
            except Exception as e:
                last_error = e
        time.sleep(POLL_INTERVAL_FAST)

    raise Exception(f"未找到元素 {locators}: {last_error}")


def click_element(driver, locators, check_enabled=True):
    """尝试多种方式点击元素"""
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
                time.sleep(POLL_INTERVAL_FAST)
                continue

            elem.click()
            time.sleep(0.1)
            return True, loc_type
        except:
            continue
    return False, None


def input_text(driver, locators, text, clear_first=True):
    """清空并输入文本"""
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
                elem.click()
                time.sleep(0.1)
                if clear_first:
                    try:
                        elem.clear()
                        time.sleep(0.1)
                    except:
                        pass
                elem.send_keys(text)
                return True
        except Exception as e:
            print(f"    input_text 失败: {e}")
            continue
    return False


def run_test_cycle(driver, cycle_num):
    """执行一次测试循环"""
    print(f"\n{'='*50}")
    print(f"开始第 {cycle_num} 次测试")
    print(f"{'='*50}")

    # 用于统计耗时：启动App到点击登录按钮
    app_to_login_time = 0.0

    # 1. 启动 App
    print("\n[Step 1] 启动 App...")
    step_start = time.time()
    try:
        driver.activate_app(BUNDLE_ID)
        print(f"    第{cycle_num}次 - 已启动 App")
    except Exception as e:
        print(f"    第{cycle_num}次 - 启动 App: {e}")

    # 用更高效的轮询等待"客户登录"按钮出现
    btn_found = False
    max_polls = int(APP_LAUNCH_TIMEOUT / POLL_INTERVAL_FAST)
    for wait_idx in range(max_polls):
        try:
            buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                f"name == '{TEXT_CUSTOMER_LOGIN}' AND type == 'XCUIElementTypeButton'")
            for btn in buttons:
                if btn.is_displayed():
                    btn_found = True
                    print(f"    第{cycle_num}次 - 客户登录按钮出现(iter {wait_idx})")
                    break
        except:
            pass
        if btn_found:
            break
        time.sleep(POLL_INTERVAL_FAST)
    screenshot(driver, f"step1_launch_{cycle_num}")

    # 2. 点击登录按钮
    print(f"\n[Step 2] 点击{LOGIN_TEXT}...")

    # 使用更高效的 Predicate 定位方式（优先）
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
        # 兜底：xpath方式
        success, loc_type = click_element(driver, [
            ("xpath", f'//XCUIElementTypeButton[@name="{LOGIN_TEXT}"]'),
            ("xpath", f'//*[contains(@name,"{LOGIN_TEXT}")]'),
            ("accessibility id", LOGIN_TEXT),
        ])
        if success:
            print(f"    第{cycle_num}次 - 已点击{LOGIN_TEXT}({loc_type})")
        else:
            screenshot(driver, f"error_step2_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'{LOGIN_TEXT}'按钮")
    else:
        login_btn.click()
        print(f"    第{cycle_num}次 - 已点击{LOGIN_TEXT}(Predicate)")

    # 记录：启动App到点击登录按钮的耗时
    app_to_login_time = time.time() - step_start

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
    screenshot(driver, f"step2_customer_login_{cycle_num}")

    # 3. 输入账号
    print(f"\n[Step 3] 输入{LOGIN_MODE}账号...")

    if LOGIN_MODE == "customer":
        id_card_locators = [
            ("xpath", f'//XCUIElementTypeTextField[@value="{TEXT_ID_PLACEHOLDER}"]'),
            ("xpath", '//XCUIElementTypeTextField[contains(@value,"身份证")]'),
            ("xpath", '//XCUIElementTypeTextField[contains(@value,"411525")]'),
            ("xpath", '//XCUIElementTypeTextField[1]'),
        ]
    else:
        # 客户经理输入工号
        id_card_locators = [
            ("xpath", f'//XCUIElementTypeTextField[@value="{TEXT_MANAGER_ID_PLACEHOLDER}"]'),
            ("xpath", '//XCUIElementTypeTextField[contains(@value,"工号")]'),
            ("xpath", '//XCUIElementTypeTextField[1]'),
        ]

    success = input_text(driver, id_card_locators, LOGIN_ID, clear_first=True)
    if success:
        print(f"    第{cycle_num}次 - 已输入{LOGIN_MODE}账号")
    else:
        screenshot(driver, f"error_step3_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到账号输入框")

    screenshot(driver, f"step3_id_card_{cycle_num}")

    # 4. 输入密码
    print("\n[Step 4] 输入密码...")

    password_locators = [
        ("xpath", f'//XCUIElementTypeSecureTextField[@value="{TEXT_PASSWORD_PLACEHOLDER}"]'),
        ("xpath", '//XCUIElementTypeSecureTextField[contains(@value,"密码")]'),
        ("xpath", '//XCUIElementTypeSecureTextField[1]'),
    ]

    success = input_text(driver, password_locators, LOGIN_PASSWORD, clear_first=False)
    if success:
        print(f"    第{cycle_num}次 - 已输入密码")
    else:
        screenshot(driver, f"error_step4_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")

    screenshot(driver, f"step4_password_{cycle_num}")

    # 5. 输入验证码
    print("\n[Step 5] 输入验证码...")

    captcha_locators = [
        ("xpath", f'//XCUIElementTypeTextField[@value="{TEXT_CAPTCHA_PLACEHOLDER}"]'),
        ("xpath", '//XCUIElementTypeTextField[contains(@value,"验证码")]'),
        ("xpath", '//XCUIElementTypeTextField[2]'),
    ]

    success = input_text(driver, captcha_locators, LOGIN_CAPTCHA, clear_first=True)
    if success:
        print(f"    第{cycle_num}次 - 已输入验证码")
    else:
        screenshot(driver, f"error_step5_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")

    screenshot(driver, f"step5_captcha_{cycle_num}")

    # 6. 点击登录按钮
    print("\n[Step 6] 点击登录按钮...")

    # 使用Predicate定位登录按钮
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
        print(f"    第{cycle_num}次 - 已点击登录按钮(Predicate)")
    else:
        success, loc_type = click_element(driver, [
            ("xpath", f'//XCUIElementTypeButton[@name="{TEXT_LOGIN_BTN}"]'),
            ("xpath", f'//XCUIElementTypeButton[contains(@name,"{TEXT_LOGIN_BTN}")]'),
        ])
        if success:
            print(f"    第{cycle_num}次 - 已点击登录按钮({loc_type})")
        else:
            screenshot(driver, f"error_step6_{cycle_num}")
            raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_LOGIN_BTN}'按钮")

    # 记录登出开始时间
    logout_start = time.time()

    # 等待登录完成 + 查找"我的"按钮
    print(f"    第{cycle_num}次 - 等待页面加载...")
    my_btn = None
    max_polls = int(PAGE_LOAD_TIMEOUT / POLL_INTERVAL_FAST)
    for wait_idx in range(max_polls):
        if my_btn is None:
            try:
                buttons = driver.find_elements(AppiumBy.IOS_PREDICATE,
                    f"name CONTAINS '{TEXT_MY}' AND type == 'XCUIElementTypeButton'")
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        my_btn = btn
                        print(f"    第{cycle_num}次 - 提前找到'{TEXT_MY}'按钮(iter {wait_idx})")
                        break
            except:
                pass

        if my_btn and TEXT_CAPTCHA_PLACEHOLDER not in driver.page_source:
            print(f"    第{cycle_num}次 - 页面加载完成，等待了 {wait_idx*POLL_INTERVAL_FAST:.1f} 秒")
            break

        time.sleep(POLL_INTERVAL_FAST)
    screenshot(driver, f"step6_after_login_{cycle_num}")

    # 7. 点击【我的】
    print("\n[Step 7] 点击【我的】...")

    if my_btn is None:
        # 兜底：再找一次
        try:
            buttons = driver.find_elements(AppiumBy.IOS_PREDICATE, f"name CONTAINS '{TEXT_MY}' AND type == 'XCUIElementTypeButton'")
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    my_btn = btn
                    break
        except:
            pass

    if my_btn is None:
        screenshot(driver, f"error_step7_{cycle_num}")
        try:
            all_buttons = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeButton')
            visible = [b for b in all_buttons if b.is_displayed()]
            print(f"    页面可见按钮数: {len(visible)}")
            for b in visible:
                print(f"    按钮: name={b.get_attribute('name')}, label={b.get_attribute('label')}")
        except:
            pass
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_MY}'按钮")

    my_btn.click()
    print(f"    第{cycle_num}次 - 已点击【我的】")
    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step7_my_page_{cycle_num}")

    # 验证"我的"页面内容
    if TEXT_LOGOUT not in driver.page_source:
        print(f"    第{cycle_num}次 - 警告：我的页面未包含'{TEXT_LOGOUT}'，可能点击未成功")
        screenshot(driver, f"warning_step7_{cycle_num}")

    # 8. 点击退出登录按钮
    print("\n[Step 8] 点击退出登录按钮...")

    logout_start = time.time()

    logout_btn = None
    # 使用 Predicate 查找
    try:
        buttons = driver.find_elements(AppiumBy.IOS_PREDICATE, f"name CONTAINS '{TEXT_LOGOUT}' AND type == 'XCUIElementTypeButton'")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                logout_btn = btn
                print(f"    第{cycle_num}次 - 找到'{TEXT_LOGOUT}'按钮")
                break
    except:
        pass

    # 兜底：传统方式查找
    if logout_btn is None:
        max_polls = int(LOGOUT_CONFIRM_TIMEOUT / POLL_INTERVAL_NORMAL)
        for wait_idx in range(max_polls):
            try:
                all_buttons = driver.find_elements(By.CLASS_NAME, 'XCUIElementTypeButton')
                for btn in all_buttons:
                    name = btn.get_attribute('name') or ''
                    if (TEXT_LOGOUT in name) and btn.is_displayed() and btn.is_enabled():
                        logout_btn = btn
                        print(f"    第{cycle_num}次 - 找到'{TEXT_LOGOUT}'按钮(兜底 iter {wait_idx})")
                        break
                if logout_btn:
                    break
            except:
                pass
            time.sleep(POLL_INTERVAL_NORMAL)

    if logout_btn:
        logout_btn.click()
        print(f"    第{cycle_num}次 - 已点击退出登录按钮")
    else:
        screenshot(driver, f"error_step8_{cycle_num}")
        raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_LOGOUT}'按钮")

    # 9. 确认退出登录
    print("\n[Step 9] 确认退出登录...")

    # 直接尝试切换 WebView
    webview_ctx = None
    for ctx in driver.contexts:
        if 'WEBVIEW' in ctx:
            webview_ctx = ctx
            break

    if webview_ctx:
        try:
            driver.switch_to.context(webview_ctx)
        except:
            webview_ctx = None

    # 在 WebView 下点击确认按钮
    confirm_success = False
    for selector in [
        (By.CSS_SELECTOR, '.van-dialog__confirm'),
        (By.XPATH, "//button[contains(text(),'确认')]"),
        (By.CSS_SELECTOR, 'button.van-dialog__confirm'),
        (By.ID, "confirmBtn"),
    ]:
        try:
            confirm_btn = driver.find_element(selector[0], selector[1])
            if confirm_btn.is_displayed():
                driver.execute_script("arguments[0].click();", confirm_btn)
                print(f"    第{cycle_num}次 - JS click {selector[1]} 成功")
                confirm_success = True
                break
        except:
            pass

    # 切回原生 context
    if webview_ctx:
        try:
            driver.switch_to.context("NATIVE_APP")
        except:
            pass

    # 验证退出结果
    time.sleep(1.5)
    logout_time = time.time() - logout_start
    screenshot(driver, f"step9_verify_{cycle_num}")
    source = driver.page_source

    if '是否确认退出登录' not in source:
        print(f"    第{cycle_num}次 - 弹窗消失，退出成功")
    elif TEXT_LOGOUT not in source:
        print(f"    第{cycle_num}次 - '{TEXT_LOGOUT}'按钮消失，退出成功")
    elif (LOGIN_MODE == "customer" and TEXT_ID_PLACEHOLDER in source and LOGIN_TEXT in source) or \
         (LOGIN_MODE == "manager" and TEXT_MANAGER_ID_PLACEHOLDER in source and LOGIN_TEXT in source):
        print(f"    第{cycle_num}次 - 检测到登录界面，退出成功")
    else:
        print(f"    第{cycle_num}次 - 警告：页面状态不确定")
        screenshot(driver, f"warning_step9_{cycle_num}")

    # 10. 点击 Home 键返回桌面
    print("\n[Step 10] 点击 Home 键返回桌面...")
    try:
        driver.execute_script("mobile: pressButton", {"name": "home"})
        print(f"    第{cycle_num}次 - 已点击 Home 键")
    except Exception as e:
        print(f"    Home 键点击失败: {e}")
    time.sleep(POLL_INTERVAL_SLOW)
    screenshot(driver, f"step10_home_{cycle_num}")

    print(f"\n第 {cycle_num} 次测试完成！")
    print(f"    App启动到登录耗时: {app_to_login_time:.2f}s")
    print(f"    登出耗时: {logout_time:.2f}s")
    return app_to_login_time, logout_time


def main():
    loop_count = 1

    if len(sys.argv) > 1:
        try:
            loop_count = int(sys.argv[1])
        except ValueError:
            loop_count = 1

    print("=" * 50)
    print("iOS App 双录自动化测试")
    print(f"登录模式: {LOGIN_MODE}")
    print(f"Appium 地址: {APPIUM_URL}")
    print(f"WDA 地址: {WDA_URL}")
    print(f"UDID: {UDID}")
    print(f"Bundle ID: {BUNDLE_ID}")
    print(f"iOS 版本: {PLATFORM_VERSION}")
    print(f"循环次数: {loop_count} 次")
    print(f"截图功能: {'开启' if ENABLE_SCREENSHOT else '关闭'}")
    print("=" * 50)

    success_count = 0
    fail_count = 0
    total_app_to_login_time = 0.0
    total_logout_time = 0.0

    for i in range(1, loop_count + 1):
        driver = None
        try:
            options = get_desired_caps()
            driver = webdriver.Remote(APPIUM_URL, options=options)

            app_login_t, logout_t = run_test_cycle(driver, i)
            total_app_to_login_time += app_login_t
            total_logout_time += logout_t
            success_count += 1

        except Exception as e:
            fail_count += 1
            print(f"\n[第 {i} 次测试失败] {str(e)}")
            if driver:
                try:
                    screenshot(driver, f"error_cycle_{i}")
                except:
                    pass
            print("    继续执行下一次测试...")

        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

        time.sleep(2)

    # 打印汇总结果
    print("\n" + "=" * 50)
    print("测试汇总")
    print("=" * 50)
    print(f"总循环次数: {loop_count}")
    print(f"成功次数: {success_count}")
    print(f"失败次数: {fail_count}")
    print(f"成功率: {success_count/loop_count*100:.1f}%")
    if success_count > 0:
        print(f"平均App启动到登录耗时: {total_app_to_login_time/success_count:.2f}s")
        print(f"平均登出耗时: {total_logout_time/success_count:.2f}s")
        print(f"总App启动到登录耗时: {total_app_to_login_time:.2f}s")
        print(f"总登出耗时: {total_logout_time:.2f}s")
    print("=" * 50)

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
