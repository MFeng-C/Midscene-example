"""iOS 自助双录测试签字：读取真实画布边界，通过原生触摸输入测试轨迹。"""
import time
import os
from ios_phase_timing import timed_call, timed_flow
from time import perf_counter

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput


SNAPSHOT_SCRIPT = r"""
const visible = e => {
  const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
};
const rect = e => {
  const r = e.getBoundingClientRect();
  return {x:r.x, y:r.y, width:r.width, height:r.height};
};
const text = document.body.innerText;
const controls = Array.from(document.querySelectorAll('button, [role="button"]'))
  .filter(visible).map(e => ({text:e.innerText.trim(),
    enabled:!e.disabled && e.getAttribute('aria-disabled') !== 'true', rect:rect(e)}));
const confirm = controls.find(e => ['确定','确认'].includes(e.text));
// 摄像头可能也使用全屏 canvas；签字画布必须位于签字确定按钮上方。
const canvases = Array.from(document.querySelectorAll('canvas')).filter(visible)
  .filter(e => {const r=rect(e); return confirm && r.width>=40 && r.height>=40 &&
    r.y>=0 && r.y+r.height<=confirm.rect.y+1;})
  .sort((a,b) => b.clientWidth*b.clientHeight-a.clientWidth*a.clientHeight);
const signaturePrompt = arguments[0] || '请客户进行签字';
const c = text.replace(/\s/g,'').includes(signaturePrompt) ? canvases[0] : null;
// 直接对像素计算笔迹指纹，避免每次 PNG 压缩和 base64 编码。
let ink = null;
if (c) {
  const data = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
  let hash = 2166136261;
  for (let i=0;i<data.length;i++) hash = Math.imul(hash ^ data[i],16777619);
  ink = c.width + 'x' + c.height + ':' + (hash >>> 0);
}
return {text, width:innerWidth, height:innerHeight, controls,
  canvas:c ? {rect:rect(c), ink} : null};
"""


@timed_flow('签名定位/完整读取（含原生定位）')
def signature_snapshot(driver, cache=None, signature_prompt='请客户进行签字', keep_webview=False):
    cache = cache if cache is not None else {}
    view = cache.get('view')
    if view is None:
        timed_call('签名定位/进入原生上下文', driver.switch_to.context, 'NATIVE_APP')
        views = timed_call('签名定位/原生WebView查询', driver.find_elements,
                           AppiumBy.CLASS_NAME, 'XCUIElementTypeWebView')
        for element in views:
            if timed_call('签名定位/WebView可见性请求', element.is_displayed):
                view = timed_call('签名定位/WebView边界请求', lambda: element.rect)
                break
    else:
        print('    [签名定位] 复用已核验的原生WebView边界缓存')
    if view is None:
        raise RuntimeError('签字页未找到可见 WebView，不能安全定位画布')
    started = time.monotonic()
    try:
        contexts = ([cache['context']] if cache.get('context') else
                    [c for c in timed_call('签名定位/上下文枚举请求', lambda: driver.contexts)
                     if 'WEBVIEW' in c])
        for context in contexts:
            timed_call('签名定位/进入WebView上下文', driver.switch_to.context, context)
            snapshot = (timed_call('签名定位/DOM画布及笔迹请求', driver.execute_script, SNAPSHOT_SCRIPT)
                        if signature_prompt == '请客户进行签字'
                        else timed_call('签名定位/DOM画布及笔迹请求', driver.execute_script,
                                        SNAPSHOT_SCRIPT, signature_prompt))
            # 旋转后重新读取原生 WebView 边界，禁止沿用旧坐标。
            dimensions = (snapshot['width'], snapshot['height'])
            if cache.get('dimensions', dimensions) != dimensions:
                print('    [签名定位] 视口尺寸变化，清除缓存并重新定位')
                cache.clear()
                return signature_snapshot(driver, cache, signature_prompt=signature_prompt,
                                          keep_webview=keep_webview)
            cache.update(view=view, context=context, dimensions=dimensions)
            if signature_prompt in ''.join(snapshot['text'].split()) or '业务办理完成' in snapshot['text']:
                snapshot['view'] = view
                return snapshot
        # 等待播报时仍返回当前业务页状态。
        if contexts:
            snapshot['view'] = view
            return snapshot
        raise RuntimeError('签字页 WebView 调试上下文不可用')
    except Exception:
        cache.clear()
        raise
    finally:
        if not keep_webview:
            timed_call('签名定位/返回原生上下文', driver.switch_to.context, 'NATIVE_APP')
        elapsed = time.monotonic() - started
        if elapsed >= 2:
            print(f'    签字页面读取及上下文切换耗时 {elapsed:.2f}s')


def native_point(snapshot, rect, x=0.5, y=0.5):
    view = snapshot['view']
    return (round(view['x'] + (rect['x'] + rect['width'] * x) * view['width'] / snapshot['width']),
            round(view['y'] + (rect['y'] + rect['height'] * y) * view['height'] / snapshot['height']))


