// === State ===
const state = {
  socket: null,
  userId: null,
  selectedPlatform: null,
  selectedRole: 'customer',
  selectedBusinessType: null,
  platforms: [],
  tasks: [],
  currentTaskId: null,
  autoScroll: true
};

const MAX_RENDERED_LOG_LINES = 1001;

// === DOM Elements ===
const elements = {
  userId: document.getElementById('userId'),
  connectionStatus: document.getElementById('connectionStatus'),
  platformCards: document.querySelectorAll('.platform-card'),
  configPanel: document.getElementById('configPanel'),
  configLoops: document.getElementById('configLoops'),
  btnRun: document.getElementById('btnRun'),
  tasksList: document.getElementById('tasksList'),
  logContent: document.getElementById('logContent'),
  logViewer: document.getElementById('logViewer'),
  btnClearLog: document.getElementById('btnClearLog'),
  btnAutoScroll: document.getElementById('btnAutoScroll'),
  btnRefresh: document.getElementById('btnRefresh'),
  queueInfo: document.getElementById('queueInfo'),
  serverTime: document.getElementById('serverTime'),
  roleTabs: document.getElementById('roleTabs'),
  businessTypes: document.getElementById('businessTypes'),
  businessTypeGroup: document.getElementById('businessTypeGroup'),
  roleGroup: document.getElementById('roleGroup'),
  deviceStatusBar: document.getElementById('deviceStatusBar'),
  deviceStatusIcon: document.getElementById('deviceStatusIcon'),
  deviceStatusTitle: document.getElementById('deviceStatusTitle'),
  deviceStatusMsg: document.getElementById('deviceStatusMsg'),
  reportPanel: document.getElementById('reportPanel'),
  reportTotal: document.getElementById('reportTotal'),
  reportSuccess: document.getElementById('reportSuccess'),
  reportFail: document.getElementById('reportFail'),
  reportFailButton: document.getElementById('reportFailButton'),
  reportRate: document.getElementById('reportRate'),
  reportLink: document.getElementById('reportLink'),
  reportFailures: document.getElementById('reportFailures'),
  reportFailuresList: document.getElementById('reportFailuresList'),
  reportFailuresClose: document.getElementById('reportFailuresClose')
};

