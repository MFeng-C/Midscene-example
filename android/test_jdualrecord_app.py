"""
Android UI 自动化测试脚本
包名：PACKAGE_NAME
启动类：ACTIVITY_NAME
测试流程：客户登录 -> 我的 -> 退出登录
支持循环执行
"""

import uiautomator2 as u2
import time
import subprocess
import sys
import pymysql
from config import *
from customer_self_transitions import transition as customer_self_transition

# 截图开关：True=开启截图，False=关闭截图（只保留错误截图）
DEBUG_SCREENSHOT = False


def check_and_reset_order_state(order_id):
    """检查订单状态，如果state非0则重置为0"""
    print(f"\n[订单状态检查] 检查订单状态...")
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
        cursor.execute(f"SELECT {DB_STATE_FIELD} FROM {DB_TABLE} WHERE order_id = %s", (order_id,))
        result = cursor.fetchone()

        if result is None:
            print(f"    [订单状态检查] 订单 {order_id} 不存在")
            cursor.close()
            conn.close()
            return False

        current_state = result[0]
        print(f"    [订单状态检查] 订单 {order_id} 当前状态: {current_state}")

        if current_state != 0:
            print(f"    [订单状态检查] 状态非0，正在重置为0...")
            cursor.execute(f"UPDATE {DB_TABLE} SET {DB_STATE_FIELD} = 0 WHERE order_id = %s", (order_id,))
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


def maybe_screenshot(d, filename):
    """调试用截图，只有开启DEBUG_SCREENSHOT时才会保存截图"""
    if DEBUG_SCREENSHOT:
        d.screenshot(filename)


def clear_and_set_text(d, element, text):
    """清空输入框并设置新文本"""
    element.click()
    time.sleep(0.3)
    element.clear_text()
    time.sleep(0.2)
    if element.get_text() != "":
        element.long_click()
        time.sleep(0.5)
        d(text=TEXT_SELECT_ALL).click_exists(timeout=1)
        time.sleep(0.2)
    element.clear_text()
    element.set_text(text)


def restore_system_input_method(d):
    """恢复系统输入法，避免自动化输入法工具栏残留在页面底部。"""
    try:
        enabled_input_methods = d.shell(["ime", "list", "-s"]).output
        if SYSTEM_INPUT_METHOD in enabled_input_methods:
            d.shell(["ime", "set", SYSTEM_INPUT_METHOD])
    except Exception as error:
        print(f"    恢复系统输入法失败，继续执行: {error}")


def is_keyboard_visible(d):
    """根据输入法窗口的可见节点判断软键盘是否仍显示。"""
    try:
        input_method_package = SYSTEM_INPUT_METHOD.split("/", 1)[0]
        return d(packageName=input_method_package).exists(timeout=0.3)
    except Exception:
        return False


def hide_keyboard_for_login(d, timeout=5):
    """可靠收起登录键盘，避免按钮点击落到输入法区域。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            d.hide_keyboard()
        except Exception:
            pass
        time.sleep(0.4)
        if not is_keyboard_visible(d):
            return True
        d.press("back")
        time.sleep(0.5)
        if not is_keyboard_visible(d):
            return True
        # 搜狗数字键盘的返回键偶发无效，点击工具栏右上角向下箭头兜底。
        width, height = d.window_size()
        d.click(int(width * 0.90), int(height * 0.645))
        time.sleep(0.6)
        if not is_keyboard_visible(d):
            return True
    return not is_keyboard_visible(d)


def ensure_field_value(d, resource_id, value, field_name, attempts=3):
    """写入并校验登录字段，避免输入法切换时 set_text 静默失败。"""
    for _ in range(attempts):
        field = d(resourceId=resource_id)
        if not field.exists(timeout=3):
            continue
        clear_and_set_text(d, field, value)
        time.sleep(0.4)
        current = d(resourceId=resource_id).get_text() or ""
        if current == value:
            return
    raise Exception(f"{field_name}输入未生效")


def click_bottom_navigation(d, label, timeout=10):
    """只点击底部导航栏，避免命中订单内容或隐藏 DOM 中的同名文本。"""
    _, height = d.window_size()
    deadline = time.time() + timeout
    while time.time() < deadline:
        candidates = []
        matches = d(text=label)
        for index in range(matches.count):
            item = matches[index]
            try:
                bounds = item.info.get("bounds", {})
                center_y = (bounds["top"] + bounds["bottom"]) // 2
                if (
                    bounds["right"] > bounds["left"]
                    and bounds["bottom"] > bounds["top"]
                    and center_y >= int(height * 0.75)
                ):
                    candidates.append((center_y, item))
            except Exception:
                continue
        if candidates:
            max(candidates, key=lambda value: value[0])[1].click()
            return True
        time.sleep(0.5)
    return False


def enter_manager_pure_record_page(d, cycle_num):
    """与客户纯录制一致：按文本、描述、XPath 点击导航，等待页面加载。"""
    d.press("back")
    time.sleep(1)
    d.press("back")
    time.sleep(2)

    found = False
    if d(text="纯录制").exists:
        d(text=TEXT_PURE_RECORD).click()
        found = True
    elif d(description="纯录制").exists:
        d(description="纯录制").click()
        found = True
    elif d.xpath('//*[@text="纯录制"]').exists:
        d.xpath('//*[@text="纯录制"]').click()
        found = True

    if not found:
        d.screenshot(f"manager_pure_record_error_step7_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'纯录制'按钮")
    print(f"    第{cycle_num}次 - 已点击【纯录制】")
    time.sleep(3)


def wait_scene_order_page(d, timeout=15):
    """确认当前已经切换到现场订单页，而不是仍停留在远程页。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        # WebView 会保留旧页面及同名隐藏节点，不能只检查第一个匹配项。
        # 筛选标签也可能显示已选值，不能要求它们始终为“订单状态/产品类型”。
        width, height = d.window_size()
        for selector in (d(text="现场双录"), d(description="现场双录")):
            for index in range(selector.count):
                try:
                    bounds = selector[index].info.get("bounds", {})
                    if (
                        0 <= bounds["left"] < bounds["right"] <= width
                        and 0 <= bounds["top"] < bounds["bottom"] <= height * 0.15
                    ):
                        return True
                except Exception:
                    continue
        time.sleep(0.5)
    return False


def ensure_customer_self_login_form(d, cycle_num, timeout=30):
    """每轮先识别账号状态，恢复已登录会话时先登出再进入客户登录。"""
    deadline = time.monotonic() + timeout
    logout_requested = False
    customer_entry_clicked = False
    while time.monotonic() < deadline:
        # 优先检查登录后的导航，避免隐藏的登录输入框造成误判。
        logged_in = d(text=TEXT_LOGOUT).exists or d(text=TEXT_MY).exists or d(description=TEXT_MY).exists
        if logged_in:
            print(f"    第{cycle_num}次 - 检测到已登录账号，先执行退出登录")
            customer_self_transition(d, cycle_num, 'logout')
            logout_requested = True
            continue

        try:
            # 两个角色都有三个输入框，不能仅凭数量判定客户表单。
            if (
                d.xpath('//*[@text="客户登录" and @selected="true"]').exists
                and d(className="android.widget.EditText").count >= 3
            ):
                print(f"    第{cycle_num}次 - 已确认客户登录标签选中、登录表单就绪")
                return
            if d(text="客户登录").exists and (
                not customer_entry_clicked or not d.xpath('//*[@text="客户登录" and @selected="true"]').exists
            ):
                # XPath 从新层级获取坐标，避开 WebView 文本节点的失效缓存。
                d.xpath('//*[@text="客户登录"]').click()
                customer_entry_clicked = True
                print(f"    第{cycle_num}次 - 已点击【客户登录】，等待标签选中及输入框加载")
        except Exception:
            # WebView 切换时节点可能失效，重新读取当前状态。
            pass
        time.sleep(0.3)

    d.screenshot(f"customer_self_error_step2_{cycle_num}.png")
    raise Exception(f"第{cycle_num}次 - 未能恢复到客户登录表单（已请求登出: {logout_requested}）")


def manager_login_form_visible(d):
    """判断客户经理登录的三个输入框是否已经可见。"""
    width, height = d.window_size()
    for resource_id in ("van-field-4-input", "van-field-5-input", INPUT_CAPTCHA):
        field = d(resourceId=resource_id)
        if not field.exists(timeout=0.5):
            return False
        try:
            bounds = field.info.get("bounds", {})
            if not (
                0 <= bounds["left"] < bounds["right"] <= width
                and 0 <= bounds["top"] < bounds["bottom"] <= height
            ):
                return False
        except Exception:
            return False
    return True


