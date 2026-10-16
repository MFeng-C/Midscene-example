import express from 'express';
import { createServer } from 'http';
import { Server } from 'socket.io';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { v4 as uuidv4 } from 'uuid';
import { spawn, execSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import http from 'http';
import {
  getTaskById,
  getTaskFailureLogs,
  initializeDatabase,
  listTasks,
  loadInterruptedTasks,
  saveTask
} from './database.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..', '..');
const REPORT_DIR = path.join(__dirname, '..', 'reports');
const DATA_DIR = path.join(__dirname, '..', 'data');
const isWindows = process.platform === 'win32';
const TASK_DETAIL_LOG_LIMIT = 1000;
const SHARED_ROOM = 'dashboard';
const LOG_TIME_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23'
});

if (!fs.existsSync(REPORT_DIR)) {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
}
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

let saveTimer = null;
function saveTasks() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    saveTimer = null;
    try {
      await Promise.all(Array.from(tasks.values()).map(task => saveTask(task)));
    } catch (e) {
      console.error('Save tasks failed:', e.message);
    }
  }, 500);
}

async function loadTasks() {
  try {
    const interruptedTasks = await loadInterruptedTasks();
    for (const task of interruptedTasks) {
      task.status = 'failed';
      if (!task.completedAt) task.completedAt = new Date().toISOString();
      task.logs = task.logs || [];
      appendTaskLog(task, '[ERROR] 服务重启，任务中断');
      tasks.set(task.id, task);
      await saveTask(task);
      tasks.delete(task.id);
    }
    console.log(`Recovered ${interruptedTasks.length} interrupted tasks from MySQL`);
  } catch (e) {
    console.error('Load tasks from MySQL failed:', e.message);
    throw e;
  }
}

const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST', 'DELETE']
  }
});

app.use(express.json());
app.use(express.static(join(__dirname, '..', 'public')));
app.use('/reports', express.static(REPORT_DIR));

const tasks = new Map();
const runningProcesses = new Map();
const userQueues = new Map();

const businessTypes = {
  android: {
    customer: [
      { id: 'customer_self', name: '自助双录', desc: '客户自助双录业务流程' },
      { id: 'customer_record', name: '纯录制', desc: '客户纯录制业务流程' }
    ],
    manager: [
      { id: 'scene_ai', name: '现场双录(AI)', desc: '客户经理现场AI双录业务' },
      { id: 'scene_manual', name: '现场双录(人工)', desc: '客户经理现场人工双录业务' },
      { id: 'record', name: '纯录制', desc: '客户经理纯录制业务流程' }
    ]
  },
  ios: {
    customer: [
      { id: 'customer_self', name: '自助双录', desc: '客户自助双录业务流程' },
      { id: 'customer_record', name: '纯录制', desc: '客户纯录制业务流程' }
    ],
    manager: [
      { id: 'scene_ai', name: '现场双录(AI)', desc: '客户经理现场AI双录业务' },
      { id: 'scene_manual', name: '现场双录(人工)', desc: '客户经理现场人工双录业务' },
      { id: 'record', name: '纯录制', desc: '客户经理纯录制业务流程' }
    ]
  },
  h5: {
    all: [
      { id: 'h5_business_flow', name: 'H5业务流程', desc: 'H5端双录业务流程测试' },
      { id: 'h5_remind_ready', name: 'H5待就绪页', desc: 'H5端同意并开始双录页面测试' }
    ]
  },
  pc: {
    all: [
      { id: 'pc_business_flow', name: 'PC业务流程', desc: 'PC端双录业务流程测试' },
      { id: 'pc_broadcast_speed', name: 'PC播报语速', desc: 'PC端播报语速调节测试' },
      { id: 'pc_node_selection', name: 'PC节点选择', desc: 'PC端节点选择功能测试' }
    ]
  },
  dual: {
    all: [
      { id: 'dual_business_flow', name: 'H5预约双录(AI双录)', desc: 'H5客户 + PC客户经理 AI 双录流程' },
      { id: 'dual_manual_business_flow', name: 'H5预约双录(人工双录)', desc: 'H5客户 + PC客户经理 人工双录流程' }
    ]
  }
};