// === Utilities ===
function formatTime(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

function formatDuration(start, end) {
  if (!start) return '';
  const startTime = new Date(start);
  const endTime = end ? new Date(end) : new Date();
  const elapsed = endTime - startTime;
  if (!Number.isFinite(elapsed)) return '';
  const seconds = Math.max(0, Math.floor(elapsed / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return [hours, minutes, secs].map(value => String(value).padStart(2, '0')).join(':');
}

function getPlatformIcon(platform) {
  const icons = { android: '🤖', ios: '📱', h5: '🌐', pc: '💻' };
  return icons[platform] || '📦';
}

function getStatusText(status) {
  const texts = {
    pending: '测试中',
    running: '测试中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  };
  return texts[status] || status;
}

// === Platform Config ===
function getPlatformConfig(platform) {
  return state.platforms.find(p => p.id === platform);
}

function getBusinessList(platform, role) {
  const p = getPlatformConfig(platform);
  if (!p) return [];
  const bts = p.businessTypes || {};
  return bts[role] || bts.all || [];
}

// === Device Check ===
function checkDevice(platform) {
  const btn = document.getElementById('deviceCheck-' + platform);
  if (btn) {
    btn.textContent = '⏳ 检查中';
    btn.classList.add('checking');
  }

  updateDeviceStatusBar(platform, 'checking', '设备检查中...');

  if (state.socket && state.socket.connected) {
    state.socket.emit('device:check', { platform });
  } else {
    fetch('/api/devices/' + platform)
      .then(res => res.json())
      .then(result => handleDeviceStatus(platform, result))
      .catch(err => updateDeviceStatusBar(platform, 'unavailable', '检查失败: ' + err.message));
  }
}

function handleDeviceStatus(platform, result) {
  const btn = document.getElementById('deviceCheck-' + platform);
  if (btn) {
    btn.textContent = result.available ? '✅ 已连接' : '❌ 未连接';
    btn.classList.remove('checking');
  }

  const statusClass = result.available ? 'available' : 'unavailable';
  const statusTitle = result.available ? '设备已连接' : '设备未连接';
  const statusMessage = platform === 'ios' && result.available
    ? `WDA 地址：${result.wdaUrl}` : result.message;
  updateDeviceStatusBar(platform, statusClass, statusTitle, statusMessage);
  if (platform === 'ios') {
    document.getElementById('wdaSettingsMessage').textContent = result.available
      ? 'WDA 连接正常，设备检测通过。'
      : 'WDA 连接失败，请检查地址、网络及手机上的 WDA 服务。';
  }
}

function updateDeviceStatusBar(platform, statusClass, title, msg = '') {
  const bar = elements.deviceStatusBar;
  const icon = platform === 'android' ? '🤖' : platform === 'ios' ? '📱' : '💻';

  bar.style.display = 'flex';
  bar.className = 'device-status-bar ' + statusClass;
  elements.deviceStatusIcon.textContent = icon;
  elements.deviceStatusTitle.textContent = title;
  elements.deviceStatusMsg.textContent = msg || '';
}

// === Platform Selection ===
function selectPlatform(platform) {
  document.getElementById('wdaSettings').style.display = platform === 'ios' ? 'block' : 'none';
  if (platform === 'ios') loadWdaSettings();
  state.selectedPlatform = platform;
  state.selectedBusinessType = null;

  elements.platformCards.forEach(card => {
    card.classList.toggle('selected', card.dataset.platform === platform);
  });

  elements.configPanel.classList.add('active');

  const p = getPlatformConfig(platform);
  const bts = p?.businessTypes || {};

  // Show/hide role tabs
  const hasRoles = bts.customer && bts.manager;
  elements.roleGroup.style.display = hasRoles ? 'flex' : 'none';
  elements.businessTypeGroup.style.display = (bts.customer || bts.manager || bts.all) ? 'flex' : 'none';

  // Ensure selectedRole is valid for this platform
  const validRoles = [];
  if (bts.customer) validRoles.push('customer');
  if (bts.manager) validRoles.push('manager');
  if (bts.all) validRoles.push('all');
  if (!validRoles.includes(state.selectedRole)) {
    // Pick the first valid role, default priority: customer > manager > all
    state.selectedRole = validRoles[0] || 'customer';
  }

  renderRoleTabs();
  renderBusinessTypes();
  updateRunButton();
}

async function loadWdaSettings() {
  try {
    const response = await fetch('/api/settings/wda');
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '读取失败');
    document.getElementById('wdaAddress').value = result.wdaUrl;
  } catch (error) {
    document.getElementById('wdaSettingsMessage').textContent = error.message;
  }
}

document.getElementById('wdaSave').addEventListener('click', async () => {
  const button = document.getElementById('wdaSave');
  const message = document.getElementById('wdaSettingsMessage');
  button.disabled = true;
  try {
    const response = await fetch('/api/settings/wda', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wdaUrl: document.getElementById('wdaAddress').value })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '保存失败');
    document.getElementById('wdaAddress').value = result.wdaUrl;
    message.textContent = '地址已保存，正在检测连接…';
    checkDevice('ios');
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

function renderRoleTabs() {
  const tabs = elements.roleTabs.querySelectorAll('.role-tab');
  const platform = state.selectedPlatform;
  const p = getPlatformConfig(platform);
  const bts = p?.businessTypes || {};

  tabs.forEach(tab => {
    const role = tab.dataset.role;
    const hasRole = bts[role];
    tab.style.display = hasRole ? 'flex' : 'none';
    tab.classList.toggle('active', role === state.selectedRole);
  });
}

function selectRole(role) {
  state.selectedRole = role;
  state.selectedBusinessType = null;
  renderRoleTabs();
  renderBusinessTypes();
  updateRunButton();
}

function renderBusinessTypes() {
  const list = getBusinessList(state.selectedPlatform, state.selectedRole);
  const container = elements.businessTypes;

  if (list.length === 0) {
    container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);">该平台无业务类型配置</div>';
    return;
  }

  // Auto-select first
  if (!state.selectedBusinessType || !list.find(b => b.id === state.selectedBusinessType)) {
    state.selectedBusinessType = list[0].id;
  }

  container.innerHTML = list.map(item => `
    <div class="business-type-item ${item.id === state.selectedBusinessType ? 'selected' : ''}"
         data-id="${item.id}">
      <div class="business-type-name">${item.name}</div>
      <div class="business-type-desc">${item.desc || ''}</div>
    </div>
  `).join('');

  container.querySelectorAll('.business-type-item').forEach(el => {
    el.addEventListener('click', () => {
      state.selectedBusinessType = el.dataset.id;
      renderBusinessTypes();
      updateRunButton();
    });
  });

  updateRunButton();
}

function updateRunButton() {
  const hasSelection = state.selectedPlatform && state.selectedBusinessType;
  const hasActiveTask = state.tasks.some(t =>
    t.platform === state.selectedPlatform &&
    (t.status === 'running' || t.status === 'pending')
  );
  elements.btnRun.disabled = !hasSelection || hasActiveTask;
  if (hasActiveTask) {
    elements.btnRun.textContent = '⏳ 测试进行中';
  } else {
    elements.btnRun.textContent = '▶ 开始测试';
  }
}

// === Task Management ===
function renderTasks() {
  if (state.tasks.length === 0) {
    elements.tasksList.innerHTML = `
      <div class="empty-state">
        <p>暂无测试任务</p>
        <p class="empty-hint">请从左侧选择一个终端开始测试</p>
      </div>
    `;
    return;
  }

  elements.tasksList.innerHTML = state.tasks.map(task => `
    <div class="task-item ${task.id === state.currentTaskId ? 'selected' : ''} ${task.status === 'running' ? 'running' : ''}"
         data-task-id="${task.id}">
      <div class="task-main">
        <span class="task-icon">${getPlatformIcon(task.platform)}</span>
        <span class="task-platform">${task.platform.toUpperCase()}</span>
        ${task.businessLabel ? `<span class="task-business">${task.businessLabel}</span>` : ''}
        <span class="task-business task-loops" title="任务配置的循环次数">循环 ${Number.isInteger(Number(task.config?.loops)) && Number(task.config.loops) > 0 ? Number(task.config.loops) : 1} 次</span>
        <span class="task-time">开始：${formatTime(task.startedAt || task.createdAt)}</span>
        ${task.completedAt ? `<span class="task-time task-completed-time">结束：${formatClientLogTimestamp(new Date(task.completedAt)).slice(0, 19)}</span>` : ''}
      </div>
      <div class="task-info">
        <span class="task-status ${task.status}">${getStatusText(task.status)}</span>
        <span class="task-duration">${formatDuration(task.startedAt, task.completedAt)}</span>
      </div>
      <div class="task-actions">
        ${task.status === 'running' || task.status === 'pending' ?
          `<button class="btn btn-cancel" data-task-id="${task.id}" title="停止当前测试及后续循环">${task.status === 'running' ? '■ 停止测试' : '取消排队'}</button>` :
          `<button class="btn btn-icon" data-task-id="${task.id}" title="查看日志">📋</button>`
        }
      </div>
    </div>
  `).join('');

  elements.tasksList.querySelectorAll('.btn-cancel').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      cancelTask(btn.dataset.taskId);
    });
  });

  elements.tasksList.querySelectorAll('.task-item').forEach(item => {
    item.addEventListener('click', () => {
      viewTaskLog(item.dataset.taskId);
    });
  });
}

