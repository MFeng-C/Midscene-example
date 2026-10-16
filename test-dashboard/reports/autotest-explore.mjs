import { chromium } from '../../node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';

const url = 'http://192.168.2.110/autotest/#/';
const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const events = [];
page.on('console', msg => {
  if (msg.type() === 'error') events.push({ type: 'console', text: msg.text() });
});
page.on('pageerror', error => events.push({ type: 'pageerror', text: error.message }));
page.on('response', response => {
  if (response.status() >= 400) events.push({ type: 'http', status: response.status(), url: response.url() });
});

await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
await page.screenshot({ path: 'reports/autotest-home.png', fullPage: true });
const snapshot = await page.evaluate(() => ({
  title: document.title,
  url: location.href,
  text: document.body.innerText,
  interactive: [...document.querySelectorAll('a,button,input,select,textarea,[role="menuitem"],[role="tab"]')].map((el, index) => ({
    index,
    tag: el.tagName,
    text: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim(),
    href: el.href || '',
    type: el.type || '',
    disabled: Boolean(el.disabled),
  })),
}));
await fs.writeFile('reports/autotest-home.json', JSON.stringify({ snapshot, events }, null, 2));
console.log(JSON.stringify({ snapshot, events }, null, 2));
await browser.close();
