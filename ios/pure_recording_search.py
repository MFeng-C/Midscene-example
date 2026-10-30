"""纯录制搜索表单快速路径；不提交查询，后续仍核验订单和录制确认弹窗。"""
import time


SEARCH_SCRIPT = r"""
const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&
 getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';};
const inputs=Array.from(document.querySelectorAll('input')).filter(e=>visible(e)&&!e.disabled&&!e.readOnly);
const field=word=>inputs.find(e=>[e.placeholder,e.getAttribute('aria-label'),e.name,
 e.closest('.van-field')?.innerText].some(v=>(v||'').includes(word)));
const order=field('订单号'),customer=field('客户名称');
if(order && customer && order!==customer) {
 const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
 for(const [e,value] of [[order,arguments[0]],[customer,arguments[1]]]) {
  set.call(e,value);e.dispatchEvent(new Event('input',{bubbles:true}));
  e.dispatchEvent(new Event('change',{bubbles:true}));
 }
 document.activeElement?.blur();
 return {ready:order.value===arguments[0]&&customer.value===arguments[1],opened:false};
}
if(arguments[2]) {
 const e=Array.from(document.querySelectorAll('button,a,span,div,[role="button"]'))
  .find(e=>['全局搜索','高级搜索'].includes(e.textContent.trim())&&visible(e)&&
   !Array.from(e.children).some(c=>['全局搜索','高级搜索'].includes(c.textContent.trim())));
 if(e) {const r=e.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
  if(top&&(e===top||e.contains(top)||top.contains(e))) {e.click();return {ready:false,opened:true};}}
}
return {ready:false,opened:false};
"""


def prepare_search(driver, order_id, customer_name, switch_to_webview, timeout=3):
    started = time.monotonic()
    try:
        if not switch_to_webview(driver):
            return False
        opened = False
        while True:
            state = driver.execute_script(SEARCH_SCRIPT, order_id, customer_name, not opened)
            opened = opened or state['opened']
            if state['ready']:
                print(f'    搜索表单填写并失焦耗时 {time.monotonic() - started:.2f}s')
                return True
            if time.monotonic() - started >= timeout:
                return False
            time.sleep(.15)
    except Exception as error:
        print(f'    搜索快速路径不可用，使用原生兜底：{type(error).__name__}')
        return False
    finally:
        driver.switch_to.context('NATIVE_APP')


def confirm_keyboard_hidden(driver, fallback):
    """快速路径不聚焦输入框；仍通过原生状态确认键盘已关闭。"""
    try:
        if driver.is_keyboard_shown() is False:
            return True
    except Exception:
        pass
    return fallback(driver)
