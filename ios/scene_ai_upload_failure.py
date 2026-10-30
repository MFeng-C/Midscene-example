"""仅对明确的上传失败执行界面退出，每步核验后再推进。"""
import time
import math
import xml.etree.ElementTree as ET
from ios_phase_timing import timed_call
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from self_service_signature import native_point

STATE_SCRIPT = r"""
const visible=e=>{const r=e.getBoundingClientRect();
 if(r.width<=0||r.height<=0)return false;
 for(let p=e;p;p=p.parentElement){const s=getComputedStyle(p);
  if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0')return false;}
 return true;};
const text=document.body.innerText.replace(/\s/g,'');
const compact=e=>(e.innerText||e.textContent||'').replace(/\s/g,'');
const candidates=Array.from(document.querySelectorAll('button,[role="button"],a,span,div'));
const exact=(scope,label)=>candidates.filter(e=>scope.contains(e)&&compact(e)===label&&visible(e)&&
 !e.closest('[disabled],[aria-disabled="true"],.van-button--disabled'))
 .filter(e=>!Array.from(e.children).some(c=>compact(c)===label&&visible(c)));
// 将文字节点提升到同文案的按钮容器，白底/描边颜色不参与禁用判定。
const control=(e,scope,label)=>{
 let b=e;
 for(let p=e.parentElement;p&&p!==scope&&scope.contains(p);p=p.parentElement){
  if(compact(p)!==label)break;
  if(!visible(p)||p.closest('[disabled],[aria-disabled="true"],.van-button--disabled'))break;
  // 优先使用真实按钮。描边按钮通常远宽于内部文字，不能用宽度比拒绝它。
  if(p.tagName==='BUTTON'||p.tagName==='A'||p.getAttribute?.('role')==='button')return p;
  // 顶部结束不能提升为整条页头，否则触摸中心可能落在空白处。
  // 这个限制仅用于顶部自定义结束控件，不用于弹窗取消/确认。
  if(label!=='结束'||p.getBoundingClientRect().width<=e.getBoundingClientRect().width*3)b=p;
 }
 return b;
};
const dialogs=Array.from(document.querySelectorAll('.van-dialog,[role="dialog"],.el-dialog,.el-message-box,.v-dialog,.modal')).filter(visible);
// 自定义弹窗可能没有组件类名，按标题及操作按钮寻找最小可见容器。
for(const token of ['上传失败','结束办理']){
 const titles=candidates.filter(e=>visible(e)&&compact(e).includes(token)&&
  !Array.from(e.children).some(c=>compact(c).includes(token)));
 for(const title of titles){
  for(let p=title.parentElement;p&&p!==document.body;p=p.parentElement){
   if(visible(p)&&exact(p,'确认').length&&exact(p,'取消').length){dialogs.push(p);break;}
  }
 }
}
const uniqueDialogs=[...new Set(dialogs)];
const failure=uniqueDialogs.filter(d=>compact(d).includes('文件上传失败'));
const ending=uniqueDialogs.filter(d=>/结束办理/.test(compact(d)));
const phase=arguments[0];
const scopes=phase==='cancel'?failure:phase==='confirm'?ending:[document.body];
const label={cancel:'取消',end:'结束',confirm:'确认'}[phase];
let clicked=false,tapTarget=null,reason='observe',candidateCount=0,rawCandidateCount=0,targetTag=null,hitTag=null;
if(label&&(phase!=='end'||dialogs.length===0)){
 let buttons=[...new Set(scopes.flatMap(s=>exact(s,label).map(e=>control(e,s,label))))];
 rawCandidateCount=buttons.length;
 if(phase==='end'){
  // 回看页中可能保留多个“结束”节点；只允许点击当前视口右上方的控件。
  // 使用 WebView CSS 视口尺寸，不依赖手机截图像素或横竖屏固定坐标。
  const width=document.documentElement.clientWidth,height=document.documentElement.clientHeight;
  buttons=buttons.filter(b=>{const r=b.getBoundingClientRect();
   if(r.x<0||r.y<0||r.x+r.width>width||r.y+r.height>height||
      r.x+r.width/2<width*.6||r.y+r.height>height*.25)return false;
   const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
   return top&&(top===b||b.contains(top));
  });
 }
 candidateCount=buttons.length;
 reason=buttons.length===0?'no_candidate':buttons.length>1?'ambiguous_candidates':'blocked';
 if(buttons.length===1){const b=buttons[0],r=b.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
 targetTag=b.tagName;hitTag=top&&top.tagName;
 if(top&&(top===b||b.contains(top))){
  if(phase==='end'){
   tapTarget={rect:{x:r.x,y:r.y,width:r.width,height:r.height},
    width:document.documentElement.clientWidth,height:document.documentElement.clientHeight};
   reason='native_touch_ready';
  }else{b.click();clicked=true;reason='clicked';}
 }}
}else if(label){reason='dialog_still_open';
}
return {clicked,failed:text.includes('业务办理失败')&&dialogs.length===0,
 failureDialog:failure.length>0,endingDialog:ending.length>0,dialogCount:uniqueDialogs.length,
 reason,candidateCount,rawCandidateCount,targetTag,hitTag,tapTarget};
"""