function updatePlatformStatus() {
  ['android', 'ios', 'h5', 'pc'].forEach(platform => {
    const statusEl = document.getElementById('status-' + platform);
    const runningTask = state.tasks.find(t => t.platform === platform && t.status === 'running');
    const pendingTask = state.tasks.find(t => t.platform === platform && t.status === 'pending');

    if (runningTask) {
      statusEl.innerHTML = '<span class="status-indicator running"></span> 测试中';
    } else if (pendingTask) {
      statusEl.innerHTML = '<span class="status-indicator pending"></span> 测试中';
    } else {
      statusEl.innerHTML = '<span class="status-indicator idle"></span> 空闲';
    }
  });
}

function updateQueueInfo() {
  const pending = state.tasks.filter(t => t.status === 'pending').length;
  const running = state.tasks.filter(t => t.status === 'running').length;
  elements.queueInfo.textContent = `队列: ${pending + running} 个测试中`;
}

// === Report Viewer ===
function showReport(task) {
  if (!task || !task.report) {
    elements.reportPanel.style.display = 'none';
    return;
  }

  const r = task.report;
  elements.reportPanel.style.display = 'block';
  elements.reportTotal.textContent = r.totalCycles || 0;
  elements.reportSuccess.textContent = r.successCount || 0;
  elements.reportFail.textContent = r.failCount || 0;
  elements.reportRate.textContent = (r.successRate || 0) + '%';
  renderFailureLogs(task);
  
  if (task.reportUrl) {
    elements.reportLink.href = task.reportUrl;
    elements.reportLink.style.display = 'inline-block';
  } else {
    elements.reportLink.style.display = 'none';
  }
}

