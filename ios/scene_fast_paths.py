"""现场人工双录专用 WebView 快速路径；不修改客户纯录制调用。"""
import time
from pure_recording_search import SEARCH_SCRIPT


OPEN_SEARCH_SCRIPT = r"""
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
const fields=Array.from(document.querySelectorAll('input')).filter(visible);
if(fields.some(e=>e.name==='orderId'||(e.placeholder||'').includes('订单号')))return {opened:true};
// 真机结构：筛选事件绑定在导航栏右侧容器，不能只点击内部装饰性 i/svg。
const right=document.querySelector('.van-nav-bar__right');
if(right&&visible(right)&&right.querySelector('svg')){
 const r=right.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
 // 真机验证：合成 click 不展开表单，必须交给原生触摸。
 if(top&&(top===right||right.contains(top)))return {opened:false,entry:'nav-right',nativeTap:true};
}
const candidates=Array.from(document.querySelectorAll('button,a,[role="button"],i,span,div,svg,img'));
const matches=candidates.filter(e=>{
 if(!visible(e))return false;
 const text=(e.textContent||'').trim();
 const hint=['aria-label','title','class','src','data-icon'].map(k=>e.getAttribute(k)||'').join(' ');
 return ['全局搜索','高级搜索','筛选'].includes(text)||/filter|filtrate|funnel|shaixuan/i.test(hint)||
  /^(搜索|筛选|全局搜索)$/.test(e.getAttribute('aria-label')||'');
});
// 图标可能没有文字或类名：仅在现场页的顶部导航右侧寻找小图标。
if((document.body.innerText||'').replace(/\s/g,'').includes('现场双录')){
 for(const e of candidates){const r=e.getBoundingClientRect();
  if(visible(e)&&r.x>innerWidth*.75&&r.y>=0&&r.y<innerHeight*.16&&
     r.width<=64&&r.height<=64&&
     (['svg','img','i'].includes(e.tagName.toLowerCase())||e.getAttribute('role')==='button'))
   if(!matches.includes(e))matches.push(e);
 }
}
for(const button of matches){const r=button.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
 if(top&&(button===top||button.contains(top)||top.contains(button))){
  const target=button.closest('button,a,[role="button"]')||button;
  target.click();return {opened:true,entry:target.tagName};}}
return {opened:false,candidates:matches.length};
"""

QUERY_SCRIPT = r"""
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
const button=Array.from(document.querySelectorAll('button,[role="button"]'))
 .find(e=>e.textContent.trim()==='查询'&&visible(e)&&!e.disabled);
if(!button)return false;
const r=button.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
if(!top||!(button===top||button.contains(top)||top.contains(button)))return false;
button.click();return true;
"""

RESULT_SCRIPT = r"""
const text=document.body.innerText;
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
return text.includes(arguments[0])&&text.includes(arguments[1])&&
 !Array.from(document.querySelectorAll('button,[role="button"]')).some(e=>e.textContent.trim()==='查询'&&visible(e))&&
 Array.from(document.querySelectorAll('button,[role="button"]')).some(e=>e.textContent.trim()==='录制'&&visible(e));
"""