const platformConfig = {
  android: {
    name: 'Android',
    icon: '🤖',
    workingDir: path.join(ROOT_DIR, 'android'),
    command: 'python',
    getArgs: (config) => {
      const args = ['-u', 'test_jdualrecord_app.py'];
      if (config.businessType) {
        args.push(config.businessType);
      }
      if (config.loops) {
        args.push(config.loops.toString());
      }
      return args;
    },
    deviceCheck: {
      method: 'adb',
      script: 'config.py',
      deviceKey: 'DEVICE_ID'
    }
  },
  ios: {
    name: 'iOS',
    icon: '📱',
    workingDir: path.join(ROOT_DIR, 'ios'),
    command: 'python',
    getArgs: (config) => {
      const args = ['test_jdualrecord_app.py'];
      if (config.businessType) {
        args.push(config.businessType);
      }
      if (config.loops) {
        args.push(config.loops.toString());
      }
      return args;
    },
    deviceCheck: {
      method: 'appium-wda',
      configKeys: ['WDA_URL', 'UDID']
    }
  },
  h5: {
    name: 'H5',
    icon: '🌐',
    workingDir: path.join(ROOT_DIR, 'H5-e2e'),
    command: 'node',
    getArgs: (config) => {
      const caseMap = {
        'h5_business_flow': 'tests/dualrecord-e2e/cases/mobile-browser/h5-business-flow.yaml',
        'h5_remind_ready': 'tests/dualrecord-e2e/cases/mobile-browser/h5-remind-ready.yaml'
      };
      const casePath = caseMap[config.businessType] || caseMap['h5_business_flow'];
      return ['internal/dualrecord-e2e/bin/dualrecord-e2e.mjs', '-c', casePath, '--headed', '--json'];
    },
    deviceCheck: null,
    resetOrderState: {
      command: 'node',
      scriptPath: 'internal/dualrecord-e2e/scripts/reset-order-state.js',
      presetFile: 'local-route-config.example.json',
      presetKey: 'mobile-browser'
    }
  },
  pc: {
    name: 'PC',
    icon: '💻',
    workingDir: path.join(ROOT_DIR, 'H5-e2e'),
    command: 'node',
    getArgs: (config) => {
      const caseMap = {
        'pc_business_flow': 'tests/dualrecord-e2e/cases/pc/pc-business-flow.yaml',
        'pc_broadcast_speed': 'tests/dualrecord-e2e/cases/pc/pc-broadcast-speed.yaml',
        'pc_node_selection': 'tests/dualrecord-e2e/cases/pc/pc-node-selection.yaml'
      };
      const casePath = caseMap[config.businessType] || caseMap['pc_business_flow'];
      return ['internal/dualrecord-e2e/bin/dualrecord-e2e.mjs', '-c', casePath, '--headed', '--json'];
    },
    deviceCheck: null,
    resetOrderState: {
      command: 'node',
      scriptPath: 'internal/dualrecord-e2e/scripts/reset-order-state.js',
      presetFile: 'local-route-config.example.json',
      presetKey: 'pc'
    }
  },
  dual: {
    name: '双端',
    icon: '🔗',
    workingDir: path.join(ROOT_DIR, 'H5-e2e'),
    command: 'node',
    getArgs: (config) => {
      const caseMap = {
        'dual_business_flow': 'tests/dualrecord-e2e/cases/dual/dual-business-flow.yaml',
        'dual_manual_business_flow': 'tests/dualrecord-e2e/cases/dual/dual-manual-business-flow.yaml'
      };
      const casePath = caseMap[config.businessType] || caseMap['dual_business_flow'];
      return [
        'internal/dualrecord-e2e/scripts/run-loop-test.mjs',
        '--count', config.loops.toString(),
        '--interval', '3',
        '--order-id', config.orderId,
        '--case', casePath,
        '--headed'
      ];
    },
    deviceCheck: null,
    orderIdPreset: {
      presetFile: 'dual-route-config.example.json',
      presetKey: 'pc'
    }
  }
};

function createTask(userId, platform, config) {
  const id = uuidv4();
  const businessLabel = getBusinessLabel(platform, config.businessType, config.loginMode);
  const task = {
    id,
    userId,
    platform,
    businessType: config.businessType || null,
    businessLabel,
    status: 'pending',
    config,
    createdAt: new Date().toISOString(),
    startedAt: null,
    completedAt: null,
    logs: [],
    exitCode: null
  };
  tasks.set(id, task);
  return task;
}

function getBusinessLabel(platform, businessType, loginMode) {
  if (!businessType) return '';
  const roleMap = businessTypes[platform];
  if (!roleMap) return businessType;
  const list = roleMap[loginMode] || roleMap.all || [];
  const item = list.find(b => b.id === businessType);
  return item ? item.name : businessType;
}

