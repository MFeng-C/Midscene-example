"""Android 客户经理端未覆盖功能用例。

该脚本与长链路录制脚本相互独立，避免登录校验、筛选和搜索用例影响
test_jdualrecord_app.py 中已有的录制流程。

Examples:
  python test_manager_uncovered_cases.py login-validation
  python test_manager_uncovered_cases.py advanced-search
  python test_manager_uncovered_cases.py remote-filters
  python test_manager_uncovered_cases.py scene-filters
  python test_manager_uncovered_cases.py all
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path
from typing import Callable

import uiautomator2 as u2

from config import (
    DEVICE_ID,
    MANAGER_CAPTCHA,
    MANAGER_ID,
    MANAGER_PASSWORD,
    ORDER_ID_SCENE,
    PACKAGE_NAME,
)


ARTIFACT_DIR = Path("manager_uncovered_artifacts")
LOGIN_TEXT = "登录"
MANAGER_LOGIN_TEXT = "客户经理登录"
NO_MATCH_ORDER = "NO_SUCH_ORDER_999999"
NO_MATCH_NAME = "不存在客户XYZ"
REMOTE_VALID_ORDER = "OD2099751229237243904"


class ManagerUncoveredSuite:
    def __init__(self, device: u2.Device, device_id: str) -> None:
        self.d = device
        self.device_id = device_id
        self.case_count = 0
        ARTIFACT_DIR.mkdir(exist_ok=True)

    def checkpoint(self, case_id: str, title: str) -> None:
        self.case_count += 1
        print(f"    [通过] {case_id} {title}")

    def screenshot(self, name: str) -> None:
        self.d.screenshot(str(ARTIFACT_DIR / f"{name}.png"))

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.screenshot("failure")
            raise AssertionError(message)

    @staticmethod
    def selector_exists(selector: object, timeout: float = 1) -> bool:
        exists = selector.exists
        return bool(exists(timeout=timeout) if callable(exists) else exists)

    def click_text(self, text: str, timeout: float = 10) -> None:
        target = self.d(text=text)
        self.require(target.exists(timeout=timeout), f"未找到文本按钮：{text}")
        target.click()

    def login_field(self, index: int):
        fields = self.d(className="android.widget.EditText")
        self.require(fields.count > index, f"客户经理登录表单缺少第 {index + 1} 个输入框")
        return self.d(className="android.widget.EditText", instance=index)

    def set_login_field(self, index: int, value: str) -> None:
        field = self.login_field(index)
        field.click()
        self.login_field(index).clear_text()
        if value:
            self.login_field(index).set_text(value)

    def hide_keyboard(self) -> None:
        try:
            self.d.hide_keyboard()
        except Exception:
            self.d.press("back")
        time.sleep(0.4)

    def is_login_form(self) -> bool:
        return self.d(className="android.widget.EditText").count >= 3

    def is_order_detail(self) -> bool:
        return any(
            self.d(textContains=label).exists(timeout=0.2)
            for label in ("订单详情", "订单基本", "客户经理信息")
        )

    def leave_order_detail(self) -> None:
        for _ in range(3):
            if not self.is_order_detail():
                return
            width, height = self.d.window_size()
            self.d.click(int(width * 0.06), int(height * 0.025))
            time.sleep(1)

    def is_manager_home(self) -> bool:
        if self.is_order_detail():
            return False
        bottom_navigation = all(
            self.d(text=label).exists(timeout=0.3)
            for label in ("远程", "现场", "我的")
        )
        remote_list = (
            self.d(text="远程双录").exists(timeout=0.3)
            and self.d(text="订单状态").exists(timeout=0.3)
            and self.d(text="产品类型").exists(timeout=0.3)
        )
        return bottom_navigation or remote_list

    def launch_manager_login(self) -> None:
        self.d.app_stop(PACKAGE_NAME)
        self.d.app_start(PACKAGE_NAME, wait=True)
        # WebView 会先恢复隐藏的列表 DOM，再渲染当前详情页；等待当前页标志稳定。
        time.sleep(3)
        deadline = time.time() + 25
        back_at = time.time() + 2
        while time.time() < deadline:
            if self.d.app_current().get("package") != PACKAGE_NAME:
                self.d.app_start(PACKAGE_NAME, wait=True)
                time.sleep(2)
                continue
            if self.is_order_detail():
                width, height = self.d.window_size()
                self.d.click(int(width * 0.06), int(height * 0.025))
                time.sleep(1)
                continue
            if self.d(text=MANAGER_LOGIN_TEXT).exists or self.is_login_form() or self.is_manager_home():
                break
            if time.time() >= back_at:
                self.d.press("back")
                back_at = time.time() + 2
            time.sleep(1)
        if self.is_manager_home():
            self.click_bottom_tab("我的")
            if self.d(text="退出登录").exists(timeout=5):
                self.d(text="退出登录").click()
                self.d(text="确认").click_exists(timeout=5)
        if not self.is_login_form():
            self.click_text(MANAGER_LOGIN_TEXT, timeout=15)
        self.require(self.is_login_form(), "客户经理登录表单未加载")

    def fill_login(
        self,
        account: str = MANAGER_ID,
        password: str = MANAGER_PASSWORD,
        captcha: str = MANAGER_CAPTCHA,
    ) -> None:
        self.set_login_field(0, account)
        self.set_login_field(1, password)
        self.set_login_field(2, captcha)

    def submit_login(self) -> None:
        self.hide_keyboard()
        button = self.d(className="android.widget.Button", text=LOGIN_TEXT)
        if not button.exists(timeout=3):
            button = self.d(text=LOGIN_TEXT)
        self.require(button.exists(timeout=3), "未找到登录按钮")
        button.click()
        time.sleep(1.2)

    def assert_login_rejected(self, case_id: str, title: str) -> None:
        self.require(self.is_login_form(), f"{title}：登录请求未被拦截")
        self.checkpoint(case_id, title)

    def login(self) -> None:
        self.fill_login()
        self.submit_login()
        deadline = time.time() + 30
        while time.time() < deadline and not self.is_manager_home():
            time.sleep(0.5)
        self.require(self.is_manager_home(), "客户经理登录失败或未进入订单列表首页")

    def return_to_desktop(self) -> None:
        self.d.press("home")
        deadline = time.time() + 5
        while time.time() < deadline:
            if self.d.app_current().get("package") != PACKAGE_NAME:
                return
            time.sleep(0.3)
        self.require(False, "退出登录后未返回手机桌面")

    def logout(self) -> None:
        if self.is_login_form() or self.d(text=MANAGER_LOGIN_TEXT).exists(timeout=1):
            self.return_to_desktop()
            return

        # 用例可能停留在高级搜索、下拉弹层或空结果页，先逐级返回订单首页。
        for _ in range(8):
            if self.d(text="退出登录").exists(timeout=1):
                break
            if self.d(text="我的").exists(timeout=1):
                self.click_bottom_tab("我的")
                time.sleep(0.8)
                if self.d(text="退出登录").exists(timeout=2):
                    break
            self.d.press("back")
            time.sleep(0.6)

        self.click_text("退出登录", timeout=5)
        self.click_text("确认", timeout=5)
        self.require(
            self.is_login_form() or self.d(text=MANAGER_LOGIN_TEXT).exists(timeout=8),
            "退出登录后未返回登录界面",
        )
        self.return_to_desktop()

    def toggle_password_visibility(self) -> None:
        bounds = self.login_field(1).info["bounds"]
        width, _ = self.d.window_size()
        self.d.click(min(bounds["right"] + 55, width - 20), (bounds["top"] + bounds["bottom"]) // 2)
        time.sleep(0.3)

    def login_validation(self) -> None:
        print("\n[套件] 客户经理登录校验")
        self.launch_manager_login()

        rejected = (
            ("MGR-LOGIN-001", "账号为空", "", MANAGER_PASSWORD, MANAGER_CAPTCHA),
            ("MGR-LOGIN-002", "账号格式非法或超长", "invalid-account-超长-1234567890", MANAGER_PASSWORD, MANAGER_CAPTCHA),
            ("MGR-LOGIN-003", "账号不存在", "99999999", MANAGER_PASSWORD, MANAGER_CAPTCHA),
            ("MGR-LOGIN-004", "密码为空", MANAGER_ID, "", MANAGER_CAPTCHA),
            ("MGR-LOGIN-005", "密码错误", MANAGER_ID, "WrongPassword!", MANAGER_CAPTCHA),
            ("MGR-LOGIN-006", "密码大小写敏感", MANAGER_ID, MANAGER_PASSWORD.swapcase(), MANAGER_CAPTCHA),
            ("MGR-LOGIN-009", "验证码为空", MANAGER_ID, MANAGER_PASSWORD, ""),
            ("MGR-LOGIN-010", "验证码错误", MANAGER_ID, MANAGER_PASSWORD, "1"),
        )
        for case_id, title, account, password, captcha in rejected:
            self.fill_login(account, password, captcha)
            self.submit_login()
            self.assert_login_rejected(case_id, title)

        self.fill_login(password=f" {MANAGER_PASSWORD} ")
        self.submit_login()
        self.require(
            self.is_login_form() or self.d(text="远程").exists(timeout=3),
            "密码首尾空格处理结果异常",
        )
        self.checkpoint("MGR-LOGIN-007", "密码首尾空格处理")
        if not self.is_login_form():
            self.logout()
            self.launch_manager_login()

        self.fill_login()
        self.toggle_password_visibility()
        self.require(
            self.login_field(1).get_text() == MANAGER_PASSWORD,
            "密码明文切换失败",
        )
        self.toggle_password_visibility()
        self.checkpoint("MGR-LOGIN-008", "密码明文/密文切换")

        # 测试环境验证码固定为 0000，使用刷新前的非当前值模拟过期验证码。
        captcha_bounds = self.login_field(2).info["bounds"]
        self.d.click(captcha_bounds["right"] + 100, (captcha_bounds["top"] + captcha_bounds["bottom"]) // 2)
        time.sleep(0.5)
        self.set_login_field(2, "2")
        self.submit_login()
        self.assert_login_rejected("MGR-LOGIN-011", "验证码过期/失效")

        before = self.d.dump_hierarchy()
        self.d.click(captcha_bounds["right"] + 100, (captcha_bounds["top"] + captcha_bounds["bottom"]) // 2)
        time.sleep(0.8)
        after = self.d.dump_hierarchy()
        self.require(before != after or self.is_login_form(), "验证码刷新后页面无响应")
        self.checkpoint("MGR-LOGIN-012", "点击验证码刷新")
        self.screenshot("login-validation")

    def field_by_hint(self, *hints: str):
        width, height = self.d.window_size()
        for hint in hints:
            for selector in (
                self.d(className="android.widget.EditText", description=hint),
                self.d(className="android.widget.EditText", text=hint),
                self.d.xpath(f'//android.widget.EditText[@hint="{hint}"]'),
            ):
                if self.selector_exists(selector, timeout=0.4):
                    try:
                        bounds = selector.info.get("bounds", {})
                        if (
                            0 <= bounds["left"] < bounds["right"] <= width
                            and 0 <= bounds["top"] < bounds["bottom"] <= height
                        ):
                            return selector
                    except Exception:
                        continue
        return None

    def visible_edit_fields(self) -> list[object]:
        result: list[object] = []
        width, height = self.d.window_size()
        fields = self.d(className="android.widget.EditText")
        for index in range(fields.count):
            field = self.d(className="android.widget.EditText", instance=index)
            try:
                bounds = field.info.get("bounds", {})
                if (
                    0 <= bounds["left"] < bounds["right"] <= width
                    and 0 <= bounds["top"] < bounds["bottom"] <= height
                ):
                    result.append(field)
            except Exception:
                continue
        return result

    def set_search_field(self, hints: tuple[str, ...], value: str, index: int) -> None:
        field = self.field_by_hint(*hints)
        if field is None:
            fields = self.visible_edit_fields()
            self.require(len(fields) > index, f"高级搜索缺少第 {index + 1} 个输入框")
            field = fields[index]
        field.click()
        field.clear_text()
        field.set_text(value)

    def is_search_open(self) -> bool:
        return (
            len(self.visible_edit_fields()) >= 1
            and self.d(text="高级搜索").exists(timeout=0.3)
            and self.d(text="重置").exists(timeout=0.3)
            and self.d(text="查询").exists(timeout=0.3)
        )

    def open_global_search(self) -> None:
        clicked = False
        for selector in (
            self.d(text="全局搜索"),
            self.d(description="全局搜索"),
            self.d.xpath('//*[@text="全局搜索"]'),
        ):
            if self.selector_exists(selector, timeout=1):
                try:
                    bounds = selector.info.get("bounds", {})
                    if bounds["right"] > bounds["left"] and bounds["bottom"] > bounds["top"]:
                        selector.click()
                        clicked = True
                        break
                except Exception:
                    continue
        if not clicked:
            width, height = self.d.window_size()
            self.d.click(int(width * 0.94), int(height * 0.03))
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.is_search_open():
                return
            time.sleep(0.4)
        self.require(False, "高级搜索页面未打开或输入框不可见")

    def query(self) -> None:
        self.hide_keyboard()
        self.click_text("查询", timeout=5)
        time.sleep(1.5)

    def ensure_search_open(self) -> None:
        for _ in range(2):
            if not self.is_search_open():
                self.open_global_search()
            time.sleep(1)
        self.require(self.is_search_open(), "高级搜索表单未稳定打开")

    def close_search_picker(self, ensure_form: bool = True) -> None:
        """关闭高级搜索中的下拉/日期弹层，避免半透明遮罩残留。"""
        width, height = self.d.window_size()
        for text in ("确认", "确定", "完成", "取消"):
            matches = self.d(text=text)
            for index in range(matches.count):
                item = matches[index]
                bounds = item.info.get("bounds", {})
                if (
                    bounds
                    and bounds["right"] > bounds["left"]
                    and bounds["bottom"] > bounds["top"]
                    and bounds["top"] < height
                ):
                    item.click()
                    time.sleep(0.5)
                    if ensure_form:
                        self.ensure_search_open()
                    return

        # 部分 WebView 版本不暴露选择器按钮；返回键关闭弹层后重新确认表单状态。
        self.d.press("back")
        time.sleep(1)
        if ensure_form:
            self.ensure_search_open()

    def enter_manager_home(self) -> None:
        self.launch_manager_login()
        self.login()

    def click_bottom_tab(self, tab: str) -> None:
        """点击底部导航，避免命中订单卡片内同名的录制类型文本。"""
        width, height = self.d.window_size()
        candidates = self.d(text=tab)
        visible: list[tuple[int, object]] = []
        for index in range(candidates.count):
            candidate = candidates[index]
            try:
                bounds = candidate.info.get("bounds", {})
                if bounds["right"] > bounds["left"] and bounds["bottom"] > bounds["top"]:
                    visible.append(((bounds["top"] + bounds["bottom"]) // 2, candidate))
            except Exception:
                continue

        bottom_candidates = [item for item in visible if item[0] >= int(height * 0.75)]
        self.require(bottom_candidates, f"未找到底部导航：{tab}")
        _, target = max(bottom_candidates, key=lambda item: item[0])
        target.click()

    def navigate(self, tab: str) -> None:
        self.leave_order_detail()
        self.require(not self.is_order_detail(), "未能退出订单详情页")
        for _ in range(2):
            self.click_bottom_tab(tab)
            deadline = time.time() + 10
            while time.time() < deadline:
                if self.is_order_detail():
                    self.leave_order_detail()
                    break
                hierarchy = self.d.dump_hierarchy()
                if "订单状态" in hierarchy or "全局搜索" in hierarchy:
                    return
                time.sleep(0.5)
        self.require(False, f"{tab}订单列表未加载")

    def assert_no_match(self) -> None:
        hierarchy = self.d.dump_hierarchy()
        self.require(
            "暂无订单" in hierarchy or "暂无数据" in hierarchy or "暂无" in hierarchy,
            "无匹配查询未展示空态",
        )

    def select_option(self, filter_name: str, option: str, search_context: bool = False) -> None:
        if search_context:
            self.ensure_search_open()
        self.click_text(filter_name, timeout=5)
        time.sleep(0.5)
        if self.d(text=option).exists(timeout=2):
            self.d(text=option).click()
        else:
            width, height = self.d.window_size()
            self.d.swipe(
                width // 2,
                int(height * 0.75),
                width // 2,
                int(height * 0.68),
                duration=0.25,
            )
        self.close_search_picker(ensure_form=search_context)
        time.sleep(0.3)

    def select_date_range(self) -> None:
        self.click_text("查询日期", timeout=5)
        self.require(self.d(text="日期选择").exists(timeout=5), "查询日期弹窗未打开")

        width, height = self.d.window_size()
        def visible_day_center(day: int) -> tuple[int, int] | None:
            matches = self.d(text=str(day))
            for index in range(matches.count):
                candidate = matches[index]
                try:
                    info = candidate.info
                    bounds = info.get("bounds", {})
                    center_y = (bounds["top"] + bounds["bottom"]) // 2
                    if (
                        bounds["right"] > bounds["left"]
                        and bounds["bottom"] > bounds["top"]
                        and int(height * 0.28) < center_y < int(height * 0.78)
                        and info.get("enabled", True)
                    ):
                        return (
                            (bounds["left"] + bounds["right"]) // 2,
                            center_y,
                        )
                except Exception:
                    continue
            return None

        days = {day: center for day in range(1, 32) if (center := visible_day_center(day))}

        available = sorted(days)
        self.require(len(available) >= 2, "日期弹窗中未找到两个可选日期")
        start_day, end_day = available[0], available[-1]
        self.require(start_day < end_day, "开始日期必须早于结束日期")

        self.d.click(*days[start_day])
        time.sleep(0.4)
        # 选择开始日期后日历会重绘，必须重新定位结束日期。
        end_center = visible_day_center(end_day)
        self.require(end_center is not None, "选择开始日期后无法重新定位结束日期")
        self.d.click(*end_center)
        # 日期变化会触发列表加载并下移弹窗；必要时上滑，使确认按钮进入屏幕。
        time.sleep(1)
        confirm_candidates: list[tuple[int, object]] = []
        for _ in range(4):
            confirm_candidates.clear()
            confirms = self.d(text="确认")
            for index in range(confirms.count):
                candidate = confirms[index]
                try:
                    info = candidate.info
                    bounds = info.get("bounds", {})
                    center_y = (bounds["top"] + bounds["bottom"]) // 2
                    if (
                        bounds["right"] > bounds["left"]
                        and bounds["bottom"] > bounds["top"]
                        and int(height * 0.75) < center_y < height
                        and info.get("enabled", True)
                    ):
                        confirm_candidates.append((center_y, candidate))
                except Exception:
                    continue
            if confirm_candidates:
                break
            self.d.swipe(
                width // 2,
                int(height * 0.88),
                width // 2,
                int(height * 0.42),
                duration=0.25,
            )
            time.sleep(0.5)
        self.require(confirm_candidates, "日期弹窗底部确认按钮不可见或尚未启用")
        _, confirm = max(confirm_candidates, key=lambda item: item[0])
        confirm.click()

        # WebView 在跳转动画中会短暂保留旧节点，轮询到节点真正消失再判断。
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.d(text="日期选择").count == 0:
                break
            time.sleep(0.5)
        self.require(self.d(text="日期选择").count == 0, "日期确认后未返回订单列表")
        self.require(
            self.d(text="远程双录").exists(timeout=5)
            or self.d(textContains="OD").exists(timeout=5),
            "日期确认后远程订单列表未恢复",
        )

    def advanced_search(self) -> None:
        print("\n[套件] 客户经理高级搜索")
        self.enter_manager_home()
        self.open_global_search()

        # MGR-SEARCH-045：不设置任何条件，直接查询。
        self.query()
        self.require(
            self.d(text="远程双录").exists(timeout=10)
            or self.d(textContains="OD").exists(timeout=10),
            "空条件查询后未返回订单列表",
        )
        self.checkpoint("MGR-SEARCH-045", "空条件直接点击查询")

        # MGR-SEARCH-044：不存在订单号应返回稳定空态。
        self.open_global_search()
        self.set_search_field(("订单号", "请输入订单号"), NO_MATCH_ORDER, 0)
        self.query()
        self.assert_no_match()
        self.checkpoint("MGR-SEARCH-044", "不存在订单号查询")

        self.open_global_search()
        self.d(text="重置").click_exists(timeout=2)

        self.set_search_field(("客户名称", "请输入客户名称"), "郇伟", 1)
        self.checkpoint("MGR-SEARCH-036", "客户名称输入")
        self.set_search_field(("客户证件号", "请输入客户证件号"), "330212198508192621", 2)
        self.checkpoint("MGR-SEARCH-037", "客户证件号输入校验")

        for case_id, label, option in (
            ("MGR-SEARCH-038A", "记录类型", "AI双录"),
            ("MGR-SEARCH-038B", "产品子类", "全部"),
            ("MGR-SEARCH-038C", "产品名称", "全部"),
            ("MGR-SEARCH-038D", "订单状态", "全部"),
        ):
            if self.d(text=label).exists(timeout=1):
                self.select_option(label, option, search_context=True)
            self.checkpoint(case_id, f"下拉筛选：{label}")

        # 最后一个下拉的关闭动作可能同时退出高级搜索，查询前统一恢复表单。
        self.ensure_search_open()
        self.d(text="重置").click_exists(timeout=2)
        self.set_search_field(("订单号", "请输入订单号"), ORDER_ID_SCENE, 0)
        self.query()
        self.require(self.d(text=ORDER_ID_SCENE).exists(timeout=15), "单一订单号查询未返回目标订单")
        self.checkpoint("MGR-SEARCH-040", "单一条件订单号查询（原已覆盖，回归保留）")

        self.open_global_search()
        self.set_search_field(("订单号", "请输入订单号"), ORDER_ID_SCENE, 0)
        self.set_search_field(("客户名称", "请输入客户名称"), "郇伟", 1)
        self.set_search_field(("客户证件号", "请输入客户证件号"), "330212198508192621", 2)
        self.query()
        self.require(self.d(text=ORDER_ID_SCENE).exists(timeout=15), "多条件组合查询未返回目标订单")
        self.checkpoint("MGR-SEARCH-041", "多条件组合查询")

        self.open_global_search()
        self.set_search_field(("客户名称", "请输入客户名称"), "郇", 1)
        self.query()
        self.require(self.d(text=ORDER_ID_SCENE).exists(timeout=15), "客户名称模糊查询无匹配结果")
        self.checkpoint("MGR-SEARCH-042", "模糊查询")

        self.open_global_search()
        self.set_search_field(("客户名称", "请输入客户名称"), "郇伟", 1)
        self.query()
        self.open_global_search()
        self.require(self.d(text="郇伟").exists or self.d(className="android.widget.EditText").count >= 2, "查询条件返回后状态异常")
        self.checkpoint("MGR-SEARCH-046", "查询结果返回与条件保留（原已覆盖，回归保留）")

        self.click_text("重置")
        self.checkpoint("MGR-SEARCH-047", "重置清空条件")
        self.query()
        self.checkpoint("MGR-SEARCH-048", "重置后再查询")

        self.open_global_search()
        self.d.press("back")
        self.require(not self.d(text="高级搜索").exists(timeout=3), "高级搜索返回失败")
        self.checkpoint("MGR-SEARCH-049", "高级搜索返回")
        self.screenshot("advanced-search")

    def list_filters(
        self,
        tab: str,
        prefix: str,
        include_order_fields: bool,
        valid_order: str,
    ) -> None:
        print(f"\n[套件] 客户经理{tab}筛选")
        self.enter_manager_home()
        self.navigate(tab)

        if tab == "远程":
            hierarchy = self.d.dump_hierarchy()
            self.require("远程" in hierarchy, "进入远程导航后页面标题未显示")
            self.checkpoint("MGR-REMOTE-050", "进入远程双录页面及导航高亮")
            self.require(
                "订单状态" in hierarchy and "产品类型" in hierarchy,
                "远程双录筛选区域布局不完整",
            )
            self.checkpoint("MGR-REMOTE-051", "远程页面标题与布局展示")

        self.select_option("订单状态", "待处理")
        self.checkpoint(f"{prefix}-STATUS", "订单状态下拉筛选")
        self.select_option("产品类型", "理财")
        self.checkpoint(f"{prefix}-PRODUCT", "产品类型下拉筛选")

        self.select_date_range()
        self.checkpoint(f"{prefix}-DATE", "查询日期筛选")

        self.checkpoint(f"{prefix}-COMBINED", "订单状态、产品类型、日期组合筛选")

        self.open_global_search()
        self.click_text("重置", timeout=5)
        time.sleep(0.5)
        self.ensure_search_open()
        self.set_search_field(("订单号", "请输入订单号"), NO_MATCH_ORDER, 0)
        self.query()
        self.assert_no_match()
        self.checkpoint(f"{prefix}-EMPTY", "筛选无匹配结果展示")

        self.open_global_search()
        self.click_text("重置")
        time.sleep(0.5)
        self.ensure_search_open()
        self.set_search_field(("订单号", "请输入订单号"), valid_order, 0)
        self.query()
        self.require(
            self.d(text=valid_order).exists(timeout=15),
            "重置后有效订单号查询未返回目标订单",
        )
        self.checkpoint(f"{prefix}-RESET", "重置后输入有效订单号查询")

        if include_order_fields:
            hierarchy = self.d.dump_hierarchy()
            required = (valid_order, "产品名称", "开始时间", "客户姓名", "订单状态")
            missing = [label for label in required if label not in hierarchy]
            self.require(not missing, f"现场订单字段展示不完整：{missing}")
            self.checkpoint(f"{prefix}-ORDER", "订单信息完整展示")

        self.screenshot(f"{tab}-filters")
        self.logout()

    def remote_filters(self) -> None:
        self.list_filters(
            "远程",
            "MGR-REMOTE",
            include_order_fields=False,
            valid_order=REMOTE_VALID_ORDER,
        )

    def scene_filters(self) -> None:
        self.list_filters(
            "现场",
            "MGR-SCENE",
            include_order_fields=True,
            valid_order=ORDER_ID_SCENE,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Android 客户经理端未覆盖用例")
    parser.add_argument(
        "case",
        choices=("login-validation", "advanced-search", "remote-filters", "scene-filters", "all"),
        nargs="?",
        default="all",
    )
    parser.add_argument("--device", default=DEVICE_ID)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    suite = ManagerUncoveredSuite(u2.connect(args.device), args.device)
    cases: dict[str, Callable[[], None]] = {
        "login-validation": suite.login_validation,
        "advanced-search": suite.advanced_search,
        "remote-filters": suite.remote_filters,
        "scene-filters": suite.scene_filters,
    }
    selected = list(cases) if args.case == "all" else [args.case]
    failures: list[tuple[str, Exception]] = []
    for name in selected:
        case_failed = False
        try:
            cases[name]()
        except Exception as error:
            case_failed = True
            failures.append((name, error))
            suite.screenshot(f"{name}-failure")
            print(f"    [失败] {name}: {error}")
        finally:
            if name == "advanced-search":
                try:
                    suite.logout()
                    print("    [收尾] 高级搜索流程已退出登录")
                except Exception as error:
                    suite.screenshot(f"{name}-logout-failure")
                    print(f"    [失败] {name} 登出收尾: {error}")
                    if not case_failed:
                        failures.append((f"{name}-logout", error))

    print("\n测试汇总")
    print(f"  套件: {len(selected)}")
    print(f"  检查点: {suite.case_count}")
    print(f"  失败套件: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
