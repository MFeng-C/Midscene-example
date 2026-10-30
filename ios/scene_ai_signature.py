"""AI 三字签名：复用人工笔迹校验，减少原生与 WebView 往返。"""
import time
from time import perf_counter

from scene_manual_signature import sign_scene_name
from self_service_signature import signature_snapshot, draw_test_signature
from scene_ai_ocr import AI_NODE_SCRIPT
from ios_phase_timing import timed_call, timed_flow


CONFIRM_SCRIPT = r"""
const label=arguments[0],rect=arguments[1];
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
const matches=Array.from(document.querySelectorAll('button,[role="button"]'))
 .filter(e=>e.innerText.trim()===label&&visible(e)&&!e.disabled&&
 e.getAttribute('aria-disabled')!=='true');
if(matches.length!==1)return false;
const b=matches[0],r=b.getBoundingClientRect();
if(Math.abs(r.x-rect.x)>1||Math.abs(r.y-rect.y)>1||
 Math.abs(r.width-rect.width)>1||Math.abs(r.height-rect.height)>1)return false;
const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
if(!top||!(b===top||b.contains(top)))return false;
b.click();return true;
"""


@timed_flow('AI签名/完整阶段（含逐字核验及衔接）')
def sign_ai_name(driver, cycle_num, character_count=3, timeout=90, ocr_closed_at=None):
    first_draw = True
    def read(d, **kwargs):
        return timed_call('AI签名/画布及笔迹读取', signature_snapshot,
                          d, keep_webview=True, **kwargs)

    def draw(d, state):
        nonlocal first_draw
        # 仅画笔动作走原生，仍必须在真实画布生成笔迹。
        timed_call('AI签名/进入原生触摸上下文', d.switch_to.context, 'NATIVE_APP')
        if first_draw and ocr_closed_at is not None:
            print(f'    [AI签名衔接] 最后一次OCR关闭核验至首字触摸开始: '
                  f'{perf_counter()-ocr_closed_at:.3f}s')
        first_draw = False
        draw_test_signature(d, state)

    def confirm(d, state, control):
        started = time.monotonic()
        if not d.execute_script(CONFIRM_SCRIPT, control['text'], control['rect']):
            raise RuntimeError('AI 签名确认控件已变化、被遮挡或不可点击')
        print(f'    [AI签名分段] {control["text"]}点击: {time.monotonic()-started:.2f}s')

    def complete(d):
        started = time.monotonic()
        deadline = started + 30
        while True:
            print('    [AI签名衔接] 发起节点读取请求')
            result = timed_call('AI签名衔接/节点读取请求', d.execute_script,
                                AI_NODE_SCRIPT, False, None)
            if 'ocr' in result:
                raise RuntimeError('AI 签名结束后仍存在 OCR 弹窗，停止推进')
            state = result['node']
            progress = state['progress']
            if progress is not None and not 1 <= progress[0] <= progress[1]:
                raise RuntimeError('AI 签名结束后进度无效')
            if (progress is not None and state['next'] and not state.get('signature')
                    and not state.get('finish') and not state.get('review')):
                print('    [AI签名衔接] 发起下一步校验及点击请求')
                result = timed_call('AI签名衔接/下一步校验及点击请求', d.execute_script,
                                    AI_NODE_SCRIPT, True, progress)
                if 'ocr' in result:
                    raise RuntimeError('AI 签名衔接时出现 OCR 弹窗，停止点击')
                state = result['node']
            print(f'    [AI签名衔接] 进度={state["progress"]}，下一步={state["next"]}，'
                  f'签字页={state.get("signature", False)}，已点击={state["clicked"]}，'
                  f'完成录制={state.get("finish", False)}，回看={state.get("review", False)}，'
                  f'累计 {time.monotonic()-started:.2f}s')
            if state['clicked'] or state.get('finish') or state.get('review'):
                if state['progress'] is not None:
                    state['progress'] = tuple(state['progress'])
                return state
            if time.monotonic() >= deadline:
                raise RuntimeError('AI 签名提交后30秒内未能点击下一步或进入完成录制/回看页')
            time.sleep(.2)

    return sign_scene_name(driver, cycle_num, character_count=character_count, timeout=timeout,
                           snapshot_reader=read, draw_action=draw, confirm_action=confirm,
                           on_complete=complete, on_submit=complete, completion_timeout=30)
