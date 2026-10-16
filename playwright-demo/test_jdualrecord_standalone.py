"""Standalone JDualRecord automation.

The script intentionally does not import any existing demo script. It uses:
  * Playwright for the DualPortal web page;
  * Windows UI Automation for the browser protocol prompt and app window;
  * Playwright over CDP for the embedded JCEF page when CDP is available;
  * window-relative mouse clicks only as a final fallback.

Examples:
  python test_jdualrecord_standalone.py --launch-from-portal --action inspect
  python test_jdualrecord_standalone.py --action ai
  python test_jdualrecord_standalone.py --action manual
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pyautogui
import win32api
import win32con
import win32gui
from playwright.sync_api import Browser, Page, Playwright, sync_playwright
from pywinauto import Desktop


pyautogui.FAILSAFE = True
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BROWSER_WINDOW_CLASSES = {"Chrome_WidgetWin_1"}
PLUGIN_TITLES = ("JDualAgent", "JDualRecord", "双录系统", "录音录像", "正在录制")
CDP_PORTS = (12222, 9222)


@dataclass(frozen=True)
class Config:
    portal_url: str = os.getenv("DUAL_PORTAL_URL", "http://192.168.18.223:18530")
    username: str = os.getenv("DUAL_PORTAL_USERNAME", "10001")
    password: str = os.getenv("DUAL_PORTAL_PASSWORD", "Aa123456")
    verification_code: str = os.getenv("DUAL_PORTAL_VERIFY_CODE", "0000")
    id_number: str = os.getenv("DUAL_PORTAL_ID_NUMBER", "411525200006040977")
    amount: str = os.getenv("DUAL_PORTAL_AMOUNT", "1000")
    artifact_dir: Path = Path(os.getenv("JDUAL_ARTIFACT_DIR", "jdualrecord_artifacts"))


def log(message: str) -> None:
    print(message, flush=True)


def visible_windows() -> list[tuple[int, str, str, tuple[int, int, int, int]]]:
    windows: list[tuple[int, str, str, tuple[int, int, int, int]]] = []

    def callback(hwnd: int, _: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            windows.append(
                (
                    hwnd,
                    win32gui.GetWindowText(hwnd),
                    win32gui.GetClassName(hwnd),
                    win32gui.GetWindowRect(hwnd),
                )
            )
        except Exception:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    return windows


def activate_window(hwnd: int) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        # A click is sufficient to transfer foreground permission on Windows.
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        pyautogui.click((left + right) // 2, max(top + 12, 1))
        win32gui.SetForegroundWindow(hwnd)


class PortalFlow:
    def __init__(self, playwright: Playwright, config: Config) -> None:
        self.config = config
        self.browser: Browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        self.context = self.browser.new_context(no_viewport=True)
        self.page = self.context.new_page()

    def launch_onsite_recording(self) -> Page:
        page = self.page
        cfg = self.config
        log("[Portal] Login")
        page.goto(cfg.portal_url, wait_until="domcontentloaded", timeout=30_000)
        page.locator('input[type="text"]').first.fill(cfg.username)
        page.locator('input[type="password"]').first.fill(cfg.password)
        page.locator('input[placeholder*="验证"]').first.fill(cfg.verification_code)
        page.get_by_role("button", name="登录").click()
        page.wait_for_url("**/dashboard/**", timeout=15_000)

        log("[Portal] Open onsite recording form")
        page.get_by_text("录音录像", exact=True).click()
        page.get_by_text("发起双录", exact=True).click()
        page.wait_for_url("**/record/**", timeout=15_000)

        self._select("请选择客户类型", "个人客户")
        self._select("请选择证件类型", "身份证")
        page.evaluate(
            """idNumber => {
                const inputs = [...document.querySelectorAll('input[type="text"]')];
                const input = inputs.find(el => !el.placeholder && !el.readOnly && el.offsetParent);
                if (!input) throw new Error('ID input not found');
                input.value = idNumber;
                input.dispatchEvent(new Event('input', {bubbles: true}));
                input.dispatchEvent(new Event('blur', {bubbles: true}));
            }""",
            cfg.id_number,
        )
        page.get_by_role("button", name="查询").click()
        page.wait_for_timeout(2_000)
        page.get_by_role("button", name="下一步").click()
        page.locator('input[placeholder="请选择产品类型"]').wait_for(
            state="visible", timeout=15_000
        )

        self._select("请选择产品类型", "理财")
        self._select("请选择产品子类", "代销理财")
        self._select("请选择产品", "理财产品")
        page.locator('.el-form-item:has-text("购买金额") input').fill(cfg.amount)
        page.get_by_role("button", name="确定", exact=True).click()
        page.locator('input[placeholder="请选择录制类型"]').wait_for(
            state="visible", timeout=15_000
        )

        self._select("请选择录制类型", "现场")
        page.get_by_role("button", name="开始录制").click()
        log("[Portal] External-protocol prompt requested")
        return page

    def _select(self, placeholder: str, option: str) -> None:
        field = self.page.locator(f'input[placeholder="{placeholder}"]').first
        field.wait_for(state="visible", timeout=15_000)
        field.click()
        self.page.locator(
            f'.el-select-dropdown__item:visible:has-text("{option}")'
        ).first.click()

    def close(self) -> None:
        self.context.close()
        self.browser.close()


class ProtocolPrompt:
    BUTTON_NAMES = ("打开JDualRecord", "打开", "打开 JDualAgent", "打开 JDualRecord")

    @staticmethod
    def _normalized_name(value: str) -> str:
        return "".join(value.split()).lower()

    @staticmethod
    def accept(timeout: float = 10, artifact_dir: Path | None = None) -> None:
        # The external-protocol bubble is browser chrome and appears
        # asynchronously after the web click has already returned.
        time.sleep(3)
        deadline = time.time() + timeout
        browser_hwnd: int | None = None
        browser_title = ""
        foreground = win32gui.GetForegroundWindow()
        try:
            foreground_class = win32gui.GetClassName(foreground)
            foreground_title = win32gui.GetWindowText(foreground)
            if foreground_class in BROWSER_WINDOW_CLASSES:
                browser_hwnd = foreground
                browser_title = foreground_title
        except Exception:
            pass

        while time.time() < deadline and browser_hwnd is None:
            for hwnd, title, class_name, _ in visible_windows():
                if class_name in BROWSER_WINDOW_CLASSES and "双录系统" in title:
                    browser_hwnd, browser_title = hwnd, title
                    break
            if browser_hwnd is None:
                time.sleep(0.2)

        if browser_hwnd is None:
            raise RuntimeError("DualPortal browser window was not found")

        win32gui.ShowWindow(browser_hwnd, win32con.SW_MAXIMIZE)
        time.sleep(0.5)
        activate_window(browser_hwnd)
        rect = win32gui.GetWindowRect(browser_hwnd)
        log(
            f"[Protocol] Browser activated: hwnd={browser_hwnd}, "
            f"title={browser_title!r}, rect={rect}"
        )

        if artifact_dir:
            left, top, right, bottom = win32gui.GetWindowRect(browser_hwnd)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            pyautogui.screenshot(
                region=(left, top, right - left, bottom - top)
            ).save(artifact_dir / "protocol_prompt.png")

        desktop = Desktop(backend="uia")
        root = desktop.window(handle=browser_hwnd)
        expected_names = {
            ProtocolPrompt._normalized_name(name) for name in ProtocolPrompt.BUTTON_NAMES
        }

        # Chrome/Edge native bubbles are not always direct children of the
        # browser's top-level window. Search both the browser subtree and the
        # complete desktop UIA tree, then explicitly focus the matched button.
        candidates = []
        for scope in (root, desktop):
            try:
                candidates.extend(scope.descendants(control_type="Button"))
            except Exception:
                pass

        seen_handles: set[int] = set()
        matching_buttons = []
        for button in candidates:
            try:
                handle = button.handle
                if handle and handle in seen_handles:
                    continue
                if handle:
                    seen_handles.add(handle)
                name = button.window_text().strip()
                normalized = ProtocolPrompt._normalized_name(name)
                if normalized not in expected_names and not (
                    normalized.startswith("打开")
                    and ("jdualrecord" in normalized or "jdualagent" in normalized)
                ):
                    continue
                rect = button.rectangle()
                log(
                    f"[Protocol] UIA button candidate: {name!r}, rect={rect}"
                )
                matching_buttons.append((button, name, rect))
            except Exception as error:
                log(f"[Protocol] UIA button click failed: {error}")

        if matching_buttons:
            screen_width, _ = pyautogui.size()
            expected_x = screen_width // 2 + (125 if "Edge" in browser_title else 67)
            expected_y = 159 if "Edge" in browser_title else 212
            button, name, rect = min(
                matching_buttons,
                key=lambda item: (
                    ((item[2].left + item[2].right) // 2 - expected_x) ** 2
                    + ((item[2].top + item[2].bottom) // 2 - expected_y) ** 2
                ),
            )
            click_x = (rect.left + rect.right) // 2
            click_y = (rect.top + rect.bottom) // 2
            button.set_focus()
            time.sleep(0.2)
            win32api.SetCursorPos((click_x, click_y))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(1)
            try:
                button_still_visible = button.is_visible()
            except Exception:
                button_still_visible = False
            if button_still_visible:
                button.set_focus()
                pyautogui.press("enter")
                time.sleep(1)
            try:
                button_still_visible = button.is_visible()
            except Exception:
                button_still_visible = False
            if button_still_visible:
                raise RuntimeError("'打开JDualRecord' button is still visible after click")
            log(
                f"[Protocol] Focused and physically clicked selected UIA button: "
                f"{name!r}, rect={rect}, point=({click_x}, {click_y})"
            )
            return

        # This machine reports Win32 coordinates in DPI-scaled units while
        # PyAutoGUI uses physical screen pixels. Clicking the native prompt by
        # physical screen position both transfers focus and activates Open.
        activate_window(browser_hwnd)
        screen_width, _ = pyautogui.size()
        if "Edge" in browser_title:
            click_x, click_y = screen_width // 2 + 125, 159
        else:
            click_x, click_y = screen_width // 2 + 67, 212
        pyautogui.moveTo(click_x, click_y, duration=0.2)
        pyautogui.click()
        log(
            f"[Protocol] Focused and clicked native prompt at physical "
            f"coordinates ({click_x}, {click_y})"
        )


class PluginWindow:
    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd

    @classmethod
    def wait(cls, timeout: float = 30) -> "PluginWindow":
        deadline = time.time() + timeout
        while time.time() < deadline:
            for hwnd, title, class_name, rect in visible_windows():
                if class_name in BROWSER_WINDOW_CLASSES:
                    continue
                if any(token.lower() in title.lower() for token in PLUGIN_TITLES):
                    width, height = rect[2] - rect[0], rect[3] - rect[1]
                    if width > 300 and height > 200:
                        log(
                            f"[Plugin] Window found: hwnd={hwnd}, title={title!r}, "
                            f"class={class_name!r}, size={width}x{height}"
                        )
                        return cls(hwnd)
            time.sleep(0.5)
        raise TimeoutError("JDualRecord/JDualAgent window did not appear")

    def activate(self, maximize: bool = True) -> None:
        if maximize:
            win32gui.ShowWindow(self.hwnd, win32con.SW_MAXIMIZE)
        activate_window(self.hwnd)

    def screenshot(self, path: Path) -> None:
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        path.parent.mkdir(parents=True, exist_ok=True)
        pyautogui.screenshot(
            region=(left, top, right - left, bottom - top)
        ).save(path)

    def click_relative(self, x_ratio: float, y_ratio: float) -> None:
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        x = left + round((right - left) * x_ratio)
        y = top + round((bottom - top) * y_ratio)
        pyautogui.click(x, y)
        log(f"[Plugin] Relative click at ({x}, {y})")


class PluginController:
    def __init__(self, playwright: Playwright, window: PluginWindow) -> None:
        self.playwright = playwright
        self.window = window
        self.cdp_browser: Browser | None = None
        self.page: Page | None = None

    def connect_cdp(self, ports: Iterable[int] = CDP_PORTS) -> bool:
        configured = os.getenv("JDUAL_CDP_PORT")
        candidates = ([int(configured)] if configured else []) + list(ports)
        for port in dict.fromkeys(candidates):
            try:
                browser = self.playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}", timeout=2_000
                )
                pages = [page for context in browser.contexts for page in context.pages]
                page = next(
                    (
                        item
                        for item in pages
                        if any(token in item.title() for token in ("双录", "录音录像"))
                    ),
                    pages[0] if pages else None,
                )
                if page is None:
                    browser.close()
                    continue
                self.cdp_browser, self.page = browser, page
                log(f"[Plugin] CDP connected on port {port}: {page.title()!r}")
                return True
            except Exception:
                continue
        log("[Plugin] CDP unavailable; using UIA/relative-click fallback")
        return False

    def inspect(self) -> None:
        if self.page:
            buttons = self.page.get_by_role("button").all_inner_texts()
            log(f"[Plugin] DOM buttons: {buttons}")
            return
        try:
            root = Desktop(backend="uia").window(handle=self.window.hwnd)
            buttons = [item.window_text() for item in root.descendants(control_type="Button")]
            log(f"[Plugin] UIA buttons: {buttons}")
        except Exception as error:
            log(f"[Plugin] UIA inspection failed: {error}")

    def select_recording(self, mode: str) -> None:
        label = "AI双录" if mode == "ai" else "人工双录"
        if self.page:
            button = self.page.get_by_role("button", name=label)
            button.wait_for(state="visible", timeout=15_000)
            button.click()
            log(f"[Plugin] Clicked by CDP: {label}")
            return

        try:
            root = Desktop(backend="uia").window(handle=self.window.hwnd)
            button = root.child_window(title=label, control_type="Button")
            if button.exists(timeout=2):
                button.click_input()
                log(f"[Plugin] Clicked by UIA: {label}")
                return
        except Exception:
            pass

        # Ratios are based on the maximized 1920x1152 JDualRecord window.
        x_ratio = 0.568 if mode == "ai" else 0.497
        self.window.click_relative(x_ratio, 0.895)
        log(f"[Plugin] Clicked by relative fallback: {label}")

    def close(self) -> None:
        # Do not call Browser.close() on an attached CDP target: it may close
        # the embedded browser owned by JDualRecord. Stopping Playwright only
        # disconnects this automation client.
        self.page = None
        self.cdp_browser = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone JDualRecord automation")
    parser.add_argument(
        "--launch-from-portal",
        action="store_true",
        help="Create an onsite recording in DualPortal and accept the protocol prompt",
    )
    parser.add_argument(
        "--action",
        choices=("inspect", "ai", "manual"),
        default="inspect",
        help="Action after connecting to JDualRecord (default: inspect)",
    )
    parser.add_argument("--keep-open", action="store_true", help="Keep browser/CDP open")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Config()
    portal: PortalFlow | None = None
    controller: PluginController | None = None

    with sync_playwright() as playwright:
        try:
            if args.launch_from_portal:
                portal = PortalFlow(playwright, config)
                portal.launch_onsite_recording()
                ProtocolPrompt.accept(artifact_dir=config.artifact_dir)

            plugin = PluginWindow.wait()
            plugin.activate()
            plugin.screenshot(config.artifact_dir / "plugin_connected.png")

            controller = PluginController(playwright, plugin)
            controller.connect_cdp()
            controller.inspect()
            if args.action in ("ai", "manual"):
                controller.select_recording(args.action)
                time.sleep(2)
                plugin.screenshot(config.artifact_dir / f"after_{args.action}.png")

            log("[PASS] JDualRecord automation completed")
            if args.keep_open:
                input("Press Enter to close automation connections...")
            return 0
        except Exception as error:
            if portal:
                config.artifact_dir.mkdir(parents=True, exist_ok=True)
                try:
                    portal.page.screenshot(
                        path=config.artifact_dir / "failure.png", full_page=True
                    )
                except Exception:
                    pass
            log(f"[FAIL] {type(error).__name__}: {error}")
            return 1
        finally:
            if controller:
                controller.close()
            if portal:
                portal.close()


if __name__ == "__main__":
    sys.exit(main())
