# 自动化测试管理平台 - 技术架构

## 1. 系统概述

Midscene 测试调度平台是一个基于 Node.js 的 Web 应用，用于统一管理和调度 Android、iOS、H5、PC 四个端的自动化测试脚本。

## 2. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | Express.js | HTTP 服务器 |
| 实时通信 | Socket.IO | WebSocket 封装 |
| 进程管理 | child_process | 执行 Python/Node 脚本 |
| 前端 | 原生 HTML/CSS/JS | 轻量级、无框架依赖 |

## 3. 模块设计

### 3.1 服务器模块 (server/index.js)

```
职责：
- 初始化 Express 和 Socket.IO
- 管理 HTTP API 路由
- 处理 Socket.IO 连接事件
- 协调任务队列和执行器

端口：3000
```

### 3.2 任务队列模块 (server/taskQueue.js)

```javascript
class TaskQueue {
  // 状态：pending | running | completed | failed | cancelled
  // 每个用户独立的队列
  // FIFO 调度
}
```

### 3.3 测试执行器 (server/runner.js)

```
职责：
- 根据终端类型选择执行命令
- 设置环境变量
- 捕获 stdout/stderr
- 通过 Socket.IO 推送实时日志
- 更新任务状态
```

| 终端 | 执行命令 |
|------|----------|
| Android | python test_jdualrecord_app.py |
| iOS | python test_devices_ios.py |
| H5 | pnpm --filter H5-e2e test |
| PC | pnpm --filter playwright-demo test |

## 4. 数据模型

### 4.1 Task

```typescript
interface Task {
  id: string;           // UUID
  userId: string;       // 用户标识
  platform: 'android' | 'ios' | 'h5' | 'pc';
  status: TaskStatus;
  config: TaskConfig;
  createdAt: Date;
  startedAt?: Date;
  completedAt?: Date;
  logs: string[];
  exitCode?: number;
}

type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

interface TaskConfig {
  loops?: number;       // 循环次数
  loginMode?: 'customer' | 'manager';
  screenshot?: boolean;
}
```

## 5. Socket.IO 协议

### 5.1 客户端 → 服务器

| 事件 | payload | 描述 |
|------|---------|------|
| join | { userId } | 用户加入房间 |
| task:create | TaskConfig | 创建新任务 |

### 5.2 服务器 → 客户端

| 事件 | payload | 描述 |
|------|---------|------|
| task:created | Task | 新任务信息 |
| task:updated | { id, status, ... } | 任务状态更新 |
| log:append | { taskId, level, message } | 日志追加 |
| task:completed | { id, exitCode } | 任务完成 |

## 6. 安全考虑

- 用户通过 sessionId 识别，不涉及认证
- 每个用户只能操作自己的任务
- 执行命令路径限制在项目目录内

## 7. 部署

```bash
cd test-dashboard
npm install
npm start
```

访问 http://localhost:3000