function hideReport() {
  elements.reportPanel.style.display = 'none';
  elements.reportFailures.hidden = true;
  elements.reportFailButton.setAttribute('aria-expanded', 'false');
}

function getFailureLogs(task) {
  const normalizeFailure = (value, fallbackTime = null) => {
    const rawMessage = typeof value === 'string' ? value : String(value?.message || '');
    const timestampMatch = rawMessage.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]\s*/);
    return {
      message: timestampMatch ? rawMessage.slice(timestampMatch[0].length) : rawMessage,
      timestamp: timestampMatch?.[1] || formatFailureTimestamp(value?.createdAt || fallbackTime)
    };
  };

  const structured = Array.isArray(task.report?.failedCycles)
    ? task.report.failedCycles.map(item => {
        const normalized = normalizeFailure(item.log || item.error || '未记录错误详情', item.createdAt);
        return {
          cycle: item.cycle ? `第 ${item.cycle} 次` : '失败',
          ...normalized
        };
      })
    : [];
  if (structured.length > 0) return structured;

  const sourceLogs = Array.isArray(task.failureLogs) && task.failureLogs.length > 0
    ? task.failureLogs
    : (task.logs || []);
  return sourceLogs
    .filter(log => /\[ERROR\]|\[第\s*\d+\s*次测试失败\]|\bFAIL(?:ED)?\b/i.test(typeof log === 'string' ? log : log?.message || ''))
    .map(log => {
      const normalized = normalizeFailure(log);
      const match = normalized.message.match(/第\s*(\d+)\s*次测试失败/);
      return { cycle: match ? `第 ${match[1]} 次` : '错误', ...normalized };
    });
}

function formatFailureTimestamp(value) {
  if (!value) return '--';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '--' : formatClientLogTimestamp(date);
}

function renderFailureLogs(task) {
  const failures = getFailureLogs(task);
  const canOpen = Number(task.report?.failCount || 0) > 0;
  elements.reportFailButton.disabled = !canOpen;
  elements.reportFailButton.title = canOpen ? '查看失败日志' : '没有失败日志';
  elements.reportFailButton.setAttribute('aria-expanded', 'false');
  elements.reportFailures.hidden = true;
  elements.reportFailuresList.replaceChildren();

  const visibleFailures = failures.slice(0, 200);
  visibleFailures.forEach(failure => {
    const row = document.createElement('div');
    row.className = 'failure-log-entry';
    const cycle = document.createElement('span');
    cycle.className = 'failure-log-cycle';
    cycle.textContent = failure.cycle;
    const timestamp = document.createElement('time');
    timestamp.className = 'failure-log-time';
    timestamp.textContent = failure.timestamp;
    const message = document.createElement('span');
    message.className = 'failure-log-message';
    message.textContent = failure.message;
    row.append(timestamp, cycle, message);
    elements.reportFailuresList.appendChild(row);
  });

  if (visibleFailures.length === 0 && canOpen) {
    const empty = document.createElement('div');
    empty.className = 'failure-log-more';
    empty.textContent = '该历史报告没有保存结构化失败日志，请查看下方运行日志。';
    elements.reportFailuresList.appendChild(empty);
  } else if (failures.length > visibleFailures.length) {
    const more = document.createElement('div');
    more.className = 'failure-log-more';
    more.textContent = `另有 ${failures.length - visibleFailures.length} 条失败日志未显示，请查看完整报告。`;
    elements.reportFailuresList.appendChild(more);
  }
}

function toggleFailureLogs(visible) {
  if (elements.reportFailButton.disabled) return;
  const shouldShow = visible ?? elements.reportFailures.hidden;
  elements.reportFailures.hidden = !shouldShow;
  elements.reportFailButton.setAttribute('aria-expanded', String(shouldShow));
  if (shouldShow) elements.reportFailures.scrollIntoView({ block: 'nearest' });
}

