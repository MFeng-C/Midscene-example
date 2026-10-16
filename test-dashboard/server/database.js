import mysql from 'mysql2/promise';

const DEFAULTS = {
  host: '192.168.18.223',
  port: 3306,
  user: 'kiwi',
  database: 'test'
};

let pool;

function getPool() {
  if (!pool) {
    const password = process.env.TEST_DASHBOARD_DB_PASSWORD || process.env.DUALRECORD_DB_PASSWORD;
    if (!password) throw new Error('缺少环境变量 TEST_DASHBOARD_DB_PASSWORD');
    pool = mysql.createPool({
      host: process.env.TEST_DASHBOARD_DB_HOST || DEFAULTS.host,
      port: Number(process.env.TEST_DASHBOARD_DB_PORT || DEFAULTS.port),
      user: process.env.TEST_DASHBOARD_DB_USER || DEFAULTS.user,
      password,
      database: process.env.TEST_DASHBOARD_DB_NAME || DEFAULTS.database,
      charset: 'utf8mb4',
      waitForConnections: true,
      connectionLimit: 5,
      queueLimit: 0
    });
  }
  return pool;
}

function parseJson(value, fallback) {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'object') return value;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function rowToTask(row) {
  return {
    id: row.id,
    userId: row.user_id,
    platform: row.platform,
    businessType: row.business_type,
    businessLabel: row.business_label,
    status: row.status,
    config: parseJson(row.config_json, {}),
    createdAt: row.created_at,
    startedAt: row.started_at,
    completedAt: row.completed_at,
    exitCode: row.exit_code,
    report: parseJson(row.report_json, null),
    reportUrl: row.report_url,
    logCount: Number(row.log_count || 0)
  };
}

export async function initializeDatabase() {
  const db = getPool();
  await db.execute(`
    CREATE TABLE IF NOT EXISTS test_dashboard_tasks (
      id VARCHAR(36) PRIMARY KEY,
      user_id VARCHAR(128) NOT NULL,
      platform VARCHAR(32) NOT NULL,
      business_type VARCHAR(128) NULL,
      business_label VARCHAR(255) NULL,
      status VARCHAR(32) NOT NULL,
      config_json LONGTEXT NULL,
      exit_code INT NULL,
      created_at VARCHAR(40) NOT NULL,
      started_at VARCHAR(40) NULL,
      completed_at VARCHAR(40) NULL,
      report_json LONGTEXT NULL,
      report_url VARCHAR(1024) NULL,
      log_count INT NOT NULL DEFAULT 0,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_dashboard_tasks_user_created (user_id, created_at),
      INDEX idx_dashboard_tasks_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `);
  await db.execute(`
    CREATE TABLE IF NOT EXISTS test_dashboard_task_logs (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      task_id VARCHAR(36) NOT NULL,
      sequence_no INT NOT NULL,
      message LONGTEXT NOT NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY uq_dashboard_task_log_sequence (task_id, sequence_no),
      INDEX idx_dashboard_task_logs_task (task_id, sequence_no),
      CONSTRAINT fk_dashboard_task_logs_task
        FOREIGN KEY (task_id) REFERENCES test_dashboard_tasks(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `);
}

