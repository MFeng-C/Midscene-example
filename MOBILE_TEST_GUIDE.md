# 移动端双录App UI自动化测试脚本使用指南

**文档版本：** v1.0
**更新日期：** 2026-06-16
**适用平台：** Android / iOS

---

## 一、概述

本文档介绍双录App UI自动化测试脚本的使用方法，支持Android和iOS双平台，覆盖客户自助、客户经理等多种业务场景。

---

## 二、测试脚本清单

### 2.1 Android 脚本

| 脚本文件 | 描述 | 测试场景 |
|----------|------|----------|
| `test_jdualrecord_app.py` | Android双录主测试脚本 | 客户登录、客户纯录制、客户经理纯录制、客户经理现场双录(AI/人工)、客户自助双录 |

**运行命令示例：**
```bash
# 客户登录测试
python test_jdualrecord_app.py customer

# 客户纯录制测试
python test_jdualrecord_app.py customer_record

# 客户经理登录测试
python test_jdualrecord_app.py manager

# 客户经理纯录制测试
python test_jdualrecord_app.py record

# 客户自助双录测试
python test_jdualrecord_app.py customer_self

# 客户经理现场双录(AI)
python test_jdualrecord_app.py scene ai

# 客户经理现场双录(人工)
python test_jmanual scene manual

# 循环执行
python test_jdualrecord_app.py scene ai 10  # AI双录循环10次
```

---

### 2.2 iOS 脚本

| 脚本文件 | 描述 | 测试场景 |
|----------|------|----------|
| `test_devices_ios.py` | iOS通用登录登出测试 | 客户登录、客户经理登录、登出 |
| `test_pure_recording_ios.py` | iOS纯录制/自助业务测试 | 客户纯录制、客户自助双录 |
| `test_manager_pure_recording_ios.py` | iOS客户经理业务测试 | 客户经理纯录制、客户经理现场双录(AI/人工) |

**运行命令示例：**
```bash
# 客户登录登出测试（循环1次）
python test_devices_ios.py
python test_devices_ios.py 10  # 循环10次

# 客户经理登录测试
python test_devices_ios.py manager 10

# 客户纯录制测试（默认关闭截图，加速执行）
python test_pure_recording_ios.py

# 客户自助业务测试
python test_pure_recording_ios.py self
python test_pure_recording_ios.py self 5  # 循环5次

# 客户经理纯录制测试
python test_manager_pure_recording_ios.py

# 客户经理现场双录(AI)
python test_manager_pure_recording_ios.py scene ai
python test_manager_pure_recording_ios.py scene ai 10  # 循环10次

# 客户经理现场双录(人工)
python test_manager_pure_recording_ios.py scene manual
python test_manager_pure_recording_ios.py scene manual 5  # 循环5次

# 开启截图功能（调试用）
SCREENSHOT=1 python test_pure_recording_ios.py self
```

---

### 2.3 Playwright 临柜双录脚本（Windows浏览器 + JDualRecord插件）

| 脚本文件 | 描述 | 测试场景 |
|----------|------|----------|
| `test_dualrecord_ai_lingui.py` | 临柜AI双录自动化测试 | 登录 → 临柜双录 → AI双录模式 → 开始/终止录制 |
| `test_dualrecord_lingui_manual.py` | 临柜人工双录自动化测试 | 登录 → 临柜双录 → 人工双录模式 → 开始/终止录制 |

**运行命令示例：**
```bash
cd playwright-demo

# 临柜AI双录测试
python test_dualrecord_ai_lingui.py

# 临柜人工双录测试
python test_dualrecord_lingui_manual.py
```

**业务流程（AI和人工相同，仅按钮不同）：**
```
登录系统 → 发起双录 → 临柜双录 → 填写客户信息 → 填写产品信息 → 选择现场录制 → 开始录制
→ 协议弹窗(点击打开JDualRecord) → JDualRecord插件窗口激活
→ 点击"AI双录"或"人工双录" → 点击"开始双录" → 等待倒计时 → 点击"终止双录" → 点击"放弃录制" → 关闭窗口
```