// === Log Viewer ===
function formatClientLogTimestamp(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(date);
  const values = Object.fromEntries(
    parts.filter(part => part.type !== 'literal').map(part => [part.type, part.value])
  );
  const milliseconds = String(date.getMilliseconds()).padStart(3, '0');
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}.${milliseconds}`;
}

function appendLog(level, message) {
  const emptyEl = elements.logContent.querySelector('.log-empty');
  if (emptyEl) emptyEl.remove();

  const line = document.createElement('div');
  line.className = 'log-line ' + level;
  const text = String(message);
  line.textContent = /^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\]/.test(text)
    ? text
    : `[${formatClientLogTimestamp()}] ${text}`;
  elements.logContent.appendChild(line);

  while (elements.logContent.childElementCount > MAX_RENDERED_LOG_LINES) {
    elements.logContent.firstElementChild?.remove();
  }

  if (state.autoScroll) {
    elements.logViewer.scrollTop = elements.logViewer.scrollHeight;
  }
}

function clearLogs() {
  elements.logContent.innerHTML = '<div class="log-empty">等待任务开始...</div>';
}

async function viewTaskLog(taskId) {
  const task = state.tasks.find(t => t.id === taskId);
  if (!task) return;

  state.currentTaskId = taskId;
  clearLogs();
  appendLog('system', '正在加载任务日志...');

  try {
    const response = await fetch(`/api/tasks/${taskId}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const detail = await response.json();
    Object.assign(task, detail);
  } catch (err) {
    if (state.currentTaskId === taskId) {
      clearLogs();
      appendLog('error', '加载任务日志失败: ' + err.message);
    }
    return;
  }

  if (state.currentTaskId !== taskId) return;
  clearLogs();

  if (task.report) {
    showReport(task);
  } else {
    hideReport();
  }

  if (task.logs && task.logs.length > 0) {
    if (task.logsTruncated) {
      appendLog('system', `日志共 ${task.logCount} 行，为保证页面流畅，仅显示最近 ${task.logs.length} 行。`);
    }
    task.logs.forEach(log => {
      const level = log.includes('[ERROR]') ? 'error' :
                    log.includes('[WARN]') ? 'warn' :
                    log.includes('[INFO]') ? 'info' :
                    log.includes('[SUCCESS]') ? 'success' : 'info';
      appendLog(level, log);
    });
  } else {
    appendLog('system', `任务 ${task.platform.toUpperCase()} - ${task.businessLabel || '默认'}`);
    if (task.status === 'pending') appendLog('info', '任务等待中，即将开始执行...');
    if (task.status === 'running') appendLog('info', '任务正在执行中，日志将实时更新...');
  }

  renderTasks();
}

// === Actions ===
async function startTask() {
  if (!state.selectedPlatform || !state.selectedBusinessType) return;

  const config = {
    businessType: state.selectedBusinessType,
    loginMode: state.selectedRole,
    loops: parseInt(elements.configLoops.value)
  };

  elements.btnRun.disabled = true;
  elements.btnRun.textContent = '⏳ 启动中...';

  try {
    const response = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        userId: state.userId,
        platform: state.selectedPlatform,
        config
      })
    });

    const task = await response.json();
    if (!response.ok) throw new Error(task.error || `HTTP ${response.status}`);
    state.currentTaskId = task.id;
    clearLogs();
    appendLog('system', `已创建任务: ${task.platform.toUpperCase()} - ${task.businessLabel}`);
    appendLog('info', '等待任务开始执行...');
  } catch (err) {
    appendLog('error', '创建任务失败: ' + err.message);
    elements.btnRun.disabled = false;
    elements.btnRun.textContent = '▶ 开始测试';
  }
}

async function cancelTask(taskId) {
  const button = Array.from(elements.tasksList.querySelectorAll('.btn-cancel')).find(btn => btn.dataset.taskId === taskId);
  if (button) {
    button.disabled = true;
    button.textContent = '停止中…';
  }
  try {
    const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    const task = state.tasks.find(item => item.id === taskId);
    if (task) Object.assign(task, result);
    renderTasks();
    updatePlatformStatus();
    updateQueueInfo();
    updateRunButton();
    appendLog('system', '已停止任务，后续循环不再执行。');
  } catch (err) {
    appendLog('error', '停止任务失败: ' + err.message);
    renderTasks();
  }
}

