"""纯录制关键页面切换：以可见、可命中的业务状态验证操作结果。"""
import time


TRANSITION_SCRIPT = r"""
const visible=e=>{
 const r=e.getBoundingClientRect();
 if(!r.width||!r.height) return false;
 for(let p=e;p;p=p.parentElement) {
  const s=getComputedStyle(p);
  if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
 }
 const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
 return top && (top===e||e.contains(top)||top.contains(e));
};
const find=(text,root=document)=>Array.from(root.querySelectorAll('button,a,[role="button"],span,div'))
 .find(e=>e.textContent.trim()===text && visible(e) &&
  !e.closest('[disabled],[aria-disabled="true"],.van-button--disabled') &&
  !Array.from(e.children).some(c=>c.textContent.trim()===text));
const dialogs=Array.from(document.querySelectorAll('[role="dialog"],.van-dialog,.el-message-box,.modal'))
 .filter(visible);
const dialogConfirm=pattern=>{
 const dialog=dialogs.find(e=>pattern.test(e.innerText));
 return dialog && (find('确认',dialog)||find('确定',dialog));
};
const risk=dialogConfirm(/风险|跳过|检测/);
const upload=dialogConfirm(/上传成功/);
const text=document.body.innerText;
let target=null;
switch(arguments[0]) {
 case '跳过': target=find('跳过'); break;
 case '风险确认': target=risk; break;
 case '开始录制': target=find('开始录制'); break;
 case '上传确认': target=upload; break;
 case '返回': if(text.includes('业务办理完成')) target=find('返回'); break;
}
let clicked=false;
if(target) {(target.closest('button,[role="button"]')||target).click();clicked=true;}
const complete=text.includes('业务办理完成');
return {clicked,skip:!!find('跳过'),risk:!!risk,start:!!find('开始录制'),
 recording:!!find('暂停'),uploadSuccess:text.includes('上传成功'),uploadConfirm:!!upload,
 end:!!find('结束'),complete,
 list:!complete && !!find('我的') && /订单/.test(text) && /纯录制|录制订单|订单列表/.test(text),
 text:text.slice(-500)};
"""


def _run(driver, cycle_num, screenshot, phase, advance, timeout):
    """各阶段独立预算；远程调用返回后先检查结果，超时只读核验一次。"""
    try:
        context = next((c for c in driver.contexts if 'WEBVIEW' in c), None)
        if context is None:
            raise RuntimeError(f'{phase}：未找到业务 WebView')
        driver.switch_to.context(context)
        stage = None
        deadline = time.monotonic() + timeout
        action = None
        final_check = False
        while True:
            state = driver.execute_script(TRANSITION_SCRIPT, action)
            if action and state['clicked']:
                print(f'    第{cycle_num}次 - 已点击【{action}】，等待业务状态核验')
            done, next_stage, next_action = advance(state, action)
            if done:
                print(f'    第{cycle_num}次 - 已核验{next_stage}')
                return True
            now = time.monotonic()
            if next_stage != stage:
                first_read = stage is None
                stage = next_stage
                if not first_read:
                    deadline = now + timeout
                    final_check = False
                print(f'    第{cycle_num}次 - {stage}')
            if now >= deadline:
                if final_check:
                    raise RuntimeError(f'{phase}超时（阶段：{stage}），最后状态：{state}')
                final_check = True
                action = None
            else:
                action = next_action
            time.sleep(.2)
    except Exception:
        driver.switch_to.context('NATIVE_APP')
        screenshot(driver, f'error_pure_transition_{phase}_{cycle_num}')
        raise
    finally:
        driver.switch_to.context('NATIVE_APP')


def detect_and_start(driver, cycle_num, screenshot, timeout):
    stage = '等待检测结果'

    def advance(s, action):
        nonlocal stage
        if action and s['clicked']:
            stage = {'跳过': '等待风险提示或开始录制', '风险确认': '等待开始录制',
                     '开始录制': '等待录制工具栏'}[action]
        if stage == '等待录制工具栏':
            if s['recording'] and not s['start'] and not s['risk']:
                return True, '录制已启动', None
            return False, stage, None
        if stage in ('等待检测结果', '等待风险提示或开始录制') and s['risk']:
            return False, stage, '风险确认'
        if s['start'] and not s['risk']:
            return False, stage, '开始录制'
        if stage == '等待检测结果' and s['skip']:
            return False, stage, '跳过'
        return False, stage, None

    return _run(driver, cycle_num, screenshot, '检测及开始录制', advance, timeout)


def wait_upload(driver, cycle_num, screenshot, timeout):
    success_seen = False
    confirmed = False

    def advance(s, action):
        nonlocal success_seen, confirmed
        success_seen = success_seen or s['uploadSuccess']
        confirmed = confirmed or (action == '上传确认' and s['clicked'])
        if success_seen and not s['uploadConfirm'] and (s['end'] or s['complete'] or s['list']):
            return True, '上传成功及后续页面', None
        if confirmed:
            return False, '等待上传确认弹窗关闭及后续页面', None
        return False, '等待上传成功', '上传确认' if success_seen and s['uploadConfirm'] else None

    return _run(driver, cycle_num, screenshot, '文件上传', advance, timeout)


def return_to_order_list(driver, cycle_num, screenshot, timeout):
    clicked = False

    def advance(s, action):
        nonlocal clicked
        clicked = clicked or (action == '返回' and s['clicked'])
        return s['list'], '纯录制订单列表' if s['list'] else '等待纯录制订单列表', None if clicked else '返回'

    return _run(driver, cycle_num, screenshot, '返回订单列表', advance, timeout)
