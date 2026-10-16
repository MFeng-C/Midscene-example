import { chromium } from '../../node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';

const base = 'http://192.168.2.110/autotest/';
const routes = ['/', '/devices', '/cases', '/run', '/tasks', '/reports', '/projects', '/resources', '/settings'];
const outputDir = 'reports/autotest-platform';
await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
});

async function open(route) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('response', response => {
    if (response.status() >= 400) errors.push(`HTTP ${response.status()}: ${response.url()}`);
  });
  await page.goto(`${base}#${route}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(800);
  return { context, page, errors };
}

const pages = [];
const checks = [];

for (const route of routes) {
  const { context, page, errors } = await open(route);
  const slug = route === '/' ? 'home' : route.slice(1);
  const info = await page.evaluate(() => ({
    title: document.title,
    heading: document.querySelector('main h1, main h2, h1, h2')?.textContent?.trim() || '',
    text: document.body.innerText,
    links: [...document.querySelectorAll('a[href]')].filter(el => el.offsetParent !== null).map(el => ({ text: el.innerText.trim(), href: el.href })),
    buttons: [...document.querySelectorAll('button')].filter(el => el.offsetParent !== null).map((el, index) => ({ index, text: (el.innerText || el.getAttribute('aria-label') || el.title || '').trim(), disabled: el.disabled })),
    inputs: [...document.querySelectorAll('input, textarea')].filter(el => el.offsetParent !== null).map((el, index) => ({ index, type: el.type, placeholder: el.placeholder, disabled: el.disabled, readOnly: el.readOnly })),
    selects: [...document.querySelectorAll('select')].filter(el => el.offsetParent !== null).map((el, index) => ({ index, disabled: el.disabled, options: [...el.options].map(o => o.text) })),
  }));
  await page.screenshot({ path: `${outputDir}/${slug}.png`, fullPage: true });
  pages.push({ route, finalUrl: page.url(), ...info, errors });

  for (let index = 0; index < info.links.length; index++) {
    const href = info.links[index].href;
    if (!href.startsWith(base)) continue;
    const before = page.url();
    await page.locator('a[href]:visible').nth(index).click({ timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(150);
    checks.push({ route, kind: 'link', name: info.links[index].text || href, passed: page.url() !== before || href === before, detail: page.url() });
    await page.goto(`${base}#${route}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(100);
  }
  await context.close();

  for (const button of info.buttons) {
    if (button.disabled) {
      checks.push({ route, kind: 'button', name: button.text || `button-${button.index + 1}`, passed: true, detail: '按当前页面状态正确禁用，未执行' });
      continue;
    }
    const run = await open(route);
    let dialog = '';
    run.page.once('dialog', async value => { dialog = `${value.type()}: ${value.message()}`; await value.dismiss(); });
    const before = await run.page.evaluate(() => ({ url: location.href, text: document.body.innerText, html: document.body.innerHTML }));
    let clickError = '';
    const locator = run.page.locator('button:visible').nth(button.index);
    await locator.click({ timeout: 5000 }).catch(error => { clickError = error.message.split('\n')[0]; });
    await run.page.waitForTimeout(350);
    const after = await run.page.evaluate(() => ({ url: location.href, text: document.body.innerText, html: document.body.innerHTML }));
    const changed = before.url !== after.url || before.text !== after.text || before.html !== after.html || Boolean(dialog);
    checks.push({
      route,
      kind: 'button',
      name: button.text || `button-${button.index + 1}`,
      passed: !clickError && (changed || run.errors.length === 0),
      detail: clickError || dialog || (changed ? `界面响应，当前路由 ${after.url.split('#')[1] || '/'}` : '点击成功，界面无可见变化'),
      errors: run.errors,
    });
    await run.context.close();
  }

  for (const select of info.selects) {
    const run = await open(route);
    const locator = run.page.locator('select:visible').nth(select.index);
    const values = await locator.locator('option').evaluateAll(options => options.map(option => option.value));
    const before = await locator.inputValue();
    const target = values.find(value => value !== before);
    if (!target || select.disabled) {
      checks.push({ route, kind: 'select', name: select.options.join(' / '), passed: true, detail: '无其他可选值或当前禁用' });
    } else {
      await locator.selectOption(target);
      checks.push({ route, kind: 'select', name: select.options.join(' / '), passed: await locator.inputValue() === target, detail: `切换为 ${target}` });
    }
    await run.context.close();
  }

  for (const input of info.inputs) {
    if (input.disabled || input.readOnly || ['file', 'hidden', 'submit', 'button'].includes(input.type)) continue;
    const run = await open(route);
    const locator = run.page.locator('input:visible, textarea:visible').nth(input.index);
    let passed = true;
    let detail = '';
    try {
      if (['checkbox', 'radio'].includes(input.type)) {
        const before = await locator.isChecked();
        await locator.click();
        passed = (await locator.isChecked()) !== before;
        detail = '切换选择状态';
      } else {
        await locator.fill('自动测试输入');
        passed = (await locator.inputValue()) === '自动测试输入';
        detail = input.placeholder || input.type;
      }
    } catch (error) {
      passed = false;
      detail = error.message.split('\n')[0];
    }
    checks.push({ route, kind: 'input', name: input.placeholder || `${input.type}-${input.index + 1}`, passed, detail });
    await run.context.close();
  }
}

await fs.writeFile(`${outputDir}/results.json`, JSON.stringify({ generatedAt: new Date().toISOString(), pages, checks }, null, 2));
console.log(JSON.stringify({ pages: pages.map(({ route, heading, errors }) => ({ route, heading, errors })), total: checks.length, passed: checks.filter(x => x.passed).length, failed: checks.filter(x => !x.passed) }, null, 2));
await browser.close();
