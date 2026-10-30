"""客户 H5 登出：复用 WebView，以页面状态驱动点击。"""
import time


LOGOUT_SCRIPT = r"""
const visible = e => {
  const r=e.getBoundingClientRect();
  if (!r.width || !r.height) return false;
  for(let p=e;p;p=p.parentElement) {
    const s=getComputedStyle(p);
    if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
  }
  const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
  return top && (top===e||e.contains(top)||top.contains(e));
};
const find = text => Array.from(document.querySelectorAll('button,a,[role="button"],span,div'))
  .find(e => e.innerText.trim()===text && !e.disabled && visible(e) &&
    !Array.from(e.children).some(c => c.innerText && c.innerText.trim()===text));
const action=arguments[0];
// 仅在本次点击退出登录后监听相应弹窗，不等待下一次 WebKit 往返。
if(action==='退出登录') {
  if(window.__iosLogoutConfirm) window.__iosLogoutConfirm.stop();
  const task={confirmed:null};
  let observer, timer, poll;
  task.stop=()=>{if(observer) observer.disconnect(); clearTimeout(timer); clearInterval(poll);};
  const check=()=>{
    if(task.confirmed) return;
    const dialogs=Array.from(document.querySelectorAll(
      '[role="dialog"],.van-dialog,.el-message-box,.v-dialog,.modal'));
    const dialog=dialogs.find(e => visible(e) && /退出登录|退出当前|确定退出|确认退出/.test(e.textContent));
    if(!dialog) return;
    const button=Array.from(dialog.querySelectorAll('button,[role="button"],a,span,div'))
      .find(e => ['确认','确定'].includes(e.textContent.trim()) && visible(e) &&
        !e.closest('[disabled],[aria-disabled="true"],.van-button--disabled') &&
        !Array.from(e.children).some(c => ['确认','确定'].includes(c.textContent.trim())));
    if(button) {
      task.confirmed=button.textContent.trim();
      task.confirmedAt=Date.now();
      task.stop();
      button.click();
    }
  };
  window.__iosLogoutConfirm=task;
  observer=new MutationObserver(check);
  observer.observe(document.body,{childList:true,subtree:true,attributes:true,characterData:true});
  // CSS 动画结束不一定产生 DOM mutation；短轮询补充可见性检查。
  poll=setInterval(check,100);
  timer=setTimeout(task.stop,20000);
}
let clicked=false;
if(action && !(['确认','确定'].includes(action) && window.__iosLogoutConfirm?.confirmed)) {
  const e=find(action);
  if(e) {
    if(['确认','确定'].includes(action) && window.__iosLogoutConfirm) {
      window.__iosLogoutConfirm.confirmed=action;
      window.__iosLogoutConfirm.stop();
    }
    e.click();clicked=true;
  }
}
return {clicked, autoConfirmed:window.__iosLogoutConfirm?.confirmed || null,
  loggedOut:!!find('登录') && document.body.innerText.includes('客户登录'),
  my:!!find('我的'), logout:!!find('退出登录'),
  confirm:!!find('确认'), confirmAlt:!!find('确定')};
"""


def stop_logout_confirmation(driver):
    driver.execute_script("if(window.__iosLogoutConfirm) {"
                          "window.__iosLogoutConfirm.stop(); delete window.__iosLogoutConfirm; }")


def logout_customer_ios(driver, cycle_num, screenshot, timeout=20, login_marker='客户登录'):
    """timeout 为每个阶段的等待预算；远程调用耗时单独记录。"""
    if login_marker not in ('客户登录', '客户经理登录'):
        raise ValueError('不支持的登录页标识')
    started = time.monotonic()
    previous = driver.get_settings()
    confirmation_watcher = False
    script = (LOGOUT_SCRIPT if login_marker == '客户登录' else
              LOGOUT_SCRIPT.replace("document.body.innerText.includes('客户登录')",
                                    "document.body.innerText.includes('客户经理登录')"))
    if login_marker == '客户经理登录':
        script = script.replace('e.innerText.trim()===text',
                                "e.innerText.replace(/\\s/g,'')===text")
        script = script.replace('c.innerText.trim()===text',
                                "c.innerText.replace(/\\s/g,'')===text")
    try:
        driver.update_settings({'waitForIdleTimeout': 0})
        context = next((c for c in driver.contexts if 'WEBVIEW' in c), None)
        if context is None:
            raise RuntimeError('退出登录未找到业务 WebView')
        driver.switch_to.context(context)
        deadline = time.monotonic() + timeout
        action = None
        pending = None
        stage = '查找登出入口'
        final_check = False
        while True:
            call_started = time.monotonic()
            if action == '退出登录':
                confirmation_watcher = True
            state = driver.execute_script(script, action)
            now = time.monotonic()
            call_elapsed = now - call_started
            if call_elapsed >= 2:
                print(f'    第{cycle_num}次 - 登出远程调用【{action or "读取状态"}】'
                      f'耗时 {call_elapsed:.2f}s，阶段：{stage}')
            if state['clicked']:
                print(f'    第{cycle_num}次 - 已点击【{action}】，累计 {time.monotonic() - started:.2f}s')
                pending = action
                # 点击完成后才开始等待下一页面，不能消耗前一阶段的余额。
                stage = {'我的': '等待登出入口', '退出登录': '等待确认弹窗',
                         '确认': '等待客户登录页', '确定': '等待客户登录页'}[action]
                deadline = now + timeout
                final_check = False
            if state.get('autoConfirmed') and pending not in ('确认', '确定'):
                pending = state['autoConfirmed']
                print(f'    第{cycle_num}次 - 页面内已点击登出【{pending}】，'
                      f'累计 {now - started:.2f}s，继续核验登录页')
                stage = '等待客户登录页'
                deadline = now + timeout
                final_check = False
            action = None
            if state['loggedOut']:
                print(f'    第{cycle_num}次 - 已确认返回登录页，登出耗时 {time.monotonic() - started:.2f}s')
                driver.switch_to.context('NATIVE_APP')
                screenshot(driver, f'step14_logout_confirm_{cycle_num}')
                return True
            if state['confirm'] and pending == '退出登录':
                action = '确认'
            elif state['confirmAlt'] and pending == '退出登录':
                action = '确定'
            elif state['logout'] and pending not in ('退出登录', '确认', '确定'):
                action = '退出登录'
            elif state['my'] and pending is None:
                action = '我的'
            # 新阶段已可操作时优先执行，避免慢查询返回后直接漏掉确认。
            next_stage = f'点击{action}' if action else stage
            if next_stage != stage:
                stage = next_stage
                deadline = now + timeout
                final_check = False
            if now >= deadline:
                if final_check:
                    raise RuntimeError(f'退出登录超时，未确认返回客户登录页（阶段：{stage}，'
                                       f'累计 {now - started:.2f}s，最后状态：{state}）')
                # 异步跳转可能在当前查询后完成；超时前再做一次只读核验。
                final_check = True
                action = None
                continue
            if action is None:
                time.sleep(.15)
    except Exception:
        driver.switch_to.context('NATIVE_APP')
        screenshot(driver, f'error_step14_logout_{cycle_num}')
        raise
    finally:
        if confirmation_watcher:
            try:
                driver.switch_to.context(context)
                stop_logout_confirmation(driver)
            except Exception as error:
                print(f'    登出确认监听清理失败（监听最多保留20s）：{error}')
        driver.switch_to.context('NATIVE_APP')
        driver.update_settings({'waitForIdleTimeout': previous.get('waitForIdleTimeout', 10)})
