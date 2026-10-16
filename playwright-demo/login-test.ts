import { chromium } from 'playwright';
import 'dotenv/config';

const sleep = (ms: number | undefined) => new Promise((r) => setTimeout(r, ms));

Promise.resolve(
  (async () => {
    const browser = await chromium.launch({
      headless: false,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const page = await browser.newPage();
    await page.setViewportSize({
      width: 1280,
      height: 768,
    });

    console.log('1. 打开浏览器进入测试页面');
    await page.goto('http://192.168.18.223:18530/');

    console.log('2. 输入账号、密码、验证码');
    // 等待页面加载，输入账号
    await page.waitForSelector('input[type="text"], input[type="username"], input[name*="user"], input[name*="account"]', { timeout: 10000 });
    await page.fill('input[type="text"], input[type="username"], input[name*="user"], input[name*="account"]', '10001');

    // 输入密码
    await page.fill('input[type="password"], input[name*="pwd"], input[name*="pass"]', 'Aa123456');

    // 输入验证码
    await page.fill('input[name*="code"], input[name*="captcha"], input[name*="verify"]', '0000');

    console.log('3. 点击登录按钮');
    await page.click('button[type="submit"], button:has-text("登录"), button:has-text("登录")');

    console.log('4. 验证登录结果成功');
    // 等待页面跳转或出现登录成功的标识
    await sleep(2000);

    // 检查是否登录成功（根据实际情况调整选择器）
    // 常见成功标识：URL变化、出现用户信息、出现退出按钮等
    const currentUrl = page.url();
    console.log('当前URL:', currentUrl);

    // 获取页面内容用于判断
    const pageContent = await page.content();
    const isLoginSuccess = !pageContent.includes('登录') || pageContent.includes('退出') || pageContent.includes('用户');

    if (isLoginSuccess) {
      console.log('✓ 登录成功');
    } else {
      console.log('✗ 登录可能失败，请检查页面状态');
    }

    await browser.close();
    console.log('测试完成');
  })()
);
