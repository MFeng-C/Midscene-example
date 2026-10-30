"""现场人工双录逐字签名，复用客户场景的画布定位和原生触摸。"""
import time

from self_service_signature import signature_snapshot, draw_test_signature, native_point

SIGNATURE_PROMPT = '请客户经理进行签字'


def sign_scene_name(driver, cycle_num, character_count=3, timeout=90,
                    snapshot_reader=None, draw_action=None, confirm_action=None,
                    on_complete=None, completion_timeout=None, on_submit=None):
    snapshot_reader = snapshot_reader or signature_snapshot
    draw_action = draw_action or draw_test_signature
    confirm_action = confirm_action or (lambda d, s, c: d.tap([native_point(s, c['rect'])]))
    previous = driver.get_settings()
    restore = {key: previous.get(key, default) for key, default in
               (('waitForIdleTimeout', 10), ('animationCoolOffTimeout', 2))}
    cache = {}
    signed = 0
    pending_ink = None
    transition_deadline = None
    submitted = False
    deadline = time.monotonic() + timeout
    try:
        driver.update_settings({'waitForIdleTimeout': 0, 'animationCoolOffTimeout': 0})
        while completion_timeout is not None or time.monotonic() < deadline:
            state = snapshot_reader(driver, cache=cache, signature_prompt=SIGNATURE_PROMPT)
            canvas = state['canvas']
            controls = {c['text']: c for c in state['controls'] if c['enabled']}
            completed = (signed == character_count and canvas is None
                         and '提交签名' not in controls
                         and SIGNATURE_PROMPT not in ''.join(state['text'].split())
                         and any(label in controls for label in ('下一步', '完成录制', '确认完成')))
            # AI 页面读取本身可能较慢；先核验刚读取到的完成页，再判断超时。
            if completion_timeout is not None and completed:
                print(f'    第{cycle_num}次 - 现场签名已完成，共 {signed} 字')
                return on_complete(driver) if on_complete else True
            if completion_timeout is not None and time.monotonic() >= deadline:
                phase = '提交后确认页' if submitted else '三字确认后衔接' if signed == character_count else '绘制阶段'
                raise RuntimeError(f'现场签名{phase}超时，已签 {signed}/{character_count} 字')
            if pending_ink is not None:
                if canvas is None or canvas['ink'] != pending_ink:
                    pending_ink = None
                elif time.monotonic() >= transition_deadline:
                    raise RuntimeError('现场签名确定后画布未清空或切换')
                else:
                    time.sleep(.2)
                    continue
            if canvas is None:
                if signed != character_count:
                    raise RuntimeError(f'现场签名提前结束：已签 {signed}/{character_count} 字')
                if '提交签名' in controls:
                    if not submitted:
                        confirm_action(driver, state, controls['提交签名'])
                        submitted = True
                        if on_submit is not None:
                            # 三字笔迹已逐一核验；提交后由独立的节点状态机接管。
                            return on_submit(driver)
                        if completion_timeout is not None:
                            deadline = time.monotonic() + completion_timeout
                            print(f'    [AI签名衔接] 已提交签名，独立核验确认页（{completion_timeout}s）')
                elif SIGNATURE_PROMPT not in ''.join(state['text'].split()) and any(
                        label in controls for label in ('下一步', '完成录制', '确认完成')):
                    print(f'    第{cycle_num}次 - 现场签名已完成，共 {signed} 字')
                    return on_complete(driver) if on_complete else True
            else:
                if signed >= character_count:
                    raise RuntimeError('已签满三字，页面仍要求额外签名')
                draw_action(driver, state)
                drawn = snapshot_reader(driver, cache=cache, signature_prompt=SIGNATURE_PROMPT)
                if not drawn['canvas'] or drawn['canvas']['ink'] == canvas['ink']:
                    raise RuntimeError('现场签名触摸未生成笔迹')
                confirm = next((c for c in drawn['controls']
                                if c['enabled'] and c['text'] in ('确定', '确认')), None)
                if confirm is None:
                    raise RuntimeError('现场签名确定按钮未启用')
                confirm_action(driver, drawn, confirm)
                signed += 1
                if completion_timeout is not None and signed == character_count:
                    deadline = time.monotonic() + completion_timeout
                    print(f'    [AI签名衔接] 三字已确认，独立等待提交或确认页（{completion_timeout}s）')
                pending_ink = drawn['canvas']['ink']
                transition_deadline = time.monotonic() + 10
                print(f'    第{cycle_num}次 - 已绘制并确认现场签名 {signed}/{character_count}')
            time.sleep(.2)
        raise RuntimeError(f'现场签名超时，已签 {signed}/{character_count} 字')
    finally:
        driver.switch_to.context('NATIVE_APP')
        driver.update_settings(restore)