def draw_test_signature(driver, snapshot):
    prepared_at = perf_counter()
    rect = snapshot['canvas']['rect']
    if (rect['width'] < 40 or rect['height'] < 40 or rect['x'] < 0 or rect['y'] < 0
            or rect['x'] + rect['width'] > snapshot['width'] + 1
            or rect['y'] + rect['height'] > snapshot['height'] + 1):
        raise RuntimeError('签字画布边界无效或超出视口，拒绝盲点')
    # 与 Android 相同的测试折线，限制在画布内部，不模拟客户真实手写字迹。
    points = [(0.18, .32), (.35, .25), (.48, .18), (.48, .72),
              (.62, .58), (.76, .44), (.82, .38)]
    actions = ActionBuilder(driver, mouse=PointerInput('touch', 'signature'), duration=80)
    x, y = native_point(snapshot, rect, *points[0])
    actions.pointer_action.move_to_location(x, y)
    actions.pointer_action.pointer_down()
    for px, py in points[1:]:
        x, y = native_point(snapshot, rect, px, py)
        actions.pointer_action.move_to_location(x, y)
        actions.pointer_action.pause(.03)
    actions.pointer_action.pointer_up()
    print(f'    [耗时细分] 签名/坐标换算及W3C轨迹构建: {perf_counter()-prepared_at:.3f}s')
    started = time.monotonic()
    timed_call('签名/WDA动作请求（含设备执行及响应）', actions.perform)
    elapsed = time.monotonic() - started
    if elapsed >= 2:
        print(f'    签字原生触摸执行耗时 {elapsed:.2f}s')


def wait_self_service_completion(driver, cycle_num, screenshot, customer_name,
                                 timeout=180, completion_timeout=60):
    """签字与提交后的等待分别计时；超时前仍读取一次最新完成状态。"""
    previous = driver.get_settings()
    restore = {'waitForIdleTimeout': previous.get('waitForIdleTimeout', 10),
               'animationCoolOffTimeout': previous.get('animationCoolOffTimeout', 2)}
    deadline = time.monotonic() + timeout
    signed = 0
    submitted = False
    completion_wait_started = False
    pending_ink = None
    transition_deadline = None
    cache = {}
    signature_started = None
    detailed = os.environ.get('IOS_SIGNATURE_DETAIL_SCREENSHOTS', '0') == '1'
    try:
        # 摄像头预览持续变化，WDA 不应在触摸之后等待画面动画稳定。
        # 仍由笔迹变化、字符切换及最终完成页判定操作是否生效。
        driver.update_settings({'waitForIdleTimeout': 0, 'animationCoolOffTimeout': 0})
        while True:
            # 页面读取/截图本身也可能耗时，不能在读取最终完成页之前就报超时。
            state = signature_snapshot(driver, cache=cache)
            if '业务办理完成' in state['text']:
                screenshot(driver, f'step8_business_complete_{cycle_num}')
                print(f'    第{cycle_num}次 - 已确认业务办理完成，签字 {signed} 个字符')
                return True
            if not completion_wait_started and '录制已完成' in state['text']:
                completion_wait_started = True
                deadline = time.monotonic() + completion_timeout
                print(f'    第{cycle_num}次 - 录制已完成，独立等待业务完成页（{completion_timeout}s）')
            if time.monotonic() >= deadline:
                phase = '提交/录制完成后' if completion_wait_started else '播报及签字阶段'
                limit = completion_timeout if completion_wait_started else timeout
                raise RuntimeError(f'自助双录{phase}在 {limit}s 内未出现业务办理完成，已签 {signed} 个字符')
            canvas = state['canvas']
            if pending_ink is not None:
                if canvas is None or canvas['ink'] != pending_ink:
                    pending_ink = None
                    transition_deadline = None
                elif time.monotonic() >= transition_deadline:
                    raise RuntimeError('签字确定后画布未清空或切换，未进入下一字符')
                else:
                    time.sleep(.2)
                    continue
            controls = {c['text']: c for c in state['controls'] if c['enabled']}
            if '提交签名' in controls and not submitted:
                driver.tap([native_point(state, controls['提交签名']['rect'])])
                submitted = True
                if signature_started is not None:
                    print(f'    第{cycle_num}次 - 签字至提交耗时 {time.monotonic() - signature_started:.2f}s')
                screenshot(driver, f'step8_signature_submitted_{cycle_num}')
                # 给提交后的上传/页面跳转完整的等待窗口，不复用签字阶段剩余时间。
                completion_wait_started = True
                deadline = time.monotonic() + completion_timeout
                print(f'    第{cycle_num}次 - 已提交测试签名')
            elif canvas is not None and not submitted:
                if signed >= len(customer_name):
                    raise RuntimeError('已签客户姓名全部字符，但仍停留签字画布')
                if signature_started is None:
                    signature_started = time.monotonic()
                if detailed:
                    screenshot(driver, f'step8_signature_before_{cycle_num}_{signed + 1}')
                draw_test_signature(driver, state)
                drawn = signature_snapshot(driver, cache=cache)
                if not drawn['canvas'] or drawn['canvas']['ink'] == canvas['ink']:
                    raise RuntimeError('签字触摸未在画布生成笔迹')
                controls = {c['text']: c for c in drawn['controls'] if c['enabled']}
                confirm = next((controls[t] for t in ('确定', '确认') if t in controls), None)
                if confirm is None:
                    raise RuntimeError('签字后确定按钮未启用')
                if detailed:
                    screenshot(driver, f'step8_signature_ink_{cycle_num}_{signed + 1}')
                driver.tap([native_point(drawn, confirm['rect'])])
                pending_ink = drawn['canvas']['ink']
                transition_deadline = time.monotonic() + 8
                signed += 1
                print(f'    第{cycle_num}次 - 已绘制并确认第 {signed} 个测试签字字符')
            elif '下一步' in controls:
                driver.tap([native_point(state, controls['下一步']['rect'])])
            time.sleep(.3)
    except Exception:
        screenshot(driver, f'error_self_signature_{cycle_num}')
        raise
    finally:
        driver.update_settings(restore)