def select_manager_login(d, timeout=10):
    """明确点击可见的客户经理登录入口，再等待表单，避免隐藏节点误判。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        entries = d(text=TEXT_MANAGER_LOGIN)
        width, height = d.window_size()
        for index in range(entries.count):
            entry = entries[index]
            try:
                bounds = entry.info.get("bounds", {})
                if not (
                    0 <= bounds["left"] < bounds["right"] <= width
                    and 0 <= bounds["top"] < bounds["bottom"] <= height
                ):
                    continue
                entry.click()
                form_deadline = min(deadline, time.time() + 3)
                while time.time() < form_deadline:
                    if manager_login_form_visible(d):
                        return True
                    time.sleep(0.2)
                break
            except Exception:
                continue
        time.sleep(0.3)
    return False


def ensure_manager_login_form(d, cycle_num, record_type):
    """App 恢复已登录状态时先登出，再进入客户经理登录表单。"""
    if select_manager_login(d, timeout=5):
        print(f"    第{cycle_num}次 - 已点击客户经理登录并确认表单可见")
        return

    print(f"    第{cycle_num}次 - 未发现登录界面，检查并退出当前登录账号")
    for _ in range(3):
        if click_bottom_navigation(d, TEXT_MY, timeout=3):
            if d(text=TEXT_LOGOUT).exists(timeout=5):
                d(text=TEXT_LOGOUT).click()
                if d(text=TEXT_CONFIRM).exists(timeout=5):
                    d(text=TEXT_CONFIRM).click()
                break
        d.press("back")
        time.sleep(1)

    deadline = time.time() + 15
    while time.time() < deadline:
        if select_manager_login(d, timeout=3):
            print(f"    第{cycle_num}次 - 登出后已点击客户经理登录并确认表单可见")
            return
        time.sleep(0.5)

    d.screenshot(f"scene_{record_type}_error_login_state_{cycle_num}.png")
    raise Exception(f"第{cycle_num}次 - 未能从当前账号状态恢复到客户经理登录表单")


def submit_manager_login(d, cycle_num, record_type):
    """连接中断时有限重连；先确认登录结果，避免重复提交。"""
    for recovery in range(3):
        try:
            if recovery:
                d = u2.connect(DEVICE_ID)
            if d(text="远程").exists or d(text="我的").exists:
                return d
            _submit_manager_login(d, cycle_num, record_type)
            return d
        except Exception as error:
            connection_reset = (
                isinstance(error, ConnectionResetError)
                or getattr(error, "winerror", None) == 10054
                or "10054" in str(error)
                or "Connection reset by peer" in str(error)
            )
            if not connection_reset or recovery == 2:
                raise
            print(f"    第{cycle_num}次 - 登录连接中断，第{recovery + 1}/2次重连并核验页面")
            time.sleep(1)


def _submit_manager_login(d, cycle_num, record_type):
    """收起键盘、点击登录并确认已经离开客户经理登录表单。"""
    for attempt in range(1, 3):
        if not hide_keyboard_for_login(d):
            print(f"    第{cycle_num}次 - 第{attempt}次收起键盘未确认成功，继续重试登录")

        login_btn = d(className="android.widget.Button", text=TEXT_LOGIN_BTN)
        if not login_btn.exists(timeout=5):
            login_btn = d(text=TEXT_LOGIN_BTN)
        if not login_btn.exists(timeout=5):
            continue

        login_btn.click()
        deadline = time.time() + 15
        while time.time() < deadline:
            if d(text="远程").exists(timeout=0.5) or d(text="我的").exists(timeout=0.5):
                print(f"    第{cycle_num}次 - 已点击登录按钮并进入订单首页")
                return
            time.sleep(0.5)

        print(f"    第{cycle_num}次 - 第{attempt}次点击登录后仍在登录页，准备重试")

    d.screenshot(f"scene_{record_type}_error_step6_{cycle_num}.png")
    raise Exception(f"第{cycle_num}次 - 登录按钮未生效或未进入订单首页")


def submit_scene_signature(d, cycle_num):
    """容忍提交期间节点刷新，已进入下一步时不重复提交。"""
    for attempt in range(3):
        try:
            if (
                d(text=TEXT_NEXT_STEP, enabled=True).exists
                or d(text="预质检结果").exists
                or d(text="业务办理完成").exists
            ):
                return True
            button = d(text="提交签名")
            if not button.exists:
                return False
            bounds = button.info.get("bounds", {})
            x = (bounds.get("left", 0) + bounds.get("right", 0)) // 2
            y = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
            if x <= 0 or y <= 0:
                raise ValueError("提交签名按钮坐标无效")
            # 读取边界后再次确认页面，避免按钮消失后的旧坐标点击。
            if d(text=TEXT_NEXT_STEP, enabled=True).exists:
                return True
            subprocess.run([
                "adb", "-s", DEVICE_ID, "shell", "input", "tap", str(x), str(y)
            ], check=True)
            print(f"    第{cycle_num}次 - 已点击【提交签名】，等待页面确认")
            for _ in range(10):
                time.sleep(0.5)
                if (
                    d(text=TEXT_NEXT_STEP, enabled=True).exists
                    or d(text="预质检结果").exists
                    or d(text="业务办理完成").exists
                ):
                    return True
        except Exception as error:
            if not any(marker in str(error) for marker in (
                "StaleObjectException", "UiObjectNotFoundException"
            )) or attempt == 2:
                raise
            print(f"    第{cycle_num}次 - 提交签名节点已刷新，重新识别提交结果")
            time.sleep(0.3)
    raise Exception(f"第{cycle_num}次 - 提交签名后未确认进入下一步")


def exercise_customer_record_controls(d, cycle_num):
    """验证客户纯录制中的暂停、继续录制和截图功能。"""
    print(f"    第{cycle_num}次 - 点击【暂停】按钮")
    pause_button = d(text=TEXT_PAUSE_RECORD)
    if not pause_button.exists(timeout=10):
        d.screenshot(f"customer_record_error_pause_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'暂停'按钮")
    pause_button.click()

    print(f"    第{cycle_num}次 - 等待【继续录制】按钮倒计时结束...")
    continue_button = d(text=TEXT_CONTINUE_RECORD, enabled=True)
    if not continue_button.exists(timeout=10):
        d.screenshot(f"customer_record_error_continue_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - '继续录制'按钮未恢复可点击")
    continue_button.click()
    print(f"    第{cycle_num}次 - 已点击【继续录制】，等待3s倒计时...")
    time.sleep(3)

    print(f"    第{cycle_num}次 - 点击【截图】按钮")
    screenshot_button = d(text=TEXT_SCREENSHOT)
    if not screenshot_button.exists(timeout=10):
        d.screenshot(f"customer_record_error_screenshot_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'截图'按钮")
    screenshot_button.click()
    print(f"    第{cycle_num}次 - 已点击【截图】")
    maybe_screenshot(d, f"customer_record_controls_{cycle_num}.png")
    print(
        f"    第{cycle_num}次 - 截图完成，等待 "
        f"{WAIT_SCREENSHOT_BEFORE_END}s 后再结束录制..."
    )
    time.sleep(WAIT_SCREENSHOT_BEFORE_END)


def exercise_manager_pure_record_controls(d, cycle_num):
    """验证客户经理纯录制中的暂停、继续录制和截图功能。"""
    print(f"    第{cycle_num}次 - 点击【暂停】按钮")
    pause_button = d(text=TEXT_PAUSE_RECORD)
    if not pause_button.exists(timeout=10):
        d.screenshot(f"manager_pure_record_error_pause_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'暂停'按钮")
    pause_button.click()

    print(f"    第{cycle_num}次 - 等待【继续录制】按钮倒计时结束...")
    continue_button = d(text=TEXT_CONTINUE_RECORD, enabled=True)
    if not continue_button.exists(timeout=10):
        d.screenshot(f"manager_pure_record_error_continue_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - '继续录制'按钮未恢复可点击")
    continue_button.click()
    print(f"    第{cycle_num}次 - 已点击【继续录制】，等待3s倒计时...")
    time.sleep(3)

    print(f"    第{cycle_num}次 - 点击【截图】按钮")
    screenshot_button = d(text=TEXT_SCREENSHOT)
    if not screenshot_button.exists(timeout=10):
        d.screenshot(f"manager_pure_record_error_screenshot_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'截图'按钮")
    screenshot_button.click()
    print(f"    第{cycle_num}次 - 已点击【截图】")
    maybe_screenshot(d, f"manager_pure_record_controls_{cycle_num}.png")
    print(
        f"    第{cycle_num}次 - 截图完成，等待 "
        f"{WAIT_SCREENSHOT_BEFORE_END}s 后再结束录制..."
    )
    time.sleep(WAIT_SCREENSHOT_BEFORE_END)


def wait_scene_upload_completion(d, cycle_num, record_type, timeout=180):
    """等待上传确认并验证完成页，晚到的弹窗也必须在本步骤处理。"""
    deadline = time.monotonic() + timeout
    attempts = 0
    last_click = float("-inf")
    upload_seen = False
    last_error = None

    def find(label):
        # WebView 刷新时重新获取节点，兼容 text、description 和 XPath。
        for node in (d(text=label), d(description=label), d.xpath(f'//*[@text="{label}"]')):
            if node.exists:
                return node
        return None

    while time.monotonic() < deadline:
        try:
            upload_dialog = find("文件上传成功")
            if upload_dialog is None:
                upload_dialog = find("文件上传成功，确认结束")
            if upload_dialog is not None:
                upload_seen = True
                if attempts < 3 and time.monotonic() - last_click >= 3:
                    confirm = find(TEXT_CONFIRM)
                    if confirm is not None:
                        attempts += 1
                        last_click = time.monotonic()
                        confirm.click()
                        print(f"    第{cycle_num}次 - 已点击上传成功弹窗【确认】（第{attempts}次）")
            elif find("业务办理完成") is not None and find(TEXT_RETURN) is not None:
                print(f"    第{cycle_num}次 - 已确认进入【业务办理完成】页面")
                return
        except Exception as error:
            # 弹窗渲染/关闭时节点可能失效，下一轮重取；不把异常当作成功。
            last_error = str(error)
        time.sleep(0.5)

    d.screenshot(f"scene_{record_type}_error_upload_completion_{cycle_num}.png")
    reason = "已出现上传成功弹窗，但确认后未进入业务办理完成页" if upload_seen else "未识别到上传成功弹窗或业务办理完成页"
    detail = f"；最后一次节点操作异常：{last_error}" if last_error else ""
    raise Exception(f"第{cycle_num}次 - 等待上传完成超时（{timeout}s）：{reason}，确认尝试{attempts}次{detail}")


def exercise_scene_pause_resume(d, cycle_num):
    """在现场录制首个播报节点验证暂停和继续录制。"""
    print(f"    第{cycle_num}次 - 首个播报节点点击【暂停】")
    pause_button = d(text=TEXT_PAUSE_RECORD)
    if not pause_button.exists(timeout=10):
        d.screenshot(f"scene_ai_error_pause_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 首个播报节点未找到'暂停'按钮")
    time.sleep(1)
    pause_button.click()

    print(f"    第{cycle_num}次 - 等待弹窗【继续录制】3s倒计时结束...")
    continue_button = d(text=TEXT_CONTINUE_RECORD, enabled=True)
    if not continue_button.exists(timeout=10):
        d.screenshot(f"scene_ai_error_continue_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - '继续录制'按钮未恢复可点击")
    continue_button.click()
    print(f"    第{cycle_num}次 - 已点击【继续录制】，等待3s恢复倒计时...")
    time.sleep(3)


def run_manager_scene_ai_nodes(
    d, cycle_num, handle_preview=True, require_ocr_confirmation=True
):
    """按页面实际状态推进现场 AI 双录的全部业务节点。"""
    deadline = time.time() + 600
    next_count = 0
    signed_characters = 0
    ocr_skip_count = 0
    last_next_progress = None

    while time.time() < deadline:
        if d(text="业务办理完成").exists:
            return

        # 人工流程可能在最后一次“下一步”后直接进入回看页，
        # 此时“完成录制”已消失，必须退出节点循环交给预质检/上传步骤。
        if (
            d(text=TEXT_CONFIRM_COMPLETE).exists
            and d(text="预质检结果").exists
        ):
            print(f"    第{cycle_num}次 - 已进入录制回看页，继续预质检及确认完成")
            break

        finish_button = d(text=TEXT_FINISH_RECORD, enabled=True)
        if finish_button.exists:
            finish_button.click()
            print(f"    第{cycle_num}次 - 已完成全部节点并点击【完成录制】")
            break

        if signed_characters == 3:
            # WebView 中该按钮视觉上已启用时，节点的 enabled 属性偶尔仍为 false。
            # 按文本读取实际边界并点击中心，确保最后一次签名只执行“提交签名”。
            if submit_scene_signature(d, cycle_num):
                signed_characters += 1
                continue

        signing = any(
            d(textContains=marker).exists
            for marker in ("签名", "签字")
        )
        if signing and signed_characters < 3:
            width, height = d.window_size()
            # 参考手写轨迹：左上起笔，沿上弧向下，再向右上收笔。
            # 现场横屏签名画布约为 x=37%-63%、y=18%-75%，轨迹完全约束在内部。
            signature_path = [
                (int(width * 0.40), int(height * 0.39)),
                (int(width * 0.43), int(height * 0.33)),
                (int(width * 0.46), int(height * 0.29)),
                (int(width * 0.49), int(height * 0.29)),
                (int(width * 0.52), int(height * 0.34)),
                (int(width * 0.54), int(height * 0.43)),
                (int(width * 0.55), int(height * 0.53)),
                (int(width * 0.57), int(height * 0.61)),
                (int(width * 0.60), int(height * 0.57)),
            ]
            try:
                # 使用一次连续多点手势快速完成曲线，避免逐段滑动造成停顿感。
                d.swipe_points(signature_path, duration=0.05)
            except Exception as error:
                print(
                    f"    第{cycle_num}次 - UI签名轨迹注入失败，"
                    f"改用设备级分段轨迹: {error}"
                )
                for start, end in zip(signature_path, signature_path[1:]):
                    subprocess.run([
                        "adb", "-s", DEVICE_ID, "shell", "input", "swipe",
                        str(start[0]), str(start[1]), str(end[0]), str(end[1]), "10"
                    ], check=True)

            confirm_text = next(
                (
                    text for text in ("确定", "确认", "确认签名")
                    if d(text=text, enabled=True).exists(timeout=3)
                ),
                None,
            )
            if confirm_text is None:
                d.screenshot(f"scene_ai_error_sign_confirm_{cycle_num}.png")
                raise Exception(f"第{cycle_num}次 - 第{signed_characters + 1}次签名后确认按钮未启用")
            d(text=confirm_text).click()
            signed_characters += 1
            print(
                f"    第{cycle_num}次 - 签名节点已完成第 "
                f"{signed_characters}/3 次并点击【{confirm_text}】"
            )
            if signed_characters == 3:
                # 最后一个字变绿后，WebView 偶尔仍保留一次“确定”；等待渲染完成后补确认，
                # 随后页面才会展示“提交签名”或进入可继续的节点状态。
                time.sleep(0.5)
                if not d(text="提交签名").exists and d(text="确定", enabled=True).exists:
                    d(text="确定").click()
                    print(f"    第{cycle_num}次 - 最后一次签名状态已稳定并补点【确定】")
            time.sleep(0.35 if signed_characters == 3 else 0.25)
            continue

        current_progress = next(
            (index for index in range(1, 7) if d(text=f"进度 {index}/6").exists),
            None,
        )

        # OCR 人工确认弹窗优先处理，避免点击底层残留的“下一步”。
        ocr_dialog = d(text="OCR识别人工确认")
        if ocr_dialog.exists:
            if ocr_skip_count >= 2:
                d.screenshot(f"scene_ai_error_extra_ocr_dialog_{cycle_num}.png")
                raise Exception(f"第{cycle_num}次 - OCR人工确认弹窗超过预期的两次")

            skip_button = d(text="跳过")
            if skip_button.exists:
                bounds = skip_button.info.get("bounds", {})
                center_x = (bounds.get("left", 0) + bounds.get("right", 0)) // 2
                center_y = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
                if center_x <= 0 or center_y <= 0:
                    d.screenshot(f"scene_ai_error_ocr_skip_bounds_{cycle_num}.png")
                    raise Exception(f"第{cycle_num}次 - OCR人工确认窗口的'跳过'按钮坐标无效")
                subprocess.run([
                    "adb", "-s", DEVICE_ID, "shell", "input", "tap",
                    str(center_x), str(center_y)
                ], check=True)
                ocr_skip_count += 1
                face_name = "人像面" if ocr_skip_count == 1 else "国徽面"
                print(
                    f"    第{cycle_num}次 - {face_name}OCR人工确认已点击【跳过】"
                    f"（{ocr_skip_count}/2）"
                )
                time.sleep(1)
            else:
                time.sleep(0.3)
            continue

        # 两次 OCR 弹窗都处理完后，进度 4/6 页面才允许点击“下一步”进入签名。
        next_button = d(text=TEXT_NEXT_STEP, enabled=True)
        if next_button.exists:
            if (
                require_ocr_confirmation
                and current_progress == 4
                and ocr_skip_count < 2
            ):
                time.sleep(0.3)
                continue
            if current_progress is None or current_progress != last_next_progress:
                next_button.click()
                next_count += 1
                last_next_progress = current_progress
                progress_label = f"进度 {current_progress}/6" if current_progress else "未知进度"
                print(
                    f"    第{cycle_num}次 - 已推进业务节点（{progress_label}，"
                    f"下一步 {next_count}）"
                )
                time.sleep(1)
                continue
            # 同一进度中的旧“下一步”节点可能仍残留，继续检查 OCR 人工确认窗口。

        time.sleep(0.5)
    else:
        d.screenshot(f"scene_ai_error_nodes_timeout_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 现场AI双录节点推进超时")

    print(f"    第{cycle_num}次 - 等待录制回看界面...")
    if not (
        d(text="预质检结果").exists(timeout=30)
        or d(text=TEXT_CONFIRM_COMPLETE).exists(timeout=2)
    ):
        d.screenshot(f"scene_ai_error_review_page_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 完成录制后未进入录制回看界面")

    if not handle_preview:
        return

    preview_button = d(text="预质检结果", enabled=True)
    if preview_button.exists:
        preview_button.click()
        print(f"    第{cycle_num}次 - 已点击【预质检结果】")
        if d(text="预质检结果清单").exists(timeout=10):
            close_button = d(text="×")
            if close_button.exists:
                close_button.click()
            elif d(description="关闭").exists:
                d(description="关闭").click()
            else:
                width, height = d.window_size()
                d.click(int(width * 0.95), int(height * 0.08))
            print(f"    第{cycle_num}次 - 已关闭预质检结果")
            time.sleep(1)


def start_app(d, device_id, package_name, activity_name):
    """启动App，支持多桌面查找"""
    # 按home确保回到主屏幕
    d.press("home")
    time.sleep(2)

    # 方法1：直接查找并点击图标
    if d(text="智能双录").exists(timeout=5):
        d(text=APP_NAME).click()
        return True

    # 获取屏幕尺寸
    width, height = d.window_size()

    # 方法2：向左滑动查找（从右向左滑动）
    for i in range(10):
        subprocess.run([
            "adb", "-s", device_id, "shell", "input", "swipe",
            str(int(width * 0.9)), str(int(height * 0.5)),
            str(int(width * 0.1)), str(int(height * 0.5))
        ])
        time.sleep(1.5)

        if d(text="智能双录").exists(timeout=3):
            d(text=APP_NAME).click()
            return True

    # 方法3：向右滑动回到起始位置
    for i in range(10):
        subprocess.run([
            "adb", "-s", device_id, "shell", "input", "swipe",
            str(int(width * 0.1)), str(int(height * 0.5)),
            str(int(width * 0.9)), str(int(height * 0.5))
        ])
        time.sleep(0.8)

    return False


def run_test_cycle(d, device_id, cycle_num):
    """执行一次测试循环"""
    print(f"\n{'='*50}")
    print(f"开始第 {cycle_num} 次测试")
    print(f"{'='*50}")

    # 1. 启动 App
    print("\n[Step 1] 启动 App...")
    d.app_stop(PACKAGE_NAME)
    time.sleep(2)

    # 优先判断当前桌面是否有图标
    if d(text="智能双录").exists(timeout=3):
        d(text=APP_NAME).click()
        print(f"    第{cycle_num}次 - 已点击【智能双录】图标启动App")
    else:
        # 当前桌面没有，按home后向左滑动查找
        d.press("home")
        time.sleep(2)
        if not d(text="智能双录").exists(timeout=3):
            # 向左滑动查找
            width, height = d.window_size()
            for i in range(10):
                subprocess.run([
                    "adb", "-s", device_id, "shell", "input", "swipe",
                    str(int(width * 0.9)), str(int(height * 0.5)),
                    str(int(width * 0.1)), str(int(height * 0.5))
                ])
                time.sleep(1.5)
                if d(text="智能双录").exists(timeout=3):
                    d(text=APP_NAME).click()
                    break
        else:
            d(text=APP_NAME).click()
        print(f"    第{cycle_num}次 - 已启动【智能双录】App")

    print("    App 已启动，等待页面加载...")
    time.sleep(5)

    maybe_screenshot(d, f"step1_after_launch_{cycle_num}.png")

    # 2. 点击客户登录
    print("\n[Step 2] 点击客户登录...")

    # 等待客户登录按钮出现
    login_timeout = 10
    login_start = time.time()
    while time.time() - login_start < login_timeout:
        if d(text="客户登录").exists(timeout=1):
            d(text=TEXT_CUSTOMER_LOGIN).click()
            print(f"    第{cycle_num}次 - 已点击客户登录")
            break
        time.sleep(0.5)
    else:
        d.screenshot(f"error_step2_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'客户登录'按钮")
    time.sleep(2)

    maybe_screenshot(d, f"step2_after_customer_login_{cycle_num}.png")

    # 3. 输入身份证号
    print("\n[Step 3] 输入身份证号...")
    id_card_input = d(resourceId=INPUT_ID_CARD)
    if id_card_input.exists(timeout=5):
        clear_and_set_text(d, id_card_input, CUSTOMER_ID)
        print(f"    第{cycle_num}次 - 已输入身份证号")
    else:
        d.screenshot(f"error_step3_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到身份证输入框")
    time.sleep(0.5)

    # 4. 输入密码
    print("\n[Step 4] 输入密码...")
    password_input = d(resourceId=INPUT_PASSWORD)
    if password_input.exists(timeout=5):
        clear_and_set_text(d, password_input, CUSTOMER_PASSWORD)
        print(f"    第{cycle_num}次 - 已输入密码")
    else:
        d.screenshot(f"error_step4_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    time.sleep(0.5)

    # 5. 输入验证码
    print("\n[Step 5] 输入验证码...")
    captcha_input = d(resourceId=INPUT_CAPTCHA)
    if captcha_input.exists(timeout=5):
        clear_and_set_text(d, captcha_input, CUSTOMER_CAPTCHA)
        print(f"    第{cycle_num}次 - 已输入验证码")
    else:
        d.screenshot(f"error_step5_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    time.sleep(0.5)

    # 6. 点击登录按钮
    print("\n[Step 6] 点击登录按钮...")
    d.press("back")
    time.sleep(1)

    login_btn = d(className="android.widget.Button", text=TEXT_LOGIN_BTN)
    if login_btn.exists(timeout=5):
        login_btn.click()
        print(f"    第{cycle_num}次 - 已点击登录按钮")
    elif d(text="登录").exists(timeout=5):
        d(text=TEXT_LOGIN_BTN).click()
        print(f"    第{cycle_num}次 - 已点击登录按钮")
    else:
        d.screenshot(f"error_step6_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'登录'按钮")

    time.sleep(3)
    maybe_screenshot(d, f"step6_after_login_{cycle_num}.png")

    # 7. 点击【我的】
    print("\n[Step 7] 点击【我的】...")
    d.press("back")
    time.sleep(1)
    d.press("back")
    time.sleep(2)

    found = False
    if d(text="我的").exists:
        d(text=TEXT_MY).click()
        print(f"    第{cycle_num}次 - 已点击【我的】(方式1)")
        found = True
    elif d(description="我的").exists:
        d(description=TEXT_MY).click()
        print(f"    第{cycle_num}次 - 已点击【我的】(方式2)")
        found = True
    elif d.xpath('//*[@text="我的"]').exists:
        d.xpath('//*[@text="我的"]').click()  # noqa
        print(f"    第{cycle_num}次 - 已点击【我的】(方式3)")
        found = True

    if not found:
        d.screenshot(f"error_step7_{cycle_num}.png")
    time.sleep(2)
    maybe_screenshot(d, f"step7_my_page_{cycle_num}.png")

    # 8. 点击退出登录按钮
    print("\n[Step 8] 点击退出登录按钮...")
    if d(text="退出登录").exists(timeout=10):
        d(text=TEXT_LOGOUT).click()
        print(f"    第{cycle_num}次 - 已点击退出登录按钮")
    else:
        d.screenshot(f"error_step8_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")
    time.sleep(1)

    # 9. 确认退出登录
    print("\n[Step 9] 确认退出登录...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】按钮")
    else:
        d.screenshot(f"error_step9_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(1)

    # 10. 点击Home键返回手机桌面
    print("\n[Step 10] 点击Home键返回手机桌面...")
    d.press("home")
    print(f"    第{cycle_num}次 - 已点击Home键，返回手机桌面")
    time.sleep(1)

    print(f"\n第 {cycle_num} 次测试完成！")
    return True


def run_customer_record_cycle(d, device_id, cycle_num):
    """执行客户纯录制测试循环"""
    print(f"\n{'='*50}")
    print(f"开始第 {cycle_num} 次客户纯录制测试")
    print(f"{'='*50}")

    t0 = time.time()
    t_step = t0

    # 1. 启动 App - 每次循环强制重启确保状态一致
    print("\n[Step 1] 启动 App...")
    d.app_stop(PACKAGE_NAME)
    time.sleep(1)

    if d(text=APP_NAME).exists(timeout=3):
        d(text=APP_NAME).click()
    else:
        d.press("home")
        time.sleep(1)
        width, height = d.window_size()
        for i in range(5):  # 最多滑5次（原10次）
            subprocess.run([
                "adb", "-s", device_id, "shell", "input", "swipe",
                str(int(width * 0.9)), str(int(height * 0.5)),
                str(int(width * 0.1)), str(int(height * 0.5))
            ])
            time.sleep(1)
            if d(text=APP_NAME).exists(timeout=2):
                d(text=APP_NAME).click()
                break

    time.sleep(5)  # 等待App启动（原8s）
    print("    App 已启动，等待页面加载...")
    maybe_screenshot(d, f"customer_record_step1_{cycle_num}.png")
    print(f"    [计时] Step1 耗时: {time.time()-t_step:.1f}s")
    t_step = time.time()

    # 2. 点击客户登录
    print("\n[Step 2] 点击客户登录...")
    if d(text=TEXT_CUSTOMER_LOGIN).exists(timeout=10):
        d(text=TEXT_CUSTOMER_LOGIN).click()
        print(f"    第{cycle_num}次 - 已点击客户登录")
    else:
        d.screenshot(f"customer_record_error_step2_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'客户登录'按钮")
    time.sleep(1)
    maybe_screenshot(d, f"customer_record_step2_{cycle_num}.png")
    print(f"    [计时] Step2 耗时: {time.time()-t_step:.1f}s")
    t_step = time.time()

    # 3. 输入身份证号
    print("\n[Step 3] 输入身份证号...")
    id_card_input = d(resourceId=INPUT_ID_CARD)
    if id_card_input.exists(timeout=5):
        clear_and_set_text(d, id_card_input, CUSTOMER_ID)
        print(f"    第{cycle_num}次 - 已输入身份证号")
    else:
        d.screenshot(f"customer_record_error_step3_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到身份证输入框")
    time.sleep(0.5)
    print(f"    [计时] Step3 耗时: {time.time()-t_step:.1f}s")
    t_step = time.time()

    # 4. 输入密码
    print("\n[Step 4] 输入密码...")
    password_input = d(resourceId=INPUT_PASSWORD)
    if password_input.exists(timeout=5):
        clear_and_set_text(d, password_input, CUSTOMER_PASSWORD)
        print(f"    第{cycle_num}次 - 已输入密码")
    else:
        d.screenshot(f"customer_record_error_step4_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    time.sleep(0.5)
    print(f"    [计时] Step4 耗时: {time.time()-t_step:.1f}s")
    t_step = time.time()

    # 5. 输入验证码
    print("\n[Step 5] 输入验证码...")
    captcha_input = d(resourceId=INPUT_CAPTCHA)
    if captcha_input.exists(timeout=5):
        clear_and_set_text(d, captcha_input, CUSTOMER_CAPTCHA)
        print(f"    第{cycle_num}次 - 已输入验证码")
    else:
        d.screenshot(f"customer_record_error_step5_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    time.sleep(0.5)
    print(f"    [计时] Step5 耗时: {time.time()-t_step:.1f}s")
    t_step = time.time()

    # 6. 点击登录按钮
    print("\n[Step 6] 点击登录按钮...")
    d.press("back")
    time.sleep(1)

    login_btn = d(className="android.widget.Button", text=TEXT_LOGIN_BTN)
    if login_btn.exists(timeout=5):
        login_btn.click()
    elif d(text=TEXT_LOGIN_BTN).exists(timeout=5):
        d(text=TEXT_LOGIN_BTN).click()
    else:
        d.screenshot(f"customer_record_error_step6_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'登录'按钮")
    print(f"    第{cycle_num}次 - 已点击登录按钮")
    time.sleep(3)
    maybe_screenshot(d, f"customer_record_step6_{cycle_num}.png")
    print(f"    [计时] Step6 耗时: {time.time()-t_step:.1f}s")
    t_step = time.time()
    print(f"    [计时] 启动到登录总耗时: {time.time()-t0:.1f}s")

    # 7. 点击【纯录制】菜单
    print("\n[Step 7] 点击【纯录制】菜单...")
    d.press("back")
    time.sleep(1)
    d.press("back")
    time.sleep(2)

    found = False
    if d(text="纯录制").exists:
        d(text=TEXT_PURE_RECORD).click()
        found = True
    elif d(description="纯录制").exists:
        d(description="纯录制").click()
        found = True
    elif d.xpath('//*[@text="纯录制"]').exists:
        d.xpath('//*[@text="纯录制"]').click()
        found = True

    if not found:
        d.screenshot(f"customer_record_error_step7_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'纯录制'按钮")
    print(f"    第{cycle_num}次 - 已点击【纯录制】")
    time.sleep(3)
    maybe_screenshot(d, f"customer_record_step7_{cycle_num}.png")

    # 8. 使用全局搜索精确定位客户纯录制订单。
    print("\n[Step 8] 使用【全局搜索】查询纯录制订单...")
    global_search = d(text="全局搜索")
    if global_search.exists:
        global_search.click()
    else:
        width, height = d.window_size()
        d.click(int(width * 0.94), int(height * 0.03))
    time.sleep(0.8)

    edit_texts = d(className="android.widget.EditText")
    order_input = d(className="android.widget.EditText", text="订单号")
    customer_name_input = d(className="android.widget.EditText", text="客户名称")
    if order_input.exists and customer_name_input.exists:
        clear_and_set_text(d, order_input, ORDER_ID_CUSTOMER_PURE_RECORD)
        clear_and_set_text(d, customer_name_input, CUSTOMER_NAME_PURE_RECORD)
    elif edit_texts.count >= 2:
        order_input = d(className="android.widget.EditText", instance=0)
        customer_name_input = d(className="android.widget.EditText", instance=1)
        clear_and_set_text(d, order_input, ORDER_ID_CUSTOMER_PURE_RECORD)
        clear_and_set_text(d, customer_name_input, CUSTOMER_NAME_PURE_RECORD)
    else:
        # 高级搜索是 WebView 自绘表单，部分 Android 版本不会暴露 HTML 输入框。
        width, height = d.window_size()
        d.click(int(width * 0.78), int(height * 0.105))
        time.sleep(0.3)
        d.send_keys(ORDER_ID_CUSTOMER_PURE_RECORD, clear=True)
        d.click(int(width * 0.78), int(height * 0.352))
        time.sleep(0.3)
        d.send_keys(CUSTOMER_NAME_PURE_RECORD, clear=True)
    print(
        f"    第{cycle_num}次 - 已输入订单号 {ORDER_ID_CUSTOMER_PURE_RECORD}，"
        f"客户名称 {CUSTOMER_NAME_PURE_RECORD}"
    )

    # 使用自动化输入法隐藏键盘后立即查询，避免坐标落到输入法字母键上。
    d.hide_keyboard()
    width, height = d.window_size()
    d.click(int(width * 0.74), int(height * 0.71))
    print(f"    第{cycle_num}次 - 已点击【查询】")
    time.sleep(1.5)

    search_result_ready = False
    for _ in range(20):
        if not d(text="高级搜索").exists and d(text="录制").exists:
            search_result_ready = True
            break
        time.sleep(0.5)

    if not search_result_ready or not d(text=ORDER_ID_CUSTOMER_PURE_RECORD).exists(timeout=2):
        d.screenshot(f"customer_record_error_search_result_{cycle_num}.png")
        raise Exception(
            f"第{cycle_num}次 - 查询结果未出现订单 {ORDER_ID_CUSTOMER_PURE_RECORD}"
        )
    restore_system_input_method(d)
    print(f"    第{cycle_num}次 - 已查询到目标纯录制订单")
    maybe_screenshot(d, f"customer_record_global_search_{cycle_num}.png")

    # 8.1 点击查询结果订单上的【录制】按钮
    print("\n[Step 8.1] 点击查询结果订单上的【录制】按钮...")
    if d(text="录制").exists(timeout=10):
        d(text=TEXT_RECORD_BTN).click()
        print(f"    第{cycle_num}次 - 已点击【录制】按钮")
    else:
        d.screenshot(f"customer_record_error_step8_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'录制'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"customer_record_step8_{cycle_num}.png")

    # 9. 弹窗点击【确认】按钮
    print("\n[Step 9] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】按钮")
    else:
        d.screenshot(f"customer_record_error_step9_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"customer_record_step9_{cycle_num}.png")

    # 10. 跳转到办理提示界面，点击【同意并开始双录】按钮
    print("\n[Step 10] 点击【同意并开始双录】按钮...")
    if d(text="同意并开始双录").exists(timeout=10):
        d(text=TEXT_AGREE_AND_START).click()
        print(f"    第{cycle_num}次 - 已点击【同意并开始双录】")
    else:
        d.screenshot(f"customer_record_error_step10_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意并开始双录'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"customer_record_step10_{cycle_num}.png")

    # 11. 弹窗点击【立即开始】按钮
    print("\n[Step 11] 弹窗点击【立即开始】按钮...")
    if d(text="立即开始").exists(timeout=5):
        d(text=TEXT_IMMEDIATELY_START).click()
        print(f"    第{cycle_num}次 - 已点击【立即开始】")
    else:
        d.screenshot(f"customer_record_error_step11_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'立即开始'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"customer_record_step11_{cycle_num}.png")

    # 12. 跳转到检测界面，点击【同意检测】按钮
    print("\n[Step 12] 点击【同意检测】按钮...")
    if d(text="同意检测").exists(timeout=10):
        d(text=TEXT_AGREE_CHECK).click()
        print(f"    第{cycle_num}次 - 已点击【同意检测】")
    else:
        d.screenshot(f"customer_record_error_step12_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意检测'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"customer_record_step12_{cycle_num}.png")

    # 13. 等待检测结果
    print("\n[Step 13] 等待检测结果...")
    result = wait_for_detection_result(d, cycle_num, timeout=120)

    if result == "passed":
        print(f"    第{cycle_num}次 - 检测通过，等待3s后自动跳转...")
        time.sleep(3)

        # 14. 点击"开始录制"后弹窗显示3s倒计时，弹窗关闭后2s再点击"结束录制"
        print(f"    第{cycle_num}次 - 检查录制按钮状态")
        if d(text="开始录制").exists(timeout=5):
            print(f"    第{cycle_num}次 - 点击【开始录制】按钮")
            d(text=TEXT_START_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【开始录制】，等待3s倒计时...")
            # 弹窗显示3s倒计时，倒计时结束弹窗关闭
            time.sleep(3)
            # 弹窗关闭后再等2s
            print(f"    第{cycle_num}次 - 倒计时结束，等待2s...")
            time.sleep(2)

        exercise_customer_record_controls(d, cycle_num)

        print(f"    第{cycle_num}次 - 点击【结束录制】按钮")
        if d(text="结束录制").exists(timeout=10):
            d(text=TEXT_END_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【结束录制】")
        else:
            d.screenshot(f"customer_record_error_step14_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'结束录制'按钮")
        # 点击"结束录制"后跳转到录制结束界面，显示"重新录制"，"确认完成"，"结束"按钮，等待2s后点击"确认完成"
        time.sleep(2)
        print(f"    第{cycle_num}次 - 录制结束界面，等待2s后点击【确认完成】...")
        time.sleep(2)
        if d(text="确认完成").exists(timeout=5):
            d(text=TEXT_CONFIRM_COMPLETE).click()
            print(f"    第{cycle_num}次 - 已点击【确认完成】")
        else:
            d.screenshot(f"customer_record_error_step14_confirm_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'确认完成'按钮")
        maybe_screenshot(d, f"customer_record_step14_{cycle_num}.png")

        # ====== 统一处理：等待文件上传成功弹窗 ======
        # 录制结束界面点击"确认完成"后，可能出现业务完成弹窗/文件上传成功弹窗，需要处理
        print(f"    第{cycle_num}次 - 检查业务完成弹窗...")
        time.sleep(3)
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】(业务完成)")

        # 点击"业务完成"后，文件开始上传（显示转圈约4s），需要等待上传完成再点确认
        print(f"    第{cycle_num}次 - 等待文件上传完成（8s，含弹窗渲染）...")
        time.sleep(8)  # 等待文件上传完成+弹窗渲染

        # 现在上传应该完成了，等待"文件上传成功"弹窗出现
        print(f"    第{cycle_num}次 - 等待'文件上传成功'弹窗出现...")
        upload_timeout = 30
        upload_start = time.time()
        upload_found = False

        while time.time() - upload_start < upload_timeout:
            elapsed = int(time.time() - upload_start)
            if elapsed % 5 == 0:
                print(f"    第{cycle_num}次 - 等待上传成功弹窗...（已{elapsed}s）")

            # 方式1: XPath 定位
            try:
                xpath_btn = d.xpath('//*[@text="确认"]')
                if xpath_btn.exists:
                    xpath_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(xpath方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - XPath方式异常: {e}")

            # 方式2: className + text 定位
            try:
                class_btn = d(className="android.widget.Button", text="确认")
                if class_btn.exists(timeout=0.3):
                    class_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(className+text方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - className方式异常: {e}")

            # 方式3: 直接 text 定位
            try:
                if d(text="确认").exists(timeout=0.3):
                    d(text="确认").click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(text方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - text方式异常: {e}")

            time.sleep(0.5)

        if not upload_found:
            print(f"    第{cycle_num}次 - 等待{upload_timeout}秒仍未找到上传成功弹窗，跳过继续...")
            maybe_screenshot(d, f"customer_record_upload_skip_{cycle_num}.png")

        # 点击文件上传成功后，等待界面稳定
        print(f"    第{cycle_num}次 - 等待界面稳定...")
        time.sleep(5)
    elif result == "failed":
        print(f"    第{cycle_num}次 - 检测失败，点击【跳过】")
        if d(text="跳过").exists(timeout=5):
            d(text=TEXT_SKIP).click()
            print(f"    第{cycle_num}次 - 已点击【跳过】")
        time.sleep(2)

        # 风险提示弹窗点击【确认】
        print(f"    第{cycle_num}次 - 风险提示弹窗，点击【确认】")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        time.sleep(2)

        # 点击【开始录制】按钮
        print(f"    第{cycle_num}次 - 点击【开始录制】按钮")
        if d(text="开始录制").exists(timeout=10):
            d(text=TEXT_START_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【开始录制】，等待3s倒计时...")
            # 弹窗显示3s倒计时，倒计时结束弹窗关闭
            time.sleep(3)
            # 弹窗关闭后再等2s
            print(f"    第{cycle_num}次 - 倒计时结束，等待2s...")
            time.sleep(2)
        else:
            d.screenshot(f"customer_record_error_step14_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'开始录制'按钮")

        exercise_customer_record_controls(d, cycle_num)

        print(f"    第{cycle_num}次 - 点击【结束录制】按钮")
        if d(text="结束录制").exists(timeout=10):
            d(text=TEXT_END_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【结束录制】")
        else:
            d.screenshot(f"customer_record_error_step15_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'结束录制'按钮")
        # 点击"结束录制"后跳转到录制结束界面，等待2s后点击"确认完成"
        time.sleep(2)
        print(f"    第{cycle_num}次 - 录制结束界面，等待2s后点击【确认完成】...")
        time.sleep(2)
        if d(text="确认完成").exists(timeout=5):
            d(text=TEXT_CONFIRM_COMPLETE).click()
            print(f"    第{cycle_num}次 - 已点击【确认完成】")
        else:
            d.screenshot(f"customer_record_error_step15_confirm_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'确认完成'按钮")
        maybe_screenshot(d, f"customer_record_step15_{cycle_num}.png")

        # 录制结束界面点击"确认完成"后，可能出现业务完成弹窗/文件上传成功弹窗，需要处理
        print(f"    第{cycle_num}次 - 检查业务完成弹窗...")
        time.sleep(3)
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】(业务完成)")

        # 点击"业务完成"后，文件开始上传（显示转圈约4s），需要等待上传完成再点确认
        print(f"    第{cycle_num}次 - 等待文件上传完成（8s，含弹窗渲染）...")
        time.sleep(8)  # 等待文件上传完成+弹窗渲染

        # 现在上传应该完成了，等待"文件上传成功"弹窗出现
        print(f"    第{cycle_num}次 - 等待'文件上传成功'弹窗出现...")
        upload_timeout = 30
        upload_start = time.time()
        upload_found = False

        while time.time() - upload_start < upload_timeout:
            elapsed = int(time.time() - upload_start)
            if elapsed % 5 == 0:
                print(f"    第{cycle_num}次 - 等待上传成功弹窗...（已{elapsed}s）")

            # 方式1: XPath 定位
            try:
                xpath_btn = d.xpath('//*[@text="确认"]')
                if xpath_btn.exists:
                    xpath_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(xpath方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - XPath方式异常: {e}")

            # 方式2: className + text 定位
            try:
                class_btn = d(className="android.widget.Button", text="确认")
                if class_btn.exists(timeout=0.3):
                    class_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(className+text方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - className方式异常: {e}")

            # 方式3: 直接 text 定位
            try:
                if d(text="确认").exists(timeout=0.3):
                    d(text="确认").click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(text方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - text方式异常: {e}")

            time.sleep(0.5)

        if not upload_found:
            print(f"    第{cycle_num}次 - 等待{upload_timeout}秒仍未找到上传成功弹窗，跳过继续...")
            maybe_screenshot(d, f"customer_record_upload_skip_{cycle_num}.png")
            maybe_screenshot(d, f"customer_record_upload_timeout_{cycle_num}.png")

        # 点击文件上传成功后，等待界面稳定
        print(f"    第{cycle_num}次 - 等待界面稳定...")
        time.sleep(5)
    else:
        print(f"    第{cycle_num}次 - 检测超时，继续执行...")

    # 新版流程在上传确认后会直接进入业务办理完成页；旧版仍需点击右上角【结束】。
    business_complete = (
        d(text="业务办理完成").exists(timeout=2)
        or d(text=TEXT_RETURN).exists(timeout=1)
    )
    if business_complete:
        print(f"    第{cycle_num}次 - 已进入【业务办理完成】，跳过【结束】和确认弹窗")
    else:
        print(f"    第{cycle_num}次 - 点击右上角【结束】按钮")
    # Step 15已处理完上传成功弹窗，此处直接等待录制结束界面出现
    if not business_complete:
        time.sleep(3)
    maybe_screenshot(d, f"customer_record_step16_before_{cycle_num}.png")

    # 等待录制结束界面出现，找到就点，不过滤异常
    if not business_complete:
        print(f"    第{cycle_num}次 - 等待'结束'按钮出现...")
    found = business_complete
    for attempt in range(0 if business_complete else 20):
        # xpath方式
        try:
            xpath_el = d.xpath('//*[@text="结束"]')
            if xpath_el.exists:
                xpath_el.click()
                print(f"    第{cycle_num}次 - 已点击【结束】(xpath，第{attempt+1}次)")
                found = True
                break
        except Exception:
            pass

        # description方式
        try:
            desc_el = d(description=TEXT_END)
            if desc_el.exists(timeout=0.5):
                desc_el.click()
                print(f"    第{cycle_num}次 - 已点击【结束】(description，第{attempt+1}次)")
                found = True
                break
        except Exception:
            pass

        # text方式
        try:
            text_el = d(text=TEXT_END)
            if text_el.exists(timeout=0.5):
                text_el.click()
                print(f"    第{cycle_num}次 - 已点击【结束】(text，第{attempt+1}次)")
                found = True
                break
        except Exception:
            pass

        if attempt < 19:
            print(f"    第{cycle_num}次 - '结束'按钮未出现，等待1秒...(第{attempt+1}次)")
            time.sleep(1)

    if not found:
        d.screenshot(f"customer_record_error_step16_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'结束'按钮")
    if not business_complete:
        time.sleep(2)
    maybe_screenshot(d, f"customer_record_step16_{cycle_num}.png")

    # 17. 弹窗点击【确认】按钮
    if not business_complete:
        print(f"    第{cycle_num}次 - 弹窗点击【确认】按钮")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        else:
            d.screenshot(f"customer_record_error_step17_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
        time.sleep(2)
        maybe_screenshot(d, f"customer_record_step17_{cycle_num}.png")

    # 18. 点击【返回】按钮
    print(f"    第{cycle_num}次 - 点击【返回】按钮")
    return_button = d(text=TEXT_RETURN)
    if not return_button.exists(timeout=10):
        d.screenshot(f"customer_record_error_step18_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'返回'按钮")

    returned_to_list = False
    for attempt in range(3):
        if attempt == 0:
            return_button.click()
        else:
            # WebView 有时接受节点 click 但不触发页面事件，改用按钮中心的系统级点击。
            bounds = return_button.info.get("bounds", {})
            center_x = (bounds.get("left", 0) + bounds.get("right", 0)) // 2
            center_y = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
            subprocess.run([
                "adb", "-s", device_id, "shell", "input", "tap",
                str(center_x), str(center_y)
            ], check=True)
        time.sleep(1)
        if not d(text="业务办理完成").exists and d(text=TEXT_MY).exists:
            returned_to_list = True
            break

    if not returned_to_list:
        d.screenshot(f"customer_record_error_return_not_effective_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 已点击'返回'，但仍停留在业务办理完成界面")
    print(f"    第{cycle_num}次 - 已返回纯录制订单列表")
    maybe_screenshot(d, f"customer_record_step18_{cycle_num}.png")

    # 19. 点击【我的】菜单
    print(f"    第{cycle_num}次 - 点击【我的】菜单")
    found = False
    if d(text="我的").exists:
        d(text=TEXT_MY).click()
        found = True
    elif d(description="我的").exists:
        d(description=TEXT_MY).click()
        found = True
    elif d.xpath('//*[@text="我的"]').exists:
        d.xpath('//*[@text="我的"]').click()  # noqa
        found = True

    if not found:
        d.screenshot(f"customer_record_error_step19_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'我的'按钮")
    print(f"    第{cycle_num}次 - 已点击【我的】")
    time.sleep(2)
    maybe_screenshot(d, f"customer_record_step19_{cycle_num}.png")

    # 20. 点击【退出登录】按钮
    print(f"    第{cycle_num}次 - 点击【退出登录】按钮")
    if d(text="退出登录").exists(timeout=10):
        d(text=TEXT_LOGOUT).click()
        print(f"    第{cycle_num}次 - 已点击【退出登录】")
    else:
        d.screenshot(f"customer_record_error_step20_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")
    time.sleep(1)

    # 21. 弹窗点击【确认】按钮
    print("\n[Step 21] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】")
    else:
        d.screenshot(f"customer_record_error_step21_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"customer_record_step21_{cycle_num}.png")

    # 22. 点击Home键返回手机桌面
    print("\n[Step 22] 点击Home键返回手机桌面...")
    d.press("home")
    print(f"    第{cycle_num}次 - 已点击Home键，返回手机桌面")
    time.sleep(1)

    print(f"\n第 {cycle_num} 次客户纯录制测试完成！")
    return True


def run_customer_self_record_cycle(d, device_id, cycle_num):
    """执行客户自助双录测试循环"""
    print(f"\n{'='*50}")
    print(f"开始第 {cycle_num} 次客户自助双录测试")
    print(f"{'='*50}")

    # 1. 启动 App - 每次循环强制重启，确保 WebView 和登录页状态一致。
    print("\n[Step 1] 启动 App...")
    d.app_stop(PACKAGE_NAME)
    restore_system_input_method(d)
    time.sleep(2)

    if d(text="智能双录").exists(timeout=3):
        d(text=APP_NAME).click()
    else:
        d.press("home")
        time.sleep(2)
        width, height = d.window_size()
        for i in range(10):
            subprocess.run([
                "adb", "-s", device_id, "shell", "input", "swipe",
                str(int(width * 0.9)), str(int(height * 0.5)),
                str(int(width * 0.1)), str(int(height * 0.5))
            ])
            time.sleep(1.5)
            if d(text="智能双录").exists(timeout=3):
                d(text=APP_NAME).click()
                break

    time.sleep(8)
    d.app_start(PACKAGE_NAME)
    time.sleep(5)

    print("    App 已启动，等待页面加载...")
    maybe_screenshot(d, f"customer_self_step1_{cycle_num}.png")

    # 2. 进入客户登录表单。应用可能恢复到上次已经打开的登录表单。
    print("\n[Step 2] 进入客户登录...")
    ensure_customer_self_login_form(d, cycle_num)
    maybe_screenshot(d, f"customer_self_step2_{cycle_num}.png")

    # 3. 输入身份证号
    print("\n[Step 3] 输入身份证号...")
    id_card_input = d(resourceId=INPUT_ID_CARD)
    clear_and_set_text(d, id_card_input, CUSTOMER_ID)
    hide_keyboard_for_login(d)
    print(f"    第{cycle_num}次 - 已输入身份证号")
    time.sleep(0.5)

    # 4. 输入密码
    print("\n[Step 4] 输入密码...")
    password_input = d(resourceId=INPUT_PASSWORD)
    clear_and_set_text(d, password_input, CUSTOMER_PASSWORD)
    hide_keyboard_for_login(d)
    print(f"    第{cycle_num}次 - 已输入密码")
    time.sleep(0.5)

    # 5. 输入验证码
    print("\n[Step 5] 输入验证码...")
    captcha_input = d(resourceId=INPUT_CAPTCHA)
    clear_and_set_text(d, captcha_input, CUSTOMER_CAPTCHA)
    print(f"    第{cycle_num}次 - 已输入验证码")
    time.sleep(0.5)

    # 6. 点击登录按钮
    print("\n[Step 6] 点击登录按钮...")
    d.press("back")
    time.sleep(1)

    login_btn = d(className="android.widget.Button", text=TEXT_LOGIN_BTN)
    if login_btn.exists(timeout=5):
        login_btn.click()
    elif d(text="登录").exists(timeout=5):
        d(text=TEXT_LOGIN_BTN).click()
    else:
        d.screenshot(f"customer_self_error_step6_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'登录'按钮")
    print(f"    第{cycle_num}次 - 已点击登录按钮")
    customer_self_transition(d, cycle_num, 'login')
    print(f"    第{cycle_num}次 - 已确认登录成功、订单首页就绪")
    maybe_screenshot(d, f"customer_self_step6_{cycle_num}.png")

    # 7. 点击【自助】菜单
    print("\n[Step 7] 点击【自助】菜单...")
    customer_self_transition(d, cycle_num, 'self')
    print(f"    第{cycle_num}次 - 已点击【自助】")
    time.sleep(0.8)
    maybe_screenshot(d, f"customer_self_step7_{cycle_num}.png")

    # 8. 使用全局搜索精确定位本次测试订单。
    print("\n[Step 8] 使用【全局搜索】查询自助订单...")
    global_search = d(text="全局搜索")
    if global_search.exists:
        global_search.click()
    else:
        width, height = d.window_size()
        d.click(int(width * 0.94), int(height * 0.03))
    time.sleep(0.8)

    edit_texts = d(className="android.widget.EditText")
    order_input = d(className="android.widget.EditText", text="订单号")
    customer_name_input = d(className="android.widget.EditText", text="客户名称")
    if order_input.exists and customer_name_input.exists:
        clear_and_set_text(d, order_input, ORDER_ID_SELF_SERVICE)
        clear_and_set_text(d, customer_name_input, CUSTOMER_NAME_SELF_SERVICE)
    elif edit_texts.count >= 2:
        order_input = d(className="android.widget.EditText", instance=0)
        customer_name_input = d(className="android.widget.EditText", instance=1)
        clear_and_set_text(d, order_input, ORDER_ID_SELF_SERVICE)
        clear_and_set_text(d, customer_name_input, CUSTOMER_NAME_SELF_SERVICE)
    else:
        # 高级搜索是 WebView 自绘表单，部分 Android 版本不会暴露 HTML 输入框。
        width, height = d.window_size()
        d.click(int(width * 0.78), int(height * 0.105))
        time.sleep(0.3)
        d.send_keys(ORDER_ID_SELF_SERVICE, clear=True)
        d.click(int(width * 0.78), int(height * 0.352))
        time.sleep(0.3)
        d.send_keys(CUSTOMER_NAME_SELF_SERVICE, clear=True)
    print(
        f"    第{cycle_num}次 - 已输入订单号 {ORDER_ID_SELF_SERVICE}，"
        f"客户名称 {CUSTOMER_NAME_SELF_SERVICE}"
    )

    # EditText 可识别时会走上面的 set_text 分支，原逻辑没有执行收键盘动作。
    # 先切换到自动化输入法并发送隐藏广播，避免恢复搜狗后因输入框仍聚焦而再次弹起。
    d.hide_keyboard()

    width, height = d.window_size()
    d.click(int(width * 0.74), int(height * 0.71))
    print(f"    第{cycle_num}次 - 已点击【查询】")
    time.sleep(1.5)

    search_result_ready = False
    for _ in range(20):
        if not d(text="高级搜索").exists and d(text="录制").exists:
            search_result_ready = True
            break
        time.sleep(0.5)

    if not search_result_ready or not d(text=ORDER_ID_SELF_SERVICE).exists(timeout=2):
        d.screenshot(f"customer_self_error_search_result_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 查询结果未出现订单 {ORDER_ID_SELF_SERVICE}")
    restore_system_input_method(d)
    print(f"    第{cycle_num}次 - 已查询到目标自助订单")
    maybe_screenshot(d, f"customer_self_global_search_{cycle_num}.png")

    # 8.1 点击查询结果订单上的【录制】按钮
    print("\n[Step 8.1] 点击查询结果订单上的【录制】按钮...")
    if d(text="录制").exists(timeout=10):
        d(text=TEXT_RECORD_BTN).click()
        print(f"    第{cycle_num}次 - 已点击【录制】按钮")
    else:
        d.screenshot(f"customer_self_error_step8_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'录制'按钮")
    time.sleep(0.3)
    maybe_screenshot(d, f"customer_self_step8_{cycle_num}.png")

    # 9. 弹窗点击【确认】按钮
    print("\n[Step 9] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】按钮")
    else:
        d.screenshot(f"customer_self_error_step9_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(0.5)
    maybe_screenshot(d, f"customer_self_step9_{cycle_num}.png")

    # 10. 跳转到办理提示界面，点击【同意并开始录制】按钮
    print("\n[Step 10] 点击【同意并开始录制】按钮...")
    # 尝试多种按钮文本
    btn_found = False
    for btn_text in [TEXT_AGREE_AND_START_RECORD, TEXT_AGREE_AND_START, "同意并开始"]:
        if d(text=btn_text).exists(timeout=3):
            d(text=btn_text).click()
            print(f"    第{cycle_num}次 - 已点击【{btn_text}】")
            btn_found = True
            break

    if not btn_found:
        d.screenshot(f"customer_self_error_step10_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意并开始录制'按钮")
    time.sleep(0.5)
    maybe_screenshot(d, f"customer_self_step10_{cycle_num}.png")

    # 首次进入自助录制时，MIUI 会依次申请相机和麦克风权限。
    # 已授权的设备不会出现这些弹窗，因此按实际出现次数处理。
    for permission_index in range(2):
        if d(text="立即开始").exists:
            break
        allow_button = d(text="仅在使用中允许")
        if not allow_button.exists(timeout=1):
            break
        permission_title = "系统权限"
        if d(textContains="拍摄照片和录制视频").exists(timeout=0.5):
            permission_title = "相机权限"
        elif d(textContains="进行通话录音或本地录音").exists(timeout=0.5):
            permission_title = "麦克风权限"
        allow_button.click()
        print(f"    第{cycle_num}次 - 已点击【仅在使用中允许】（{permission_title}）")
        time.sleep(0.5)

    # 11. 弹窗点击【立即开始】按钮
    print("\n[Step 11] 弹窗点击【立即开始】按钮...")
    if d(text="立即开始").exists(timeout=5):
        d(text=TEXT_IMMEDIATELY_START).click()
        print(f"    第{cycle_num}次 - 已点击【立即开始】")
    else:
        d.screenshot(f"customer_self_error_step11_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'立即开始'按钮")
    time.sleep(0.5)
    maybe_screenshot(d, f"customer_self_step11_{cycle_num}.png")

    # 12. 跳转到检测界面，点击【同意检测】按钮
    print("\n[Step 12] 点击【同意检测】按钮...")
    if d(text="同意检测").exists(timeout=10):
        d(text=TEXT_AGREE_CHECK).click()
        print(f"    第{cycle_num}次 - 已点击【同意检测】")
    else:
        d.screenshot(f"customer_self_error_step12_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意检测'按钮")
    time.sleep(0.5)
    maybe_screenshot(d, f"customer_self_step12_{cycle_num}.png")

    # 13. 等待检测结果
    print("\n[Step 13] 等待检测结果...")
    result = wait_for_detection_result(d, cycle_num, timeout=120)

    if result == "failed":
        print(f"    第{cycle_num}次 - 检测未通过，点击【跳过】")
        if d(text="跳过").exists(timeout=5):
            d(text=TEXT_SKIP).click()
            print(f"    第{cycle_num}次 - 已点击【跳过】")
        time.sleep(2)

        # 风险提示弹窗点击【确认】
        print(f"    第{cycle_num}次 - 风险提示弹窗，点击【确认】")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        time.sleep(3)
    elif result == "passed":
        print(f"    第{cycle_num}次 - 检测通过，等待业务节点自动跳转...")
    else:
        print(f"    第{cycle_num}次 - 检测超时，继续执行...")
        time.sleep(2)

    maybe_screenshot(d, f"customer_self_step13_{cycle_num}.png")

    # 14. 第三个节点（播报）自动执行，等待第四个签名节点出现。
    print("\n[Step 14] 播报节点，等待进入签名节点...")
    signature_ready = False
    for _ in range(360):
        if d(text="请客户进行签字").exists(timeout=0.2):
            signature_ready = True
            break
        time.sleep(0.3)
    if not signature_ready:
        d.screenshot(f"customer_self_error_wait_signature_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 播报节点后未进入签名节点")
    print(f"    第{cycle_num}次 - 已进入第4/4签名节点")
    maybe_screenshot(d, f"customer_self_signature_ready_{cycle_num}.png")

    # 15. 第四个节点：逐字签名并确认。
    print("\n[Step 15] 签名节点，逐字签名并确认...")
    width, height = d.window_size()
    signed_characters = 0
    business_completed = False
    for _ in range(75):
        if d(text="业务办理完成").exists:
            business_completed = True
            break
        if d(text="提交签名").exists:
            break

        confirm_text = None
        for candidate in ("确定", "确认"):
            if d(text=candidate).exists:
                confirm_text = candidate
                break
        if confirm_text is None:
            time.sleep(0.2)
            continue

        offset = signed_characters * int(width * 0.015)
        signature_path = [
            (int(width * 0.31) + offset, int(height * 0.43)),
            (int(width * 0.38) + offset, int(height * 0.41)),
            (int(width * 0.47) + offset, int(height * 0.38)),
            (int(width * 0.47) + offset, int(height * 0.56)),
            (int(width * 0.55) + offset, int(height * 0.51)),
            (int(width * 0.64) + offset, int(height * 0.46)),
            (int(width * 0.70) + offset, int(height * 0.44)),
        ]
        d.swipe_points(signature_path, duration=0.10)
        time.sleep(0.05)
        d(text=confirm_text).click()
        signed_characters += 1
        print(f"    第{cycle_num}次 - 已完成第 {signed_characters} 个字符并点击【{confirm_text}】")
        time.sleep(0.2)

    if not business_completed:
        submit_signature = d(text="提交签名")
        if submit_signature.exists(timeout=10):
            submit_signature.click()
            print(f"    第{cycle_num}次 - 已点击【提交签名】")
            maybe_screenshot(d, f"customer_self_signature_submitted_{cycle_num}.png")
        elif d(text="业务办理完成").exists(timeout=3):
            business_completed = True
            print(f"    第{cycle_num}次 - 签名确认后已直接进入业务办理完成界面")
        else:
            d.screenshot(f"customer_self_error_signature_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 签名未完成，且未出现'提交签名'或完成页")

    # 16. 录制完成后必须明确进入业务办理完成页。
    print("\n[Step 16] 等待业务办理完成界面...")
    if not business_completed and not d(text="业务办理完成").exists(timeout=180):
        d.screenshot(f"customer_self_error_business_complete_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未进入'业务办理完成'界面")
    print(f"    第{cycle_num}次 - 已进入【业务办理完成】界面")
    maybe_screenshot(d, f"customer_self_business_complete_{cycle_num}.png")

    # 17. 点击完成页【返回】，回到自助订单列表。
    print("\n[Step 17] 点击【返回】按钮...")
    customer_self_transition(d, cycle_num, 'return')
    print(f"    第{cycle_num}次 - 已确认返回订单列表")
    maybe_screenshot(d, f"customer_self_step17_{cycle_num}.png")

    # 18. 自助订单列表，点击【我的】菜单
    print("\n[Step 18] 自助订单列表，点击【我的】菜单...")
    maybe_screenshot(d, f"customer_self_step18_{cycle_num}.png")

    found = False
    for attempt in range(5):
        if d(text="我的").exists:
            d(text=TEXT_MY).click()
            found = True
            break
        elif d(description="我的").exists:
            d(description=TEXT_MY).click()
            found = True
            break
        elif d.xpath('//*[@text="我的"]').exists:
            d.xpath('//*[@text="我的"]').click()  # noqa
            found = True
            break
        time.sleep(1)

    if not found:
        d.screenshot(f"customer_self_error_step18_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'我的'按钮")
    print(f"    第{cycle_num}次 - 已点击【我的】")
    time.sleep(0.5)
    maybe_screenshot(d, f"customer_self_step18_{cycle_num}.png")

    # 19. 点击【退出登录】按钮
    print("\n[Step 19] 点击【退出登录】按钮...")
    if d(text="退出登录").exists(timeout=10):
        d(text=TEXT_LOGOUT).click()
        print(f"    第{cycle_num}次 - 已点击【退出登录】")
    else:
        d.screenshot(f"customer_self_error_step19_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")
    time.sleep(0.3)

    # 20. 弹窗点击【确认】按钮
    print("\n[Step 20] 弹窗点击【确认】按钮...")
    customer_self_transition(d, cycle_num, 'logout')
    print(f"    第{cycle_num}次 - 已确认退出登录并返回登录页")
    maybe_screenshot(d, f"customer_self_step20_{cycle_num}.png")

    # 21. 点击Home键返回手机桌面
    print("\n[Step 21] 点击Home键返回手机桌面...")
    d.press("home")
    print(f"    第{cycle_num}次 - 已点击Home键，返回手机桌面")
    time.sleep(0.2)

    print(f"\n第 {cycle_num} 次客户自助双录测试完成！")
    return True


def run_manager_test_cycle(d, device_id, cycle_num):
    """执行客户经理登录测试循环"""
    print(f"\n{'='*50}")
    print(f"开始第 {cycle_num} 次客户经理登录测试")
    print(f"{'='*50}")

    # 1. 启动 App - 每次循环强制重启确保状态一致
    print("\n[Step 1] 启动 App...")
    d.app_stop(PACKAGE_NAME)
    time.sleep(2)

    # 先判断当前桌面是否有App图标
    if d(text="智能双录").exists:
        print("    当前桌面已有App图标，直接点击打开")
        d(text=APP_NAME).click()
    else:
        print("    当前桌面没有App图标，查找并打开")
        d.press("home")
        time.sleep(2)

        if d(text="智能双录").exists:
            d(text=APP_NAME).click()
        else:
            # 向左滑动查找App
            width, height = d.window_size()
            for i in range(10):
                subprocess.run([
                    "adb", "-s", device_id, "shell", "input", "swipe",
                    str(int(width * 0.9)), str(int(height * 0.5)),
                    str(int(width * 0.1)), str(int(height * 0.5))
                ])
                time.sleep(1.5)
                if d(text="智能双录").exists:
                    d(text=APP_NAME).click()
                    break

    # 等待App页面加载
    print("    等待App页面加载...")
    time.sleep(5)
    maybe_screenshot(d, f"manager_step1_launch_{cycle_num}.png")

    # 2. 明确选择客户经理登录；已登录时先登出。
    ensure_manager_login_form(d, cycle_num, "manager")
    maybe_screenshot(d, f"manager_step2_{cycle_num}.png")

    # 等待登录表单加载完成
    print("    等待登录表单加载...")
    form_timeout = 15
    form_start = time.time()
    while time.time() - form_start < form_timeout:
        if d(resourceId="van-field-4-input").exists:
            print("    登录表单已加载")
            break
        time.sleep(0.5)
    else:
        d.screenshot(f"manager_form_timeout_{cycle_num}.png")
        print("    登录表单加载超时，继续尝试...")

    # 3. 输入工号（第一个输入框）
    print("\n[Step 3] 输入工号...")
    work_id_input = d(resourceId="van-field-4-input")
    if work_id_input.exists(timeout=5):
        clear_and_set_text(d, work_id_input, MANAGER_ID)
        print(f"    第{cycle_num}次 - 已输入工号: 10001")
    else:
        d.screenshot(f"manager_error_step3_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到工号输入框")
    time.sleep(0.5)

    # 4. 输入密码（第二个输入框）
    print("\n[Step 4] 输入密码...")
    password_input = d(resourceId="van-field-5-input")
    if password_input.exists(timeout=5):
        clear_and_set_text(d, password_input, MANAGER_PASSWORD)
        print(f"    第{cycle_num}次 - 已输入密码: Aa123456")
    else:
        d.screenshot(f"manager_error_step4_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    time.sleep(0.5)

    # 5. 输入验证码（第三个输入框）
    print("\n[Step 5] 输入验证码...")
    captcha_input = d(resourceId=INPUT_CAPTCHA)
    if captcha_input.exists(timeout=5):
        clear_and_set_text(d, captcha_input, CUSTOMER_CAPTCHA)
        print(f"    第{cycle_num}次 - 已输入验证码: 0000")
    else:
        d.screenshot(f"manager_error_step5_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    time.sleep(0.5)

    # 6. 点击登录按钮
    print("\n[Step 6] 点击登录按钮...")
    d.press("back")
    time.sleep(1)

    login_btn = d(className="android.widget.Button", text=TEXT_LOGIN_BTN)
    if login_btn.exists(timeout=5):
        login_btn.click()
        print(f"    第{cycle_num}次 - 已点击登录按钮")
    elif d(text="登录").exists(timeout=5):
        d(text=TEXT_LOGIN_BTN).click()
        print(f"    第{cycle_num}次 - 已点击登录按钮")
    else:
        d.screenshot(f"manager_error_step6_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'登录'按钮")
    time.sleep(5)
    maybe_screenshot(d, f"manager_step6_login_{cycle_num}.png")

    # 7. 检查是否登录成功
    print("\n[Step 7] 检查登录状态...")
    d.press("back")
    time.sleep(1)
    d.press("back")
    time.sleep(2)

    found = False
    if d(text="纯录制").exists:
        d(text=TEXT_PURE_RECORD).click()
        found = True
    elif d(description="纯录制").exists:
        d(description="纯录制").click()
        found = True
    elif d.xpath('//*[@text="纯录制"]').exists:
        d.xpath('//*[@text="纯录制"]').click()
        found = True

    if not found:
        d.screenshot(f"manager_error_step7_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'纯录制'按钮")
    print(f"    第{cycle_num}次 - 已点击【纯录制】")
    time.sleep(3)
    maybe_screenshot(d, f"manager_step7_{cycle_num}.png")

    # 8. 点击订单上的【录制】按钮
    print("\n[Step 8] 点击订单上的【录制】按钮...")
    if d(text="录制").exists(timeout=10):
        d(text=TEXT_RECORD_BTN).click()
        print(f"    第{cycle_num}次 - 已点击【录制】按钮")
    else:
        d.screenshot(f"manager_error_step8_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'录制'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step8_{cycle_num}.png")

    # 9. 弹窗点击【确认】按钮
    print("\n[Step 9] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】按钮")
    else:
        d.screenshot(f"manager_error_step9_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step9_{cycle_num}.png")

    # 10. 点击【同意并开始双录】按钮
    print("\n[Step 10] 点击【同意并开始双录】按钮...")
    if d(text="同意并开始双录").exists(timeout=10):
        d(text=TEXT_AGREE_AND_START).click()
        print(f"    第{cycle_num}次 - 已点击【同意并开始双录】")
    else:
        d.screenshot(f"manager_error_step10_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意并开始双录'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step10_{cycle_num}.png")

    # 11. 弹窗点击【立即开始】按钮
    print("\n[Step 11] 弹窗点击【立即开始】按钮...")
    if d(text="立即开始").exists(timeout=5):
        d(text=TEXT_IMMEDIATELY_START).click()
        print(f"    第{cycle_num}次 - 已点击【立即开始】")
    else:
        d.screenshot(f"manager_error_step11_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'立即开始'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step11_{cycle_num}.png")

    # 12. 点击【同意检测】按钮
    print("\n[Step 12] 点击【同意检测】按钮...")
    if d(text="同意检测").exists(timeout=10):
        d(text=TEXT_AGREE_CHECK).click()
        print(f"    第{cycle_num}次 - 已点击【同意检测】")
    else:
        d.screenshot(f"manager_error_step12_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意检测'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step12_{cycle_num}.png")

    # 13. 等待检测结果
    print("\n[Step 13] 等待检测结果...")
    result = wait_for_detection_result(d, cycle_num, timeout=120)

    if result == "passed":
        print(f"    第{cycle_num}次 - 检测通过")
        d.screenshot(f"manager_step13_passed_{cycle_num}.png")
    elif result == "failed":
        print(f"    第{cycle_num}次 - 检测未通过，点击【跳过】")
        d.screenshot(f"manager_step13_failed_{cycle_num}.png")
        if d(text="跳过").exists(timeout=5):
            d(text=TEXT_SKIP).click()
            print(f"    第{cycle_num}次 - 已点击【跳过】")
        time.sleep(2)
        d.screenshot(f"manager_step13_skip_{cycle_num}.png")

        # 风险提示弹窗点击【确认】
        print(f"    第{cycle_num}次 - 风险提示弹窗，点击【确认】")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        time.sleep(2)
        d.screenshot(f"manager_step13_confirm_{cycle_num}.png")
    else:
        print(f"    第{cycle_num}次 - 检测超时，跳过录制步骤")
        d.press("home")
        time.sleep(1)
        return True

    # 14. 点击【开始录制】按钮
    print("\n[Step 14] 点击【开始录制】按钮...")
    if d(text="开始录制").exists(timeout=10):
        d(text=TEXT_START_RECORD).click()
        print(f"    第{cycle_num}次 - 已点击【开始录制】")
    else:
        d.screenshot(f"manager_error_step14_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'开始录制'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step14_{cycle_num}.png")

    # 15. 等待3s倒计时后点击【结束录制】按钮
    print("\n[Step 15] 等待3s倒计时后点击【结束录制】按钮...")
    time.sleep(3)

    if d(text="结束录制").exists(timeout=10):
        d(text=TEXT_END_RECORD).click()
        print(f"    第{cycle_num}次 - 已点击【结束录制】")
    else:
        d.screenshot(f"manager_error_step15_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'结束录制'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step15_{cycle_num}.png")

    # 16. 录制结束界面，点击【确认完成】按钮
    print("\n[Step 16] 录制结束界面，点击【确认完成】按钮...")
    time.sleep(3)
    if d(text="确认完成").exists(timeout=10):
        d(text=TEXT_CONFIRM_COMPLETE).click()
        print(f"    第{cycle_num}次 - 已点击【确认完成】")
    else:
        d.screenshot(f"manager_error_step16_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认完成'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step16_{cycle_num}.png")

    # 17. 业务完成弹窗，点击【确认】按钮
    print("\n[Step 17] 业务完成弹窗，点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】(业务完成)")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step17_{cycle_num}.png")

    # 18. 等待文件上传（转圈约5s），等待文件上传成功弹窗，点击【确认】
    print(f"    第{cycle_num}次 - 等待'确认'按钮...")
    upload_timeout = 120
    upload_start = time.time()
    upload_found = False

    while time.time() - upload_start < upload_timeout:
        elapsed = int(time.time() - upload_start)
        if elapsed % 10 == 0:
            print(f"    第{cycle_num}次 - 等待确认按钮...（已{elapsed}s）")

        try:
            # 方式1：text精确匹配
            btn = d(text="确认")
            if btn.exists(timeout=0.3):
                try:
                    bounds = btn.info.get("bounds", {})
                    if bounds:
                        print(f"    第{cycle_num}次 - 找到'确认'按钮, bounds={bounds}")
                        btn.click()
                        print(f"    第{cycle_num}次 - 点击【确认】(text精确)")
                        upload_found = True
                        break
                except Exception:
                    pass

            # 方式2：className包含Button + text确认
            btn2 = d(classNameMatches=".*Button.*", text="确认")
            if btn2.exists(timeout=0.3):
                try:
                    bounds = btn2.info.get("bounds", {})
                    if bounds:
                        print(f"    第{cycle_num}次 - 找到'确认'按钮, bounds={bounds}")
                        btn2.click()
                        print(f"    第{cycle_num}次 - 点击【确认】(Button+text)")
                        upload_found = True
                        break
                except Exception:
                    pass

            # 方式3：resourceId匹配confirm
            btn3 = d(resourceIdMatches=".*confirm.*", enabled=True)
            if btn3.exists(timeout=0.3):
                try:
                    bounds = btn3.info.get("bounds", {})
                    if bounds:
                        print(f"    第{cycle_num}次 - 找到确认按钮, bounds={bounds}")
                        btn3.click()
                        print(f"    第{cycle_num}次 - 点击【确认】(resourceId匹配)")
                        upload_found = True
                        break
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.5)

    if not upload_found:
        print(f"    第{cycle_num}次 - 确认按钮点击失败，截图诊断...")
        maybe_screenshot(d, f"manager_upload_timeout_{cycle_num}.png")
    time.sleep(3)
    maybe_screenshot(d, f"manager_step18_{cycle_num}.png")

    # 19. 录制结束界面，点击右上角【结束】按钮
    print("\n[Step 19] 录制结束界面，点击右上角【结束】按钮...")
    time.sleep(3)
    found = False
    if d(description="结束").exists:
        d(description=TEXT_END).click()
        found = True
    elif d(text="结束").exists:
        d(text=TEXT_END).click()
        found = True
    elif d.xpath('//*[@text="结束"]').exists:
        d.xpath('//*[@text="结束"]').click()
        found = True

    if not found:
        d.screenshot(f"manager_error_step19_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'结束'按钮")
    print(f"    第{cycle_num}次 - 已点击【结束】")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step19_{cycle_num}.png")

    # 20. 结束办理弹窗，点击【确认】按钮
    print("\n[Step 20] 结束办理弹窗，点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】(结束办理)")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step20_{cycle_num}.png")

    # 21. 业务办理完成界面，点击【返回】按钮
    print("\n[Step 21] 业务办理完成界面，点击【返回】按钮...")
    time.sleep(3)
    if d(text="返回").exists(timeout=10):
        d(text=TEXT_RETURN).click()
        print(f"    第{cycle_num}次 - 已点击【返回】")
    else:
        d.screenshot(f"manager_error_step21_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'返回'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step21_{cycle_num}.png")

    # 22. 点击【我的】菜单
    print("\n[Step 22] 点击【我的】菜单...")
    time.sleep(3)
    found = False
    if d(text="我的").exists:
        d(text=TEXT_MY).click()
        found = True
        print(f"    第{cycle_num}次 - 已点击【我的】(方式1)")
    elif d(description="我的").exists:
        d(description=TEXT_MY).click()
        found = True
        print(f"    第{cycle_num}次 - 已点击【我的】(方式2)")
    elif d.xpath('//*[@text="我的"]').exists:
        d.xpath('//*[@text="我的"]').click()  # noqa
        found = True
        print(f"    第{cycle_num}次 - 已点击【我的】(方式3)")

    if not found:
        d.screenshot(f"manager_error_step22_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'我的'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_step22_{cycle_num}.png")

    # 23. 点击【退出登录】
    print("\n[Step 23] 点击【退出登录】...")
    if d(text="退出登录").exists(timeout=10):
        d(text=TEXT_LOGOUT).click()
        print(f"    第{cycle_num}次 - 已点击【退出登录】")
    else:
        d.screenshot(f"manager_error_step23_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")
    time.sleep(1)

    # 24. 弹窗点击【确认】
    print("\n[Step 24] 弹窗点击【确认】...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】")
    else:
        d.screenshot(f"manager_error_step24_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(1)

    # 25. 返回桌面
    print("\n[Step 25] 返回桌面...")
    d.press("home")
    print(f"    第{cycle_num}次 - 已返回桌面")
    time.sleep(1)

    print(f"\n第 {cycle_num} 次客户经理纯录制测试完成！")
    return True


def wait_for_detection_result(d, cycle_num, timeout=120):
    """等待检测结果，返回 passed/failed/skip"""
    print(f"\n    等待检测结果（最多 {timeout} 秒）...")
    start_time = time.time()
    last_screenshot_time = start_time

    while time.time() - start_time < timeout:
        if d(text="已通过").exists(timeout=2):
            elapsed = int(time.time() - start_time)
            print(f"    第{cycle_num}次 - 环境检测已通过！（耗时 {elapsed} 秒）")
            maybe_screenshot(d, f"manager_record_passed_{cycle_num}.png")
            return "passed"

        if d(text="未通过").exists(timeout=2):
            elapsed = int(time.time() - start_time)
            print(f"    第{cycle_num}次 - 环境检测未通过！（耗时 {elapsed} 秒）")
            maybe_screenshot(d, f"manager_record_failed_{cycle_num}.png")
            return "failed"

        # 每10秒截一次图记录进度
        if time.time() - last_screenshot_time >= 10:
            maybe_screenshot(d, f"manager_record_detecting_{cycle_num}_{int(time.time()-start_time)}s.png")
            last_screenshot_time = time.time()

        time.sleep(1)

    print(f"    第{cycle_num}次 - 检测超时（超过 {timeout} 秒）")
    maybe_screenshot(d, f"manager_record_timeout_{cycle_num}.png")
    return "timeout"


def run_manager_record_cycle(d, device_id, cycle_num):
    """执行客户经理纯录制测试循环"""
    print(f"\n{'='*50}")
    print(f"开始第 {cycle_num} 次客户经理纯录制测试")
    print(f"{'='*50}")

    # 1. 启动 App
    print("\n[Step 1] 启动 App...")
    d.app_stop(PACKAGE_NAME)
    time.sleep(2)

    if d(text="智能双录").exists(timeout=3):
        d(text=APP_NAME).click()
    else:
        d.press("home")
        time.sleep(2)
        width, height = d.window_size()
        for i in range(10):
            subprocess.run([
                "adb", "-s", device_id, "shell", "input", "swipe",
                str(int(width * 0.9)), str(int(height * 0.5)),
                str(int(width * 0.1)), str(int(height * 0.5))
            ])
            time.sleep(1.5)
            if d(text="智能双录").exists(timeout=3):
                d(text=APP_NAME).click()
                break

    # 等待App完全启动，确保在前台
    time.sleep(8)

    # 如果App未启动，尝试直接通过包名启动
    d.app_start(PACKAGE_NAME)
    time.sleep(5)

    print("    App 已启动，等待页面加载...")
    maybe_screenshot(d, f"record_step1_launch_{cycle_num}.png")

    # 2. 点击客户经理登录菜单
    print("\n[Step 2] 点击客户经理登录...")
    ensure_manager_login_form(d, cycle_num, "record")
    time.sleep(1)
    maybe_screenshot(d, f"record_step2_{cycle_num}.png")

    # 3. 输入工号
    print("\n[Step 3] 输入工号...")
    work_id_input = d(resourceId="van-field-4-input")
    if work_id_input.exists(timeout=5):
        clear_and_set_text(d, work_id_input, MANAGER_ID)
        print(f"    第{cycle_num}次 - 已输入工号: 10001")
    else:
        d.screenshot(f"record_error_step3_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到工号输入框")
    time.sleep(0.5)

    # 4. 输入密码
    print("\n[Step 4] 输入密码...")
    password_input = d(resourceId="van-field-5-input")
    if password_input.exists(timeout=5):
        clear_and_set_text(d, password_input, MANAGER_PASSWORD)
        print(f"    第{cycle_num}次 - 已输入密码")
    else:
        d.screenshot(f"record_error_step4_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    time.sleep(0.5)

    # 5. 输入验证码
    print("\n[Step 5] 输入验证码...")
    captcha_input = d(resourceId=INPUT_CAPTCHA)
    if captcha_input.exists(timeout=5):
        clear_and_set_text(d, captcha_input, CUSTOMER_CAPTCHA)
        print(f"    第{cycle_num}次 - 已输入验证码")
    else:
        d.screenshot(f"record_error_step5_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    time.sleep(0.5)

    # 6. 收起键盘并确认登录成功后再切换导航。
    print("\n[Step 6] 点击登录按钮...")
    d = submit_manager_login(d, cycle_num, "record")
    maybe_screenshot(d, f"record_step6_login_{cycle_num}.png")

    # 7. 只点击底部纯录制导航，不用返回键干扰登录后的页面。
    print("\n[Step 7] 点击【纯录制】菜单...")
    enter_manager_pure_record_page(d, cycle_num)
    maybe_screenshot(d, f"manager_pure_record_step7_{cycle_num}.png")

    # 8. 使用全局搜索精确定位客户经理纯录制订单。
    print("\n[Step 8] 使用【全局搜索】查询纯录制订单...")
    global_search = d(text="全局搜索")
    if global_search.exists:
        global_search.click()
    else:
        width, height = d.window_size()
        d.click(int(width * 0.94), int(height * 0.03))
    time.sleep(0.8)

    edit_texts = d(className="android.widget.EditText")
    order_input = d(className="android.widget.EditText", text="订单号")
    customer_name_input = d(className="android.widget.EditText", text="客户名称")
    if order_input.exists and customer_name_input.exists:
        clear_and_set_text(d, order_input, ORDER_ID_PURE_RECORD)
        clear_and_set_text(d, customer_name_input, CUSTOMER_NAME_PURE_RECORD)
    elif edit_texts.count >= 2:
        order_input = d(className="android.widget.EditText", instance=0)
        customer_name_input = d(className="android.widget.EditText", instance=1)
        clear_and_set_text(d, order_input, ORDER_ID_PURE_RECORD)
        clear_and_set_text(d, customer_name_input, CUSTOMER_NAME_PURE_RECORD)
    else:
        # 高级搜索是 WebView 自绘表单，部分 Android 版本不会暴露 HTML 输入框。
        width, height = d.window_size()
        d.click(int(width * 0.78), int(height * 0.105))
        time.sleep(0.3)
        d.send_keys(ORDER_ID_PURE_RECORD, clear=True)
        d.click(int(width * 0.78), int(height * 0.352))
        time.sleep(0.3)
        d.send_keys(CUSTOMER_NAME_PURE_RECORD, clear=True)
    print(
        f"    第{cycle_num}次 - 已输入订单号 {ORDER_ID_PURE_RECORD}，"
        f"客户名称 {CUSTOMER_NAME_PURE_RECORD}"
    )

    # 使用自动化输入法隐藏键盘后立即查询，避免坐标落到输入法字母键上。
    d.hide_keyboard()
    width, height = d.window_size()
    d.click(int(width * 0.74), int(height * 0.71))
    print(f"    第{cycle_num}次 - 已点击【查询】")
    time.sleep(1.5)

    search_result_ready = False
    for _ in range(20):
        if not d(text="高级搜索").exists and d(text="录制").exists:
            search_result_ready = True
            break
        time.sleep(0.5)

    if not search_result_ready or not d(text=ORDER_ID_PURE_RECORD).exists(timeout=2):
        d.screenshot(f"manager_pure_record_error_search_result_{cycle_num}.png")
        raise Exception(
            f"第{cycle_num}次 - 查询结果未出现订单 {ORDER_ID_PURE_RECORD}"
        )
    restore_system_input_method(d)
    print(f"    第{cycle_num}次 - 已查询到目标纯录制订单")
    maybe_screenshot(d, f"manager_pure_record_global_search_{cycle_num}.png")

    # 8.1 点击查询结果订单上的【录制】按钮
    print("\n[Step 8.1] 点击查询结果订单上的【录制】按钮...")
    if d(text="录制").exists(timeout=10):
        d(text=TEXT_RECORD_BTN).click()
        print(f"    第{cycle_num}次 - 已点击【录制】按钮")
    else:
        d.screenshot(f"manager_pure_record_error_step8_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'录制'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_pure_record_step8_{cycle_num}.png")

    # 9. 弹窗点击【确认】按钮
    print("\n[Step 9] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】按钮")
    else:
        d.screenshot(f"manager_pure_record_error_step9_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_pure_record_step9_{cycle_num}.png")

    # 10. 跳转到办理提示界面，点击【同意并开始双录】按钮
    print("\n[Step 10] 点击【同意并开始双录】按钮...")
    if d(text="同意并开始双录").exists(timeout=10):
        d(text=TEXT_AGREE_AND_START).click()
        print(f"    第{cycle_num}次 - 已点击【同意并开始双录】")
    else:
        d.screenshot(f"manager_pure_record_error_step10_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意并开始双录'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_pure_record_step10_{cycle_num}.png")

    # 11. 弹窗点击【立即开始】按钮
    print("\n[Step 11] 弹窗点击【立即开始】按钮...")
    if d(text="立即开始").exists(timeout=5):
        d(text=TEXT_IMMEDIATELY_START).click()
        print(f"    第{cycle_num}次 - 已点击【立即开始】")
    else:
        d.screenshot(f"manager_pure_record_error_step11_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'立即开始'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_pure_record_step11_{cycle_num}.png")

    # 12. 跳转到检测界面，点击【同意检测】按钮
    print("\n[Step 12] 点击【同意检测】按钮...")
    if d(text="同意检测").exists(timeout=10):
        d(text=TEXT_AGREE_CHECK).click()
        print(f"    第{cycle_num}次 - 已点击【同意检测】")
    else:
        d.screenshot(f"manager_pure_record_error_step12_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意检测'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_pure_record_step12_{cycle_num}.png")

    # 13. 等待检测结果
    print("\n[Step 13] 等待检测结果...")
    result = wait_for_detection_result(d, cycle_num, timeout=120)

    if result == "passed":
        print(f"    第{cycle_num}次 - 检测通过，等待3s后自动跳转...")
        time.sleep(3)

        # 14. 点击"开始录制"后弹窗显示3s倒计时，弹窗关闭后2s再点击"结束录制"
        print(f"    第{cycle_num}次 - 检查录制按钮状态")
        if d(text="开始录制").exists(timeout=5):
            print(f"    第{cycle_num}次 - 点击【开始录制】按钮")
            d(text=TEXT_START_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【开始录制】，等待3s倒计时...")
            # 弹窗显示3s倒计时，倒计时结束弹窗关闭
            time.sleep(3)
            # 弹窗关闭后再等2s
            print(f"    第{cycle_num}次 - 倒计时结束，等待2s...")
            time.sleep(2)

        exercise_manager_pure_record_controls(d, cycle_num)

        print(f"    第{cycle_num}次 - 点击【结束录制】按钮")
        if d(text="结束录制").exists(timeout=10):
            d(text=TEXT_END_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【结束录制】")
        else:
            d.screenshot(f"manager_pure_record_error_step14_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'结束录制'按钮")
        # 点击"结束录制"后跳转到录制结束界面，显示"重新录制"，"确认完成"，"结束"按钮，等待2s后点击"确认完成"
        time.sleep(2)
        print(f"    第{cycle_num}次 - 录制结束界面，等待2s后点击【确认完成】...")
        time.sleep(2)
        if d(text="确认完成").exists(timeout=5):
            d(text=TEXT_CONFIRM_COMPLETE).click()
            print(f"    第{cycle_num}次 - 已点击【确认完成】")
        else:
            d.screenshot(f"manager_pure_record_error_step14_confirm_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'确认完成'按钮")
        maybe_screenshot(d, f"manager_pure_record_step14_{cycle_num}.png")

        # ====== 统一处理：等待文件上传成功弹窗 ======
        # 录制结束界面点击"确认完成"后，可能出现业务完成弹窗/文件上传成功弹窗，需要处理
        print(f"    第{cycle_num}次 - 检查业务完成弹窗...")
        time.sleep(3)
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】(业务完成)")

        # 点击"业务完成"后，文件开始上传（显示转圈约4s），需要等待上传完成再点确认
        print(f"    第{cycle_num}次 - 等待文件上传完成（8s，含弹窗渲染）...")
        time.sleep(8)  # 等待文件上传完成+弹窗渲染

        # 现在上传应该完成了，等待"文件上传成功"弹窗出现
        print(f"    第{cycle_num}次 - 等待'文件上传成功'弹窗出现...")
        upload_timeout = 30
        upload_start = time.time()
        upload_found = False

        while time.time() - upload_start < upload_timeout:
            elapsed = int(time.time() - upload_start)
            if elapsed % 5 == 0:
                print(f"    第{cycle_num}次 - 等待上传成功弹窗...（已{elapsed}s）")

            # 方式1: XPath 定位
            try:
                xpath_btn = d.xpath('//*[@text="确认"]')
                if xpath_btn.exists:
                    xpath_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(xpath方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - XPath方式异常: {e}")

            # 方式2: className + text 定位
            try:
                class_btn = d(className="android.widget.Button", text="确认")
                if class_btn.exists(timeout=0.3):
                    class_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(className+text方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - className方式异常: {e}")

            # 方式3: 直接 text 定位
            try:
                if d(text="确认").exists(timeout=0.3):
                    d(text="确认").click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(text方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - text方式异常: {e}")

            time.sleep(0.5)

        if not upload_found:
            print(f"    第{cycle_num}次 - 等待{upload_timeout}秒仍未找到上传成功弹窗，跳过继续...")
            maybe_screenshot(d, f"manager_pure_record_upload_skip_{cycle_num}.png")

        # 点击文件上传成功后，等待界面稳定
        print(f"    第{cycle_num}次 - 等待界面稳定...")
        time.sleep(5)
    elif result == "failed":
        print(f"    第{cycle_num}次 - 检测失败，点击【跳过】")
        if d(text="跳过").exists(timeout=5):
            d(text=TEXT_SKIP).click()
            print(f"    第{cycle_num}次 - 已点击【跳过】")
        time.sleep(2)

        # 风险提示弹窗点击【确认】
        print(f"    第{cycle_num}次 - 风险提示弹窗，点击【确认】")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        time.sleep(2)

        # 点击【开始录制】按钮
        print(f"    第{cycle_num}次 - 点击【开始录制】按钮")
        if d(text="开始录制").exists(timeout=10):
            d(text=TEXT_START_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【开始录制】，等待3s倒计时...")
            # 弹窗显示3s倒计时，倒计时结束弹窗关闭
            time.sleep(3)
            # 弹窗关闭后再等2s
            print(f"    第{cycle_num}次 - 倒计时结束，等待2s...")
            time.sleep(2)
        else:
            d.screenshot(f"manager_pure_record_error_step14_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'开始录制'按钮")

        exercise_manager_pure_record_controls(d, cycle_num)

        print(f"    第{cycle_num}次 - 点击【结束录制】按钮")
        if d(text="结束录制").exists(timeout=10):
            d(text=TEXT_END_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【结束录制】")
        else:
            d.screenshot(f"manager_pure_record_error_step15_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'结束录制'按钮")
        # 点击"结束录制"后跳转到录制结束界面，等待2s后点击"确认完成"
        time.sleep(2)
        print(f"    第{cycle_num}次 - 录制结束界面，等待2s后点击【确认完成】...")
        time.sleep(2)
        if d(text="确认完成").exists(timeout=5):
            d(text=TEXT_CONFIRM_COMPLETE).click()
            print(f"    第{cycle_num}次 - 已点击【确认完成】")
        else:
            d.screenshot(f"manager_pure_record_error_step15_confirm_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'确认完成'按钮")
        maybe_screenshot(d, f"manager_pure_record_step15_{cycle_num}.png")

        # 录制结束界面点击"确认完成"后，可能出现业务完成弹窗/文件上传成功弹窗，需要处理
        print(f"    第{cycle_num}次 - 检查业务完成弹窗...")
        time.sleep(3)
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】(业务完成)")

        # 点击"业务完成"后，文件开始上传（显示转圈约4s），需要等待上传完成再点确认
        print(f"    第{cycle_num}次 - 等待文件上传完成（8s，含弹窗渲染）...")
        time.sleep(8)  # 等待文件上传完成+弹窗渲染

        # 现在上传应该完成了，等待"文件上传成功"弹窗出现
        print(f"    第{cycle_num}次 - 等待'文件上传成功'弹窗出现...")
        upload_timeout = 30
        upload_start = time.time()
        upload_found = False

        while time.time() - upload_start < upload_timeout:
            elapsed = int(time.time() - upload_start)
            if elapsed % 5 == 0:
                print(f"    第{cycle_num}次 - 等待上传成功弹窗...（已{elapsed}s）")

            # 方式1: XPath 定位
            try:
                xpath_btn = d.xpath('//*[@text="确认"]')
                if xpath_btn.exists:
                    xpath_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(xpath方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - XPath方式异常: {e}")

            # 方式2: className + text 定位
            try:
                class_btn = d(className="android.widget.Button", text="确认")
                if class_btn.exists(timeout=0.3):
                    class_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(className+text方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - className方式异常: {e}")

            # 方式3: 直接 text 定位
            try:
                if d(text="确认").exists(timeout=0.3):
                    d(text="确认").click()
                    print(f"    第{cycle_num}次 - 已点击【确认】(text方式)")
                    upload_found = True
                    break
            except Exception as e:
                print(f"    第{cycle_num}次 - text方式异常: {e}")

            time.sleep(0.5)

        if not upload_found:
            print(f"    第{cycle_num}次 - 等待{upload_timeout}秒仍未找到上传成功弹窗，跳过继续...")
            maybe_screenshot(d, f"manager_pure_record_upload_skip_{cycle_num}.png")
            maybe_screenshot(d, f"manager_pure_record_upload_timeout_{cycle_num}.png")

        # 点击文件上传成功后，等待界面稳定
        print(f"    第{cycle_num}次 - 等待界面稳定...")
        time.sleep(5)
    else:
        print(f"    第{cycle_num}次 - 检测超时，继续执行...")

    # 新版流程在上传确认后会直接进入业务办理完成页；旧版仍需点击右上角【结束】。
    business_complete = (
        d(text="业务办理完成").exists(timeout=2)
        or d(text=TEXT_RETURN).exists(timeout=1)
    )
    if business_complete:
        print(f"    第{cycle_num}次 - 已进入【业务办理完成】，跳过【结束】和确认弹窗")
    else:
        print(f"    第{cycle_num}次 - 点击右上角【结束】按钮")
    # Step 15已处理完上传成功弹窗，此处直接等待录制结束界面出现
    if not business_complete:
        time.sleep(3)
    maybe_screenshot(d, f"manager_pure_record_step16_before_{cycle_num}.png")

    # 等待录制结束界面出现，找到就点，不过滤异常
    if not business_complete:
        print(f"    第{cycle_num}次 - 等待'结束'按钮出现...")
    found = business_complete
    for attempt in range(0 if business_complete else 20):
        # xpath方式
        try:
            xpath_el = d.xpath('//*[@text="结束"]')
            if xpath_el.exists:
                xpath_el.click()
                print(f"    第{cycle_num}次 - 已点击【结束】(xpath，第{attempt+1}次)")
                found = True
                break
        except Exception:
            pass

        # description方式
        try:
            desc_el = d(description=TEXT_END)
            if desc_el.exists(timeout=0.5):
                desc_el.click()
                print(f"    第{cycle_num}次 - 已点击【结束】(description，第{attempt+1}次)")
                found = True
                break
        except Exception:
            pass

        # text方式
        try:
            text_el = d(text=TEXT_END)
            if text_el.exists(timeout=0.5):
                text_el.click()
                print(f"    第{cycle_num}次 - 已点击【结束】(text，第{attempt+1}次)")
                found = True
                break
        except Exception:
            pass

        if attempt < 19:
            print(f"    第{cycle_num}次 - '结束'按钮未出现，等待1秒...(第{attempt+1}次)")
            time.sleep(1)

    if not found:
        d.screenshot(f"manager_pure_record_error_step16_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'结束'按钮")
    if not business_complete:
        time.sleep(2)
    maybe_screenshot(d, f"manager_pure_record_step16_{cycle_num}.png")

    # 17. 弹窗点击【确认】按钮
    if not business_complete:
        print(f"    第{cycle_num}次 - 弹窗点击【确认】按钮")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        else:
            d.screenshot(f"manager_pure_record_error_step17_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
        time.sleep(2)
        maybe_screenshot(d, f"manager_pure_record_step17_{cycle_num}.png")

    # 18. 点击【返回】按钮
    print(f"    第{cycle_num}次 - 点击【返回】按钮")
    return_button = d(text=TEXT_RETURN)
    if not return_button.exists(timeout=10):
        d.screenshot(f"manager_pure_record_error_step18_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'返回'按钮")

    returned_to_list = False
    for attempt in range(3):
        if attempt == 0:
            return_button.click()
        else:
            # WebView 有时接受节点 click 但不触发页面事件，改用按钮中心的系统级点击。
            bounds = return_button.info.get("bounds", {})
            center_x = (bounds.get("left", 0) + bounds.get("right", 0)) // 2
            center_y = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
            subprocess.run([
                "adb", "-s", device_id, "shell", "input", "tap",
                str(center_x), str(center_y)
            ], check=True)
        time.sleep(1)
        if not d(text="业务办理完成").exists and d(text=TEXT_MY).exists:
            returned_to_list = True
            break

    if not returned_to_list:
        d.screenshot(f"manager_pure_record_error_return_not_effective_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 已点击'返回'，但仍停留在业务办理完成界面")
    print(f"    第{cycle_num}次 - 已返回纯录制订单列表")
    maybe_screenshot(d, f"manager_pure_record_step18_{cycle_num}.png")

    # 19. 点击【我的】菜单
    print(f"    第{cycle_num}次 - 点击【我的】菜单")
    found = False
    if d(text="我的").exists:
        d(text=TEXT_MY).click()
        found = True
    elif d(description="我的").exists:
        d(description=TEXT_MY).click()
        found = True
    elif d.xpath('//*[@text="我的"]').exists:
        d.xpath('//*[@text="我的"]').click()  # noqa
        found = True

    if not found:
        d.screenshot(f"manager_pure_record_error_step19_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'我的'按钮")
    print(f"    第{cycle_num}次 - 已点击【我的】")
    time.sleep(2)
    maybe_screenshot(d, f"manager_pure_record_step19_{cycle_num}.png")

    # 20. 点击【退出登录】按钮
    print(f"    第{cycle_num}次 - 点击【退出登录】按钮")
    if d(text="退出登录").exists(timeout=10):
        d(text=TEXT_LOGOUT).click()
        print(f"    第{cycle_num}次 - 已点击【退出登录】")
    else:
        d.screenshot(f"manager_pure_record_error_step20_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")
    time.sleep(1)

    # 21. 弹窗点击【确认】按钮
    print("\n[Step 21] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】")
    else:
        d.screenshot(f"manager_pure_record_error_step21_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"manager_pure_record_step21_{cycle_num}.png")

    # 22. 点击Home键返回手机桌面
    print("\n[Step 22] 点击Home键返回手机桌面...")
    d.press("home")
    print(f"    第{cycle_num}次 - 已点击Home键，返回手机桌面")
    time.sleep(1)

    print(f"\n第 {cycle_num} 次客户经理纯录制测试完成！")
    return True


def run_manager_scene_record_cycle(d, device_id, cycle_num, record_type="ai"):
    """执行客户经理现场双录测试循环
    record_type: "ai" - AI双录流程, "manual" - 人工双录流程
    """
    print(f"\n{'='*50}")
    print(f"开始第 {cycle_num} 次客户经理现场双录测试 ({'AI' if record_type == 'ai' else '人工'}双录)")
    print(f"{'='*50}")

    # 1. 启动 App - 每次循环强制重启确保状态一致
    print("\n[Step 1] 启动 App...")
    d.app_stop(PACKAGE_NAME)
    time.sleep(2)

    # 先判断当前桌面是否有App图标
    if d(text="智能双录").exists:
        print("    当前桌面已有App图标，直接点击打开")
        d(text=APP_NAME).click()
    else:
        print("    当前桌面没有App图标，查找并打开")
        d.press("home")
        time.sleep(2)

        if d(text="智能双录").exists:
            d(text=APP_NAME).click()
        else:
            # 向左滑动查找App
            width, height = d.window_size()
            for i in range(10):
                subprocess.run([
                    "adb", "-s", device_id, "shell", "input", "swipe",
                    str(int(width * 0.9)), str(int(height * 0.5)),
                    str(int(width * 0.1)), str(int(height * 0.5))
                ])
                time.sleep(1.5)
                if d(text="智能双录").exists:
                    d(text=APP_NAME).click()
                    break

    # 等待App页面加载
    print("    等待App页面加载...")
    time.sleep(5)
    maybe_screenshot(d, f"scene_{record_type}_step1_launch_{cycle_num}.png")

    # 2. 点击客户经理登录菜单
    print("\n[Step 2] 检查登录状态并进入客户经理登录...")
    ensure_manager_login_form(d, cycle_num, record_type)
    maybe_screenshot(d, f"scene_{record_type}_step2_{cycle_num}.png")

    # 3. 输入工号
    print("\n[Step 3] 输入工号...")
    work_id_input = d(resourceId="van-field-4-input")
    if work_id_input.exists(timeout=5):
        ensure_field_value(d, "van-field-4-input", MANAGER_ID, "工号")
        print(f"    第{cycle_num}次 - 已输入工号: 10001")
    else:
        d.screenshot(f"scene_{record_type}_error_step3_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到工号输入框")
    time.sleep(0.5)

    # 4. 输入密码
    print("\n[Step 4] 输入密码...")
    password_input = d(resourceId="van-field-5-input")
    if password_input.exists(timeout=5):
        clear_and_set_text(d, password_input, MANAGER_PASSWORD)
        print(f"    第{cycle_num}次 - 已输入密码")
    else:
        d.screenshot(f"scene_{record_type}_error_step4_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    time.sleep(0.5)

    # 5. 输入验证码
    print("\n[Step 5] 输入验证码...")
    captcha_input = d(resourceId=INPUT_CAPTCHA)
    if captcha_input.exists(timeout=5):
        ensure_field_value(d, INPUT_CAPTCHA, MANAGER_CAPTCHA, "验证码")
        print(f"    第{cycle_num}次 - 已输入验证码")
    else:
        d.screenshot(f"scene_{record_type}_error_step5_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    time.sleep(0.5)

    # 6. 点击登录按钮
    print("\n[Step 6] 点击登录按钮...")
    d = submit_manager_login(d, cycle_num, record_type)
    maybe_screenshot(d, f"scene_{record_type}_step6_login_{cycle_num}.png")

    # 7. 参照纯录制：等待登录页收尾，按文本/描述/XPath 点击现场导航。
    print("\n[Step 7] 从【远程】导航栏切换到【现场】...")
    d.press("back")
    time.sleep(1)
    d.press("back")
    time.sleep(2)

    found = False
    if d(text=TEXT_SCENE).exists:
        d(text=TEXT_SCENE).click()
        found = True
    elif d(description=TEXT_SCENE).exists:
        d(description=TEXT_SCENE).click()
        found = True
    elif d.xpath('//*[@text="现场"]').exists:
        d.xpath('//*[@text="现场"]').click()
        found = True

    if not found:
        d.screenshot(f"scene_{record_type}_error_step7_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'现场'导航")
    print(f"    第{cycle_num}次 - 已点击【现场】")
    time.sleep(3)
    maybe_screenshot(d, f"scene_{record_type}_step7_{cycle_num}.png")

    # 8. 使用全局搜索精确定位现场业务订单。
    print("\n[Step 8] 使用【全局搜索】查询现场业务订单...")
    global_search = d(text="全局搜索")
    if global_search.exists:
        global_search.click()
    else:
        width, height = d.window_size()
        d.click(int(width * 0.94), int(height * 0.03))
    time.sleep(0.8)

    edit_texts = d(className="android.widget.EditText")
    order_input = d(className="android.widget.EditText", text="订单号")
    customer_name_input = d(className="android.widget.EditText", text="客户名称")
    if order_input.exists and customer_name_input.exists:
        clear_and_set_text(d, order_input, ORDER_ID_SCENE)
        clear_and_set_text(d, customer_name_input, CUSTOMER_NAME_SCENE)
    elif edit_texts.count >= 2:
        order_input = d(className="android.widget.EditText", instance=0)
        customer_name_input = d(className="android.widget.EditText", instance=1)
        clear_and_set_text(d, order_input, ORDER_ID_SCENE)
        clear_and_set_text(d, customer_name_input, CUSTOMER_NAME_SCENE)
    else:
        # 高级搜索是 WebView 自绘表单，部分 Android 版本不会暴露 HTML 输入框。
        width, height = d.window_size()
        d.click(int(width * 0.78), int(height * 0.105))
        time.sleep(0.3)
        d.send_keys(ORDER_ID_SCENE, clear=True)
        d.click(int(width * 0.78), int(height * 0.352))
        time.sleep(0.3)
        d.send_keys(CUSTOMER_NAME_SCENE, clear=True)
    print(
        f"    第{cycle_num}次 - 已输入订单号 {ORDER_ID_SCENE}，"
        f"客户名称 {CUSTOMER_NAME_SCENE}"
    )

    d.hide_keyboard()
    width, height = d.window_size()
    d.click(int(width * 0.74), int(height * 0.71))
    print(f"    第{cycle_num}次 - 已点击【查询】")
    time.sleep(1.5)

    search_result_ready = False
    for _ in range(20):
        if not d(text="高级搜索").exists and d(text="录制").exists:
            search_result_ready = True
            break
        time.sleep(0.5)

    if not search_result_ready or not d(text=ORDER_ID_SCENE).exists(timeout=2):
        d.screenshot(f"scene_{record_type}_error_search_result_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 查询结果未出现订单 {ORDER_ID_SCENE}")
    restore_system_input_method(d)
    print(f"    第{cycle_num}次 - 已查询到目标现场业务订单")
    maybe_screenshot(d, f"scene_{record_type}_global_search_{cycle_num}.png")

    # 8.1 点击查询结果订单上的【录制】按钮
    print("\n[Step 8.1] 点击查询结果订单上的【录制】按钮...")
    if d(text="录制").exists(timeout=10):
        d(text=TEXT_RECORD_BTN).click()
        print(f"    第{cycle_num}次 - 已点击【录制】按钮")
    else:
        d.screenshot(f"scene_{record_type}_error_step8_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'录制'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step8_{cycle_num}.png")

    # 9. 弹窗点击【确认】按钮
    print("\n[Step 9] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】按钮")
    else:
        d.screenshot(f"scene_{record_type}_error_step9_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step9_{cycle_num}.png")

    # 10. 点击【同意并开始双录】按钮
    print("\n[Step 10] 点击【同意并开始双录】按钮...")
    if d(text="同意并开始双录").exists(timeout=10):
        d(text=TEXT_AGREE_AND_START).click()
        print(f"    第{cycle_num}次 - 已点击【同意并开始双录】")
    else:
        d.screenshot(f"scene_{record_type}_error_step10_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意并开始双录'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step10_{cycle_num}.png")

    # 11. 弹窗点击【立即开始】按钮
    print("\n[Step 11] 弹窗点击【立即开始】按钮...")
    if d(text="立即开始").exists(timeout=5):
        d(text=TEXT_IMMEDIATELY_START).click()
        print(f"    第{cycle_num}次 - 已点击【立即开始】")
    else:
        d.screenshot(f"scene_{record_type}_error_step11_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'立即开始'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step11_{cycle_num}.png")

    # 12. 弹窗点击【同意检测】按钮
    print("\n[Step 12] 弹窗点击【同意检测】按钮...")
    if d(text="同意检测").exists(timeout=5):
        d(text=TEXT_AGREE_CHECK).click()
        print(f"    第{cycle_num}次 - 已点击【同意检测】")
    else:
        d.screenshot(f"scene_{record_type}_error_step12_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意检测'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step12_{cycle_num}.png")

    # 13. 等待检测结果
    print("\n[Step 13] 等待检测结果...")
    result = wait_for_detection_result(d, cycle_num, timeout=120)

    if result == "passed":
        print(f"    第{cycle_num}次 - 检测通过，等待3s后自动跳转...")
        time.sleep(3)
    elif result == "failed":
        print(f"    第{cycle_num}次 - 检测未通过，点击【跳过】")
        if d(text="跳过").exists(timeout=5):
            d(text=TEXT_SKIP).click()
            print(f"    第{cycle_num}次 - 已点击【跳过】")
        time.sleep(2)

        # 风险提示弹窗点击【确认】
        print(f"    第{cycle_num}次 - 风险提示弹窗，点击【确认】")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")

        # 等待跳转到等待录制界面
        print(f"    第{cycle_num}次 - 等待界面加载...")
        time.sleep(3)
    else:
        print(f"    第{cycle_num}次 - 检测超时，继续执行...")
        time.sleep(2)

    maybe_screenshot(d, f"scene_{record_type}_step13_{cycle_num}.png")

    # 14. 业务办理界面：选择 AI 或 人工
    print(f"\n[Step 14] 选择双录方式：{'开始(AI)' if record_type == 'ai' else '开始(人工)'}...")

    # 等待业务办理界面加载（检测未通过场景需要更长时间等待界面跳转）
    time.sleep(3)
    maybe_screenshot(d, f"scene_{record_type}_step14_before_{cycle_num}.png")

    if record_type == "ai":
        btn_found = False
        for attempt in range(10):
            if d(text=TEXT_START_AI).exists(timeout=2):
                d(text=TEXT_START_AI).click()
                print(f"    第{cycle_num}次 - 已点击【开始（AI）】")
                btn_found = True
                break
            else:
                print(f"    第{cycle_num}次 - 未找到'开始（AI）'，等待1秒后重试...")
                time.sleep(1)

        if not btn_found:
            d.screenshot(f"scene_{record_type}_error_step14_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'开始（AI）'按钮")
    else:
        if d(text=TEXT_START_MANUAL).exists(timeout=10):
            d(text=TEXT_START_MANUAL).click()
            print(f"    第{cycle_num}次 - 已点击【{TEXT_START_MANUAL}】")
        else:
            d.screenshot(f"scene_{record_type}_error_step14_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'{TEXT_START_MANUAL}'按钮")

    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step14_{cycle_num}.png")

    # 15. 弹窗倒计时3s
    print(f"    第{cycle_num}次 - 等待3s倒计时...")
    time.sleep(3)

    if record_type in ("ai", "manual"):
        exercise_scene_pause_resume(d, cycle_num)

    # 16. 点击"截图"按钮
    print(f"    第{cycle_num}次 - 点击【截图】按钮...")
    screenshot_btn_found = False

    # 方式1: text定位
    if d(text="截图").exists(timeout=2):
        d(text="截图").click()
        print(f"    第{cycle_num}次 - 已点击【截图】(text方式)")
        screenshot_btn_found = True
    # 方式2: description定位
    elif d(description="截图").exists(timeout=2):
        d(description="截图").click()
        print(f"    第{cycle_num}次 - 已点击【截图】(description方式)")
        screenshot_btn_found = True
    # 方式3: XPath定位
    elif d.xpath('//*[@text="截图"]').exists:
        d.xpath('//*[@text="截图"]').click()
        print(f"    第{cycle_num}次 - 已点击【截图】(xpath方式)")
        screenshot_btn_found = True

    if screenshot_btn_found:
        time.sleep(1)
        maybe_screenshot(d, f"scene_{record_type}_step16_screenshot_{cycle_num}.png")
        print(f"    第{cycle_num}次 - 截图完成")
    else:
        print(f"    第{cycle_num}次 - 未找到'截图'按钮，继续执行...")

    if record_type == "ai":
        print("\n[AI双录流程 - 6节点]")
        run_manager_scene_ai_nodes(d, cycle_num)

    if record_type == "__legacy_ai":
        # AI双录流程
        print(f"\n[AI双录流程]")

        # 16. 问答节点 - 等待"下一步"按钮可点击
        print("\n[Step 16] AI问答节点，等待'下一步'按钮可点击...")
        maybe_screenshot(d, f"scene_{record_type}_step16_{cycle_num}.png")

        # 等待"下一步"按钮可点击（话术播报结束后AI采集回答约4s）
        btn_found = False
        for attempt in range(60):
            try:
                next_btn = d(text="下一步")
                if next_btn.exists(timeout=1):
                    # 检查按钮是否可点击（enabled=True 表示可点击）
                    if next_btn.info.get("enabled", False):
                        next_btn.click()
                        print(f"    第{cycle_num}次 - 已点击【下一步】(问答->朗读)")
                        btn_found = True
                        break
            except Exception as e:
                pass
            elapsed = attempt + 1
            print(f"    第{cycle_num}次 - '下一步'按钮不可点击，等待1秒...(已等待{elapsed}s)")
            time.sleep(1)

        if not btn_found:
            d.screenshot(f"scene_{record_type}_error_step16_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - '下一步'按钮始终不可点击")

        time.sleep(3)
        maybe_screenshot(d, f"scene_{record_type}_step16_after_{cycle_num}.png")

        # 17. 朗读节点 - 等待"完成录制"可点击
        print("\n[Step 17] 朗读节点，等待'完成录制'可点击...")
        maybe_screenshot(d, f"scene_{record_type}_step17_{cycle_num}.png")

        # 先确保在朗读节点界面上
        time.sleep(3)

        # 多种定位方式尝试点击"完成录制"
        btn_clicked = False

        # 方式1: text定位直接点击
        try:
            if d(text="完成录制").exists(timeout=2):
                d(text=TEXT_FINISH_RECORD).click()
                print(f"    第{cycle_num}次 - 已点击【完成录制】(text方式)")
                btn_clicked = True
        except Exception as e:
            print(f"    第{cycle_num}次 - text方式失败: {e}")

        # 方式2: XPath定位
        if not btn_clicked:
            try:
                finish_btn = d.xpath('//*[@text="完成录制"]')
                if finish_btn.exists:
                    finish_btn.click()
                    print(f"    第{cycle_num}次 - 已点击【完成录制】(xpath方式)")
                    btn_clicked = True
            except Exception as e:
                print(f"    第{cycle_num}次 - xpath方式失败: {e}")

        # 方式3: 坐标定位（右下角区域）
        if not btn_clicked:
            try:
                width, height = d.window_size()
                # 尝试点击右下角区域
                click_x = int(width * 0.85)
                click_y = int(height * 0.85)
                d.click(click_x, click_y)
                print(f"    第{cycle_num}次 - 已点击【完成录制】(坐标方式: {click_x}, {click_y})")
                btn_clicked = True
            except Exception as e:
                print(f"    第{cycle_num}次 - 坐标方式失败: {e}")

        # 等待一下确保点击生效
        if btn_clicked:
            time.sleep(2)
        else:
            d.screenshot(f"scene_{record_type}_error_step17_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未能点击'完成录制'按钮")
        time.sleep(2)
        maybe_screenshot(d, f"scene_{record_type}_step17_{cycle_num}.png")

        # ====== 新增：预质检结果 ======
        # 等待录制结束界面出现，点击"预质检结果"按钮，关闭弹窗
        print(f"    第{cycle_num}次 - 等待录制结束界面，点击'预质检结果'按钮...")
        time.sleep(3)
        maybe_screenshot(d, f"scene_{record_type}_step17_before_precheck_{cycle_num}.png")

        # 点击"预质检结果"按钮
        precheck_btn_found = False
        for attempt in range(10):
            if d(text="预质检结果").exists(timeout=2):
                d(text="预质检结果").click()
                print(f"    第{cycle_num}次 - 已点击【预质检结果】(text方式)")
                precheck_btn_found = True
                break
            elif d(description="预质检结果").exists(timeout=2):
                d(description="预质检结果").click()
                print(f"    第{cycle_num}次 - 已点击【预质检结果】(description方式)")
                precheck_btn_found = True
                break
            elif d.xpath('//*[@text="预质检结果"]').exists:
                d.xpath('//*[@text="预质检结果"]').click()
                print(f"    第{cycle_num}次 - 已点击【预质检结果】(xpath方式)")
                precheck_btn_found = True
                break
            time.sleep(1)

        if precheck_btn_found:
            # 等待预质检结果弹窗出现
            time.sleep(2)
            maybe_screenshot(d, f"scene_{record_type}_step17_precheck_popup_{cycle_num}.png")
            print(f"    第{cycle_num}次 - 等待'预质检结果清单'弹窗...")

            # 等待弹窗出现（通过标题"预质检结果清单"确认）
            popup_found = False
            for attempt in range(10):
                if d(text="预质检结果清单").exists(timeout=2):
                    print(f"    第{cycle_num}次 - 弹窗已出现，标题：'预质检结果清单'")
                    popup_found = True
                    break
                time.sleep(1)

            if popup_found:
                # 点击弹窗右上角的"X"关闭按钮
                print(f"    第{cycle_num}次 - 点击弹窗右上角'X'关闭按钮...")
                close_found = False

                # 等待关闭按钮出现
                time.sleep(1)

                # 方式1: text="X"
                try:
                    if d(text="X").exists:
                        d(text="X").click()
                        print(f"    第{cycle_num}次 - 已点击【X】(text方式)")
                        close_found = True
                except Exception as e:
                    print(f"    第{cycle_num}次 - text方式失败: {e}")

                # 方式2: description="关闭"
                if not close_found:
                    try:
                        if d(description="关闭").exists:
                            d(description="关闭").click()
                            print(f"    第{cycle_num}次 - 已点击【X】(description方式)")
                            close_found = True
                    except Exception as e:
                        print(f"    第{cycle_num}次 - description方式失败: {e}")

                # 方式3: XPath 查找关闭按钮
                if not close_found:
                    try:
                        close_btn = d.xpath('//*[@text="×"]')
                        if close_btn.exists:
                            close_btn.click()
                            print(f"    第{cycle_num}次 - 已点击【X】(×方式)")
                            close_found = True
                    except Exception as e:
                        print(f"    第{cycle_num}次 - ×方式失败: {e}")

                # 方式4: 坐标点击（弹窗右上角区域）
                if not close_found:
                    try:
                        width, height = d.window_size()
                        # 弹窗右上角坐标
                        close_x = int(width * 0.95)
                        close_y = int(height * 0.08)
                        d.click(close_x, close_y)
                        print(f"    第{cycle_num}次 - 已点击【X】(坐标方式: {close_x}, {close_y})")
                        close_found = True
                    except Exception as e:
                        print(f"    第{cycle_num}次 - 坐标方式失败: {e}")

                if close_found:
                    time.sleep(2)
                    maybe_screenshot(d, f"scene_{record_type}_step17_precheck_closed_{cycle_num}.png")
                    print(f"    第{cycle_num}次 - 预质检结果弹窗已关闭")
            else:
                print(f"    第{cycle_num}次 - 未找到预质检结果弹窗，继续执行...")
        else:
            print(f"    第{cycle_num}次 - 未找到'预质检结果'按钮，继续执行...")

        time.sleep(2)

    elif record_type == "manual":
        # 人工双录流程
        print("\n[人工双录流程 - 6节点]")
        run_manager_scene_ai_nodes(
            d,
            cycle_num,
            handle_preview=False,
            require_ocr_confirmation=False,
        )

        # ====== 人工双录流程：预质检结果 ======
        # 等待录制结束界面出现，点击"预质检结果"按钮，关闭弹窗
        print(f"    第{cycle_num}次 - 等待录制结束界面，点击'预质检结果'按钮...")
        time.sleep(3)
        maybe_screenshot(d, f"scene_{record_type}_step17_before_precheck_{cycle_num}.png")

        # 点击"预质检结果"按钮
        precheck_btn_found = False
        for attempt in range(10):
            if d(text="预质检结果").exists(timeout=2):
                d(text="预质检结果").click()
                print(f"    第{cycle_num}次 - 已点击【预质检结果】(text方式)")
                precheck_btn_found = True
                break
            elif d(description="预质检结果").exists(timeout=2):
                d(description="预质检结果").click()
                print(f"    第{cycle_num}次 - 已点击【预质检结果】(description方式)")
                precheck_btn_found = True
                break
            elif d.xpath('//*[@text="预质检结果"]').exists:
                d.xpath('//*[@text="预质检结果"]').click()
                print(f"    第{cycle_num}次 - 已点击【预质检结果】(xpath方式)")
                precheck_btn_found = True
                break
            time.sleep(1)

        if precheck_btn_found:
            # 等待预质检结果弹窗出现
            time.sleep(2)
            maybe_screenshot(d, f"scene_{record_type}_step17_precheck_popup_{cycle_num}.png")
            print(f"    第{cycle_num}次 - 等待'预质检结果清单'弹窗...")

            # 等待弹窗出现（通过标题"预质检结果清单"确认）
            popup_found = False
            for attempt in range(10):
                if d(text="预质检结果清单").exists(timeout=2):
                    print(f"    第{cycle_num}次 - 弹窗已出现，标题：'预质检结果清单'")
                    popup_found = True
                    break
                time.sleep(1)

            if popup_found:
                # 点击弹窗右上角的"X"关闭按钮
                print(f"    第{cycle_num}次 - 点击弹窗右上角'X'关闭按钮...")
                close_found = False

                # 等待关闭按钮出现
                time.sleep(1)

                # 方式1: text="X"
                try:
                    if d(text="X").exists:
                        d(text="X").click()
                        print(f"    第{cycle_num}次 - 已点击【X】(text方式)")
                        close_found = True
                except Exception as e:
                    print(f"    第{cycle_num}次 - text方式失败: {e}")

                # 方式2: description="关闭"
                if not close_found:
                    try:
                        if d(description="关闭").exists:
                            d(description="关闭").click()
                            print(f"    第{cycle_num}次 - 已点击【X】(description方式)")
                            close_found = True
                    except Exception as e:
                        print(f"    第{cycle_num}次 - description方式失败: {e}")

                # 方式3: XPath 查找关闭按钮
                if not close_found:
                    try:
                        close_btn = d.xpath('//*[@text="×"]')
                        if close_btn.exists:
                            close_btn.click()
                            print(f"    第{cycle_num}次 - 已点击【X】(×方式)")
                            close_found = True
                    except Exception as e:
                        print(f"    第{cycle_num}次 - ×方式失败: {e}")

                # 方式4: 坐标点击（弹窗右上角区域）
                if not close_found:
                    try:
                        width, height = d.window_size()
                        # 弹窗右上角坐标
                        close_x = int(width * 0.95)
                        close_y = int(height * 0.08)
                        d.click(close_x, close_y)
                        print(f"    第{cycle_num}次 - 已点击【X】(坐标方式: {close_x}, {close_y})")
                        close_found = True
                    except Exception as e:
                        print(f"    第{cycle_num}次 - 坐标方式失败: {e}")

                if close_found:
                    time.sleep(2)
                    maybe_screenshot(d, f"scene_{record_type}_step17_precheck_closed_{cycle_num}.png")
                    print(f"    第{cycle_num}次 - 预质检结果弹窗已关闭")
            else:
                print(f"    第{cycle_num}次 - 未找到预质检结果弹窗，继续执行...")
        else:
            print(f"    第{cycle_num}次 - 未找到'预质检结果'按钮，继续执行...")

        time.sleep(2)

    # 18. 录制回看界面 - 点击"确认完成"
    print("\n[Step 18] 录制回看界面，点击'确认完成'...")
    if d(text="确认完成").exists(timeout=10):
        d(text=TEXT_CONFIRM_COMPLETE).click()
        print(f"    第{cycle_num}次 - 已点击【确认完成】")
    else:
        d.screenshot(f"scene_{record_type}_error_step18_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认完成'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step18_{cycle_num}.png")

    # 19. 弹窗点击【确认】按钮
    print("\n[Step 19] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】")
    else:
        d.screenshot(f"scene_{record_type}_error_step19_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step19_{cycle_num}.png")

    # 20-21. 持续处理上传弹窗，确认完成页后才能进入返回步骤。
    print("\n[Step 20] 等待录制文件上传成功...")
    print("\n[Step 21] 上传成功弹窗点击【确认】...")
    wait_scene_upload_completion(d, cycle_num, record_type)
    maybe_screenshot(d, f"scene_{record_type}_step21_{cycle_num}.png")

    # 22. 业务办理完成界面 - 点击【返回】
    # 注意: 点击返回后已跳转到订单列表界面（现场tab已选中），不要点击订单，直接点击"我的"菜单
    print("\n[Step 22] 业务办理完成界面，点击'返回'...")
    if d(text="返回").exists(timeout=10):
        d(text=TEXT_RETURN).click()
        print(f"    第{cycle_num}次 - 已点击【返回】")
    else:
        d.screenshot(f"scene_{record_type}_error_step22_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'返回'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step22_{cycle_num}.png")

    # 23. 点击【我的】菜单（不要点击现场或订单，直接进入我的页面退出登录）
    print("\n[Step 23] 点击【我的】菜单...")
    found = False

    # 尝试多种定位方式
    # 方式1: text定位
    if d(text="我的").exists:
        d(text=TEXT_MY).click()
        print(f"    第{cycle_num}次 - 已点击【我的】(text方式)")
        found = True
    # 方式2: description定位
    elif d(description="我的").exists:
        d(description=TEXT_MY).click()
        print(f"    第{cycle_num}次 - 已点击【我的】(description方式)")
        found = True
    # 方式3: XPath模糊匹配
    elif d.xpath('//*[contains(@text,"我的")]').exists:
        d.xpath('//*[contains(@text,"我的")]').click()
        print(f"    第{cycle_num}次 - 已点击【我的】(xpath方式)")
        found = True
    # 方式4: 坐标定位（右下角导航栏我的位置）
    if not found:
        try:
            width, height = d.window_size()
            # 我的通常在右下角区域
            click_x = int(width * 0.85)
            click_y = int(height * 0.95)
            d.click(click_x, click_y)
            print(f"    第{cycle_num}次 - 已点击【我的】(坐标方式: {click_x}, {click_y})")
            found = True
        except Exception as e:
            print(f"    第{cycle_num}次 - 坐标方式失败: {e}")

    if not found:
        d.screenshot(f"scene_{record_type}_error_step23_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'我的'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step23_{cycle_num}.png")

    # 24. 点击【退出登录】按钮
    print("\n[Step 24] 点击【退出登录】按钮...")
    if d(text="退出登录").exists(timeout=10):
        d(text=TEXT_LOGOUT).click()
        print(f"    第{cycle_num}次 - 已点击【退出登录】")
    else:
        d.screenshot(f"scene_{record_type}_error_step24_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")
    time.sleep(1)

    # 25. 弹窗点击【确认】按钮
    print("\n[Step 25] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】")
    else:
        d.screenshot(f"scene_{record_type}_error_step25_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_{record_type}_step25_{cycle_num}.png")

    # 26. 点击Home键返回桌面
    print("\n[Step 26] 点击Home键返回桌面...")
    d.press("home")
    print(f"    第{cycle_num}次 - 已返回桌面")
    time.sleep(1)

    print(f"\n第 {cycle_num} 次客户经理现场双录测试完成！")
    return True

    # 1. 启动 App
    print("\n[Step 1] 启动 App...")

    # 先判断当前桌面是否有App图标
    if d(text="智能双录").exists:
        print("    当前桌面已有App图标，直接点击打开")
        d(text=APP_NAME).click()
    else:
        print("    当前桌面没有App图标，查找并打开")
        d.press("home")
        time.sleep(2)

        if d(text="智能双录").exists:
            d(text=APP_NAME).click()
        else:
            # 向左滑动查找App
            width, height = d.window_size()
            for i in range(10):
                subprocess.run([
                    "adb", "-s", device_id, "shell", "input", "swipe",
                    str(int(width * 0.9)), str(int(height * 0.5)),
                    str(int(width * 0.1)), str(int(height * 0.5))
                ])
                time.sleep(1.5)
                if d(text="智能双录").exists:
                    d(text=APP_NAME).click()
                    break

    # 等待App页面加载
    print("    等待App页面加载...")
    time.sleep(5)
    maybe_screenshot(d, f"scene_step1_launch_{cycle_num}.png")

    # 2. 点击客户经理登录菜单
    print("\n[Step 2] 点击客户经理登录...")

    # 等待客户经理登录按钮出现
    login_timeout = 10
    login_start = time.time()
    while time.time() - login_start < login_timeout:
        if d(text="客户经理登录").exists(timeout=1):
            d(text=TEXT_MANAGER_LOGIN).click()
            print(f"    第{cycle_num}次 - 已点击客户经理登录")
            break
        time.sleep(0.5)
    else:
        d.screenshot(f"scene_error_step2_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'客户经理登录'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_step2_{cycle_num}.png")

    # 3. 输入工号
    print("\n[Step 3] 输入工号...")
    work_id_input = d(resourceId="van-field-4-input")
    if work_id_input.exists(timeout=5):
        clear_and_set_text(d, work_id_input, MANAGER_ID)
        print(f"    第{cycle_num}次 - 已输入工号: 10001")
    else:
        d.screenshot(f"scene_error_step3_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到工号输入框")
    time.sleep(0.5)

    # 4. 输入密码
    print("\n[Step 4] 输入密码...")
    password_input = d(resourceId="van-field-5-input")
    if password_input.exists(timeout=5):
        clear_and_set_text(d, password_input, MANAGER_PASSWORD)
        print(f"    第{cycle_num}次 - 已输入密码")
    else:
        d.screenshot(f"scene_error_step4_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到密码输入框")
    time.sleep(0.5)

    # 5. 输入验证码
    print("\n[Step 5] 输入验证码...")
    captcha_input = d(resourceId=INPUT_CAPTCHA)
    if captcha_input.exists(timeout=5):
        clear_and_set_text(d, captcha_input, CUSTOMER_CAPTCHA)
        print(f"    第{cycle_num}次 - 已输入验证码")
    else:
        d.screenshot(f"scene_error_step5_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到验证码输入框")
    time.sleep(0.5)

    # 6. 点击登录按钮
    print("\n[Step 6] 点击登录按钮...")
    d.press("back")
    time.sleep(1)

    login_btn = d(className="android.widget.Button", text=TEXT_LOGIN_BTN)
    if login_btn.exists(timeout=5):
        login_btn.click()
    elif d(text="登录").exists(timeout=5):
        d(text=TEXT_LOGIN_BTN).click()
    else:
        d.screenshot(f"scene_error_step6_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'登录'按钮")
    print(f"    第{cycle_num}次 - 已点击登录按钮")
    time.sleep(3)
    maybe_screenshot(d, f"scene_step6_login_{cycle_num}.png")

    # 7. 点击【现场双录】菜单
    print("\n[Step 7] 点击【现场双录】菜单...")
    d.press("back")
    time.sleep(1)
    d.press("back")
    time.sleep(2)

    found = False
    if d(text="现场双录").exists:
        d(text="现场双录").click()
        found = True
    elif d(description="现场双录").exists:
        d(description="现场双录").click()
        found = True
    elif d.xpath('//*[@text="现场双录"]').exists:
        d.xpath('//*[@text="现场双录"]').click()
        found = True

    if not found:
        d.screenshot(f"scene_error_step7_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'现场双录'按钮")
    print(f"    第{cycle_num}次 - 已点击【现场双录】")
    time.sleep(3)
    maybe_screenshot(d, f"scene_step7_{cycle_num}.png")

    # 8. 点击订单上的【录制】按钮
    print("\n[Step 8] 点击订单上的【录制】按钮...")
    if d(text="录制").exists(timeout=10):
        d(text=TEXT_RECORD_BTN).click()
        print(f"    第{cycle_num}次 - 已点击【录制】按钮")
    else:
        d.screenshot(f"scene_error_step8_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'录制'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_step8_{cycle_num}.png")

    # 9. 弹窗点击【确认】按钮
    print("\n[Step 9] 弹窗点击【确认】按钮...")
    if d(text="确认").exists(timeout=5):
        d(text=TEXT_CONFIRM).click()
        print(f"    第{cycle_num}次 - 已点击【确认】按钮")
    else:
        d.screenshot(f"scene_error_step9_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_step9_{cycle_num}.png")

    # 10. 点击【同意并开始双录】按钮
    print("\n[Step 10] 点击【同意并开始双录】按钮...")
    if d(text="同意并开始双录").exists(timeout=10):
        d(text=TEXT_AGREE_AND_START).click()
        print(f"    第{cycle_num}次 - 已点击【同意并开始双录】")
    else:
        d.screenshot(f"scene_error_step10_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意并开始双录'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_step10_{cycle_num}.png")

    # 11. 点击【进入双录】按钮
    print("\n[Step 11] 点击【进入双录】按钮...")
    if d(text="进入双录").exists(timeout=10):
        d(text="进入双录").click()
        print(f"    第{cycle_num}次 - 已点击【进入双录】")
    else:
        d.screenshot(f"scene_error_step11_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'进入双录'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_step11_{cycle_num}.png")

    # 12. 点击【同意检测】按钮
    print("\n[Step 12] 点击【同意检测】按钮...")
    if d(text="同意检测").exists(timeout=10):
        d(text=TEXT_AGREE_CHECK).click()
        print(f"    第{cycle_num}次 - 已点击【同意检测】")
    else:
        d.screenshot(f"scene_error_step12_{cycle_num}.png")
        raise Exception(f"第{cycle_num}次 - 未找到'同意检测'按钮")
    time.sleep(2)
    maybe_screenshot(d, f"scene_step12_{cycle_num}.png")

    # 13. 等待检测结果
    print("\n[Step 13] 等待检测结果...")
    result = wait_for_detection_result(d, cycle_num, timeout=120)

    if result == "passed":
        print(f"    第{cycle_num}次 - 检测通过，测试成功")
    elif result == "failed":
        print(f"    第{cycle_num}次 - 检测失败，点击【跳过】")
        # 检测失败时点击跳过
        if d(text="跳过").exists(timeout=5):
            d(text=TEXT_SKIP).click()
            print(f"    第{cycle_num}次 - 已点击【跳过】")
        time.sleep(2)

        # 风险提示弹窗点击【确认】
        print(f"    第{cycle_num}次 - 风险提示弹窗，点击【确认】")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        time.sleep(2)

        # 点击【开始录制】按钮
        print(f"    第{cycle_num}次 - 点击【开始录制】按钮")
        if d(text="开始录制").exists(timeout=10):
            d(text=TEXT_START_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【开始录制】")
        else:
            d.screenshot(f"scene_error_step14_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'开始录制'按钮")
        time.sleep(2)
        maybe_screenshot(d, f"scene_step14_{cycle_num}.png")

        # 14. 等待3s倒计时后点击【结束录制】按钮
        print(f"    第{cycle_num}次 - 等待3s倒计时...")
        time.sleep(3)

        print(f"    第{cycle_num}次 - 点击【结束录制】按钮")
        if d(text="结束录制").exists(timeout=10):
            d(text=TEXT_END_RECORD).click()
            print(f"    第{cycle_num}次 - 已点击【结束录制】")
        else:
            d.screenshot(f"scene_error_step15_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'结束录制'按钮")
        time.sleep(2)
        maybe_screenshot(d, f"scene_step15_{cycle_num}.png")

        # 15. 点击右上角【结束】按钮
        print(f"    第{cycle_num}次 - 点击右上角【结束】按钮")
        found = False
        if d(description="结束").exists:
            d(description=TEXT_END).click()
            found = True
        elif d(text="结束").exists:
            d(text=TEXT_END).click()
            found = True
        elif d.xpath('//*[@text="结束"]').exists:
            d.xpath('//*[@text="结束"]').click()
            found = True

        if not found:
            d.screenshot(f"scene_error_step16_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'结束'按钮")
        print(f"    第{cycle_num}次 - 已点击【结束】")
        time.sleep(2)
        maybe_screenshot(d, f"scene_step16_{cycle_num}.png")

        # 16. 弹窗点击【确认】按钮
        print(f"    第{cycle_num}次 - 弹窗点击【确认】按钮")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        else:
            d.screenshot(f"scene_error_step17_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
        time.sleep(2)
        maybe_screenshot(d, f"scene_step17_{cycle_num}.png")

        # 17. 点击【返回】按钮
        print(f"    第{cycle_num}次 - 点击【返回】按钮")
        if d(text="返回").exists(timeout=10):
            d(text=TEXT_RETURN).click()
            print(f"    第{cycle_num}次 - 已点击【返回】")
        else:
            d.screenshot(f"scene_error_step18_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'返回'按钮")
        time.sleep(2)
        maybe_screenshot(d, f"scene_step18_{cycle_num}.png")

        # 18. 点击【我的】菜单
        print(f"    第{cycle_num}次 - 点击【我的】菜单")
        found = False
        if d(text="我的").exists:
            d(text=TEXT_MY).click()
            found = True
        elif d(description="我的").exists:
            d(description=TEXT_MY).click()
            found = True
        elif d.xpath('//*[@text="我的"]').exists:
            d.xpath('//*[@text="我的"]').click()  # noqa
            found = True

        if not found:
            d.screenshot(f"scene_error_step19_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'我的'按钮")
        print(f"    第{cycle_num}次 - 已点击【我的】")
        time.sleep(2)
        maybe_screenshot(d, f"scene_step19_{cycle_num}.png")

        # 19. 点击【退出登录】按钮
        print(f"    第{cycle_num}次 - 点击【退出登录】按钮")
        if d(text="退出登录").exists(timeout=10):
            d(text=TEXT_LOGOUT).click()
            print(f"    第{cycle_num}次 - 已点击【退出登录】")
        else:
            d.screenshot(f"scene_error_step20_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'退出登录'按钮")
        time.sleep(1)

        # 20. 弹窗点击【确认】按钮
        print(f"    第{cycle_num}次 - 弹窗点击【确认】按钮")
        if d(text="确认").exists(timeout=5):
            d(text=TEXT_CONFIRM).click()
            print(f"    第{cycle_num}次 - 已点击【确认】")
        else:
            d.screenshot(f"scene_error_step21_{cycle_num}.png")
            raise Exception(f"第{cycle_num}次 - 未找到'确认'按钮")
        time.sleep(2)
        maybe_screenshot(d, f"scene_step21_{cycle_num}.png")

        # 21. 点击Home键回到桌面
        print(f"    第{cycle_num}次 - 点击Home键返回桌面...")
        d.press("home")
        print(f"    第{cycle_num}次 - 已返回桌面")
        time.sleep(1)
    else:
        print(f"    第{cycle_num}次 - 检测超时")

    print(f"\n第 {cycle_num} 次客户经理现场双录测试完成！")
    return True


def main():
    # 获取测试类型和循环次数
    test_type = "customer"  # 默认客户登录
    record_type = "ai"  # 默认AI双录
    loop_count = 1

    if len(sys.argv) > 1:
        if sys.argv[1] == "manager":
            test_type = "manager"
        elif sys.argv[1] == "record":
            test_type = "record"
        elif sys.argv[1] == "customer_record":
            test_type = "customer_record"
        elif sys.argv[1] == "customer_self":
            test_type = "customer_self"
        elif sys.argv[1] == "scene":
            test_type = "scene"
            # 检查第二个参数是否为 ai 或 manual
            if len(sys.argv) > 2:
                if sys.argv[2] == "ai":
                    record_type = "ai"
                elif sys.argv[2] == "manual":
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
        elif sys.argv[1] == "scene_manual":
            test_type = "scene"
            record_type = "manual"
        else:
            test_type = "customer"

        # 处理 scene 命令后直接跟循环次数的情况
        if test_type == "scene" and len(sys.argv) == 3:
            try:
                loop_count = int(sys.argv[2])
            except ValueError:
                pass

        # 处理 record/manager/customer/customer_record/customer_self 命令后直接跟循环次数的情况
        if test_type in ("record", "manager", "customer", "customer_record", "customer_self") and len(sys.argv) >= 3:
            try:
                loop_count = int(sys.argv[2])
            except ValueError:
                pass

    device_id = DEVICE_ID
    d = u2.connect(DEVICE_ID)

    print("=" * 50)
    print("开始 App 双录终端自动化测试")
    if test_type == "manager":
        print("测试类型: 客户经理登录")
    elif test_type == "record":
        print("测试类型: 客户经理纯录制")
    elif test_type == "customer_record":
        print("测试类型: 客户纯录制")
    elif test_type == "customer_self":
        print("测试类型: 客户自助双录")
    elif test_type == "scene":
        if record_type == "ai":
            print("测试类型: 客户经理现场双录(AI)")
        else:
            print("测试类型: 客户经理现场双录(人工)")
    else:
        print("测试类型: 客户登录")
    print(f"循环次数: {loop_count} 次")
    print("=" * 50)

    success_count = 0
    fail_count = 0

    for i in range(1, loop_count + 1):
        try:
            # 根据测试类型选择订单号
            if test_type == "customer_self":
                order_id = ORDER_ID_SELF_SERVICE
            elif test_type == "customer_record":
                order_id = ORDER_ID_CUSTOMER_PURE_RECORD
            elif test_type == "scene":
                order_id = ORDER_ID_SCENE
            else:
                order_id = ORDER_ID_PURE_RECORD

            # 每次循环前检查并重置订单状态
            if not check_and_reset_order_state(order_id):
                print(f"[第 {i} 次] 订单状态检查失败，跳过本次测试")
                fail_count += 1
                continue

            if test_type == "manager":
                run_manager_test_cycle(d, device_id, i)
            elif test_type == "record":
                run_manager_record_cycle(d, device_id, i)
            elif test_type == "customer_record":
                run_customer_record_cycle(d, device_id, i)
            elif test_type == "customer_self":
                run_customer_self_record_cycle(d, device_id, i)
            elif test_type == "scene":
                run_manager_scene_record_cycle(d, device_id, i, record_type=record_type)
            else:
                run_test_cycle(d, device_id, i)
            success_count += 1
        except Exception as e:
            fail_count += 1
            print(f"\n[第 {i} 次测试失败] {str(e)}")
            d.screenshot(f"error_cycle_{i}.png")
            print("    继续执行下一次测试...")

    # 打印汇总结果
    print("\n" + "=" * 50)
    print("测试汇总")
    print("=" * 50)
    print(f"总循环次数: {loop_count}")
    print(f"成功次数: {success_count}")
    print(f"失败次数: {fail_count}")
    print(f"成功率: {success_count/loop_count*100:.1f}%")
    print("=" * 50)

    if fail_count > 0:
        exit(1)


if __name__ == "__main__":
    main()