export async function saveTask(task) {
  const db = getPool();
  const connection = await db.getConnection();
  try {
    await connection.beginTransaction();
    const logs = Array.isArray(task.logs) ? task.logs : [];
    await connection.execute(`
      INSERT INTO test_dashboard_tasks (
        id, user_id, platform, business_type, business_label, status,
        config_json, exit_code, created_at, started_at, completed_at,
        report_json, report_url, log_count
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON DUPLICATE KEY UPDATE
        user_id = VALUES(user_id), platform = VALUES(platform),
        business_type = VALUES(business_type), business_label = VALUES(business_label),
        status = VALUES(status), config_json = VALUES(config_json),
        exit_code = VALUES(exit_code), started_at = VALUES(started_at),
        completed_at = VALUES(completed_at), report_json = VALUES(report_json),
        report_url = VALUES(report_url), log_count = GREATEST(log_count, VALUES(log_count))
    `, [
      task.id, task.userId, task.platform, task.businessType || null,
      task.businessLabel || null, task.status, JSON.stringify(task.config || {}),
      task.exitCode ?? null, task.createdAt, task.startedAt || null,
      task.completedAt || null, task.report ? JSON.stringify(task.report) : null,
      task.reportUrl || null, logs.length
    ]);

    if (logs.length > 0) {
      const [rows] = await connection.execute(
        'SELECT COALESCE(MAX(sequence_no), -1) AS max_sequence FROM test_dashboard_task_logs WHERE task_id = ?',
        [task.id]
      );
      const start = Number(rows[0].max_sequence) + 1;
      for (let offset = start; offset < logs.length; offset += 100) {
        const batch = logs.slice(offset, offset + 100);
        const placeholders = batch.map(() => '(?, ?, ?)').join(', ');
        const values = batch.flatMap((message, index) => [task.id, offset + index, String(message)]);
        await connection.execute(
          `INSERT IGNORE INTO test_dashboard_task_logs (task_id, sequence_no, message) VALUES ${placeholders}`,
          values
        );
      }
      await connection.execute(
        'UPDATE test_dashboard_tasks SET log_count = ? WHERE id = ?',
        [logs.length, task.id]
      );
    }
    await connection.commit();
  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}

export async function listTasks(limit = 50) {
  const safeLimit = Math.max(1, Math.min(Number(limit) || 50, 100));
  const [rows] = await getPool().query(
    `SELECT * FROM test_dashboard_tasks ORDER BY created_at DESC LIMIT ${safeLimit}`
  );
  return rows.map(rowToTask);
}

export async function getTaskById(id, logLimit = 1000) {
  const [rows] = await getPool().execute(
    'SELECT * FROM test_dashboard_tasks WHERE id = ?',
    [id]
  );
  if (rows.length === 0) return null;
  const task = rowToTask(rows[0]);
  const safeLimit = Math.max(1, Math.min(Number(logLimit) || 1000, 100000));
  const [logRows] = await getPool().query(
    `SELECT sequence_no, message FROM test_dashboard_task_logs
     WHERE task_id = ? ORDER BY sequence_no DESC LIMIT ${safeLimit}`,
    [id]
  );
  task.logs = logRows.reverse().map(row => row.message);
  task.logsTruncated = task.logCount > task.logs.length;
  return task;
}

export async function getTaskFailureLogs(id, limit = 200) {
  const safeLimit = Math.max(1, Math.min(Number(limit) || 200, 500));
  const [rows] = await getPool().query(
    `SELECT sequence_no, message, created_at FROM test_dashboard_task_logs
     WHERE task_id = ? AND (
       message LIKE '%测试失败]%' OR
       message LIKE '%[ERROR]%' OR
       message REGEXP 'FAIL(ED)?'
     )
     ORDER BY sequence_no ASC LIMIT ${safeLimit}`,
    [id]
  );
  return rows.map(row => ({
    message: row.message,
    createdAt: row.created_at
  }));
}

export async function loadInterruptedTasks() {
  const [rows] = await getPool().query(
    "SELECT id FROM test_dashboard_tasks WHERE status IN ('pending', 'running')"
  );
  const result = [];
  for (const row of rows) {
    const task = await getTaskById(row.id, 100000);
    if (task) result.push(task);
  }
  return result;
}

export async function getDatabaseCounts() {
  const [[taskRow]] = await getPool().query('SELECT COUNT(*) AS count FROM test_dashboard_tasks');
  const [[logRow]] = await getPool().query('SELECT COUNT(*) AS count FROM test_dashboard_task_logs');
  return { tasks: Number(taskRow.count), logs: Number(logRow.count) };
}

export async function closeDatabase() {
  if (pool) {
    await pool.end();
    pool = null;
  }
}
