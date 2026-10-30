"""仅处理现场 AI 的 OCR 人工确认弹窗，不点击环境检测或其他页面的跳过。"""
import time
from time import perf_counter
from ios_phase_timing import timed_call, timed_flow
from appium.webdriver.common.appiumby import AppiumBy
from self_service_signature import native_point
from scene_fast_paths import NODE_SCRIPT


OCR_SCRIPT = r"""
const clean=s=>(s||'').replace(/\s/g,'');
if(!clean(document.body.innerText).includes('OCR识别人工确认'))return {present:false};
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
const nodes=Array.from(document.querySelectorAll('*'));
const title=nodes.find(e=>clean(e.textContent)==='OCR识别人工确认'&&visible(e));
if(!title)return {present:false};
let panel=title.closest('[role="dialog"],.van-dialog,.van-popup,.el-dialog');
if(!panel){for(let p=title.parentElement;p&&p!==document.body;p=p.parentElement){
 if(Array.from(p.querySelectorAll('button,[role="button"]')).some(e=>clean(e.textContent)==='跳过'&&visible(e))){panel=p;break;}
}}
if(!panel)return {present:true,ready:false};
const text=clean(panel.innerText);
const skip=Array.from(panel.querySelectorAll('button,[role="button"],a,span'))
 .find(e=>clean(e.textContent)==='跳过'&&visible(e)&&
 !e.closest('[disabled],[aria-disabled="true"],.van-button--disabled'));
if(!skip)return {present:true,ready:false};
const r=skip.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
const ready=!!top&&(top===skip||skip.contains(top)||top.contains(skip));
let clicked=false;
if(arguments[0]&&ready&&text===arguments[1]){skip.click();clicked=true;}
return {present:true,ready,clicked,key:text,side:/人像|姓名|身份证号码/.test(text)?'人像面':
 /国徽|签发机关|有效期限|有效期/.test(text)?'国徽面':'证件面',
 width:innerWidth,height:innerHeight,rect:{x:r.x,y:r.y,width:r.width,height:r.height}};
"""


def read_ocr(driver, click=False, key=None):
    try:
        for context in timed_call('OCR/上下文枚举', lambda: driver.contexts):
            if 'WEBVIEW' in context:
                timed_call('OCR/进入WebView', driver.switch_to.context, context)
                state = (timed_call('OCR/弹窗核验及DOM点击', driver.execute_script, OCR_SCRIPT, True, key)
                         if click else timed_call('OCR/弹窗DOM读取', driver.execute_script, OCR_SCRIPT))
                if state['present']:
                    return state
        return dict(present=False)
    finally:
        timed_call('OCR/返回原生上下文', driver.switch_to.context, 'NATIVE_APP')


@timed_flow('OCR/弹窗处理总计（含轮询间隔）')
def skip_ocr_confirmations(driver, timeout=30, initial_state=None, dom_click=False):
    deadline = time.monotonic() + timeout
    pending = None
    clicked_at = None
    clicks = 0
    observed_at = None
    observed_side = None
    while time.monotonic() < deadline:
        state = initial_state if initial_state is not None else read_ocr(driver)
        initial_state = None
        if observed_at is not None and (not state['present'] or state.get('key') != pending):
            print(f'    [耗时细分] OCR/{observed_side}/点击请求返回至关闭或切面核验: '
                  f'{perf_counter()-observed_at:.3f}s（含状态读取及轮询间隔）')
            observed_at = None
        if not state['present']:
            if pending is not None:
                print('    [AI OCR] 已核验人工确认弹窗关闭，继续业务节点')
            return clicks
        if pending is not None and state.get('key') == pending:
            if time.monotonic()-clicked_at >= 8:
                raise RuntimeError('AI OCR 点击跳过后弹窗未关闭或切换，停止重复点击')
            time.sleep(.15)
            continue
        if state.get('ready'):
            if clicks >= 2:
                raise RuntimeError('AI OCR 连续出现超过两个证件面确认弹窗')
            if dom_click:
                checked = read_ocr(driver, click=True, key=state['key'])
                if not checked.get('clicked'):
                    time.sleep(.15)
                    continue
            else:
                views = timed_call('OCR/原生WebView查找', driver.find_elements,
                                   AppiumBy.CLASS_NAME, 'XCUIElementTypeWebView')
                view = timed_call('OCR/WebView可见性及边界读取',
                                  lambda: next((e.rect for e in views if e.is_displayed()), None))
                if view is None:
                    raise RuntimeError('AI OCR 未找到可见 WebView，拒绝盲点跳过')
                state['view'] = view
                point = timed_call('OCR/坐标换算', native_point, state, state['rect'])
                timed_call(f'OCR/{state["side"]}/跳过点击请求', driver.tap, [point])
            pending, clicked_at = state['key'], time.monotonic()
            observed_at, observed_side = perf_counter(), state['side']
            clicks += 1
            print(f'    [AI OCR] 已点击{state["side"]}人工确认弹窗“跳过”，等待关闭或切换')
        time.sleep(.15)
    raise RuntimeError('AI OCR 人工确认弹窗处理超时')