// === Socket ===
function connectSocket() {
  state.socket = io();

  state.socket.on('connect', () => {
    updateConnectionStatus('connecting');
    state.socket.emit('join', { userId: state.userId });
  });

  state.socket.on('tasks:list', (tasks) => {
    state.tasks = tasks;
    renderTasks();
    updatePlatformStatus();
    updateQueueInfo();
    updateRunButton();
    updateConnectionStatus('connected');
  });

  state.socket.on('task:created', (task) => {
    state.tasks.unshift(task);
    renderTasks();
    updatePlatformStatus();
    updateQueueInfo();
    updateRunButton();
  });

  state.socket.on('task:updated', (data) => {
    const task = state.tasks.find(t => t.id === data.id);
    if (task) {
      Object.assign(task, data);
      renderTasks();
      updatePlatformStatus();
      updateQueueInfo();
      updateRunButton();
      
      if (data.report && state.currentTaskId === data.id) {
        showReport(task);
      }
    }
  });

  state.socket.on('log:append', (data) => {
    if (data.taskId === state.currentTaskId) {
      appendLog(data.level, data.message);
    }
  });

  state.socket.on('device:status', ({ platform, result }) => {
    handleDeviceStatus(platform, result);
  });

  state.socket.on('disconnect', () => {
    updateConnectionStatus('disconnected');
  });

  state.socket.on('connect_error', () => {
    updateConnectionStatus('disconnected');
  });
}

function updateConnectionStatus(status) {
  const dot = elements.connectionStatus.querySelector('.status-dot');
  const text = elements.connectionStatus.querySelector('.status-text');
  dot.className = 'status-dot ' + status;
  text.textContent = status === 'connected' ? '已连接' :
                     status === 'connecting' ? '连接中...' : '未连接';
}

// === Load Platforms ===
async function loadPlatforms() {
  try {
    const res = await fetch('/api/platforms');
    state.platforms = await res.json();
  } catch (e) {
    console.error('加载平台配置失败:', e);
  }
}

// === Events ===
function bindEvents() {
  elements.platformCards.forEach(card => {
    card.addEventListener('click', () => {
      selectPlatform(card.dataset.platform);
    });
  });

  // Device check buttons
  document.querySelectorAll('.device-check-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const platform = btn.id.replace('deviceCheck-', '');
      checkDevice(platform);
    });
  });

  // Role tabs
  elements.roleTabs.querySelectorAll('.role-tab').forEach(tab => {
    tab.addEventListener('click', () => selectRole(tab.dataset.role));
  });

  elements.btnRun.addEventListener('click', startTask);
  elements.btnClearLog.addEventListener('click', clearLogs);
  elements.reportFailButton.addEventListener('click', () => toggleFailureLogs());
  elements.reportFailuresClose.addEventListener('click', () => toggleFailureLogs(false));

  elements.btnAutoScroll.addEventListener('click', () => {
    state.autoScroll = !state.autoScroll;
    elements.btnAutoScroll.textContent = state.autoScroll ? '⬇️ 自动' : '⬆️ 手动';
  });

  elements.btnRefresh.addEventListener('click', () => {
    fetch('/api/tasks')
      .then(res => res.json())
      .then(tasks => {
        state.tasks = tasks;
        renderTasks();
        updatePlatformStatus();
        updateQueueInfo();
      });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && state.selectedPlatform && state.selectedBusinessType && !elements.btnRun.disabled) {
      startTask();
    }
    if (e.ctrlKey && e.key === 'l') {
      e.preventDefault();
      clearLogs();
    }
  });
}

// === Init ===
function init() {
  let userId = localStorage.getItem('testdashboard_userid');
  if (!userId) {
    userId = 'user_' + Math.random().toString(36).substring(2, 10);
    localStorage.setItem('testdashboard_userid', userId);
  }
  state.userId = userId;
  elements.userId.textContent = userId.substring(0, 8) + '...';

  bindEvents();
  loadPlatforms().then(() => connectSocket());

  setInterval(() => {
    elements.serverTime.textContent = new Date().toLocaleTimeString('zh-CN');
  }, 1000);
}

init();
