"""现场人工双录重跑准备、输入及页面状态核验。"""
import re
import time
import xml.etree.ElementTree as ET
import pymysql
from ios_phase_timing import timed_call, timed_flow

import config_pure_recording as config
from appium.webdriver.common.appiumby import AppiumBy
from ios_session_recovery import terminate_previous_app
from ios_customer_logout import logout_customer_ios
from scene_manual_nodes import visible_control
from scene_broadcast_runtime import clear_broadcast


SCENE_NAV_SCRIPT = r"""
const clean=s=>(s||'').replace(/\s/g,'');
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
const find=t=>Array.from(document.querySelectorAll('button,a,span,div,[role="tab"]'))
 .find(e=>clean(e.textContent)===t&&visible(e)&&
  !Array.from(e.children).some(c=>clean(c.textContent)===t&&visible(c)));
const site=find('现场'),my=find('我的');
const text=clean(document.body.innerText);
const ready=!!site&&!!my&&!!find('远程')&&!!find('纯录制');
let clicked=false;
if(arguments[0]==='返回') {
 const back=find('返回');
 if(back){const r=back.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
  if(top&&(top===back||back.contains(top)||top.contains(back))){back.click();clicked=true;}}
}
if(arguments[0]===true&&ready) {
 const r=site.getBoundingClientRect(),top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
 if(top&&(top===site||site.contains(top)||top.contains(site))&&
    !site.closest('[disabled],[aria-disabled="true"]')) {site.click();clicked=true;}
}
const tab=site?.closest('[role="tab"],.van-tabbar-item,.tab-item');
const selected=!!tab&&(tab.getAttribute('aria-selected')==='true'||
 tab.classList.contains('van-tabbar-item--active')||tab.classList.contains('active'));
return {ready,clicked,onSite:ready&&!text.includes('业务办理完成')&&text.includes('订单')&&
 (text.includes('现场双录')||selected)};
"""


def scene_navigation(driver, click=False):
    try:
        for context in driver.contexts:
            if 'WEBVIEW' not in context:
                continue
            driver.switch_to.context(context)
            state = driver.execute_script(SCENE_NAV_SCRIPT, click)
            if state['ready'] or state['clicked']:
                return state
        return dict(ready=False, clicked=False, onSite=False)
    finally:
        driver.switch_to.context('NATIVE_APP')


def open_scene_navigation(driver, cycle_num, timeout=25):
    deadline = time.monotonic() + timeout
    clicked = False
    while time.monotonic() < deadline:
        require_foreground(driver, config.BUNDLE_ID)
        state = scene_navigation(driver)
        if state['onSite']:
            print(f'    第{cycle_num}次 - 已确认现场订单列表，继续全局搜索')
            return True
        if state['ready'] and not clicked:
            clicked = scene_navigation(driver, click=True)['clicked']
            if clicked:
                print(f'    第{cycle_num}次 - 已点击现场导航，等待订单列表')
        time.sleep(.2)
    raise RuntimeError('切换现场导航超时，未确认现场订单列表')


