"""每轮启动前清理业务 App 进程及遗留登录状态，不重用上轮账号会话。"""
import time

from ios_customer_logout import LOGOUT_SCRIPT, logout_customer_ios


def terminate_previous_app(driver, bundle_id):
    driver.switch_to.context('NATIVE_APP')
    driver.terminate_app(bundle_id)
    if driver.query_app_state(bundle_id) not in (0, 1):
        raise RuntimeError('上轮业务 App 进程未结束，停止本轮以避免复用异常现场')


def prepare_login(driver, cycle_num, bundle_id, screenshot, timeout=30):
    previous = driver.get_settings()
    try:
        driver.update_settings({'waitForIdleTimeout': 0})
        terminate_previous_app(driver, bundle_id)
        print(f'    第{cycle_num}次 - 已强制结束上轮业务 App 进程')
        driver.activate_app(bundle_id)
        deadline = time.monotonic() + timeout
        navigations = 0
        while time.monotonic() < deadline:
            # ReplayKit 结束后的系统提示可能遮挡业务页，只处理已知的直播停止提示。
            driver.switch_to.context('NATIVE_APP')
            try:
                text = driver.execute_script('mobile: alert', {'action': 'getText'})
                if 'JRecordShare' in str(text) and '停止' in str(text):
                    driver.execute_script('mobile: alert', {'action': 'accept', 'buttonLabel': '好'})
            except Exception:
                pass  # 无系统 alert 是正常情况，业务状态检查仍继续。
            contexts = [c for c in driver.contexts if 'WEBVIEW' in c]
            if not contexts:
                time.sleep(.2)
                continue
            driver.switch_to.context(contexts[0])
            state = driver.execute_script(LOGOUT_SCRIPT, None)
            if state['loggedOut']:
                print(f'    第{cycle_num}次 - 已确认未登录，开始全新登录')
                return True
            if state['my'] or state['logout']:
                print(f'    第{cycle_num}次 - 检测到遗留登录状态，先退出登录')
                logout_customer_ios(driver, cycle_num, screenshot)
                return True  # 登出函数必须验证实际返回登录页。
            # 异常可能遗留在办理提醒/完成页，退回列表后再登出，不能直接跳过登录。
            if navigations < 5:
                driver.back()
                navigations += 1
                print(f'    第{cycle_num}次 - 返回上级页面检查登录状态（{navigations}/5）')
            time.sleep(.3)
        raise RuntimeError('启动清理超时，未能确认已退出上轮账号')
    except Exception:
        driver.switch_to.context('NATIVE_APP')
        screenshot(driver, f'error_session_recovery_{cycle_num}')
        raise
    finally:
        driver.switch_to.context('NATIVE_APP')
        driver.update_settings({'waitForIdleTimeout': previous.get('waitForIdleTimeout', 10)})