**核心特性：**
- 使用 Playwright 操控浏览器（Chrome/Edge）完成Web端操作
- 通过 Chrome 远程调试端口（CDP ws://127.0.0.1:12222）连接 JDualRecord Electron插件内嵌网页
- 使用 win32api 枚举/激活 JDualRecord 桌面窗口，配合 pyautogui 坐标点击插件按钮
- 支持窗口标题枚举、javaw.exe进程校验、截图调试
- 三方案兜底定位终止录制按钮：UIA深度遍历 → 全局坐标验证 → OpenCV图像识别

---

## 三、测试场景覆盖

### 3.1 业务流程矩阵

| 业务场景 | Android | iOS | Playwright临柜 | 说明 |
|----------|----------|------|------|------|
| 客户登录 | ✅ | ✅ | ❌ | 客户身份证号登录/登出 |
| 客户经理登录 | ✅ | ✅ | ❌ | 工号登录/登出 |
| 客户纯录制 | ✅ | ✅ | ❌ | 纯录制业务流程 |
| 客户自助双录 | ✅ | ✅ | ❌ | 自助AI双录+问答+朗读 |
| 客户经理纯录制 | ✅ | ✅ | ❌ | 现场录制+环境检测 |
| 客户经理现场双录(AI) | ✅ | ✅ | ❌ | AI双录流程 |
| 客户经理现场双录(人工) | ✅ | ✅ | ❌ | 人工双录流程 |
| 临柜AI双录 | ❌ | ❌ | ✅ | Playwright浏览器+JDualRecord插件 |
| 临柜人工双录 | ❌ | ❌ | ✅ | Playwright浏览器+JDualRecord插件 |

### 3.2 核心业务流程

**客户登录登出流程：**
```
启动App → 点击登录入口 → 输入账号密码验证码 → 点击登录 → 首页 → 点击"我的" → 退出登录 → 确认退出 → Home键
```

**客户纯录制流程：**
```
登录 → 点击"纯录制" → 选择订单 → 点击录制 → 确认 → 同意条款 → 开始直播 → 同意检测 → 环境检测 → 开始录制 → 结束录制 → 上传文件 → 退出
```

**临柜AI双录流程：**
```
登录系统 → 发起双录 → 临柜双录 → 填写客户信息(个人客户+身份证) → 填写产品信息(理财+代销理财)
→ 选择现场录制 → 开始录制 → 协议弹窗(打开JDualRecord) → JDualRecord插件窗口激活
→ 点击"AI双录" → 点击"开始双录" → 等待3秒倒计时 → 点击"终止双录" → 点击"放弃录制" → 关闭窗口
```

**临柜人工双录流程：**
```
登录系统 → 发起双录 → 临柜双录 → 填写客户信息(个人客户+身份证) → 填写产品信息(理财+代销理财)
→ 选择现场录制 → 开始录制 → 协议弹窗(打开JDualRecord) → JDualRecord插件窗口激活
→ 点击"人工双录" → 点击"开始双录" → 等待3秒倒计时 → 点击"终止双录" → 点击"放弃录制" → 关闭窗口
```

---

## 四、测试条件准备

### 4.1 设备要求

#### Android设备
- Android手机一台（开启USB调试模式）
- 设备已root（推荐）或已授权adb调试
- 设备ID已知

#### iOS设备
- iPhone一台（已安装企业证书App）
- 已搭建Appium测试环境
- WDA（WebDriverAgent）已启动
- 设备已连接Appium服务器

### 4.2 环境依赖

**Python版本：** Python 3.8+

**Android依赖：**
```bash
pip install uiautomator2
```

**iOS依赖：**
```bash
pip install Appium-Python-Client
pip install Selenium
```

**Playwright临柜脚本依赖（Windows）：**
```bash
pip install playwright
playwright install chromium
pip install pywinauto pygetwindow pyautogui opencv-python psutil pywin32
```

**Appium服务器：**
```bash
# 启动Appium服务
appium --address 127.0.0.1 --port 4723

# iOS额外需要WDA
# 通过Xcode启动WDA或手动启动
```

### 4.3 设备连接配置