function formatLogTimestamp(date = new Date()) {
  const parts = Object.fromEntries(
    LOG_TIME_FORMATTER.formatToParts(date)
      .filter(part => part.type !== 'literal')
      .map(part => [part.type, part.value])
  );
  const milliseconds = String(date.getMilliseconds()).padStart(3, '0');
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}.${milliseconds}`;
}

function appendTaskLog(task, message) {
  const logLine = `[${formatLogTimestamp()}] ${String(message).replace(/[\r\n]+$/, '')}`;
  task.logs.push(logLine);
  return logLine;
}

function serializeTask(task, { includeLogs = false } = {}) {
  const { logs = [], ...taskData } = task;
  if (!includeLogs) {
    return {
      ...taskData,
      logCount: logs.length
    };
  }

  const visibleLogs = logs.slice(-TASK_DETAIL_LOG_LIMIT);
  return {
    ...taskData,
    logs: visibleLogs,
    logCount: logs.length,
    logsTruncated: logs.length > visibleLogs.length
  };
}

function parseReportFromLogs(logs, platform, businessLabel, options = {}) {
  const report = {
    platform,
    businessType: businessLabel,
    totalCycles: 0,
    successCount: 0,
    failCount: 0,
    successRate: 0,
    failedCycles: [],
    duration: 0,
    summary: '',
    stepCount: 0,
    assertionCount: 0,
    assertionResults: []
  };

  let e2eResult = null;
  let inSummary = false;
  let summaryLines = [];
  const loopResults = new Map();
  let loopSummary = null;

  for (const line of logs) {
    const cleanLine = line
      .replace(/^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\]\s*/, '')
      .replace(/^\[INFO\]\s*/, '')
      .replace(/^\[ERROR\]\s*/, '');

    const totalMatch = cleanLine.match(/总循环次数[::]\s*(\d+)/);
    if (totalMatch) report.totalCycles = parseInt(totalMatch[1]);

    const successMatch = cleanLine.match(/成功次数[::]\s*(\d+)/);
    if (successMatch) report.successCount = parseInt(successMatch[1]);

    const failMatch = cleanLine.match(/失败次数[::]\s*(\d+)/);
    if (failMatch) report.failCount = parseInt(failMatch[1]);

    const rateMatch = cleanLine.match(/成功率[::]\s*([\d.]+)%/);
    if (rateMatch) report.successRate = parseFloat(rateMatch[1]);

    const failCycleMatch = cleanLine.match(/第\s*(\d+)\s*次测试失败\]?\s*(?:[：:]\s*)?(.+)/);
    if (failCycleMatch) {
      report.failedCycles.push({
        cycle: parseInt(failCycleMatch[1]),
        error: failCycleMatch[2].trim(),
        log: line
      });
    }

    const loopResultMatch = cleanLine.match(/\[loop-test\]\s*第\s*(\d+)\s*轮:\s*(PASS|FAIL)/i);
    if (loopResultMatch) {
      loopResults.set(parseInt(loopResultMatch[1]), loopResultMatch[2].toUpperCase());
    }

    const loopSummaryMatch = cleanLine.match(/\[loop-test\]\s*完成[：:]\s*(\d+)\s*\/\s*(\d+)\s*通过/);
    if (loopSummaryMatch) {
      loopSummary = {
        passed: parseInt(loopSummaryMatch[1]),
        total: parseInt(loopSummaryMatch[2])
      };
    }

    if (cleanLine.includes('测试汇总') || cleanLine.match(/^={5,}/)) {
      inSummary = true;
    }
    if (inSummary) {
      summaryLines.push(cleanLine);
    }

    const trimmed = cleanLine.trim();
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed.status && (
          parsed.stepCount !== undefined ||
          parsed.assertionCount !== undefined ||
          parsed.targets !== undefined // dual case 结构
        )) {
          e2eResult = parsed;
        }
      } catch (e) {
        // 不是 JSON，忽略
      }
    }
  }

  if (loopSummary || loopResults.size > 0) {
    const total = loopSummary?.total || Math.max(...loopResults.keys());
    const passed = loopSummary?.passed || Array.from(loopResults.values()).filter(v => v === 'PASS').length;
    report.totalCycles = total;
    report.successCount = passed;
    report.failCount = Math.max(0, total - passed);
    report.successRate = total > 0 ? Number(((passed / total) * 100).toFixed(1)) : 0;
    for (const [cycle, status] of loopResults) {
      if (status === 'FAIL') report.failedCycles.push({ cycle, error: '该轮双端测试失败' });
    }
    summaryLines.unshift(`循环测试结果: ${passed}/${total} 轮通过`);
  } else if (e2eResult) {
    report.totalCycles = 1;

    // Dual case 结果：status = both_passed / one_failed / both_failed，带 targets 结构
    if (e2eResult.targets && typeof e2eResult.targets === 'object') {
      const targetEntries = Object.entries(e2eResult.targets);
      let totalSteps = 0;
      let totalAssertions = 0;
      let successTargets = 0;
      const allAssertions = [];

      for (const [targetName, targetResult] of targetEntries) {
        const t = targetResult || {};
        totalSteps += (t.stepCount || 0);
        totalAssertions += (t.assertionCount || 0);
        const targetPassed = t.status === 'passed';
        if (targetPassed) successTargets++;
        const targetLabel =
          targetName === 'pc' ? 'PC' :
          targetName === 'mobile-browser' ? 'H5客户端' : targetName;
        summaryLines.push(`[${targetLabel}] 状态: ${t.status || 'unknown'}`);
        if (t.report) {
          summaryLines.push(`[${targetLabel}] 报告: ${JSON.stringify(t.report)}`);
        }
        if (t.error) {
          report.failedCycles.push({ cycle: 1, error: `[${targetLabel}] ${t.error}` });
        }
        if (t.browserResult?.assertionResults) {
          for (const ar of t.browserResult.assertionResults) {
            allAssertions.push({ ...ar, target: targetName });
          }
        }
      }

      report.stepCount = totalSteps;
      report.assertionCount = totalAssertions;
      report.assertionResults = allAssertions;
      const allPassed = successTargets === targetEntries.length;
      report.successCount = allPassed ? 1 : 0;
      report.failCount = allPassed ? 0 : 1;
      report.successRate = allPassed ? 100 : 0;
      summaryLines.unshift(`双端整体状态: ${e2eResult.status} (${successTargets}/${targetEntries.length} 端通过)`);
    } else {
      // 单端 case 结果
      report.stepCount = e2eResult.stepCount || 0;
      report.assertionCount = e2eResult.assertionCount || 0;
      const passed = e2eResult.status === 'passed';
      report.successCount = passed ? 1 : 0;
      report.failCount = passed ? 0 : 1;
      report.successRate = passed ? 100 : 0;
      if (e2eResult.error) {
        report.failedCycles.push({ cycle: 1, error: e2eResult.error });
      }
      if (e2eResult.browserResult?.assertionResults) {
        report.assertionResults = e2eResult.browserResult.assertionResults;
      }
      summaryLines.push(`状态: ${e2eResult.status}`);
      summaryLines.push(`步骤数: ${report.stepCount}`);
      summaryLines.push(`断言数: ${report.assertionCount}`);
      if (e2eResult.report) {
        summaryLines.push(`报告: ${JSON.stringify(e2eResult.report)}`);
      }
    }
  }

  if (report.totalCycles === 0 && report.successCount === 0 && report.failCount === 0) {
    const expectedCycles = Number.isInteger(options.expectedCycles) && options.expectedCycles > 0
      ? options.expectedCycles
      : 1;
    const hasError = logs.some(l =>
      l.includes('[ERROR]') || l.includes('Exception') || l.includes('Error')
    );
    const failed = hasError || (options.exitCode !== undefined && options.exitCode !== 0);
    report.totalCycles = expectedCycles;
    report.failCount = failed ? expectedCycles : 0;
    report.successCount = failed ? 0 : expectedCycles;
    report.successRate = failed ? 0 : 100;
  }

  report.summary = summaryLines.slice(0, 20).join('\n');
  return report;
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function generateReportHtml(task, report) {
  const platConfig = platformConfig[task.platform];
  const startDate = task.startedAt ? new Date(task.startedAt) : new Date();
  const endDate = task.completedAt ? new Date(task.completedAt) : new Date();
  const durationSec = Math.floor((endDate - startDate) / 1000);
  const durationStr = `${Math.floor(durationSec / 60)}分${durationSec % 60}秒`;

  const statusColor = report.failCount === 0 ? '#3fb950' : '#f85149';
  const statusText = report.failCount === 0 ? '通过' : '失败';

  const failedCyclesHtml = report.failedCycles.length > 0
    ? `<div class="section">
         <h3>失败详情</h3>
         <table class="detail-table">
           <thead><tr><th>循环</th><th>错误信息</th></tr></thead>
           <tbody>
             ${report.failedCycles.map(f => `
               <tr>
                 <td class="cycle-col">第 ${f.cycle} 次</td>
                 <td class="error-col">${escapeHtml(f.error)}</td>
               </tr>
             `).join('')}
           </tbody>
         </table>
       </div>`
    : '';

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>测试报告 - ${platConfig.name} - ${report.businessType}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0d1117;
      color: #e6edf3;
      padding: 30px;
      line-height: 1.6;
    }
    .container { max-width: 900px; margin: 0 auto; }
    .header {
      background: linear-gradient(135deg, #161b22 0%, #21262d 100%);
      border-radius: 12px;
      padding: 30px;
      margin-bottom: 24px;
      border: 1px solid #30363d;
    }
    .header h1 { font-size: 24px; margin-bottom: 16px; }
    .status-badge {
      display: inline-block;
      padding: 4px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      background: ${statusColor}22;
      color: ${statusColor};
      border: 1px solid ${statusColor}55;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 10px;
      padding: 20px;
      text-align: center;
    }
    .stat-value { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
    .stat-label { font-size: 13px; color: #8b949e; }
    .stat-total .stat-value { color: #58a6ff; }
    .stat-success .stat-value { color: #3fb950; }
    .stat-fail .stat-value { color: #f85149; }
    .stat-rate .stat-value { color: #a371f7; }
    .section {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 10px;
      padding: 24px;
      margin-bottom: 20px;
    }
    .section h3 { font-size: 16px; margin-bottom: 16px; color: #e6edf3; }
    .info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 24px; }
    .info-item { display: flex; gap: 12px; }
    .info-label { color: #8b949e; min-width: 100px; font-size: 14px; }
    .info-value { color: #e6edf3; font-size: 14px; }
    .detail-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .detail-table th {
      background: #21262d; padding: 10px 14px; text-align: left;
      font-weight: 600; color: #8b949e; border-bottom: 1px solid #30363d;
    }
    .detail-table td { padding: 10px 14px; border-bottom: 1px solid #21262d; }
    .cycle-col { width: 100px; color: #8b949e; }
    .error-col { color: #f85149; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
    .logs-section pre {
      background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
      padding: 16px; font-family: 'JetBrains Mono', Consolas, monospace;
      font-size: 12px; line-height: 1.5; overflow-x: auto;
      max-height: 400px; overflow-y: auto; color: #8b949e;
    }
    .footer { text-align: center; color: #6e7681; font-size: 12px; margin-top: 30px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🧪 自动化测试报告</h1>
      <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
        <span class="status-badge">${statusText}</span>
        <span style="color:#8b949e;">${platConfig.icon} ${platConfig.name} - ${report.businessType || '默认'}</span>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card stat-total">
        <div class="stat-value">${report.totalCycles}</div>
        <div class="stat-label">总循环次数</div>
      </div>
      <div class="stat-card stat-success">
        <div class="stat-value">${report.successCount}</div>
        <div class="stat-label">成功次数</div>
      </div>
      <div class="stat-card stat-fail">
        <div class="stat-value">${report.failCount}</div>
        <div class="stat-label">失败次数</div>
      </div>
      <div class="stat-card stat-rate">
        <div class="stat-value">${report.successRate.toFixed(1)}%</div>
        <div class="stat-label">成功率</div>
      </div>
    </div>

    <div class="section">
      <h3>📋 基本信息</h3>
      <div class="info-grid">
        <div class="info-item">
          <span class="info-label">测试平台</span>
          <span class="info-value">${platConfig.name}</span>
        </div>
        <div class="info-item">
          <span class="info-label">业务类型</span>
          <span class="info-value">${report.businessType || '默认'}</span>
        </div>
        <div class="info-item">
          <span class="info-label">开始时间</span>
          <span class="info-value">${startDate.toLocaleString('zh-CN')}</span>
        </div>
        <div class="info-item">
          <span class="info-label">结束时间</span>
          <span class="info-value">${endDate.toLocaleString('zh-CN')}</span>
        </div>
        <div class="info-item">
          <span class="info-label">执行时长</span>
          <span class="info-value">${durationStr}</span>
        </div>
        <div class="info-item">
          <span class="info-label">任务ID</span>
          <span class="info-value" style="font-family:monospace; font-size:12px;">${task.id.substring(0, 8)}...</span>
        </div>
      </div>
    </div>

    ${failedCyclesHtml}

    <div class="section logs-section">
      <h3>📝 测试日志</h3>
      <pre>${escapeHtml(task.logs.slice(-200).join('\n'))}</pre>
    </div>

    <div class="footer">
      Midscene Test Dashboard - 测试报告自动生成于 ${new Date().toLocaleString('zh-CN')}
    </div>
  </div>
</body>
</html>`;
}

