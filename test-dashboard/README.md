# Midscene 测试调度平台

> 统一管理 Android / iOS / H5 / PC 四端自动化测试的 Web 调度平台

## 一、项目概述

Midscene 测试调度平台是一个基于 Web 的自动化测试任务管理系统，将原本分散在四个终端（Android、iOS、H5、PC）的测试脚本整合到统一的可视化界面中，支持团队多人同时使用、任务排队、实时日志查看和测试报告自动生成。

## 二、功能概要

### 2.1 终端支持

| 终端 | 技术栈 | 测试脚本 |
|------|--------|----------|
| 🤖 Android | Python + uiautomator2 | `android/test_jdualrecord_app.py` |
| 📱 iOS | Python + Appium | `ios/test_*.py` |
| 🌐 H5 | Playwright | `H5-e2e/` |
| 💻 PC | Playwright | `playwright-demo/` |

### 2.2 核心功能

- **多终端统一调度**：在一个页面上选择不同终端的测试脚本并执行
- **角色与业务类型细分**：
  - 客户端：自助双录、纯录制
  - 客户经理端：现场双录(AI/人工)、纯录制
- **设备连接检查**：一键检测 Android/iOS 设备连接状态
- **任务队列管理**：支持多人同时提交任务，按用户独立排队
- **实时日志推送**：测试过程中日志实时展示
- **测试报告自动生成**：任务完成后自动解析日志生成结构化报告
- **历史报告归档**：HTML 格式报告持久化保存，可随时查看

### 2.3 用户系统

- 基于 localStorage 的用户标识（自动生成匿名用户ID）
- 按用户隔离任务队列和日志视图
- 支持多人同时操作，互不干扰

## 三、技术架构

### 3.1 技术栈

```
┌─────────────────────────────────────────────┐
│                  前端 (Browser)               │
│  HTML5 + CSS3 + 原生 JavaScript + Socket.IO  │
└──────────────────────┬──────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────┴──────────────────────┐
│              后端 (Node.js)                   │
│  Express + Socket.IO + child_process         │
└──────────────────────┬──────────────────────┘
                       │ spawn
┌──────────────────────┴──────────────────────┐
│           测试脚本 (Python/Node.js)           │
│  uiautomator2 / Appium / Playwright          │
└─────────────────────────────────────────────┘
```

### 3.2 目录结构

```
test-dashboard/
├── server/
│   └── index.js          # 后端服务主文件
├── public/
│   ├── index.html        # 前端页面
│   ├── css/style.css     # 样式文件
│   └── js/app.js         # 前端逻辑
├── reports/              # 测试报告存储目录
└── package.json
```

## 四、实现原理

### 4.1 后端核心流程

#### 4.1.1 任务生命周期

```
用户提交任务 → 加入用户队列 → 等待调度 → 执行子进程 → 实时推送日志 → 完成/失败 → 生成报告
```

1. **任务提交**：用户通过 REST API `POST /api/tasks` 提交任务，后端生成唯一任务ID，加入对应用户的等待队列
2. **任务调度**：每个用户维护独立的任务队列，按 FIFO 顺序调度执行
3. **进程管理**：使用 `child_process.spawn` 启动测试脚本子进程，通过 stdout/stderr 捕获输出
4. **实时推送**：子进程每一行输出都通过 Socket.IO 实时推送到前端
5. **结果处理**：子进程退出时解析 exit code，生成测试报告，更新任务状态

#### 4.1.2 关键数据结构

```javascript
// 任务对象
{
  id: "uuid",           // 任务唯一ID
  userId: "user_xxx",   // 所属用户ID
  platform: "android",  // 终端类型
  businessLabel: "纯录制", // 业务类型标签
  status: "pending",    // pending/running/completed/failed/cancelled
  config: { ... },      // 测试配置
  logs: [],             // 日志数组
  report: { ... },      // 测试报告
  createdAt: "...",     // 创建时间
  startedAt: "...",     // 开始时间
  completedAt: "..."    // 完成时间
}
```

#### 4.1.3 设备检查机制

- **Android**：执行 `adb devices` 命令，解析输出判断设备是否在线
- **iOS**：向 WDA (WebDriverAgent) 发送 HTTP 请求 `GET /status`，判断服务是否可用

### 4.2 前端核心流程

#### 4.2.1 状态管理

前端使用简单的全局 `state` 对象管理状态：