def search_scene_order(driver, cycle_num, order_id, customer_name, switch_to_webview,
                       fallback, click_result, timeout=3):
    started = time.monotonic()
    prepared = False
    try:
        if switch_to_webview(driver):
            entry = driver.execute_script(OPEN_SEARCH_SCRIPT)
            opened = entry['opened']
            print(f'    现场搜索入口：{entry}')
            if not opened:
                # 无文字筛选图标沿用已验证的原生入口坐标，但表单仍通过 DOM 填写，
                # 避免进入兼容路径的原生逐字段输入和完整收键盘链路。
                driver.switch_to.context('NATIVE_APP')
                size = driver.get_window_size()
                driver.tap([(int(size['width'] * .90), int(size['height'] * .07))])
                opened = switch_to_webview(driver)
            deadline = time.monotonic() + timeout
            while opened and time.monotonic() < deadline:
                state = driver.execute_script(SEARCH_SCRIPT, order_id, customer_name, False)
                if state['ready']:
                    prepared = True
                    break
                time.sleep(.15)
    except Exception as error:
        print(f'    现场搜索 DOM 准备异常：{type(error).__name__}，转兼容路径')
    finally:
        driver.switch_to.context('NATIVE_APP')
    if not prepared:
        print(f'    现场搜索 DOM 准备未完成，使用兼容路径（耗时 {time.monotonic()-started:.2f}s）')
        return fallback(driver, cycle_num, fast_search=True, dom_search=True,
                        order_id=order_id, customer_name=customer_name)
    print(f'    现场搜索入口及输入、失焦耗时 {time.monotonic()-started:.2f}s')
    # DOM 填写不聚焦输入框；仅确有键盘时才收起，避免完整收键盘兜底链。
    keyboard_started = time.monotonic()
    if driver.is_keyboard_shown():
        driver.hide_keyboard()
        if driver.is_keyboard_shown():
            raise RuntimeError('现场搜索键盘未隐藏，停止查询')
    print(f'    现场搜索键盘状态核验耗时 {time.monotonic()-keyboard_started:.2f}s')
    try:
        if not switch_to_webview(driver):
            raise RuntimeError('现场搜索查询时 WebView 不可用')
        if not driver.execute_script(QUERY_SCRIPT):
            raise RuntimeError('现场搜索未找到可点击的查询按钮')
        deadline = time.monotonic() + 15
        while not driver.execute_script(RESULT_SCRIPT, order_id, customer_name):
            if time.monotonic() >= deadline:
                raise RuntimeError('现场搜索未出现目标订单和客户的查询结果')
            time.sleep(.2)
    finally:
        driver.switch_to.context('NATIVE_APP')
    if not click_result(driver):
        raise RuntimeError('现场搜索结果录制按钮点击后未出现确认弹窗')
    print(f'    第{cycle_num}次 - 已查询并打开现场目标订单，累计 {time.monotonic()-started:.2f}s')
    return True


NODE_SCRIPT = r"""
const clean=s=>(s||'').replace(/\s/g,'');
const text=clean(document.body.innerText);
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
// 优先语义控件；不要为每个按钮遍历整页 div 并读取布局。
const controls=Array.from(document.querySelectorAll('button,a,[role="button"]'));
let extra=null;
const matchControl=(items,t)=>items.find(e=>clean(e.textContent)===t&&visible(e)&&
 !e.closest('[disabled],[aria-disabled="true"],.van-button--disabled')&&
 !Array.from(e.children).some(c=>clean(c.textContent)===t&&visible(c)));
const find=t=>matchControl(controls,t)||matchControl(extra||(extra=Array.from(document.querySelectorAll('span,div'))),t);
// 进度与评分可能是相邻节点；不能先删除整页空白再解析，1/4 + 95 会变成 1/495。
const progressPattern=/^\s*进度\s*[:：]?\s*(\d+)\s*\/\s*(\d+)\s*$/;
const progressElements=Array.from(document.querySelectorAll('span,div,p,label,[role="status"]'))
 .filter(e=>progressPattern.test(e.textContent||'')&&visible(e))
 .sort((a,b)=>(a.innerText||a.textContent).length-(b.innerText||b.textContent).length);
const match=progressElements.length
 ? (progressElements[0].innerText||progressElements[0].textContent).match(progressPattern)
 : document.body.innerText.match(/进度\s*[:：]?\s*(\d+)\s*\/\s*(\d+)(?!\d)/);
const next=find('下一步');let clicked=false;
if(arguments[0]&&next&&match&&Number(match[1])===arguments[1][0]&&Number(match[2])===arguments[1][1]){
 const r=next.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
 if(top&&(top===next||next.contains(top)||top.contains(next))){next.click();clicked=true;}}
return {progress:match?[Number(match[1]),Number(match[2])]:null,
 signature:text.includes('请客户经理进行签字'),finish:!!find('完成录制'),
 review:!!find('确认完成'),next:!!next,clicked};
"""


def node_snapshot(driver, click=False, progress=None):
    try:
        context = next((c for c in driver.contexts if 'WEBVIEW' in c), None)
        if context is None:
            raise RuntimeError('人工节点读取未找到 WebView')
        driver.switch_to.context(context)
        state = driver.execute_script(NODE_SCRIPT, click, progress)
        if state['progress'] is not None:
            state['progress'] = tuple(state['progress'])
        return state
    finally:
        driver.switch_to.context('NATIVE_APP')
