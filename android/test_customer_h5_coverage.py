"""Android customer regressions mirrored from the H5 single-end suite.

This module is intentionally independent from test_jdualrecord_app.py so the
existing long-running recording flows and command-line interface stay intact.

Examples:
  python test_customer_h5_coverage.py login-validation
  python test_customer_h5_coverage.py remote-filter-search
  python test_customer_h5_coverage.py all
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Callable

import uiautomator2 as u2

from config import (
    APP_NAME,
    CUSTOMER_CAPTCHA,
    CUSTOMER_ID,
    CUSTOMER_PASSWORD,
    DEVICE_ID,
    INPUT_CAPTCHA,
    INPUT_ID_CARD,
    INPUT_PASSWORD,
    ORDER_ID_CUSTOMER_PURE_RECORD,
    ORDER_ID_SELF_SERVICE,
    PACKAGE_NAME,
)


ARTIFACT_DIR = Path("customer_h5_coverage_artifacts")
LOGIN_BUTTON = "登录"
REMOTE_VALID_ORDER = "OD2099751229237243904"
NO_MATCH_ORDER = "NO_SUCH_ORDER_999999"


class CustomerRegression:
    def __init__(self, device: u2.Device, device_id: str) -> None:
        self.d = device
        self.device_id = device_id
        ARTIFACT_DIR.mkdir(exist_ok=True)

    def screenshot(self, name: str) -> None:
        path = ARTIFACT_DIR / f"{name}.png"
        self.d.screenshot(str(path))
        print(f"    [截图] {path}")

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.screenshot("failure")
            raise AssertionError(message)

    def element_info(self, selector_factory: Callable[[], object], attempts: int = 3) -> dict:
        """Read volatile WebView accessibility properties with a fresh selector."""
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                return selector_factory().info
            except Exception as error:
                last_error = error
                self.d.dump_hierarchy()
                time.sleep(0.3)
        raise AssertionError(f"读取控件属性失败：{last_error}")

    def element_text(self, selector_factory: Callable[[], object], attempts: int = 3) -> str:
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                return selector_factory().get_text() or ""
            except Exception as error:
                last_error = error
                self.d.dump_hierarchy()
                time.sleep(0.3)
        raise AssertionError(f"读取控件文本失败：{last_error}")

    def wait_text(self, text: str, timeout: float = 15) -> None:
        self.require(self.d(text=text).exists(timeout=timeout), f"未找到文本：{text}")

    @staticmethod
    def selector_exists(selector: object, timeout: float = 1) -> bool:
        exists = selector.exists
        return bool(exists(timeout=timeout) if callable(exists) else exists)

    def click_text(self, text: str, timeout: float = 10) -> None:
        self.require(self.d(text=text).exists(timeout=timeout), f"未找到可点击文本：{text}")
        self.d(text=text).click()

    def set_field(self, resource_id: str, value: str) -> None:
        last_error: Exception | None = None
        for _ in range(3):
            field = self.d(resourceId=resource_id)
            self.require(field.exists(timeout=5), f"未找到输入框：{resource_id}")
            try:
                field.click()
                self.d(resourceId=resource_id).clear_text()
                if value:
                    self.d(resourceId=resource_id).set_text(value)
                return
            except Exception as error:
                last_error = error
                self.d.dump_hierarchy()
                time.sleep(0.4)
        raise AssertionError(f"输入框写入失败 {resource_id}：{last_error}")

    def launch_login(self) -> None:
        hierarchy = ""
        for _ in range(3):
            self.d.app_stop(PACKAGE_NAME)
            self.d.app_start(PACKAGE_NAME, wait=True)
            deadline = time.time() + 20
            back_at = time.time() + 3
            while time.time() < deadline:
                hierarchy = self.d.dump_hierarchy()
                on_login = "客户登录" in hierarchy and "van-field-4-input" in hierarchy
                on_customer_home = all(
                    label in hierarchy for label in ("远程", "自助", "纯录制", "我的")
                )
                if on_login or on_customer_home:
                    break
                if time.time() >= back_at:
                    self.d.press("back")
                    back_at = time.time() + 2
                time.sleep(1)
            if on_login or on_customer_home:
                break
        self.require(on_login or on_customer_home, "App 页面启动失败")

        if on_customer_home:
            if self.d(text="我的").exists(timeout=15):
                self.d(text="我的").click()
                self.click_text("退出登录", timeout=10)
                self.click_text("确认", timeout=5)
        self.wait_text("客户登录", timeout=20)
        self.click_text("客户登录")
        self.require(
            self.d(resourceId=INPUT_ID_CARD).exists(timeout=10),
            "客户登录表单未加载",
        )

    def hide_keyboard(self) -> None:
        try:
            self.d.press("back")
        except Exception:
            pass
        time.sleep(0.4)

    def submit_login(self) -> None:
        self.hide_keyboard()
        button = self.d(className="android.widget.Button", text=LOGIN_BUTTON)
        self.require(button.exists(timeout=5), "未找到登录按钮")
        button.click()
        time.sleep(1.2)

    def assert_still_on_login(self, scenario: str) -> None:
        self.require(
            self.d(resourceId=INPUT_ID_CARD).exists(timeout=4)
            and self.d(className="android.widget.Button", text=LOGIN_BUTTON).exists(timeout=1),
            f"{scenario}：表单校验失败，页面离开了登录页",
        )
        print(f"    [通过] {scenario}时保持在登录页")

    def fill_valid_login(self) -> None:
        self.set_field(INPUT_ID_CARD, CUSTOMER_ID)
        self.set_field(INPUT_PASSWORD, CUSTOMER_PASSWORD)
        self.set_field(INPUT_CAPTCHA, CUSTOMER_CAPTCHA)

    def login(self) -> None:
        self.fill_valid_login()
        self.submit_login()
        self.wait_text("我的", timeout=30)

    def logout(self) -> None:
        self.click_bottom_tab("我的")
        self.click_text("退出登录", timeout=15)
        self.click_text("确认", timeout=5)
        self.wait_text("客户登录", timeout=20)
        self.d.press("home")
        deadline = time.time() + 5
        while time.time() < deadline:
            if self.d.app_current().get("package") != PACKAGE_NAME:
                return
            time.sleep(0.3)
        self.require(False, "退出登录后未返回手机桌面")

    def click_bottom_tab(self, tab: str) -> None:
        _, height = self.d.window_size()
        candidates: list[tuple[int, object]] = []
        matches = self.d(text=tab)
        for index in range(matches.count):
            item = matches[index]
            try:
                bounds = item.info.get("bounds", {})
                center_y = (bounds["top"] + bounds["bottom"]) // 2
                if (
                    bounds["right"] > bounds["left"]
                    and bounds["bottom"] > bounds["top"]
                    and center_y > int(height * 0.75)
                ):
                    candidates.append((center_y, item))
            except Exception:
                continue
        self.require(candidates, f"未找到底部导航：{tab}")
        max(candidates, key=lambda value: value[0])[1].click()
        time.sleep(1)

    def toggle_password_visibility(self) -> None:
        bounds = self.element_info(lambda: self.d(resourceId=INPUT_PASSWORD))["bounds"]
        x = min(bounds["right"] + 55, self.d.window_size()[0] - 20)
        y = (bounds["top"] + bounds["bottom"]) // 2
        self.d.click(x, y)
        time.sleep(0.5)

    def login_validation(self) -> None:
        """Mirror h5-customer-login-ui-validation.yaml on Android."""
        print("\n[用例] 客户登录表单校验")
        self.launch_login()

        self.set_field(INPUT_ID_CARD, "")
        self.set_field(INPUT_PASSWORD, CUSTOMER_PASSWORD)
        self.set_field(INPUT_CAPTCHA, CUSTOMER_CAPTCHA)
        self.require(
            self.element_text(lambda: self.d(resourceId=INPUT_PASSWORD)) != CUSTOMER_PASSWORD,
            "填写密码后输入框未采用密文显示",
        )
        self.submit_login()
        self.assert_still_on_login("证件号为空")

        self.set_field(INPUT_ID_CARD, "!@#")
        self.submit_login()
        self.assert_still_on_login("证件号格式非法")

        self.set_field(INPUT_ID_CARD, CUSTOMER_ID)
        self.set_field(INPUT_PASSWORD, "")
        self.submit_login()
        self.assert_still_on_login("密码为空")

        self.set_field(INPUT_PASSWORD, CUSTOMER_PASSWORD)
        self.set_field(INPUT_CAPTCHA, "")
        self.submit_login()
        self.assert_still_on_login("验证码为空")

        self.set_field(INPUT_CAPTCHA, CUSTOMER_CAPTCHA)
        self.hide_keyboard()
        self.toggle_password_visibility()
        self.require(
            self.element_text(lambda: self.d(resourceId=INPUT_PASSWORD)) == CUSTOMER_PASSWORD,
            "点击显隐图标后未显示密码明文",
        )
        self.screenshot("login-password-visible")
        self.toggle_password_visibility()
        self.require(
            self.element_text(lambda: self.d(resourceId=INPUT_PASSWORD)) != CUSTOMER_PASSWORD,
            "再次点击显隐图标后密码未恢复密文",
        )

        self.submit_login()
        self.wait_text("我的", timeout=30)
        self.screenshot("login-success")
        self.logout()
        print("    [通过] 客户登录表单校验")

    def click_search(self) -> None:
        width, height = self.d.window_size()
        self.d.click(int(width * 0.93), int(height * 0.03))
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.search_is_open():
                return
            time.sleep(0.4)
        self.require(False, "高级搜索页面未打开")

    def search_is_open(self) -> bool:
        width, height = self.d.window_size()
        for text in ("高级搜索", "重置", "查询"):
            visible = False
            matches = self.d(text=text)
            for index in range(matches.count):
                try:
                    bounds = matches[index].info.get("bounds", {})
                    if (
                        0 <= bounds["left"] < bounds["right"] <= width
                        and 0 <= bounds["top"] < bounds["bottom"] <= height
                    ):
                        visible = True
                        break
                except Exception:
                    continue
            if not visible:
                return False
        return True

    def select_date_range(self) -> None:
        self.open_top_filter("查询日期")
        self.wait_text("日期选择", timeout=5)
        width, height = self.d.window_size()

        def day_center(day: int) -> tuple[int, int] | None:
            matches = self.d(text=str(day))
            for index in range(matches.count):
                try:
                    info = matches[index].info
                    bounds = info.get("bounds", {})
                    center_y = (bounds["top"] + bounds["bottom"]) // 2
                    if (
                        bounds["right"] > bounds["left"]
                        and bounds["bottom"] > bounds["top"]
                        and int(height * 0.28) < center_y < int(height * 0.78)
                        and info.get("enabled", True)
                    ):
                        return ((bounds["left"] + bounds["right"]) // 2, center_y)
                except Exception:
                    continue
            return None

        days = {day: center for day in range(1, 32) if (center := day_center(day))}
        available = sorted(days)
        self.require(len(available) >= 2, "日期弹窗中未找到两个可选日期")
        start_day, end_day = available[0], available[-1]
        self.require(start_day < end_day, "开始日期必须早于结束日期")
        self.d.click(*days[start_day])
        time.sleep(0.4)
        end_center = day_center(end_day)
        self.require(end_center is not None, "选择开始日期后无法定位结束日期")
        self.d.click(*end_center)
        time.sleep(1)

        confirm = None
        for _ in range(8):
            matches = self.d(text="确认")
            visible: list[tuple[int, object]] = []
            for index in range(matches.count):
                item = matches[index]
                try:
                    info = item.info
                    bounds = info.get("bounds", {})
                    center_y = (bounds["top"] + bounds["bottom"]) // 2
                    if int(height * 0.75) < center_y < height and info.get("enabled", True):
                        visible.append((center_y, item))
                except Exception:
                    continue
            if visible:
                confirm = max(visible, key=lambda value: value[0])[1]
                break
            self.d.swipe(width // 2, int(height * 0.88), width // 2, int(height * 0.42), 0.25)
            time.sleep(0.5)
        self.require(confirm is not None, "日期确认按钮不可见或尚未启用")
        confirm.click()
        deadline = time.time() + 20
        while time.time() < deadline and self.d(text="日期选择").count:
            time.sleep(0.5)
        self.require(self.d(text="日期选择").count == 0, "日期确认后未返回订单列表")

    def open_top_filter(self, *labels: str) -> None:
        _, height = self.d.window_size()
        for label in labels:
            matches = self.d(text=label)
            for index in range(matches.count):
                item = matches[index]
                bounds = item.info.get("bounds", {})
                if bounds and bounds["top"] < height * 0.2:
                    item.click()
                    time.sleep(0.8)
                    return
        raise AssertionError(f"未找到顶部筛选器：{' / '.join(labels)}")

    def top_filter_exists(self, label: str) -> bool:
        _, height = self.d.window_size()
        matches = self.d(text=label)
        for index in range(matches.count):
            bounds = matches[index].info.get("bounds", {})
            if bounds and bounds["top"] < height * 0.2:
                return True
        return False

    def select_wheel_filter(
        self,
        filter_labels: str | tuple[str, ...],
        target: str,
        options: tuple[str, ...],
    ) -> None:
        target_index = options.index(target)
        width, height = self.d.window_size()
        labels = (filter_labels,) if isinstance(filter_labels, str) else filter_labels
        self.open_top_filter(*labels)
        center_x = int(width * 0.5)
        center_y = int(height * 0.75)
        target_clicked = False
        matches = self.d(text=target)
        for index in range(matches.count):
            item = matches[index]
            try:
                bounds = item.info.get("bounds", {})
                item_y = (bounds["top"] + bounds["bottom"]) // 2
                if int(height * 0.55) < item_y < height:
                    item.click()
                    target_clicked = True
                    break
            except Exception:
                continue
        if not target_clicked:
            self.d.swipe(
                center_x,
                center_y,
                center_x,
                center_y - target_index * int(height * 0.037),
                duration=0.5,
            )
        time.sleep(2)

        self.screenshot(f"picker-before-confirm-{target}")
        confirm_clicked = False
        confirms = self.d(text="确认")
        for index in range(confirms.count):
            item = confirms[index]
            try:
                bounds = item.info.get("bounds", {})
                confirm_y = (bounds["top"] + bounds["bottom"]) // 2
                if int(height * 0.5) < confirm_y < height:
                    item.click()
                    confirm_clicked = True
                    break
            except Exception:
                continue
        if not confirm_clicked:
            self.d.click(int(width * 0.89), int(height * 0.58))
        time.sleep(2)
        self.screenshot(f"filter-after-confirm-{target}")

        if target_index:
            self.require(
                self.top_filter_exists(target),
                f"筛选器确认后未显示选中值：{target}",
            )

    def field_by_hint(self, *hints: str):
        for hint in hints:
            field = self.d(className="android.widget.EditText", description=hint)
            if field.exists(timeout=0.5):
                return field
            field = self.d(className="android.widget.EditText", text=hint)
            if field.exists(timeout=0.5):
                return field
            field = self.d.xpath(f'//android.widget.EditText[@hint="{hint}"]')
            if self.selector_exists(field, timeout=0.5):
                return field
        return None

    def set_search_field(self, hints: tuple[str, ...], value: str, index: int) -> None:
        field = self.field_by_hint(*hints)
        if field is None:
            fields = self.d(className="android.widget.EditText")
            self.require(fields.count > index, f"高级搜索缺少第 {index + 1} 个输入框")
            field = fields[index]
        field.click()
        field.clear_text()
        field.set_text(value)

    def input_value(self, field: object) -> str:
        info = self.element_info(lambda: field)
        text = str(info.get("text") or "")
        hint = str(info.get("hint") or "")
        return "" if text == hint or text.startswith("请输入") else text

    def wait_remote_list_ready(self, timeout: float = 30) -> None:
        required_labels = ("产品名称", "订单状态", "录制类型")
        deadline = time.time() + timeout
        while time.time() < deadline:
            hierarchy = self.d.dump_hierarchy()
            loading = "加载中" in hierarchy
            if not loading and all(label in hierarchy for label in required_labels):
                return
            time.sleep(1)
        missing = [label for label in required_labels if label not in self.d.dump_hierarchy()]
        self.require(False, f"远程列表加载超时，缺少字段：{'、'.join(missing) or '无'}")

    def remote_filter_search(self) -> None:
        """Mirror h5-customer-remote-filter-search.yaml on Android."""
        print("\n[用例] 客户远程筛选与高级搜索")
        self.launch_login()
        self.login()
        self.wait_text("远程双录", timeout=30)
        self.wait_remote_list_ready()

        status_options = ("订单状态", "待处理", "待质检", "质检中")
        product_options = ("产品类型", "保险", "理财", "信托")

        self.select_wheel_filter("订单状态", "待处理", status_options)
        self.select_wheel_filter("产品类型", "理财", product_options)
        self.screenshot("remote-combined-filter")

        self.click_search()
        self.set_search_field(("请输入订单号", "订单号"), "OD2099751229237243904", 0)
        self.set_search_field(("请输入客户名称", "客户名称"), "自动化客户", 1)
        self.set_search_field(("请输入客户证件号", "客户证件号"), CUSTOMER_ID, 2)
        self.hide_keyboard()
        self.screenshot("remote-search-fields")

        self.click_text("重置")
        if not self.d(text="高级搜索").exists(timeout=2):
            self.click_search()
        order_field = self.field_by_hint("请输入订单号", "订单号")
        name_field = self.field_by_hint("请输入客户名称", "客户名称")
        self.require(order_field is not None and not self.input_value(order_field), "重置后订单号未清空")
        self.require(name_field is not None and not self.input_value(name_field), "重置后客户名称未清空")

        self.set_search_field(("请输入订单号", "订单号"), "NO_SUCH_ORDER_999", 0)
        self.hide_keyboard()
        self.click_text("查询")
        self.wait_text("暂无订单", timeout=30)
        self.screenshot("remote-no-match")
        self.logout()
        print("    [通过] 客户远程筛选与高级搜索")

    def customer_filter_flow(self, tab: str, valid_order: str) -> None:
        print(f"\n[用例] 客户{tab}筛选")
        self.launch_login()
        self.login()
        self.click_bottom_tab(tab)
        self.wait_remote_list_ready()

        status_options = ("订单状态", "待处理", "待质检", "质检中")
        product_options = ("产品类型", "保险", "理财", "信托")
        self.select_wheel_filter("订单状态", "待处理", status_options)
        print(f"    [通过] {tab}订单状态筛选")
        self.select_wheel_filter("产品类型", "理财", product_options)
        print(f"    [通过] {tab}产品类型筛选")
        self.select_date_range()
        print(f"    [通过] {tab}查询日期筛选")
        self.screenshot(f"{tab}-combined-filter")

        # 清除顶部组合筛选后，再用无效订单号验证空结果。
        self.click_search()
        self.click_text("重置")
        time.sleep(0.5)
        if not self.search_is_open():
            self.click_search()
        self.set_search_field(("请输入订单号", "订单号"), NO_MATCH_ORDER, 0)
        self.hide_keyboard()
        self.click_text("查询")
        self.wait_text("暂无订单", timeout=30)
        print(f"    [通过] {tab}无效订单号查询")

        # 从空结果再次打开搜索，重置后查询该业务的有效订单。
        self.click_search()
        self.click_text("重置")
        time.sleep(0.5)
        if not self.search_is_open():
            self.click_search()
        self.set_search_field(("请输入订单号", "订单号"), valid_order, 0)
        self.hide_keyboard()
        self.click_text("查询")
        self.wait_text(valid_order, timeout=30)
        print(f"    [通过] {tab}重置后有效订单查询")

        self.screenshot(f"{tab}-filters")
        self.logout()
        print(f"    [通过] 客户{tab}筛选及登出闭环")

    def remote_filters(self) -> None:
        self.customer_filter_flow("远程", REMOTE_VALID_ORDER)

    def self_service_filters(self) -> None:
        self.customer_filter_flow("自助", ORDER_ID_SELF_SERVICE)

    def pure_record_filters(self) -> None:
        self.customer_filter_flow("纯录制", ORDER_ID_CUSTOMER_PURE_RECORD)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Android 客户角色 H5 对齐回归用例")
    parser.add_argument(
        "case",
        choices=(
            "login-validation",
            "remote-filter-search",
            "remote-filters",
            "self-service-filters",
            "pure-record-filters",
            "all",
        ),
        nargs="?",
        default="all",
    )
    parser.add_argument("--device", default=DEVICE_ID, help="ADB 设备序列号")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    device = u2.connect(args.device)
    suite = CustomerRegression(device, args.device)
    cases: dict[str, Callable[[], None]] = {
        "login-validation": suite.login_validation,
        "remote-filter-search": suite.remote_filter_search,
        "remote-filters": suite.remote_filters,
        "self-service-filters": suite.self_service_filters,
        "pure-record-filters": suite.pure_record_filters,
    }
    selected = list(cases) if args.case == "all" else [args.case]
    failures: list[tuple[str, Exception]] = []

    for name in selected:
        try:
            cases[name]()
        except Exception as error:
            failures.append((name, error))
            suite.screenshot(f"{name}-failure")
            print(f"    [失败] {name}: {error}")

    print("\n测试汇总")
    print(f"  总数: {len(selected)}")
    print(f"  通过: {len(selected) - len(failures)}")
    print(f"  失败: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