function saveReportFile(task, report) {
  try {
    const dateStr = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const fileName = `${task.platform}_${task.businessType || 'default'}_${dateStr}.html`;
    const filePath = path.join(REPORT_DIR, fileName);
    const html = generateReportHtml(task, report);
    fs.writeFileSync(filePath, html, 'utf-8');
    return `/reports/${fileName}`;
  } catch (e) {
    console.error('保存报告失败:', e.message);
    return null;
  }
}

function checkAndroidDevice() {
  try {
    const androidDir = path.join(ROOT_DIR, 'android');
    const configPath = path.join(androidDir, 'config.py');
    let deviceId = null;
    if (fs.existsSync(configPath)) {
      const content = fs.readFileSync(configPath, 'utf-8');
      const match = content.match(/DEVICE_ID\s*=\s*["']([^"']+)["']/);
      if (match) deviceId = match[1];
    }

    let adbDevices = [];
    try {
      const cmd = isWindows ? 'adb devices' : 'adb devices';
      const output = execSync(cmd, { timeout: 5000, encoding: 'utf-8' });
      const lines = output.trim().split('\n').slice(1);
      adbDevices = lines
        .filter(l => l.trim() && l.includes('\t'))
        .map(l => l.split('\t')[0].trim())
        .filter(id => id);
    } catch (e) {
      adbDevices = [];
    }

    const connected = adbDevices.length > 0;
    const targetConnected = deviceId ? adbDevices.includes(deviceId) : connected;

    return {
      available: targetConnected,
      configured: deviceId ? true : false,
      targetDevice: deviceId,
      connectedDevices: adbDevices,
      message: targetConnected
        ? `设备已连接 (${deviceId || adbDevices[0]})`
        : adbDevices.length > 0
          ? `有 ${adbDevices.length} 个设备连接，但目标设备 ${deviceId} 不在其中`
          : '未检测到 Android 设备，请通过 USB 连接'
    };
  } catch (e) {
    return {
      available: false,
      connectedDevices: [],
      message: '设备检查失败: ' + e.message
    };
  }
}

