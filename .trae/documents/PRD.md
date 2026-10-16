# 自动化测试管理平台 PRD

## 1. 概述与目标

**产品名称**：Midscene 测试调度平台

**核心价值**：统一管理 Android、iOS、H5、PC 四个端的自动化测试脚本，支持团队成员多人并发使用，提供实时的测试状态监控和结果查看。

**目标用户**：测试团队成员，需要在不同终端上运行自动化回归测试。

---

## 2. 功能需求

### 2.1 终端选择与配置

| 终端 | 测试脚本 | 入口 | 技术栈 |
|------|----------|------|--------|
| Android | test_jdualrecord_app.py | android/ | Python + uiautomator2 |
| iOS | test_devices_ios.py | ios/ | Python + Appium |
| H5 | H5-e2e/playwright | H5-e2e/ | Node.js + Playwright |
| PC | playwright-demo | playwright-demo/ | Node.js + Playwright |

### 2.2 核心功能

1. **终端选择面板**
   - 四个终端的卡片式展示
   - 点击选择要执行的终端
   - 显示每个终端的最后运行状态

2. **测试配置**
   - 循环次数配置
   - 登录模式选择（customer/manager）
   - 截图开关

3. **任务队列**
   - 提交测试任务到队列
   - 任务状态：排队中、运行中、已完成、失败
   - 取消正在运行的任务

4. **实时日志**
   - WebSocket 实时推送日志
   - 分颜色显示：INFO（白）、WARNING（黄）、ERROR（红）

5. **历史记录**
   - 最近 50 条测试记录
   - 显示：终端类型、开始时间、时长、状态

### 2.3 多用户支持

- 基于 Session 的用户识别
- 每个用户的任务独立排队
- 用户只能查看和操作自己的任务

---

## 3. 技术架构

### 3.1 技术栈

- **后端**：Node.js + Express
- **前端**：原生 HTML/CSS/JavaScript（避免框架复杂性）
- **实时通信**：WebSocket（Socket.IO）
- **进程管理**：child_process 执行 Python/Node 脚本

### 3.2 项目结构

```
test-dashboard/
├── server/
│   ├── index.js          # Express + Socket.IO 服务器
│   ├── runner.js         # 测试脚本执行器
│   └── taskQueue.js      # 任务队列管理
├── public/
│   ├── index.html        # 主页面
│   ├── css/
│   │   └── style.css     # 样式
│   └── js/
│       └── app.js        # 前端逻辑
├── package.json
└── README.md
```

### 3.3 API 设计

| 端点 | 方法 | 描述 |
|------|------|------|
| /api/tasks | GET | 获取当前用户任务列表 |
| /api/tasks | POST | 创建新任务 |
| /api/tasks/:id | DELETE | 取消任务 |
| /api/tasks/:id | GET | 获取任务详情和日志 |

### 3.4 Socket.IO 事件

| 事件 | 方向 | 描述 |
|------|------|------|
| task:created | Server→Client | 新任务创建 |
| task:updated | Server→Client | 任务状态更新 |
| log:append | Server→Client | 日志追加 |

---

## 4. 页面设计

### 4.1 布局

- 顶部导航栏（标题 + 用户信息）
- 左侧：终端选择面板（4个卡片）
- 右侧：任务列表 + 日志区域
- 底部：状态栏

### 4.2 视觉风格

- 深色科技风格，符合测试平台定位
- 终端卡片带图标和状态指示灯
- 日志区 terminal 风格，等宽字体