def webview_region(source):
    """本地解析当前原生树，隐藏父节点下的 WebView 不参与边界映射。"""
    regions = {}
    def collect(element):
        if element.get('visible') == 'false':
            return
        if element.get('type', element.tag) == 'XCUIElementTypeWebView':
            view = {k: float(element.get(k, '0')) for k in ('x', 'y', 'width', 'height')}
            if all(math.isfinite(v) for v in view.values()) and view['width'] > 0 and view['height'] > 0:
                regions[tuple(view.values())] = view
        for child in element:
            collect(child)
    collect(ET.fromstring(source))
    if len(regions) != 1:
        raise RuntimeError(f'结束控件原生触摸无法确定唯一 WebView 区域：有效区域={list(regions)}')
    return next(iter(regions.values()))


def tap_end_control(driver, target, context):
    """由当前 DOM 边界换算原生触摸，不使用固定手机像素或合成 DOM 点击。"""
    rect = target['rect']
    width, height = target['width'], target['height']
    if (width <= 0 or height <= 0 or rect['width'] <= 0 or rect['height'] <= 0
            or rect['x'] < width * .6 - rect['width'] / 2 or rect['y'] < 0
            or rect['x'] + rect['width'] > width
            or rect['y'] + rect['height'] > height * .25):
        raise RuntimeError('结束控件边界无效，拒绝原生触摸')
    try:
        timed_call('上传异常/切换原生上下文', driver.switch_to.context, 'NATIVE_APP')
        source = timed_call('上传异常/原生页面单次读取', lambda: driver.page_source)
        view = timed_call('上传异常/WebView边界本地解析', webview_region, source)
        x, y = native_point(dict(view=view, width=width, height=height), rect)
        actions = ActionBuilder(driver, mouse=PointerInput('touch', 'end-recording'), duration=80)
        actions.pointer_action.move_to_location(x, y)
        actions.pointer_action.pointer_down()
        actions.pointer_action.pause(.1)
        actions.pointer_action.pointer_up()
        timed_call('上传异常/结束原生触摸', actions.perform)
    finally:
        timed_call('上传异常/恢复WebView上下文', driver.switch_to.context, context)


def close_failed_upload(driver, cycle_num, return_to_list, logout, timeout=20):
    """不重试已发出的点击；失败页确认后才返回列表及登出。"""
    try:
        context = next((c for c in driver.contexts if 'WEBVIEW' in c), None)
        if context is None:
            raise RuntimeError('上传失败退出未找到 WebView')
        driver.switch_to.context(context)
        pending_end = None
        for phase in ('cancel', 'end', 'confirm', 'failed'):
            deadline = time.monotonic() + timeout
            sent = False
            while True:
                if phase == 'end' and pending_end is not None:
                    state, pending_end = pending_end, None
                else:
                    # end 查询只定位不点击：在核验取消弹窗消失时一并取得结束位置。
                    query = 'end' if phase == 'cancel' and sent else 'observe' if sent else phase
                    state = timed_call('上传异常/页面核验及控件定位', driver.execute_script, STATE_SCRIPT, query)
                    if phase == 'cancel' and sent and not state.get('failureDialog', True) and state.get('tapTarget'):
                        pending_end = dict(state)
                if phase == 'end' and not sent and state.get('tapTarget'):
                    tap_end_control(driver, state['tapTarget'], context)
                    state['clicked'] = True
                    print(f'    第{cycle_num}次 - 已发送顶部结束控件原生触摸，等待结束办理弹窗')
                sent = sent or state['clicked']
                # 只点击一次，必须看到弹窗消失/下一弹窗出现后才推进。
                ready = state['failed'] if phase == 'failed' else sent
                if phase == 'cancel' and 'failureDialog' in state:
                    ready = sent and not state['failureDialog']
                elif phase == 'end' and 'endingDialog' in state:
                    ready = sent and state['endingDialog']
                elif phase == 'confirm' and 'endingDialog' in state:
                    ready = sent and not state['endingDialog']
                if ready:
                    label = {'cancel': '点击上传失败弹窗取消', 'end': '点击结束',
                             'confirm': '确认结束办理', 'failed': '核验业务办理失败页面'}[phase]
                    print(f'    第{cycle_num}次 - {label}完成')
                    break
                if time.monotonic() >= deadline:
                    label = {'cancel': '上传失败弹窗取消', 'end': '结束',
                             'confirm': '结束办理弹窗确认', 'failed': '业务办理失败页面核验'}[phase]
                    raise RuntimeError(f'上传失败退出步骤超时：{label}（{phase}，点击已发送={sent}，'
                                       f'失败弹窗={state.get("failureDialog")}，结束弹窗={state.get("endingDialog")}，'
                                       f'定位原因={state.get("reason")}，候选数={state.get("candidateCount")}，'
                                       f'原始候选数={state.get("rawCandidateCount")}，'
                                       f'按钮标签={state.get("targetTag")}，命中标签={state.get("hitTag")}）')
                time.sleep(.2)
    finally:
        driver.switch_to.context('NATIVE_APP')
    return_to_list()
    logout()