#### Android
```python
# 方式1: USB连接
device_id = "b76086c1"  # adb devices显示的设备ID
d = u2.connect(device_id)

# 方式2: WiFi连接
d = u2.connect("http://192.168.1.100:5555")
```

#### iOS
```python
# 配置文件修改
WDA_URL = "http://192.168.1.100:8100"  # WDA地址
APPIUM_URL = "http://192.168.1.100:4723"  # Appium地址
UDID = "你的设备UDID"
```

---

## 五、配置文件说明

### 5.1 Android配置项

```python
# 脚本内配置
device_id = "b76086c1"  # adb devices获取
package_name = "com.juphoon.hybridrecord"  # App包名
activity_name = "com.juphoon.hybrid.record.webhybrid.WebHybridActivity"  # 启动页
```

### 5.2 iOS配置项

```python
# 设备配置
WDA_URL = "http://172.16.1.34:8100"      # WDA地址
APPIUM_URL = "http://172.16.1.34:4723"   # Appium地址
UDID = "7720cc4ebea57931c047c2cdc0a9fbc5f6cf0c5c"  # 设备UDID
BUNDLE_ID = "com.juphoon.record.ios"  # App Bundle ID
PLATFORM_VERSION = "17"  # iOS版本
```

### 5.3 Playwright临柜脚本配置项

```python
# test_dualrecord_ai_lingui.py / test_dualrecord_lingui_manual.py
SYSTEM_URL = "http://192.168.18.223:18530"   # 双录系统Web地址
TEST_USERNAME = "10001"                        # 客户经理工号
TEST_PASSWORD = "Aa123456"                    # 登录密码
# CDP连接地址（JDualRecord Electron插件远程调试端口）
browser = p.chromium.connect_over_cdp("ws://127.0.0.1:12222")
# JDualRecord插件窗口标题特征
target_titles = ["双录系统", "录音录像"]
```

### 5.4 账号配置（脚本内）

| 平台 | 账号类型 | 账号 | 密码 | 验证码 |
|------|----------|------|------|------|
| Android | 客户 | 411525200006040977 | Record123456 | 0000 |
| Android | 客户经理 | 10001 | Aa123456 | 0000 |
| iOS | 客户 | 411525200006040977 | Record123456 | 0000 |
| iOS | 客户经理 | 10001 | Aa123456 | 0000 |

---

## 六、脚本参数说明

### 6.1 命令行参数

```bash
# Android参数
python test_jdualrecord_app.py <scene> [loop_count]

# 参数说明
scene: customer | record | manager | scene | customer_self
loop_count: 循环次数，默认1

# iOS参数
python xxx.py [loop_count] [detect_mode]
python xxx.py self [loop_count]
python xxx.py scene ai [loop_count]

# 参数说明
loop_count: 循环次数，默认1
detect_mode: auto | pass | not_pass（仅部分脚本支持）
```

### 6.2 环境变量

```bash
# iOS截图功能开关（默认关闭）
SCREENSHOT=1 python test_pure_recording_ios.py  # 开启截图
python test_pure_recording_ios.py  # 关闭截图（更快）
```

---

## 七、使用示例

### 7.1 快速开始

```bash
# 1. Android客户登录测试
cd android
python test_jdualrecord_app.py customer

# 2. iOS客户登录测试
cd ios
python test_devices_ios.py

# 3. iOS客户纯录制测试
python test_pure_recording_ios.py

# 4. iOS客户经理现场双录(AI)循环10次
python test_manager_pure_recording_ios.py scene ai 10
```

### 7.2 调试模式

```bash
# 开启截图功能
SCREENSHOT=1 python test_pure_recording_ios.py self 3

# 查看截图输出
ls -la screenshots_pure_recording/
```

### 7.3 连续测试

```bash
# 循环执行50次客户登录测试
python test_devices_ios.py 50

# 循环执行20次客户经理现场双录(AI)
python test_manager_pure_recording_ios.py scene ai 20
```

---

## 八、测试报告

### 8.1 终端输出