AI_NODE_SCRIPT = (
    'const ocr=(function(){' + OCR_SCRIPT + '})();'
    'if(ocr.present)return {ocr};'
    'let node=(function(){' + NODE_SCRIPT + '}).apply(null,arguments);'
    'if(arguments[2]&&node.next&&!node.signature&&!node.finish&&!node.review&&node.progress&&'
    'node.progress[0]>=1&&node.progress[0]<=node.progress[1]){'
    'node=(function(){' + NODE_SCRIPT + '}).apply(null,[true,node.progress]);}'
    'return {node};'
)


class AINodeReader:
    """单个节点推进阶段复用上下文；原生签名/OCR 后显式失效。"""
    def __init__(self):
        self.context = None
        self.active = False
        self.reads = 0
        self.switches = 0
        self.elapsed = 0
        self.last_ocr_closed_at = None

    def invalidate(self):
        self.active = False

    def __call__(self, driver, click=False, progress=None, advance=False):
        started = time.monotonic()
        try:
            while True:
                if self.context is None:
                    self.context = next((c for c in driver.contexts if 'WEBVIEW' in c), None)
                    if self.context is None:
                        raise RuntimeError('AI 节点读取未找到 WebView')
                if not self.active:
                    driver.switch_to.context(self.context)
                    self.active = True
                    self.switches += 1
                result = (driver.execute_script(AI_NODE_SCRIPT, click, progress, True)
                          if advance else driver.execute_script(AI_NODE_SCRIPT, click, progress))
                self.reads += 1
                if 'ocr' in result:
                    driver.switch_to.context('NATIVE_APP')
                    self.invalidate()
                    skip_ocr_confirmations(driver, initial_state=result['ocr'], dom_click=True)
                    self.last_ocr_closed_at = perf_counter()
                    continue
                state = result['node']
                if state['progress'] is not None:
                    state['progress'] = tuple(state['progress'])
                return state
        except Exception:
            self.context = None
            self.invalidate()
            driver.switch_to.context('NATIVE_APP')
            raise
        finally:
            self.elapsed += time.monotonic() - started


def ai_node_snapshot(driver, click=False, progress=None):
    # 与人工节点共用进度、可见性及命中校验；正常轮询只读取一次页面。
    while True:
        try:
            context = next((c for c in driver.contexts if 'WEBVIEW' in c), None)
            if context is None:
                raise RuntimeError('AI 节点读取未找到 WebView')
            driver.switch_to.context(context)
            result = driver.execute_script(AI_NODE_SCRIPT, click, progress)
        finally:
            driver.switch_to.context('NATIVE_APP')
        if 'ocr' in result:
            skip_ocr_confirmations(driver, initial_state=result['ocr'])
            # 弹窗关闭后重新核验当前进度，禁止沿用关闭前的按钮状态。
            continue
        state = result['node']
        if state['progress'] is not None:
            state['progress'] = tuple(state['progress'])
        return state
