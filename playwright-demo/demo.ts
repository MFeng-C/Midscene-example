import { chromium } from 'playwright';
import { PlaywrightAgent } from '@midscene/web/playwright';
import 'dotenv/config'; // read environment variables from .env file

const sleep = (ms: number | undefined) => new Promise((r) => setTimeout(r, ms));

Promise.resolve(
  (async () => {
    const browser = await chromium.launch({
      headless: false, // 'true' means we can't see the browser window
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const page = await browser.newPage();
    await page.setViewportSize({
      width: 1280,
      height: 768,
    });
    await page.goto('https://www.baidu.com');
    await sleep(5000); // 👀 init Midscene agent
    const agent = new PlaywrightAgent(page);

    // 👀 type keywords, perform a search
    await agent.aiAct('在搜索框中输入 "今日天气", 按回车键搜索');

    // 👀 wait for the loading
    await agent.aiWaitFor('页面展示了天气相关信息');

    // 👀 understand the page content
    const weatherInfo = await agent.aiQuery<{
      city: string;
      temperature: string;
      condition: string;
    }>('{city: string, temperature: string, condition: string}, 提取天气信息中的城市、温度和天气状况');
    console.log('天气信息:', weatherInfo);

    const isShowingWeather = await agent.aiBoolean('页面是否展示了天气信息');
    console.log('是否显示天气:', isShowingWeather);

    // 👀 assert by AI
    await agent.aiAssert('页面展示了今日天气信息');

    await browser.close();
  })()
);