def reset_scene_order(order_id):
    """仅重置指定测试订单；事务内锁定、更新并复查，异常回滚。"""
    table, field = config.DB_TABLE, config.DB_STATE_FIELD
    if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', s) for s in (table, field)):
        raise ValueError('订单表或状态字段配置无效')
    conn = pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
                           password=config.DB_PASSWORD, database=config.DB_NAME,
                           charset='utf8mb4', connect_timeout=10, read_timeout=15,
                           write_timeout=15, autocommit=False)
    try:
        with conn.cursor() as cursor:
            query = f'SELECT `{field}` FROM `{table}` WHERE order_id = %s'
            cursor.execute(query + ' FOR UPDATE', (order_id,))
            rows = cursor.fetchall()
            if len(rows) != 1:
                raise RuntimeError(f'目标现场订单匹配 {len(rows)} 条，停止重置')
            before = rows[0][0]
            if before != 0:
                cursor.execute(f'UPDATE `{table}` SET `{field}`=0 WHERE order_id=%s', (order_id,))
            cursor.execute(query, (order_id,))
            if cursor.fetchall() != ((0,),):
                raise RuntimeError('现场订单状态重置后核验失败')
        conn.commit()
        print(f'    现场订单 {order_id} 状态核验：{before} -> 0')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def wait_control(driver, label, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        button = visible_control(driver, label)
        if button is not None:
            return button
        time.sleep(.2)
    raise RuntimeError(f'等待可操作按钮超时：{label}')


def require_foreground(driver, bundle_id):
    state = driver.query_app_state(bundle_id)
    if state in (0, 1):
        raise RuntimeError(f'业务 App 已停止运行（state={state}），疑似崩溃，需设备崩溃日志确认')
    if state != 4:
        raise RuntimeError(f'业务 App 已离开前台（state={state}），停止操作以保留现场')


def capture_failure(driver, bundle_id, directory, cycle_num):
    """失败时只读诊断并截图，不结束 App；下轮启动时再清理。"""
    import os
    try:
        state = driver.query_app_state(bundle_id)
        print(f'    [失败现场] App state={state}（1=未运行，2/3=后台，4=前台）')
        active = driver.execute_script('mobile: activeAppInfo')
        print(f'    [失败现场] 活动应用：{active.get("bundleId", "未知")}')
    except Exception as error:
        print(f'    [失败现场] 状态读取失败：{type(error).__name__}')
    try:
        path = os.path.join(directory, f'scene_manual_failure_{cycle_num}_{time.time_ns()}.png')
        driver.save_screenshot(path)
        print(f'    [失败现场] 截图：{path}')
    except Exception as error:
        print(f'    [失败现场] 截图失败：{type(error).__name__}')


def startup_stage(label, function, *args):
    started = time.monotonic()
    try:
        return function(*args)
    finally:
        print(f'    [启动分段] {label}: {time.monotonic() - started:.2f}s')


def startup_snapshot(driver):
    """一次 WDA 页面读取，本地判断表单、入口、登出及遗留业务页。"""
    source = startup_stage('页面状态读取', lambda: driver.page_source)
    def parse():
        root = ET.fromstring(source)
        elements = []
        def collect(element):
            if element.get('visible') == 'false':
                return
            if element.get('enabled') != 'false':
                elements.append(element)
            for child in element:
                collect(child)
        collect(root)
        def has(label, button=False):
            return any((not button or e.get('type', e.tag) == 'XCUIElementTypeButton') and
                       any(''.join(e.get(k, '').split()) == label for k in ('name', 'label', 'value'))
                       for e in elements)
        normal = sum(e.get('type', e.tag) == 'XCUIElementTypeTextField' for e in elements)
        secure = sum(e.get('type', e.tag) == 'XCUIElementTypeSecureTextField' for e in elements)
        text = ' '.join(e.get(k, '') for e in elements for k in ('name', 'label', 'value'))
        # 两个角色共享三输入框布局和页签，不能仅凭页签存在判定角色。
        manager_form = ('工号' in text and '身份证' not in ' '.join(
            e.get(k, '') for e in elements
            if e.get('type', e.tag) == 'XCUIElementTypeTextField'
            for k in ('name', 'label', 'value')))
        layout = normal == 2 and secure == 1 and has('登录') and has('客户经理登录')
        return dict(form=layout and manager_form, formLayout=layout,
                    entry=has('客户经理登录'), loggedIn=has('我的') or has('退出登录'),
                    replayStopped='直播已停止' in text or '无效的直播会话' in text,
                    fields=[dict(kind=e.get('type', e.tag),
                                 hint=' '.join(e.get(k, '') for k in ('name', 'label')),
                                 empty=not e.get('value') or e.get('value', '').startswith('请输入'),
                                 x=float(e.get('x', 0)), y=float(e.get('y', 0)))
                            for e in elements if e.get('type', e.tag) in
                            ('XCUIElementTypeTextField', 'XCUIElementTypeSecureTextField')],
                    canBack=any(t in text for t in ('业务办理完成', '同意并开始双录', '录制回看')))
    return startup_stage('属性解析及表单判断（本地）', parse)


def configure_scene_startup(options):
    """人工、AI 共用会话启动配置；App 仅由 prepare_manager 激活一次。"""
    options.set_capability('processArguments', {'args': []})
    options.set_capability('shouldTerminateApp', False)
    options.set_capability('autoLaunch', False)
    # 保留 ReplayKit 的真实错误，由启动清理处理明确的遗留弹窗。
    options.set_capability('autoAcceptAlerts', False)
    return options


def prepare_manager(driver, cycle_num, bundle_id, screenshot, cleanup_broadcast=True):
    driver.switch_to.context('NATIVE_APP')
    if cleanup_broadcast:
        startup_stage('清理遗留系统录屏', clear_broadcast, driver)
    else:
        print('    [启动分段] 上一轮完整成功，跳过专项系统录屏查询；保留页面异常提示兜底')
    startup_stage('结束旧进程及核验', terminate_previous_app, driver, bundle_id)
    startup_stage('激活 App', driver.activate_app, bundle_id)
    if startup_stage('前台核验', driver.query_app_state, bundle_id) != 4:
        raise RuntimeError('客户经理 App 激活后未处于前台')
    # 页面就绪预算不包含录屏清理、旧进程结束及激活的请求耗时。
    deadline = time.monotonic() + 40
    backs = 0
    replay_recoveries = logout_recoveries = 0
    while True:
        require_foreground(driver, bundle_id)
        state = startup_snapshot(driver)
        if state.get('replayStopped'):
            if replay_recoveries >= 2:
                raise RuntimeError('客户经理启动直播异常提示反复出现，停止恢复')
            startup_stage('清理延迟出现的系统直播提示', clear_broadcast, driver)
            replay_recoveries += 1
            deadline = time.monotonic() + 40
            continue
        if not any(state.get(k) for k in ('form', 'entry', 'loggedIn')):
            # 原生树偶尔把整个 WebView 标为不可见，使用实际导航结构复核登录态。
            state['loggedIn'] = scene_navigation(driver)['ready']
        if state['form']:
            driver.__dict__['_scene_login_snapshot'] = (time.monotonic(), state)
            print(f'    第{cycle_num}次 - 已确认客户经理登录表单就绪')
            return True
        if state['entry']:
            print(f'    第{cycle_num}次 - 已确认客户经理登录入口就绪')
            return True
        if state['loggedIn']:
            if logout_recoveries >= 2:
                raise RuntimeError('客户经理启动登出后仍反复出现登录态，停止恢复')
            logout_customer_ios(driver, cycle_num, screenshot, login_marker='客户经理登录')
            logout_recoveries += 1
            deadline = time.monotonic() + 40
            # 登出可能触发 ReplayKit 延迟停止弹窗；重新读启动状态后才交给登录。
            continue
        # 每次请求返回先判断完成状态，再判断期限；慢请求不能吞掉成功结果。
        if time.monotonic() >= deadline:
            raise RuntimeError('客户经理启动清理超时，无法确认未登录')
        # 启动画面、加载页及未识别页面只等待；仅对已知遗留业务页返回。
        if backs < 5 and state['canBack']:
            driver.back()
            backs += 1
        time.sleep(.3)


MANAGER_FORM_SCRIPT = r"""
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
const fields=Array.from(document.querySelectorAll('input')).filter(e=>visible(e)&&!e.disabled);
if(fields.length!==3)return false;
const hints=e=>['placeholder','name','aria-label','id'].map(k=>e.getAttribute(k)||'').join(' ');
// DOM placeholder 在输入框已有值时仍保留；不读取或输出账号、密码值。
if(fields.some(e=>/身份证|证件号/.test(hints(e))))return false;
const managerField=fields.some(e=>/工号/.test(hints(e)));
const selected=Array.from(document.querySelectorAll('[aria-selected="true"],[role="tab"][data-state="active"]'))
 .some(e=>visible(e)&&e.textContent.replace(/\s/g,'')==='客户经理登录');
return (managerField||selected)&&fields.some(e=>e.type==='password')&&
 fields.some(e=>/验证码/.test(hints(e)));
"""


def manager_form_role(driver):
    """原生树丢失占位提示时，通过 DOM 稳定属性核验经理角色。"""
    try:
        for context in driver.contexts:
            if 'WEBVIEW' in context:
                driver.switch_to.context(context)
                if driver.execute_script(MANAGER_FORM_SCRIPT) is True:
                    return True
        return False
    finally:
        driver.switch_to.context('NATIVE_APP')


def manager_login_fields(driver, bulk=False):
    """优先按 name/label/value 识别；仅完整三输入框布局允许位置兜底。"""
    if bulk:
        started = time.monotonic()
        cached = driver.__dict__.pop('_scene_login_snapshot', None)
        state = cached[1] if cached and time.monotonic()-cached[0] < 3 else startup_snapshot(driver)
        descriptors = state.get('fields', [])
        if not state['form'] and state.get('formLayout') and manager_form_role(driver):
            state['form'] = True
        if not state['form'] or len(descriptors) != 3:
            return None
        fields = driver.find_elements(AppiumBy.IOS_PREDICATE,
            "visible == 1 AND enabled == 1 AND (type == 'XCUIElementTypeTextField' OR "
            "type == 'XCUIElementTypeSecureTextField')")
        if len(fields) != 3:
            return None
        # 元素查询顺序不保证与 XML 一致，必须读取每个实际元素的属性。
        descriptors = [dict(kind=e.get_attribute('type'),
                            hint=' '.join(str(e.get_attribute(k) or '') for k in ('name', 'label', 'value')),
                            **e.rect) for e in fields]
        normal = [(e, d) for e, d in zip(fields, descriptors) if d['kind'] == 'XCUIElementTypeTextField']
        secure = [e for e, d in zip(fields, descriptors) if d['kind'] == 'XCUIElementTypeSecureTextField']
        if len(normal) != 2 or len(secure) != 1:
            return None
        order = next((e for e, d in normal if '工号' in d['hint']), None)
        captcha = next((e for e, d in normal if '验证码' in d['hint']), None)
        if order is None and captcha is None:
            order, captcha = [e for e, d in sorted(normal, key=lambda pair: (pair[1]['y'], pair[1]['x']))]
        elif order is None:
            order = next(e for e, d in normal if e != captcha)
        elif captcha is None:
            captcha = next(e for e, d in normal if e != order)
        if order == captcha:
            return None
        print(f'    [启动分段] 合并表单查询及本地属性匹配: {time.monotonic()-started:.2f}s')
        return order, secure[0], captcha
    fields = startup_stage('表单输入框查找', driver.find_elements, AppiumBy.IOS_PREDICATE,
        "type == 'XCUIElementTypeTextField' OR type == 'XCUIElementTypeSecureTextField'")
    attribute_started = time.monotonic()
    fields = [e for e in fields if e.is_displayed() and e.is_enabled()]
    normal, secure = [], []
    for element in fields:
        target = secure if element.get_attribute('type') == 'XCUIElementTypeSecureTextField' else normal
        target.append(element)
    if len(normal) != 2 or len(secure) != 1 or visible_control(driver, '登录') is None:
        return None
    labels = {e.id: ' '.join(str(e.get_attribute(k) or '') for k in ('name', 'label', 'value'))
              for e in normal}
    def named(token):
        return next((e for e in normal if token in labels[e.id]), None)
    order, captcha = named('工号'), named('验证码')
    if order is None and captcha is None:
        positions = {e.id: e.rect for e in normal}
        order, captcha = sorted(normal, key=lambda e: (positions[e.id]['y'], positions[e.id]['x']))
    elif order is None:
        order = next(e for e in normal if e != captcha)
    elif captcha is None:
        captcha = next(e for e in normal if e != order)
    if order == captcha:
        return None
    print(f'    [启动分段] 输入框属性读取及匹配: {time.monotonic() - attribute_started:.2f}s')
    return order, secure[0], captcha


def replace_login_value(field, value, label):
    """明确聚焦、清空并回读；失败时停止提交，不追加重试或输出凭据。"""
    timed_call(f'登录/{label}/聚焦', field.click)
    timed_call(f'登录/{label}/clear请求', field.clear)
    cleared = timed_call(f'登录/{label}/清空核验', field.get_attribute, 'value')
    if cleared and not str(cleared).startswith('请输入'):
        raise RuntimeError(f'{label}输入框清空失败，已停止登录')
    timed_call(f'登录/{label}/send_keys请求', field.send_keys, value)
    actual = timed_call(f'登录/{label}/输入核验', field.get_attribute, 'value')
    valid = actual == value
    if label == '密码':
        valid = valid or (isinstance(actual, str) and len(actual) == len(value)
                          and set(actual) <= set('•●*'))
    if not valid:
        raise RuntimeError(f'{label}输入结果不匹配，已停止登录')


@timed_flow('登录/完整阶段')
def login_manager(driver, cycle_num, manager_id, password, captcha):
    timed_call('登录/进入原生上下文', driver.switch_to.context, 'NATIVE_APP')
    # 始终显式选择角色，再重新读取表单；禁止复用切换前的客户输入框。
    entry = timed_call('登录/经理页签定位', wait_control, driver, '客户经理登录')
    timed_call('登录/切换客户经理页签', entry.click)
    driver.__dict__.pop('_scene_login_snapshot', None)
    driver.__dict__.pop('_scene_login_empty', None)
    fields = timed_call('登录/表单定位及属性匹配', manager_login_fields, driver, bulk=True)
    if fields is None:
        entry = timed_call('登录/经理入口定位', wait_control, driver, '客户经理登录')
        timed_call('登录/经理入口点击', entry.click)
        deadline = time.monotonic() + 20
        while fields is None:
            fields = timed_call('登录/表单就绪复查', manager_login_fields, driver, bulk=True)
            if fields is not None:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('点击客户经理登录后，登录表单未就绪（需工号、密码、验证码三输入框）')
            time.sleep(.2)
    print(f'    第{cycle_num}次 - 已确认登录表单，开始原生直接输入')
    timed_call('登录/输入前前台核验', require_foreground, driver, config.BUNDLE_ID)
    for label, field, value in zip(('工号', '密码', '验证码'), fields, (manager_id, password, captcha)):
        startup_stage(f'{label}输入', replace_login_value, field, value, label)
    for label, field, value in (('工号', fields[0], manager_id), ('验证码', fields[2], captcha)):
        if field.get_attribute('value') != value:
            raise RuntimeError(f'{label}提交前核验失败，已停止登录')
    def submit():
        button = timed_call('登录/提交按钮定位', wait_control, driver, '登录')
        timed_call('登录/提交按钮点击', button.click)
    startup_stage('登录提交', submit)
    verification_started = time.monotonic()
    deadline = time.monotonic() + 20
    while True:
        timed_call('登录/提交后前台核验', require_foreground, driver, config.BUNDLE_ID)
        if timed_call('登录/提交后导航状态读取', scene_navigation, driver)['ready']:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('登录后未出现现场入口，App仍在前台；需检查登录结果或入口定位')
        time.sleep(.2)
    print(f'    第{cycle_num}次 - 客户经理登录已核验')
    print(f'    [登录分段] 提交后页面核验: {time.monotonic()-verification_started:.2f}s')


def return_scene_list(driver, cycle_num, timeout=30):
    deadline = time.monotonic() + timeout
    clicked = False
    while time.monotonic() < deadline:
        require_foreground(driver, config.BUNDLE_ID)
        state = scene_navigation(driver)
        if state['onSite']:
            print(f'    第{cycle_num}次 - 已确认返回现场订单列表')
            return True
        if not clicked:
            clicked = scene_navigation(driver, click='返回')['clicked']
            if not clicked:
                button = visible_control(driver, '返回')
                if button is not None:
                    button.click()
                    clicked = True
        time.sleep(.2)
    raise RuntimeError('返回后未确认现场订单列表')


class SceneUploadFailed(RuntimeError):
    """已观察到上传失败提示，区别于网络异常和等待超时。"""


@timed_flow('现场上传/结果核验完整阶段')
def wait_upload_success(driver, timeout=120, fail_fast=False, dom_first=False):
    if dom_first:
        from scene_ai_pages import wait_ai_upload
        return wait_ai_upload(driver, timeout=timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        source = timed_call('现场上传/原生状态读取', lambda: driver.page_source)
        result_text = source
        if fail_fast:
            root = ET.fromstring(source)
            visible_text = ' '.join(element.get(key, '') for element in root.iter()
                                    if element.get('visible') != 'false'
                                    for key in ('name', 'label', 'value'))
            if '上传失败' in visible_text:
                raise SceneUploadFailed('现场录制文件上传失败，停止等待上传成功；请检查应用及上传服务日志')
            result_text = visible_text
        if '上传成功' in result_text or '上传文件成功' in result_text:
            return True
        time.sleep(.3)
    raise RuntimeError('现场录制上传超时，未出现上传成功提示')


TRANSITION_SCRIPT = r"""
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
const text=document.body.innerText.replace(/\s/g,'');
const dialogs=Array.from(document.querySelectorAll('.van-dialog,[role="dialog"]')).filter(visible);
const confirm=dialogs.some(d=>Array.from(d.querySelectorAll('button,[role="button"]'))
 .some(b=>['确认','确定'].includes(b.textContent.trim())&&visible(b)&&!b.disabled));
return {confirm,completed:text.includes('业务办理完成')&&
 Array.from(document.querySelectorAll('button,[role="button"]')).some(e=>e.textContent.trim()==='返回'&&visible(e))};
"""


def wait_scene_transition(driver, expected, timeout=20):
    """仅用于现场人工流程；后置页面就绪即继续，超时明确失败。"""
    started = time.monotonic()
    deadline = started + timeout
    try:
        while time.monotonic() < deadline:
            for context in driver.contexts:
                if 'WEBVIEW' not in context:
                    continue
                driver.switch_to.context(context)
                if driver.execute_script(TRANSITION_SCRIPT).get(expected):
                    print(f'    [页面衔接] {expected} 已就绪: {time.monotonic()-started:.2f}s')
                    return True
            time.sleep(.15)
        raise RuntimeError(f'现场人工流程后置页面未就绪：{expected}')
    finally:
        driver.switch_to.context('NATIVE_APP')


def start_manual_recording(driver, cycle_num, timeout=30):
    from scene_fast_paths import node_snapshot
    wait_control(driver, '开始（人工）', timeout=timeout).click()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = node_snapshot(driver)
        if state['progress'] is not None or state['signature']:
            print(f'    第{cycle_num}次 - 开始人工双录后已确认业务节点就绪')
            return True
        time.sleep(.2)
    raise RuntimeError('开始人工双录后未出现业务节点')


def cleanup_session(driver, previous_settings):
    for label, action in [
        ('恢复设备等待设置', lambda: driver.update_settings({key: previous_settings.get(key, default)
            for key, default in [('waitForIdleTimeout', 10), ('animationCoolOffTimeout', 2)]})),
        ('退出 Appium 会话', driver.quit),
    ]:
        started = time.monotonic()
        try:
            action()
        except Exception as error:
            print(f'    [收尾分段] {label}失败：{type(error).__name__}')
        finally:
            print(f'    [收尾分段] {label}: {time.monotonic()-started:.2f}s')


SCENE_STEP_LABELS = {
    'reset_scene_order': (None, '订单状态重置'),
    'prepare_manager': (1, '启动 App 并检查登录状态'),
    'login_manager': (2, '客户经理登录'),
    'open_scene_navigation': (3, '切换现场导航栏'),
    'search_scene_order': (4, '搜索现场订单并进入录制'),
    'step5_scene_confirm_popup': (None, '录制提示弹窗确认'),
    'step6_scene_click_agree_and_start': (None, '同意并开始双录'),
    'step7_scene_click_start_now': (7, '开始直播'),
    'step8_scene_click_agree_detection': (None, '同意检测'),
    'step9_scene_wait_detection_result': (None, '等待检测结果'),
    'start_ai_recording': (10, '开始 AI 双录'),
    'start_manual_recording': (10, '开始人工双录'),
    'step11_scene_wait_countdown': (None, '等待录制倒计时'),
    'exercise_scene_controls': (12, '暂停、继续双录及业务截图'),
    'advance_ai_nodes': (14, 'AI 业务节点推进及三字签名'),
    'step14_scene_manual_qa_node': (None, '人工业务节点推进及三字签名'),
    'finish_ai_recording': (15, '完成 AI 录制并核验回看页'),
    'step15_scene_manual_reading_node': (None, '完成人工录制并核验回看页'),
    'step16_scene_review_and_confirm': (None, '确认完成'),
    'step17_scene_confirm_popup': (None, '业务完成弹窗确认'),
    'wait_upload_success': (18, '等待文件上传结果'),
    'step19_scene_upload_confirm': (None, '上传成功弹窗确认'),
    'close_failed_upload': (None, '上传失败退出办理'),
    'return_scene_list': (20, '返回并核验现场订单列表'),
    'logout_customer_ios': (21, '进入我的页面并退出登录'),
    'step24_scene_home': (None, '返回系统桌面'),
}


def timed_step(function, *args, **kwargs):
    name = getattr(function, '__name__', type(function).__name__)
    number, label = SCENE_STEP_LABELS.get(name, (None, name))
    if number is not None:
        print(f'\n[Step {number}] {label}...')
    started = time.monotonic()
    try:
        return function(*args, **kwargs)
    finally:
        print(f'    [节点耗时] {label}: {time.monotonic() - started:.2f}s')