function checkIOSDevice() {
  return new Promise((resolve) => {
    try {
      const iosDir = path.join(ROOT_DIR, 'ios');
      const configPath = path.join(iosDir, 'config.py');
      let wdaUrl = null;
      let udid = null;
      if (fs.existsSync(configPath)) {
        const content = fs.readFileSync(configPath, 'utf-8');
        const wdaMatch = content.match(/WDA_URL\s*=\s*["']([^"']+)["']/);
        const udidMatch = content.match(/UDID\s*=\s*["']([^"']+)["']/);
        if (wdaMatch) wdaUrl = wdaMatch[1];
        if (udidMatch) udid = udidMatch[1];
      }

      if (!wdaUrl) {
        resolve({
          available: false,
          configured: false,
          wdaUrl: null,
          udid,
          message: '未配置 WDA 地址'
        });
        return;
      }

      let done = false;
      const finish = (available, details = '') => {
        if (done) return;
        done = true;
        resolve({
          available,
          configured: !!(wdaUrl && udid),
          wdaUrl,
          udid,
          message: available
            ? `WDA 服务可用 (${wdaUrl})`
            : `WDA 服务不可用 (${wdaUrl})，请确认设备已连接且 WDA 已启动`,
          details
        });
      };

      try {
        const url = new URL(wdaUrl + '/status');
        const req = http.get(url, (res) => {
          finish(res.statusCode === 200);
        });
        req.on('error', (e) => finish(false, e.message));
        req.setTimeout(4000, () => { req.destroy(); finish(false, 'timeout'); });
      } catch (e) {
        finish(false, e.message);
      }
    } catch (e) {
      resolve({
        available: false,
        message: '设备检查失败: ' + e.message
      });
    }
  });
}

