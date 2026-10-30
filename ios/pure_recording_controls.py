"""纯录制暂停恢复：使用 WebView 命中检查和业务状态确认，避免横屏坐标误点。"""
import time


TOOLBAR_SCRIPT = r"""
const label=arguments[0];
if(!['暂停','截图'].includes(label)) return false;
const e=Array.from(document.querySelectorAll('button,a,span,div,[role="button"]')).find(e=>{
 if(e.textContent.trim()!==label || e.closest('[disabled],[aria-disabled="true"],.van-button--disabled')) return false;
 if(Array.from(e.children).some(c=>c.textContent.trim()===label)) return false;
 const r=e.getBoundingClientRect();
 if(r.width<=0||r.height<=0||r.top<0||r.bottom>innerHeight*.25) return false;
 const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
 return top&&(top===e||e.contains(top)||top.contains(e));
});
if(!e) return false;
(e.closest('button,[role="button"]')||e).click();
return true;
"""


def click_pure_toolbar(driver, label, switch_to_webview):
    try:
        if not switch_to_webview(driver):
            return False
        return driver.execute_script(TOOLBAR_SCRIPT, label) is True
    except Exception:
        return False
    finally:
        driver.switch_to.context('NATIVE_APP')


RESUME_SCRIPT = r"""
const visible = e => {
  const r=e.getBoundingClientRect();
  if (!r.width || !r.height) return false;
  for(let p=e;p;p=p.parentElement) {
    const s=getComputedStyle(p);
    if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
  }
  return true;
};
const find = text => Array.from(document.querySelectorAll('button,a,span,div,[role="button"]'))
  .filter(e => e.textContent.trim()===text && visible(e) &&
    !Array.from(e.children).some(c => c.textContent.trim()===text));
const hit = e => {
  const r=e.getBoundingClientRect();
  const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
  return top && (top===e||e.contains(top)||top.contains(e));
};
const resume=find('继续录制');
const paused=!!find('流程暂停中').length || !!resume.length;
let clicked=false;
if(arguments[0] && paused) {
  const e=resume.find(e => hit(e) &&
    !e.closest('[disabled],[aria-disabled="true"],.van-button--disabled'));
  if(e) { (e.closest('button,[role="button"]') || e).click(); clicked=true; }
}
// 返回点击前的状态，必须在下一次读取中确认跳转，不能把 click() 当作成功。
return {paused, recording:find('暂停').some(hit), clicked};
"""


def ensure_pure_recording_resumed(driver, cycle_num, switch_to_webview, timeout=20):
    try:
        if not switch_to_webview(driver):
            raise RuntimeError('继续录制失败：未找到录制 WebView')
        deadline = time.monotonic() + timeout
        attempts = 0
        next_click = 0
        while True:
            now = time.monotonic()
            state = driver.execute_script(RESUME_SCRIPT, attempts < 3 and now >= next_click)
            if not state['paused'] and state['recording']:
                print(f'    第{cycle_num}次 - 已确认暂停弹窗关闭，录制已恢复')
                return True
            if state['clicked']:
                attempts += 1
                next_click = time.monotonic() + 1
                print(f'    第{cycle_num}次 - 已发送继续录制点击（{attempts}/3），等待恢复确认')
            if time.monotonic() >= deadline:
                raise RuntimeError(f'继续录制失败：未确认暂停弹窗关闭及录制恢复，最后状态：{state}')
            time.sleep(.3)
    finally:
        driver.switch_to.context('NATIVE_APP')