测试完成后会输出汇总信息：
```
==================================================
测试汇总
==================================================
总循环次数: 50
成功次数: 50
失败次数: 0
成功率: 100.0%
平均App启动到登录耗时: 4.50s
平均登出耗时: 3.80s
==================================================
```

### 8.2 截图输出

- **Android**: `screenshots/`
- **iOS**: `screenshots/`, `screenshots_pure_recording/`, `screenshots_manager_pure_recording/`

截图命名规则: `{步骤名}_{循环次数}.png`，如 `step1_launch_1.png`

---

## 九、常见问题

### 9.1 Android

| 问题 | 解决方案 |
|------|----------|
| 找不到App图标 | 检查App是否安装，尝试重新安装 |
| 输入框定位失败 | 截图查看当前页面，可能UI变化需更新定位符 |
| 点击无效 | 检查元素是否可点击，或使用坐标点击 |

### 9.2 iOS

| 问题 | 解决方案 |
|------|----------|
| WDA连接超时 | 检查WDA服务是否启动，IP是否正确 |
| WebView切换失败 | 检查App版本，尝试 `autoWebview: True` |
| 按钮定位失败 | 使用 `SCREENSHOT=1` 开启截图排查 |
| 输入框无响应 | 可能需要先点击输入框获得焦点 |

### 9.3 环境问题

```bash
# 检查设备连接
adb devices  # Android
instruments -s devices  # iOS

# 检查Appium服务
curl http://localhost:4723/status

# 检查WDA状态
curl http://localhost:8100/status
```

### 9.4 Playwright临柜脚本

| 问题 | 解决方案 |
|------|------|
| CDP连接失败 | 确认JDualRecord插件已启动，端口12222可访问 |
| 找不到JDualRecord窗口 | 检查插件进程是否启动，窗口标题是否符合target_titles |
| 点击按钮无响应 | 使用截图调试，确认窗口已最大化激活 |
| 坐标点击偏移 | 重新分析当前分辨率下的按钮截图坐标 |

---

## 十、脚本目录结构

```
midscene-example/
├── android/
│   ├── test_jdualrecord_app.py    # Android主测试脚本
│   ├── screenshots/                # Android截图目录
│   └── README.md                   # Android专用说明
├── ios/
│   ├── test_devices_ios.py          # iOS登录登出脚本
│   ├── test_pure_recording_ios.py   # iOS纯录制脚本
│   ├── test_manager_pure_recording_ios.py  # iOS经理业务脚本
│   ├── screenshots/                 # 截图目录
│   ├── screenshots_pure_recording/
│   └── screenshots_manager_pure_recording/
├── playwright-demo/
│   ├── test_dualrecord_ai_lingui.py      # 临柜AI双录脚本
│   ├── test_dualrecord_lingui_manual.py  # 临柜人工双录脚本
│   ├── JDualRecord双录自动化测试说明.md
│   ├── 临柜AI双录测试文档.md
│   └── 临柜人工双录测试文档.md
└── docs/
    └── MOBILE_TEST_GUIDE.md        # 本文档
```

## 附录：命令行参数速查表

### Android
| 命令 | 说明 |
|------|------|
| `python test.py customer` | 客户登录 |
| `python test.py record` | 客户经理纯录制 |
| `python test.py scene ai` | 客户经理现场AI双录 |
| `python test.py scene manual` | 客户经理现场人工双录 |
| `python test.py customer_self` | 客户自助双录 |

### iOS
| 命令 | 说明 |
|------|------|
| `python test_devices_ios.py` | 客户登录(默认) |
| `python test_devices_ios.py manager` | 客户经理登录 |
| `python test_devices_ios.py 50` | 循环50次 |
| `python test_pure_recording_ios.py self 5` | 客户自助循环5次 |
| `python test_manager_pure_recording_ios.py scene ai 10` | 现场AI双录循环10次 |
| `SCREENSHOT=1 python test.py` | 开启截图 |

### Playwright临柜双录（Windows）
| 命令 | 说明 |
|------|------|
| `python test_dualrecord_ai_lingui.py` | 临柜AI双录 |
| `python test_dualrecord_lingui_manual.py` | 临柜人工双录 |