async function checkDevice(platform) {
  if (platform === 'android') {
    return checkAndroidDevice();
  } else if (platform === 'ios') {
    return checkIOSDevice();
  }
  return { available: true, message: '无需设备检查' };
}

function getOrderIdFromPreset(workingDir, presetKey, presetFile) {
  try {
    const presetPath = path.join(workingDir, 'tests', 'dualrecord-e2e', presetFile);
    if (!fs.existsSync(presetPath)) return null;
    const presetData = JSON.parse(fs.readFileSync(presetPath, 'utf8'));
    if (presetData && presetData[presetKey]?.orderId) {
      return presetData[presetKey].orderId;
    }
  } catch (e) {
    console.error('读取预设orderId失败:', e.message);
  }
  return null;
}

function runResetOrderState(task, platConfig) {
  return new Promise((resolve) => {
    const resetConfig = platConfig.resetOrderState;
    if (!resetConfig) {
      resolve({ success: true, skipped: true, message: '无需重置订单' });
      return;
    }
    const orderId = getOrderIdFromPreset(
      platConfig.workingDir,
      resetConfig.presetKey,
      resetConfig.presetFile
    );
    if (!orderId) {
      resolve({ success: true, skipped: true, message: '未在预设中找到orderId，跳过重置' });
      return;
    }
    const scriptPath = path.join(platConfig.workingDir, resetConfig.scriptPath);
    if (!fs.existsSync(scriptPath)) {
      resolve({ success: true, skipped: true, message: `重置脚本不存在: ${scriptPath}，跳过重置` });
      return;
    }
    appendTaskLog(task, `[INFO] 重置订单状态: orderId=${orderId}`);
    const child = spawn(resetConfig.command, [scriptPath, `--orderId=${orderId}`], {
      cwd: platConfig.workingDir,
      env: { ...process.env },
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe']
    });
    runningProcesses.set(task.id, child);
    let output = '';
    child.stdout.on('data', (d) => {
      const text = d.toString();
      output += text;
      const lines = text.split('\n').filter(l => l.trim());
      lines.forEach(line => {
        const logLine = appendTaskLog(task, line);
        io.to(SHARED_ROOM).emit('log:append', {
          taskId: task.id,
          level: 'info',
          message: logLine
        });
      });
    });
    child.stderr.on('data', (d) => {
      const text = d.toString();
      output += text;
      const lines = text.split('\n').filter(l => l.trim());
      lines.forEach(line => {
        const logLine = appendTaskLog(task, line);
        io.to(SHARED_ROOM).emit('log:append', {
          taskId: task.id,
          level: 'warn',
          message: logLine
        });
      });
    });
    child.on('close', (code) => {
      if (runningProcesses.get(task.id) === child) runningProcesses.delete(task.id);
      if (code === 0) {
        resolve({ success: true, message: '订单状态重置成功' });
      } else {
        resolve({ success: false, message: `订单状态重置失败 (code=${code}): ${output.slice(0, 200)}` });
      }
    });
    child.on('error', (err) => {
      resolve({ success: false, message: `重置订单出错: ${err.message}` });
    });
  });
}

