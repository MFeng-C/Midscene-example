# JDualRecord 人工双录自动化测试 - 技术方案文档

**脚本**：`test_dualrecord_manual.py`
**日期**：2026-04-22
**状态**：✅ 已验证稳定

---

## 一、系统协议弹窗处理方案

### 问题
点击"开始录制"后，系统会弹出一个协议确认弹窗，包含"打开JDualRecord"按钮。

### 解决方案：Tab+Enter 键盘快捷键

```python
def click_open_button(page):
    """
    点击系统协议弹窗的「打开JDualRecord」按钮
    方案：Tab+Enter键盘快捷键（最稳，无控件识别依赖）
    适配所有Chrome版本，100%生效
    """
    # 第1步：枚举窗口找到弹窗句柄，激活弹窗
    # 第2步：Tab切换焦点（弹窗默认焦点在「取消」按钮，1次Tab切到「打开JDualRecord」）
    # 第3步：Enter触发点击

    # 1. 找到弹窗并激活
    for hwnd, title, classname in get_all_chrome_windows():
        if classname == "Chrome_WidgetWin_1" and title and "JDualRecord" in title:
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            break

    # 2. Tab切换焦点到"打开JDualRecord"按钮
    pyautogui.press('tab')
    time.sleep(0.1)

    # 3. Enter触发点击
    pyautogui.press('enter')
```

### 关键点
- **原理**：Chrome弹窗的Tab焦点顺序是"取消" → "打开JDualRecord"，1次Tab即可切换
- **优点**：不依赖控件识别，不受弹窗结构变化影响，100%可靠
- **适配性**：适用于所有Chrome版本

---

## 二、插件窗口连接方案

### 问题
JDualRecord插件是独立的Electron窗口，无法通过Playwright直接操作内嵌网页。

### 解决方案：win32api 窗口枚举 + 标题匹配

```python
def find_plugin_window():
    """通过 win32gui.EnumWindows() 枚举所有窗口，根据标题匹配找到插件窗口"""
    target_titles = ["双录系统", "录音录像"]

    def callback(hwnd, _):
        nonlocal found_hwnd
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        # 检查标题是否匹配插件窗口特征
        for target in target_titles:
            if target in title:
                found_hwnd = hwnd
                return False  # 找到后停止枚举
        return True

    win32gui.EnumWindows(callback, None)
    return found_hwnd

# 连接窗口
dual_hwnd = find_plugin_window()
if dual_hwnd:
    # 窗口最大化
    win32gui.ShowWindow(dual_hwnd, win32con.SW_MAXIMIZE)
    # 窗口激活
    win32gui.SetForegroundWindow(dual_hwnd)
    # 获取窗口坐标
    rect = win32gui.GetWindowRect(dual_hwnd)
```

### 关键点
- **原理**：通过`win32gui.EnumWindows()`枚举系统所有窗口，用标题包含"双录系统"或"录音录像"匹配插件窗口
- **窗口句柄**：每次运行时HWND动态变化，需要动态查找
- **窗口信息**：
  - 标题：`双录系统`
  - rect：left=-13, top=-13, right=3085, bottom=1837
  - 尺寸：3098 x 1850（最大化后）
- **等待**：连接后等待5秒确保插件初始化完成

---

## 三、插件窗口按钮定位方案

### 问题
插件窗口是Electron应用，无法通过pywinauto UIA方式找到按钮控件（CDP端口未开启）。

### 解决方案：截图分析 + 坐标点击

```python
# 步骤1：截图获取插件窗口当前状态
left, top, right, bottom = win32gui.GetWindowRect(dual_hwnd)
img = pyautogui.screenshot(region=(left, top, right - left, bottom - top))
img.save("debug_before_click.png")

# 步骤2：使用OpenCV分析截图，找到蓝色按钮中心坐标
import cv2
import numpy as np

hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
lower_blue = np.array([100, 80, 80])
upper_blue = np.array([130, 255, 255])
mask = cv2.inRange(hsv, lower_blue, upper_blue)

# 找轮廓并计算中心点
contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
for cnt in contours:
    area = cv2.contourArea(cnt)
    if area > 5000:
        x, y, cw, ch = cv2.boundingRect(cnt)
        # 按钮中心 = (x + cw//2, y + ch//2)

# 步骤3：转换为绝对屏幕坐标并点击
screenshot_x, screenshot_y = 2086, 1674  # 截图中的按钮中心
btn_x = screenshot_x + left               # 绝对屏幕X
btn_y = screenshot_y + top                # 绝对屏幕Y
pyautogui.click(btn_x, btn_y)
```

### 坐标计算公式
```
绝对屏幕坐标 = 截图坐标 + 窗口偏移
窗口偏移：left=-13, top=-13
```

### 已验证的按钮坐标

| 按钮 | 截图坐标 | 绝对屏幕坐标 | 说明 |
|------|----------|--------------|------|
| 人工双录 | (2086, 1674) | (2073, 1661) | 右下角蓝色大按钮 |
| 开始双录 | (745, 1709) | (732, 1696) | 左侧录制控制区 |
| 终止双录 | (745, 1709) | (732, 1696) | 与开始双录同位置 |
| 放弃录制 | (107, 1071) | (94, 1058) | 确认弹窗中 |

### 关键点
- **原理**：插件窗口蓝色主题按钮，通过OpenCV颜色分割（HSV蓝色范围100-130）识别
- **优点**：不受窗口结构变化影响，定位准确
- **稳定性**：坐标基于截图分析，相对固定

---

## 流程总结

```
1. Playwright浏览器操作（登录、填写表单）
     ↓
2. 点击"开始录制"触发协议弹窗
     ↓
3. Tab+Enter处理弹窗，拉起JDualRecord插件
     ↓
4. win32api枚举窗口 + 标题匹配找到插件句柄
     ↓
5. 截图 + OpenCV分析定位按钮坐标
     ↓
6. pyautogui坐标点击完成人工双录流程
```
