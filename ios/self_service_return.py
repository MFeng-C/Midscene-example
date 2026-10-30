"""自助双录完成页到个人页的连续状态驱动导航。"""
import time


RETURN_TO_MY_SCRIPT = r"""
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
const find=text=>Array.from(document.querySelectorAll('button,a,[role="button"],span,div'))
 .find(e=>e.textContent.trim()===text && visible(e) &&
  !e.closest('[disabled],[aria-disabled="true"]') &&
  !Array.from(e.children).some(c=>c.textContent.trim()===text));
const text=document.body.innerText;
const complete=text.includes('业务办理完成');
let clicked=null;
if(complete && !arguments[0]) {
 const back=find('返回');
 if(back) {back.click();clicked='返回';}
} else if(!complete && /订单|自助/.test(text) && !arguments[1]) {
 const my=find('我的');
 if(my) {my.click();clicked='我的';}
}
return {clicked, complete, myReady:!complete && !!find('退出登录')};
"""


def return_and_open_my(driver, cycle_num, screenshot, timeout=20):
    started = time.monotonic()
    returned = opened_my = False
    final_check = False
    try:
        context = next((c for c in driver.contexts if 'WEBVIEW' in c), None)
        if context is None:
            raise RuntimeError('完成页返回失败：未找到业务 WebView')
        driver.switch_to.context(context)
        deadline = time.monotonic() + timeout
        while True:
            call_started = time.monotonic()
            state = driver.execute_script(RETURN_TO_MY_SCRIPT, returned, opened_my)
            now = time.monotonic()
            if now - call_started >= 2:
                print(f'    第{cycle_num}次 - 返回/我的页面调用耗时 {now - call_started:.2f}s')
            if state['clicked']:
                returned = returned or state['clicked'] == '返回'
                opened_my = opened_my or state['clicked'] == '我的'
                deadline = now + timeout
                final_check = False
                print(f'    第{cycle_num}次 - 已点击【{state["clicked"]}】，衔接累计 {now - started:.2f}s')
            if state['myReady']:
                print(f'    第{cycle_num}次 - 已确认进入我的页面，完成页至个人页耗时 {now - started:.2f}s')
                return True
            if now >= deadline:
                if final_check:
                    raise RuntimeError(f'完成页返回/进入我的页面超时，最后状态：{state}')
                final_check = True
            time.sleep(.15)
    except Exception:
        driver.switch_to.context('NATIVE_APP')
        screenshot(driver, f'error_self_return_my_{cycle_num}')
        raise
    finally:
        driver.switch_to.context('NATIVE_APP')
