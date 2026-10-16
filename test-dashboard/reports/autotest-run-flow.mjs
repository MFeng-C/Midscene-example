import { chromium } from '../../node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';

const outputDir = 'reports/autotest-platform';
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
page.on('pageerror', error => errors.push(error.message));
await page.goto('http://192.168.2.110/autotest/#/run', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(500);

const steps = [];
for (let step = 1; step <= 5; step++) {
  const snapshot = await page.evaluate(() => ({
    url: location.href,
    text: document.body.innerText,
    buttons: [...document.querySelectorAll('button')].filter(x => x.offsetParent !== null).map(x => ({ text: x.innerText.trim(), disabled: x.disabled })),
    inputs: [...document.querySelectorAll('input')].filter(x => x.offsetParent !== null).map(x => ({ type: x.type, placeholder: x.placeholder, checked: x.checked, disabled: x.disabled })),
  }));
  steps.push({ step, ...snapshot });
  await page.screenshot({ path: `${outputDir}/run-step-${step}.png`, fullPage: true });
  const text = page.locator('input[type="text"]:visible').first();
  if (await text.count()) await text.fill('自动化巡检任务');
  const checks = page.locator('input[type="checkbox"]:visible:not(:disabled)');
  if (await checks.count()) await checks.first().check();
  if (step < 5) {
    const next = page.getByRole('button', { name: '下一步', exact: true });
    if (!(await next.count()) || await next.isDisabled()) break;
    await next.click();
    await page.waitForTimeout(250);
  }
}

const planCheck = page.getByRole('button', { name: '单独检查当前计划（可选）', exact: true });
if (await planCheck.count()) {
  await planCheck.click();
  await page.waitForTimeout(300);
}
const finalButtons = page.locator('button:visible:not(:disabled)');
const finalNames = await finalButtons.allTextContents();
const executeName = finalNames.find(name => /开始.*执行/.test(name));
let execution = { attempted: false, passed: false, detail: '未找到执行按钮' };
if (executeName) {
  const before = page.url();
  await page.getByRole('button', { name: executeName, exact: true }).click();
  await page.waitForTimeout(700);
  execution = { attempted: true, passed: page.url() !== before || /任务|报告|执行/.test(await page.locator('body').innerText()), detail: page.url() };
  await page.screenshot({ path: `${outputDir}/run-executed.png`, fullPage: true });
}

const result = { reachedSteps: steps.length, steps, execution, errors };
await fs.writeFile(`${outputDir}/run-flow.json`, JSON.stringify(result, null, 2));
console.log(JSON.stringify({ reachedSteps: steps.length, headings: steps.map(x => x.text.match(/\d\. [^\n]+/g)?.find(Boolean)), execution, errors }, null, 2));
await browser.close();
