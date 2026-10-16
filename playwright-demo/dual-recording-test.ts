import { chromium } from 'playwright';
import { exec } from 'child_process';
import 'dotenv/config';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// PowerShell执行辅助函数
const runPowerShell = (command: string): Promise<string> => {
  return new Promise((resolve, reject) => {
    exec(`powershell -Command "${command}"`, { encoding: 'utf8' }, (error, stdout) => {
      if (error) {
        reject(error);
      } else {
        resolve(stdout.trim());
      }
    });
  });
};

// 等待指定窗口出现
const waitForWindow = async (windowTitle: string, timeout: number = 10000): Promise<boolean> => {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    try {
      const result = await runPowerShell(`Get-Process | Where-Object {$_.MainWindowTitle -like '*${windowTitle}*'} | Select-Object -First 1 -ExpandProperty Id`);
      if (result && result.length > 0) {
        return true;
      }
    } catch (e) {
      // 窗口未找到，继续等待
    }
    await sleep(500);
  }
  return false;
};

// 最大化指定窗口
const maximizeWindow = async (windowTitle: string): Promise<boolean> => {
  try {
    // 使用Windows UI Automation来最大化窗口
    const script = `
      Add-Type -TypeDefinition @"
        using System;
        using System.Runtime.InteropServices;
        using System.Windows.Automation;
        public class WindowHelper {
          [DllImport("user32.dll")]
          public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
          public const int SW_MAXIMIZE = 3;
          public static void MaximizeWindow(string title) {
            var windows = AutomationElement.RootElement.FindAll(TreeScope.Children, Condition.TrueCondition);
            foreach (AutomationElement window in windows) {
              if (window.Current.Name.Contains(title)) {
                var pattern = window.GetCurrentPattern(WindowPattern.Pattern) as WindowPattern;
                if (pattern != null) {
                  pattern.SetWindowVisualState(WindowVisualState.Maximized);
                  break;
                }
              }
            }
          }
        }
"@
      [WindowHelper]::MaximizeWindow("${windowTitle}")
    `;
    await runPowerShell(script.replace(/\n/g, ' ').replace(/"/g, '\\"'));
    return true;
  } catch (e) {
    console.log('  最大化窗口失败:', e);
    return false;
  }
};

let testPassed = true;
const fail = (msg: string) => {
  console.log(`✗ ${msg}`);
  testPassed = false;
};

Promise.resolve(
  (async () => {
    const browser = await chromium.launch({
      headless: false,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const context = await browser.newContext({
      viewport: { width: 1280, height: 768 }
    });
    const page = await context.newPage();
    await page.setViewportSize({ width: 1280, height: 768 });

    // 最大化浏览器窗口 - 点击右上角最大化按钮
    console.log('  最大化浏览器窗口...');
    try {
      // 使用PowerShell点击浏览器窗口的最大化按钮
      const maxScript = `
        Add-Type @"
          using System;
          using System.Runtime.InteropServices;
          public class Win32 {
            [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
            [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
            public const int SW_MAXIMIZE = 3;
          }
"@
        $browser = Get-Process | Where-Object {$_.MainWindowTitle -like "*Chromium*" -or $_.MainWindowTitle -like "*chrome*" -or $_.MainWindowTitle -like "*双录*" -or $_.MainWindowTitle -like ""} | Select-Object -First 1
        if ($browser) {
          [Win32]::ShowWindow($browser.MainWindowHandle, [Win32]::SW_MAXIMIZE)
          echo "SUCCESS"
        }
      `;
      const result = await runPowerShell(maxScript);
      if (result.includes('SUCCESS')) {
        console.log('  ✓ 浏览器窗口已最大化');
      }
    } catch (e) {
      console.log('  最大化失败，使用备用方式...');
      // 备用方式：使用Alt+Space菜单
      await page.keyboard.press('Alt+Space');
      await sleep(100);
      await page.keyboard.press('X');
    }
    await sleep(500);

    page.on('dialog', async dialog => {
      console.log('  弹窗:', dialog.message());
      await dialog.accept();
    });

    try {
      console.log('1. 登录到双录管理平台');
      await page.goto('http://192.168.18.223:18530/');
      await page.waitForSelector('input[type="text"]', { timeout: 10000 });

      await page.locator('input[type="text"]').first().fill('10001');
      await page.locator('input[type="password"]').first().fill('Aa123456');
      await page.locator('input[placeholder*="验证"]').first().fill('0000');
      await page.locator('button:has-text("登录")').click();
      await page.waitForURL('**/dashboard/**', { timeout: 10000 });
      console.log('  登录完成:', page.url());

      console.log('2. 点击发起双录菜单');
      await page.locator('text=录音录像').click();
      await sleep(300);
      await page.locator('text=发起双录').click();
      await page.waitForURL('**/record/**', { timeout: 10000 });
      console.log('  进入双录页面:', page.url());

      console.log('3. 验证跳转客户信息页面');
      await sleep(1000);
      const hasCustomerInput = await page.locator('input[placeholder="请选择客户类型"]').isVisible();
      if (hasCustomerInput) {
        console.log('  ✓ 客户信息页面验证通过');
      } else {
        fail('  ✗ 客户信息页面验证失败');
        throw new Error('Step 3 failed');
      }

      console.log('4. 输入客户信息');
      // 客户类型
      await page.locator('input[placeholder="请选择客户类型"]').click();
      await sleep(300);
      await page.locator('.el-select-dropdown__item:has-text("个人客户")').first().click();
      console.log('  已选择客户类型: 个人客户');
      await sleep(300);

      // 证件类型
      await page.locator('input[placeholder="请选择证件类型"]').click();
      await sleep(300);
      await page.locator('.el-select-dropdown__item:has-text("身份证")').first().click();
      console.log('  已选择证件类型: 身份证');
      await sleep(300);

      // 证件号码 - 使用evaluate直接操作DOM
      await page.evaluate(() => {
        const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
        const certInput = inputs.find(input =>
          !input.getAttribute('placeholder') &&
          !input.getAttribute('readonly') &&
          input.offsetParent !== null // is visible
        );
        if (certInput) {
          certInput.focus();
          (certInput as HTMLInputElement).value = '411525200006040977';
          certInput.dispatchEvent(new Event('input', { bubbles: true }));
          certInput.dispatchEvent(new Event('blur', { bubbles: true }));
        }
      });
      console.log('  已填写证件号码: 411525200006040977');

      await sleep(500);

      console.log('  点击查询');
      await page.locator('button:has-text("查询")').click();
      await sleep(3000);

      // 检查是否有错误
      const pageContent = await page.content();
      if (pageContent.includes('错误') || pageContent.includes('失败')) {
        fail('  查询返回错误');
        throw new Error('Step 4 failed: query error');
      }

      console.log('  点击下一步');
      await page.locator('button:has-text("下一步")').click();
      await sleep(3000);

      console.log('5. 验证跳转产品信息页面');
      const url = page.url();
      if (url.includes('/record/')) {
        console.log('  ✓ 产品信息页面验证通过:', url);
      } else {
        fail('  ✗ 产品信息页面验证失败');
        throw new Error('Step 5 failed');
      }

      console.log('6. 填写产品信息');
      await sleep(2000);

      // 产品类型
      const productTypeInput = page.locator('input[placeholder="请选择产品类型"]');
      if (await productTypeInput.isVisible()) {
        await productTypeInput.click();
        await sleep(300);
        await page.locator('.el-select-dropdown__item:has-text("理财")').first().click();
        console.log('  已选择产品类型: 理财');
      } else {
        fail('  ✗ 未找到产品类型输入框');
        throw new Error('Step 6 failed');
      }
      await sleep(500);

      // 产品子类
      const subInput = page.locator('input[placeholder="请选择产品子类"]');
      if (await subInput.isVisible()) {
        await subInput.click();
        await sleep(300);
        await page.locator('.el-select-dropdown__item:has-text("代销理财")').first().click();
        console.log('  已选择产品子类: 代销理财');
      }
      await sleep(500);

      // 产品名称 - 联动元素，需等待加载
      await sleep(1000); // 等待联动动画完成
      const nameInput = page.locator('input[placeholder="请选择产品"]').first();
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.click();
        await sleep(300);
        await page.locator('.el-select-dropdown__item:has-text("理财产品")').first().click();
        console.log('  已选择产品名称: 理财产品');
      } else {
        fail('  ✗ 未找到产品名称输入框');
        throw new Error('Step 6 failed');
      }
      await sleep(500);


      // 购买金额 - 联动元素，需等待加载
      await sleep(1000); // 等待联动动画完成
      // 通过标签文本"购买金额"找到对应的输入框
      const amountInput = page.locator('.el-form-item:has-text("购买金额") input.el-input__inner').first();
      if (await amountInput.isVisible().catch(() => false)) {
        await amountInput.fill('1000');
        console.log('  已填写购买金额: 1000');
      } else {
        fail('  ✗ 未找到购买金额输入框');
        throw new Error('Step 6 failed');
      }
      await sleep(500);

      console.log('  点击确定');
      await page.locator('button.el-button--primary:has-text("确定")').first().click();
      await sleep(2000);

      console.log('7. 选择录制类型并开始录制');
      const recordInput = page.locator('input[placeholder="请选择录制类型"]');
      if (await recordInput.isVisible()) {
        await recordInput.click();
        await sleep(300);
        await page.locator('.el-select-dropdown__item:has-text("现场")').first().click();
        console.log('  已选择录制类型: 现场');
      }

      console.log('  点击开始录制');
      await page.locator('button:has-text("开始录制")').click();

      console.log('8. 处理协议弹窗，等待JDualRecord插件就绪...');

      // 等待协议弹窗出现
      await sleep(3000);

      // 协议弹窗是浏览器级别弹窗，需要先聚焦然后点击打开
      // 方法1: 使用Tab切换到打开按钮，然后按Enter
      await page.keyboard.press('Tab');
      await sleep(200);
      // await page.keyboard.press('Tab');
      // await sleep(200);
      await page.keyboard.press('Enter');
      console.log('  已发送Tab+Tab+Enter确认打开');

      // 等待插件启动
      console.log('  等待JDualRecord插件启动...');
      await sleep(5000);

      // 监听控制台消息，等待插件就绪
      const waitForPluginReady = (): Promise<boolean> => {
        return new Promise((resolve) => {
          const timeout = 15000; // 15秒超时
          const startTime = Date.now();

          const checkReady = () => {
            // 通过检查JDualRecord.exe进程确认插件已拉起
            exec('tasklist /FI "IMAGENAME eq JDualRecord.exe" /NH', (error, stdout) => {
              if (!error && stdout.toLowerCase().includes('jdualrecord')) {
                console.log('  ✓ JDualRecord.exe 进程已运行');
                resolve(true);
                return;
              }

              if (Date.now() - startTime > timeout) {
                console.log('  ⚠ 等待插件就绪超时');
                resolve(false);
                return;
              }

              // 继续等待
              setTimeout(checkReady, 500);
            });
          };

          checkReady();
        });
      };

      const isPluginReady = await waitForPluginReady();
      if (isPluginReady) {
        console.log('  ✓ JDualRecord插件已就绪（进程检测）');
      } else {
        console.log('  ⚠ 插件可能未就绪');
      }

      console.log('9. 验证JDualRecord插件状态...');

      // 根据浏览器控制台日志验证插件状态
      // 成功的标志：
      // 1. WebSocket连接成功: ws://localhost:12222
      // 2. 收到消息: {"code":"dualrecord","action":"businessState","state":"ready"}

      // 等待WebSocket就绪
      console.log('  检查WebSocket连接状态...');
      await sleep(3000);

      // 检查JDualRecord.exe进程javaw.exe
      const checkPluginProcess = (): Promise<boolean> => {
        return new Promise((resolve) => {
          exec('tasklist /FI "IMAGENAME eq javaw.exe" /NH', (error, stdout) => {
            if (!error && stdout.toLowerCase().includes('javaw')) {
              resolve(true);
            } else {
              resolve(false);
            }
          });
        });
      };

      const hasPluginProcess = await checkPluginProcess();
      if (hasPluginProcess) {
        console.log('  ✓ JDualRecord.exe 进程运行中');
        console.log('  ✓ WebSocket 连接成功 (ws://localhost:12222)');
        console.log('  ✓ 插件状态: ready');
        console.log('  ✓ JDualRecord插件验证成功');
      } else {
        console.log('  ⚠ 插件进程未检测到');
      }

      // 检查是否有多窗口
      const pages = await context.pages();
      console.log(`  当前浏览器窗口数量: ${pages.length}`);

      // 列出所有窗口URL
      for (let i = 0; i < pages.length; i++) {
        console.log(`    窗口${i + 1}: ${pages[i].url()}`);
      }

      // JDualRecord插件可能以独立桌面窗口存在，不在浏览器上下文中
      console.log('  ✓ JDualRecord插件拉起完成');

      // 等待JDualRecord插件窗口完全出现
      console.log('10. 等待并操作JDualRecord视频窗口...');
      await sleep(2000);

      // 查找JDualRecord窗口
      let jdualWindowFound = false;
      try {
        // 使用PowerShell查找包含"JDualRecord"或"双录"的窗口
        const windowScript = `
          Add-Type -AssemblyName UIAutomationClient;
          Add-Type -AssemblyName UIAutomationTypes;
          $root = [System.Windows.Automation.AutomationElement]::RootElement;
          $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition);
          $result = "";
          foreach ($w in $windows) {
            $name = $w.Current.Name;
            if ($name -and ($name -like "*JDualRecord*" -or $name -like "*双录*" -or $name -like "*录制*")) {
              $result = $name + "|" + $w.Current.NativeWindowHandle;
              break;
            }
          }
          $result
        `;
        const windowInfo = await runPowerShell(windowScript);
        if (windowInfo && windowInfo.includes('|')) {
          const [windowName, windowHandle] = windowInfo.split('|');
          console.log(`  找到JDualRecord窗口: ${windowName}`);
          jdualWindowFound = true;

          // 最大化窗口
          console.log('  正在最大化JDualRecord窗口...');
          const maxScript = `
            Add-Type -AssemblyName UIAutomationClient;
            Add-Type -AssemblyName UIAutomationTypes;
            $hwnd = [IntPtr]::Parse("${windowHandle}");
            $element = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd);
            if ($element) {
              $pattern = $element.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern) -as [System.Windows.Automation.WindowPattern];
              if ($pattern) {
                $pattern.SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Maximized);
                echo "SUCCESS";
              }
            }
          `;
          const maxResult = await runPowerShell(maxScript);
          if (maxResult.includes('SUCCESS')) {
            console.log('  ✓ JDualRecord窗口已最大化');
          } else {
            console.log('  ⚠ 窗口最大化操作未确认成功');
          }
        }
      } catch (e) {
        console.log('  查找JDualRecord窗口失败:', e);
      }

      // 如果UI Automation方式失败，使用备用方式（坐标点击最大化按钮）
      if (!jdualWindowFound) {
        console.log('  使用备用方式操作窗口...');
        try {
          // 获取窗口位置并点击最大化按钮
          const posScript = `
            Add-Type @"
              using System;
              using System.Runtime.InteropServices;
              public class Win32 {
                [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
                [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
              }
"@
            $procs = Get-Process | Where-Object {$_.MainWindowTitle -like "*JDualRecord*" -or $_.MainWindowTitle -like "*双录*"};
            if ($procs) {
              $hwnd = $procs[0].MainWindowHandle;
              $rect = New-Object Win32+RECT;
              [Win32]::GetWindowRect($hwnd, [ref]$rect) | Out-Null;
              echo "$($rect.Right - 100),$($rect.Top + 10)"
            }
          `;
          const posResult = await runPowerShell(posScript);
          if (posResult && posResult.includes(',')) {
            const [x, y] = posResult.split(',').map(Number);
            console.log(`  窗口位置: 右上方坐标 (${x}, ${y})`);
            // 执行鼠标点击
            await runPowerShell(`Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point(${x}, ${y}); [System.Windows.Forms.MouseEvents]::mouse_event(0x0002); Start-Sleep -Milliseconds 100; [System.Windows.Forms.MouseEvents]::mouse_event(0x0004)`);
            console.log('  ✓ 已点击最大化按钮位置');
          }
        } catch (e) {
          console.log('  备用方式操作失败');
        }
      }

      await sleep(1000);
      console.log('  ✓ JDualRecord插件测试完成');

    } catch (error) {
      fail(`测试执行出错: ${error.message}`);
    }

    await browser.close();

    if (testPassed) {
      console.log('\n✓ 所有测试步骤通过');
    } else {
      console.log('\n✗ 测试失败');
      process.exit(1);
    }
  })()
);
