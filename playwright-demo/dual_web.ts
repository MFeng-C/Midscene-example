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

    // ==================== 登录 ====================
    await page.goto('http://192.168.18.223:18530/');
    await sleep(5000); // 👀 init Midscene agent
    const agent = new PlaywrightAgent(page);

    // 输入用户名
    await agent.aiAct('在用户名输入框中输入 "10001"');

    // 输入密码
    await agent.aiAct('在密码输入框中输入 "Aa123456"');

    // 输入验证码
    await agent.aiAct('在验证码输入框中输入 "0000"');

    // 点击登录按钮
    await agent.aiAct('点击登录按钮或确定按钮');

    // 等待登录成功后的页面
    await agent.aiWaitFor('登录成功或进入系统主界面');
    console.log('登录成功');

    // ==================== 进入录音录像 ====================
    // 点击录音录像菜单
    await agent.aiAct('点击"录音录像"菜单按钮');

    // 智能等待子菜单出现
    await agent.aiWaitFor('"发起双录"子菜单可见');
    console.log('录音录像菜单展开');

    // 点击发起双录子菜单
    await agent.aiAct('点击"发起双录"子菜单');

    // 智能等待客户信息表单加载完成
    await agent.aiWaitFor('客户信息表单已加载');
    console.log('进入发起双录页面');

    // ==================== 填写客户信息 ====================
    // 选择客户类型
    await agent.aiAct('选择客户类型下拉框为"个人客户"');

    // 选择证件类型
    await agent.aiAct('选择证件类型下拉框为"身份证"');

    // 输入证件号码
    await agent.aiAct('在证件号码输入框中输入"411525200006040977"');

    // 点击查询按钮
    await agent.aiAct('点击查询按钮');

    // 智能等待查询结果
    await agent.aiWaitFor('查询结果已显示');
    console.log('查询完成');

    // 点击下一步按钮
    await agent.aiAct('点击下一步按钮');

    // 智能等待产品信息页面加载
    await agent.aiWaitFor('产品信息表单已加载');
    console.log('进入产品信息页面');

    // ==================== 填写产品信息 ====================
    // 选择产品类型
    await agent.aiAct('选择产品类型下拉框为"理财"');

    // 选择产品子类
    await agent.aiAct('选择产品子类下拉框为"代销理财"');

    // 选择产品名称
    await agent.aiAct('选择产品名称下拉框为"理财产品"');

    // 输入购买金额
    await agent.aiAct('在购买金额输入框中输入"1000"');

    // 点击确定按钮
    await agent.aiAct('点击确定按钮');

    // 智能等待弹出窗口
    await agent.aiWaitFor('录制提示窗口已弹出');
    console.log('弹出提示窗口');

    // ==================== 录音录像 ====================
    // 选择录制类型
    await agent.aiAct('选择录制类型下拉框为"现场"');

    // 点击开始录制按钮
    await agent.aiAct('点击"开始录制"按钮');

    console.log('开始录制');

    await browser.close();
  })()
);
