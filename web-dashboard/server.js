import express from 'express';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = 3000;

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

const TEST_CONFIGS = {
  android: {
    name: 'Android',
    workingDir: path.join(__dirname, '..', 'android', 'yaml-scripts-demo'),
    command: 'npm',
    args: ['test'],
  },
  ios: {
    name: 'iOS',
    workingDir: path.join(__dirname, '..', 'ios', 'yaml-scripts-demo'),
    command: 'npm',
    args: ['test'],
  },
  playwright: {
    name: '临柜 (Playwright)',
    workingDir: path.join(__dirname, '..', 'playwright-demo'),
    command: 'npm',
    args: ['test'],
  },
  h5: {
    name: 'H5 (远程预约)',
    workingDir: path.join(__dirname, '..', 'H5-e2e'),
    command: 'pnpm',
    args: ['e2e'],
  }
};

app.get('/api/terminals', (req, res) => {
  const terminals = Object.entries(TEST_CONFIGS).map(([id, config]) => ({
    id,
    name: config.name
  }));
  res.json({ terminals });
});

app.get('/api/scenarios', (req, res) => {
  const { terminal } = req.query;
  const config = TEST_CONFIGS[terminal];
  if (!config) return res.status(400).json({ error: 'Invalid terminal' });

  const scenariosDir = path.join(config.workingDir, 'midscene-scripts');
  const scenarios = [];

  try {
    if (fs.existsSync(scenariosDir)) {
      const files = fs.readdirSync(scenariosDir);
      for (const file of files) {
        if (file.endsWith('.yaml') || file.endsWith('.yml')) {
          scenarios.push({
            id: file.replace(/\.(yaml|yml)$/, ''),
            name: file.replace(/\.(yaml|yml)$/, '').replace(/-/g, ' '),
            file: file
          });
        }
      }
    }
  } catch (err) {
    console.error('Error reading scenarios:', err);
  }

  if (scenarios.length === 0) {
    scenarios.push({ id: 'default', name: '默认场景', file: null });
  }

  res.json({ scenarios });
});

let currentProcess = null;

app.get('/api/run-test', (req, res) => {
  const { terminal, scenario } = req.query;
  const config = TEST_CONFIGS[terminal];
  if (!config) return res.status(400).json({ error: 'Invalid terminal' });

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const sendEvent = (data) => {
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  };

  if (currentProcess) {
    sendEvent({ type: 'info', message: '正在终止之前的测试...' });
    currentProcess.kill('SIGTERM');
    setTimeout(() => {
      if (currentProcess) {
        currentProcess.kill('SIGKILL');
        currentProcess = null;
      }
      startTest();
    }, 1000);
  } else {
    startTest();
  }

  function startTest() {
    sendEvent({ type: 'info', message: `开始执行: ${config.name} - ${scenario || '默认场景'}` });
    sendEvent({ type: 'info', message: `工作目录: ${config.workingDir}` });

    let args = [...config.args];
    if (terminal === 'h5' && scenario) {
      const casePath = path.join(config.workingDir, '..', 'tests', 'dualrecord-e2e', 'cases', 'single', `${scenario}.yaml`);
      args = ['e2e', '-c', casePath, '--headless'];
    }

    sendEvent({ type: 'info', message: `执行命令: ${config.command} ${args.join(' ')}` });

    currentProcess = spawn(config.command, args, {
      cwd: config.workingDir,
      env: process.env,
      shell: true
    });

    currentProcess.stdout.on('data', (data) => {
      sendEvent({ type: 'stdout', message: data.toString() });
    });

    currentProcess.stderr.on('data', (data) => {
      sendEvent({ type: 'stderr', message: data.toString() });
    });

    currentProcess.on('close', (code) => {
      sendEvent({
        type: 'exit',
        code,
        message: code === 0 ? '测试执行完成 ✓' : `测试执行结束，退出码: ${code}`
      });
      currentProcess = null;
    });

    currentProcess.on('error', (err) => {
      sendEvent({ type: 'error', message: `执行错误: ${err.message}` });
      currentProcess = null;
    });
  }

  const keepAlive = setInterval(() => {
    res.write(': keepalive\n\n');
  }, 30000);

  req.on('close', () => {
    clearInterval(keepAlive);
    if (currentProcess) {
      currentProcess.kill('SIGTERM');
      currentProcess = null;
    }
  });
});

app.post('/api/stop-test', (req, res) => {
  if (currentProcess) {
    currentProcess.kill('SIGTERM');
    currentProcess = null;
    res.json({ success: true, message: '测试已停止' });
  } else {
    res.json({ success: false, message: '没有正在运行的测试' });
  }
});

app.listen(PORT, () => {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║           双录自动化测试仪表盘 (Test Dashboard)              ║
╠════════════════════════════════════════════════════════════╣
║  📱 Android  - Android 设备自动化测试                        ║
║  📱 iOS      - iOS 设备自动化测试                            ║
║  💻 临柜    - Playwright 网页自动化测试                      ║
║  🌐 H5      - 远程预约双录自动化测试                         ║
╠════════════════════════════════════════════════════════════╣
║  🌐 Dashboard: http://localhost:${PORT}                        ║
╚════════════════════════════════════════════════════════════╝
  `);
});
