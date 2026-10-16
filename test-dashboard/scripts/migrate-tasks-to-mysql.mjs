import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  closeDatabase,
  getDatabaseCounts,
  initializeDatabase,
  saveTask
} from '../server/database.js';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const tasksFile = path.resolve(scriptDir, '..', 'data', 'tasks.json');

async function main() {
  if (!fs.existsSync(tasksFile)) throw new Error(`文件不存在: ${tasksFile}`);
  const tasks = JSON.parse(fs.readFileSync(tasksFile, 'utf8'));
  if (!Array.isArray(tasks)) throw new Error('tasks.json 顶层必须是数组');

  await initializeDatabase();
  const before = await getDatabaseCounts();
  console.log(`[migration] 数据库迁移前: tasks=${before.tasks}, logs=${before.logs}`);

  for (let index = 0; index < tasks.length; index += 1) {
    await saveTask(tasks[index]);
    if ((index + 1) % 10 === 0 || index + 1 === tasks.length) {
      console.log(`[migration] 已迁移 ${index + 1}/${tasks.length} 个任务`);
    }
  }

  const after = await getDatabaseCounts();
  const expectedLogs = tasks.reduce((sum, task) => sum + (task.logs?.length || 0), 0);
  console.log(`[migration] 数据库迁移后: tasks=${after.tasks}, logs=${after.logs}`);
  console.log(`[migration] JSON 源数据: tasks=${tasks.length}, logs=${expectedLogs}`);
  if (after.tasks < tasks.length || after.logs < expectedLogs) {
    throw new Error('迁移校验失败：数据库记录数少于 JSON 源数据');
  }
  console.log('[migration] SUCCESS');
}

main()
  .catch(error => {
    console.error(`[migration] ERROR: ${error.message}`);
    process.exitCode = 1;
  })
  .finally(closeDatabase);