async function runTask(task) {
  const platConfig = platformConfig[task.platform];
  if (!platConfig) {
    task.status = 'failed';
    appendTaskLog(task, '[ERROR] Unknown platform: ' + task.platform);
    return;
  }

  task.status = 'running';
  task.startedAt = new Date().toISOString();
  saveTasks();

  appendTaskLog(task, `[INFO] 启动 ${platConfig.name} 测试`);
  appendTaskLog(task, `[INFO] 业务类型: ${task.businessLabel || '默认'}`);

  const executionConfig = { ...task.config };
  if (platConfig.orderIdPreset) {
    executionConfig.orderId = getOrderIdFromPreset(
      platConfig.workingDir,
      platConfig.orderIdPreset.presetKey,
      platConfig.orderIdPreset.presetFile
    );
    if (!executionConfig.orderId) {
      task.status = 'failed';
      task.completedAt = new Date().toISOString();
      appendTaskLog(task, '[ERROR] 双端配置中未找到订单 ID，测试未启动');
      io.to(SHARED_ROOM).emit('task:updated', {
        id: task.id,
        status: task.status,
        completedAt: task.completedAt,
        error: '双端配置中未找到订单 ID'
      });
      saveTasks();
      processNextTask(task.userId);
      return;
    }
    if (!process.env.DUALRECORD_DB_PASSWORD) {
      task.status = 'failed';
      task.completedAt = new Date().toISOString();
      appendTaskLog(task, '[ERROR] 缺少环境变量 DUALRECORD_DB_PASSWORD，无法在每轮测试前重置订单');
      io.to(SHARED_ROOM).emit('task:updated', {
        id: task.id,
        status: task.status,
        completedAt: task.completedAt,
        error: '缺少环境变量 DUALRECORD_DB_PASSWORD'
      });
      saveTasks();
      processNextTask(task.userId);
      return;
    }
  }

  if (platConfig.resetOrderState) {
    const resetResult = await runResetOrderState(task, platConfig);
    if (task.status === 'cancelled') {
      processNextTask(task.userId);
      return;
    }
    appendTaskLog(task, `[INFO] 订单重置: ${resetResult.message}`);
    io.to(SHARED_ROOM).emit('task:updated', {
      id: task.id,
      status: task.status,
      logs: task.logs.slice(-5)
    });
    saveTasks();
    if (!resetResult.success && !resetResult.skipped) {
      appendTaskLog(task, `[WARN] 订单状态重置失败，但仍继续执行测试`);
    }
  }

  const args = platConfig.getArgs(executionConfig);
  appendTaskLog(task, `[INFO] 命令: ${platConfig.command} ${args.join(' ')}`);
  appendTaskLog(task, `[INFO] 工作目录: ${platConfig.workingDir}`);

  const env = { ...process.env, ...platConfig.env };
  if (task.config.loginMode) env.LOGIN_MODE = task.config.loginMode;
  if (task.config.loops) env.LOOPS = task.config.loops.toString();
  env.SCREENSHOT = '0';
  if (task.platform === 'android' || task.platform === 'ios') {
    env.PYTHONIOENCODING = 'utf-8';
    env.PYTHONUTF8 = '1';
  }

  const child = spawn(platConfig.command, args, {
    cwd: platConfig.workingDir,
    env,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  runningProcesses.set(task.id, child);

  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');

  child.stdout.on('data', (data) => {
    const lines = data.toString().split('\n').filter(l => l.trim());
    lines.forEach(line => {
      const logLine = appendTaskLog(task, line);
      io.to(SHARED_ROOM).emit('log:append', {
        taskId: task.id,
        level: 'info',
        message: logLine
      });
    });
  });

  child.stderr.on('data', (data) => {
    const lines = data.toString().split('\n').filter(l => l.trim());
    lines.forEach(line => {
      const trimmed = line.trim();
      const isDualrecordProgress =
        trimmed.startsWith('[dualrecord-e2e]') ||
        trimmed.startsWith('$') ||
        (trimmed.startsWith('[') && /^\[(INFO|WARN|DEBUG)\]/.test(trimmed));
      const hasErrorKeyword = /\b(ERROR|Error|Exception|FAILED|failed|Traceback)\b/.test(trimmed);

      if (isDualrecordProgress && !hasErrorKeyword) {
        const logLine = appendTaskLog(task, line);
        io.to(SHARED_ROOM).emit('log:append', {
          taskId: task.id,
          level: 'info',
          message: logLine
        });
      } else {
        const logLine = appendTaskLog(task, `[ERROR] ${line}`);
        io.to(SHARED_ROOM).emit('log:append', {
          taskId: task.id,
          level: 'error',
          message: logLine
        });
      }
    });
  });

  child.on('close', async (code) => {
    task.exitCode = code;
    task.completedAt = new Date().toISOString();
    runningProcesses.delete(task.id);
    const cancelled = task.status === 'cancelled';
    task.status = cancelled ? 'cancelled' : code === 0 ? 'completed' : 'failed';
    appendTaskLog(task, cancelled ? '[INFO] 用户已手动停止测试，后续循环不再执行' : code === 0 ? '[INFO] 测试完成' : `[ERROR] 测试异常退出 (code=${code})`);

    const report = parseReportFromLogs(task.logs, task.platform, task.businessLabel, {
      expectedCycles: task.config.loops,
      exitCode: code
    });
    const reportUrl = saveReportFile(task, report);
    task.report = report;
    task.reportUrl = reportUrl;

    try {
      await saveTask(task);
      tasks.delete(task.id);
    } catch (error) {
      console.error(`Save completed task ${task.id} failed:`, error.message);
    }

    io.to(SHARED_ROOM).emit('task:updated', {
      id: task.id,
      status: task.status,
      exitCode: task.exitCode,
      completedAt: task.completedAt,
      report: task.report,
      reportUrl: task.reportUrl
    });

    processNextTask(task.userId);
  });

  child.on('error', async (err) => {
    task.status = 'failed';
    task.completedAt = new Date().toISOString();
    appendTaskLog(task, `[ERROR] 进程启动失败: ${err.message}`);
    runningProcesses.delete(task.id);

    try {
      await saveTask(task);
      tasks.delete(task.id);
    } catch (error) {
      console.error(`Save failed task ${task.id} failed:`, error.message);
    }

    io.to(SHARED_ROOM).emit('task:updated', {
      id: task.id,
      status: task.status,
      error: err.message
    });

    processNextTask(task.userId);
  });
}

function enqueueTask(userId, task) {
  if (!userQueues.has(userId)) userQueues.set(userId, []);
  userQueues.get(userId).push(task);
}

function processNextTask(userId) {
  const queue = userQueues.get(userId);
  if (!queue || queue.length === 0) return;
  const nextTask = queue.shift();
  if (nextTask.status === 'pending') runTask(nextTask);
}

app.get('/api/platforms', (req, res) => {
  const platforms = Object.entries(platformConfig).map(([key, config]) => ({
    id: key,
    name: config.name,
    icon: config.icon,
    hasDeviceCheck: !!config.deviceCheck,
    businessTypes: businessTypes[key] || {}
  }));
  res.json(platforms);
});

app.get('/api/devices/:platform', async (req, res) => {
  const { platform } = req.params;
  if (!platformConfig[platform]) {
    return res.status(400).json({ error: 'Invalid platform' });
  }
  try {
    const result = await checkDevice(platform);
    res.json(result);
  } catch (e) {
    res.json({ available: false, message: e.message });
  }
});

app.get('/api/tasks', async (req, res) => {
  try {
    res.json(await listTasks(50));
  } catch (error) {
    res.status(500).json({ error: `查询任务失败: ${error.message}` });
  }
});

app.post('/api/tasks', async (req, res) => {
  const { userId, platform, config } = req.body;
  if (!userId || !platform) return res.status(400).json({ error: 'userId and platform required' });
  if (!platformConfig[platform]) return res.status(400).json({ error: 'Invalid platform' });

  const normalizedConfig = { ...(config || {}) };
  const loops = Number(normalizedConfig.loops ?? 1);
  if (!Number.isInteger(loops) || loops < 1 || loops > 100) {
    return res.status(400).json({ error: 'loops must be an integer between 1 and 100' });
  }
  normalizedConfig.loops = loops;
  normalizedConfig.screenshot = false;

  const task = createTask(userId, platform, normalizedConfig);
  try {
    await saveTask(task);
  } catch (error) {
    tasks.delete(task.id);
    return res.status(500).json({ error: `保存任务失败: ${error.message}` });
  }
  enqueueTask(userId, task);
  io.to(SHARED_ROOM).emit('task:created', task);

  const hasRunning = Array.from(tasks.values()).some(
    t => t.userId === userId && t.status === 'running'
  );
  if (!hasRunning) processNextTask(userId);

  res.json(task);
});

app.delete('/api/tasks/:id', async (req, res) => {
  const { id } = req.params;
  let task;
  try {
    task = tasks.get(id) || await getTaskById(id, TASK_DETAIL_LOG_LIMIT);
  } catch (error) {
    return res.status(500).json({ error: `查询任务失败: ${error.message}` });
  }
  if (!task) return res.status(404).json({ error: 'Task not found' });

  if (task.status === 'running') {
    const child = runningProcesses.get(id);
    task.status = 'cancelled';
    try {
      if (child?.pid && child.exitCode === null) {
        if (process.platform === 'win32') {
          await new Promise((resolve, reject) => {
            const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true });
            let output = '';
            killer.stderr.on('data', data => { output += data; });
            killer.once('error', reject);
            killer.once('close', code => code === 0 || child.exitCode !== null ? resolve() : reject(new Error(output || `taskkill exit ${code}`)));
          });
        } else if (!child.kill('SIGTERM')) {
          throw new Error('无法终止测试进程');
        }
      }
    } catch (error) {
      task.status = 'running';
      return res.status(500).json({ error: `停止测试失败: ${error.message}` });
    }
    task.completedAt = new Date().toISOString();
  } else if (task.status === 'pending') {
    task.status = 'cancelled';
    task.completedAt = new Date().toISOString();
    const queue = userQueues.get(task.userId);
    if (queue) {
      const idx = queue.findIndex(t => t.id === id);
      if (idx !== -1) queue.splice(idx, 1);
    }
  }

  io.to(SHARED_ROOM).emit('task:updated', {
    id: task.id,
    status: task.status,
    completedAt: task.completedAt
  });
  try {
    await saveTask(task);
  } catch (error) {
    return res.status(500).json({ error: `保存停止状态失败: ${error.message}` });
  }
  res.json(task);
});