```javascript
const state = {
  socket: null,            // Socket.IO 连接
  userId: null,            // 当前用户ID
  selectedPlatform: null,  // 选中的终端
  selectedRole: 'customer',// 选中的角色
  selectedBusinessType: null, // 选中的业务类型
  platforms: [],           // 平台配置列表
  tasks: [],               // 任务列表
  currentTaskId: null,     // 当前查看的任务ID
  autoScroll: true         // 日志自动滚动
};
```

#### 4.2.2 实时通信

使用 Socket.IO 实现双向实时通信：

| 事件 | 方向 | 说明 |
|------|------|------|
| `join` | 客户端→服务端 | 用户加入房间 |
| `tasks:list` | 服务端→客户端 | 推送用户任务列表 |
| `task:created` | 服务端→客户端 | 新任务创建通知 |
| `task:updated` | 服务端→客户端 | 任务状态更新 |
| `log:append` | 服务端→客户端 | 实时日志推送 |
| `device:status` | 服务端→客户端 | 设备检查结果 |

### 4.3 测试报告生成

#### 4.3.1 报告解析逻辑

任务完成后，`parseReportFromLogs` 函数从日志中提取关键信息：

- 从"总循环次数"、"成功次数"、"失败次数"、"成功率"等关键字行提取统计数据
- 收集失败循环的错误信息，生成失败详情列表
- 计算成功率百分比

#### 4.3.2 报告存储

- 报告以 HTML 格式保存到 `test-dashboard/reports/` 目录
- 文件名格式：`{platform}_{businessType}_{timestamp}.html`
- 通过 `/reports` 静态路由提供访问

## 五、API 接口

### 5.1 REST 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/platforms` | 获取平台配置列表 |
| GET | `/api/devices/:platform` | 检查指定平台设备连接状态 |
| GET | `/api/tasks?userId=xxx` | 获取用户任务列表 |
| POST | `/api/tasks` | 提交新任务 |
| DELETE | `/api/tasks/:id?userId=xxx` | 取消/删除任务 |

### 5.2 Socket.IO 事件

参见 4.2.2 节。

## 六、部署与运行

### MySQL 任务存储

调度平台使用 MySQL 持久化任务和运行日志，不再把 `data/tasks.json` 作为运行时数据源：

- `test_dashboard_tasks`：任务配置、状态、时间和报告摘要
- `test_dashboard_task_logs`：按任务和序号保存运行日志

数据库连接通过环境变量配置：

```powershell
$env:TEST_DASHBOARD_DB_HOST = '192.168.18.223'
$env:TEST_DASHBOARD_DB_PORT = '3306'
$env:TEST_DASHBOARD_DB_USER = 'kiwi'
$env:TEST_DASHBOARD_DB_NAME = 'test'
$env:TEST_DASHBOARD_DB_PASSWORD = '<数据库密码>'
```

首次迁移历史 JSON 数据：

```powershell
npm run migrate:mysql
```

迁移脚本可重复执行，通过任务主键和日志序号避免重复数据。迁移完成并校验任务数、日志数后，原 `data/tasks.json` 仅作为备份保留。

### 6.1 环境要求

- Node.js >= 16
- Python 3.x（运行 Android/iOS 测试脚本）
- ADB（Android 测试）
- Appium + WDA（iOS 测试）

### 6.2 启动服务

```bash
cd test-dashboard
npm install
npm start
```

服务默认运行在 `http://localhost:3001`

### 6.3 配置说明

- **端口配置**：修改 `server/index.js` 末尾的 `PORT` 变量
- **Android 设备**：修改 `android/config.py` 中的 `DEVICE_ID`
- **iOS 配置**：修改 `ios/config_*.py` 中的 Appium/WDA 地址
- **数据库配置**：修改 `android/config.py` 中的数据库连接信息

## 七、扩展指南

### 7.1 新增终端类型

1. 在 `server/index.js` 的 `platformConfig` 中添加新平台配置
2. 在 `public/index.html` 中添加对应的平台卡片
3. 实现对应的设备检查逻辑（如需要）

### 7.2 新增业务类型

1. 在 `server/index.js` 的 `businessTypes` 中添加对应平台的业务类型
2. 测试脚本中添加对应的命令行参数处理逻辑

### 7.3 自定义报告模板

修改 `server/index.js` 中的 `generateReportHtml` 函数，调整报告的 HTML 结构和样式。