app.get('/api/tasks/:id', async (req, res) => {
  const { id } = req.params;
  let task;
  try {
    task = await getTaskById(id, TASK_DETAIL_LOG_LIMIT);
  } catch (error) {
    return res.status(500).json({ error: `查询任务失败: ${error.message}` });
  }
  if (!task) return res.status(404).json({ error: 'Task not found' });
  if (Number(task.report?.failCount || 0) > 0) {
    try {
      task.failureLogs = await getTaskFailureLogs(id, 200);
    } catch (error) {
      console.error(`Query failure logs for task ${id} failed:`, error.message);
      task.failureLogs = [];
    }
  }
  res.json(task);
});

io.on('connection', (socket) => {
  console.log('Client connected:', socket.id);

  socket.on('join', async ({ userId }) => {
    socket.join(SHARED_ROOM);
    console.log(`User ${userId} joined shared dashboard`);
    try {
      socket.emit('tasks:list', await listTasks(50));
    } catch (error) {
      socket.emit('tasks:error', { message: `查询任务失败: ${error.message}` });
    }
  });

  socket.on('device:check', async ({ platform }) => {
    const result = await checkDevice(platform);
    socket.emit('device:status', { platform, result });
  });

  socket.on('disconnect', () => {
    console.log('Client disconnected:', socket.id);
  });
});

const PORT = process.env.PORT || 3001;
await initializeDatabase();
await loadTasks();
httpServer.listen(PORT, () => {
  console.log(`Midscene Test Dashboard running at http://localhost:${PORT}`);
});
