import unittest
from unittest.mock import Mock, MagicMock, PropertyMock, patch
import scene_manual_runtime as runtime


class RuntimeTest(unittest.TestCase):
    def test_startup_cleanup_and_logout_do_not_consume_page_ready_budget(self):
        driver = Mock()
        driver.query_app_state.return_value = 4
        clock = [0]
        def slow_cleanup(*args):
            clock[0] += 55
        def slow_logout(*args, **kwargs):
            clock[0] += 45
        states = [dict(form=False, entry=False, loggedIn=True), dict(form=True)]
        with patch.object(runtime.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(runtime, 'clear_broadcast', side_effect=slow_cleanup), \
             patch.object(runtime, 'terminate_previous_app'), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'logout_customer_ios', side_effect=slow_logout) as logout, \
             patch.object(runtime, 'startup_snapshot', side_effect=states) as snapshot:
            self.assertTrue(runtime.prepare_manager(driver, 1, 'bundle', Mock()))
        logout.assert_called_once()
        self.assertEqual(snapshot.call_count, 2)

    def test_slow_page_query_returns_success_before_timeout_check(self):
        driver = Mock()
        driver.query_app_state.return_value = 4
        clock = [0]
        def snapshot(*args):
            clock[0] += 45
            return dict(form=True)
        with patch.object(runtime.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(runtime, 'clear_broadcast'), \
             patch.object(runtime, 'terminate_previous_app'), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'startup_snapshot', side_effect=snapshot):
            self.assertTrue(runtime.prepare_manager(driver, 1, 'bundle', Mock()))

    def test_repeated_recovery_is_bounded(self):
        driver = Mock()
        driver.query_app_state.return_value = 4
        with patch.object(runtime, 'clear_broadcast') as clear, \
             patch.object(runtime, 'terminate_previous_app'), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'startup_snapshot', return_value=dict(replayStopped=True)):
            with self.assertRaisesRegex(RuntimeError, '反复出现'):
                runtime.prepare_manager(driver, 1, 'bundle', Mock())
        self.assertEqual(clear.call_count, 3)  # 首轮清理 + 最多两次延迟提示恢复。

    def test_startup_snapshot_reads_page_once_without_element_queries(self):
        driver = Mock()
        source = '''<App><XCUIElementTypeStaticText name="客户经理登录"/>
        <XCUIElementTypeTextField value="请输入工号"/>
        <XCUIElementTypeSecureTextField/><XCUIElementTypeTextField/>
        <XCUIElementTypeButton name="登录"/></App>'''
        with patch.object(type(driver), 'page_source', new_callable=PropertyMock, create=True,
                          return_value=source) as page:
            snapshot = runtime.startup_snapshot(driver)
        self.assertTrue(snapshot['form'])
        self.assertTrue(snapshot['entry'])
        page.assert_called_once()
        driver.find_elements.assert_not_called()

    def test_hidden_form_does_not_count_as_ready(self):
        driver = Mock(page_source='''<App><Panel visible="false">
        <Text name="客户经理登录"/><XCUIElementTypeTextField/>
        <XCUIElementTypeTextField/><XCUIElementTypeSecureTextField/>
        <XCUIElementTypeButton name="登录"/></Panel></App>''')
        self.assertFalse(runtime.startup_snapshot(driver)['form'])

    def test_prepare_uses_snapshot_instead_of_resolving_login_fields(self):
        driver = Mock()
        driver.query_app_state.return_value = 4
        with patch.object(runtime, 'terminate_previous_app'), \
             patch.object(runtime, 'clear_broadcast'), \
             patch.object(runtime, 'startup_snapshot', return_value=dict(form=True)), \
             patch.object(runtime, 'manager_login_fields') as fields:
            self.assertTrue(runtime.prepare_manager(driver, 1, 'bundle', Mock()))
        fields.assert_not_called()

    def field(self, kind, y, label=''):
        element = Mock()
        element.get_attribute.side_effect = lambda key: kind if key == 'type' else label if key == 'label' else ''
        element.rect = dict(x=10, y=y)
        return element

    def test_unlabelled_complete_form_uses_visual_order(self):
        driver = Mock()
        order = self.field('XCUIElementTypeTextField', 100)
        password = self.field('XCUIElementTypeSecureTextField', 200)
        captcha = self.field('XCUIElementTypeTextField', 300)
        driver.find_elements.return_value = [captcha, password, order]
        with patch.object(runtime, 'visible_control', return_value=Mock()):
            self.assertEqual(runtime.manager_login_fields(driver), (order, password, captcha))

    def test_label_is_used_before_position(self):
        driver = Mock()
        order = self.field('XCUIElementTypeTextField', 300, '请输入工号')
        password = self.field('XCUIElementTypeSecureTextField', 200)
        captcha = self.field('XCUIElementTypeTextField', 100, '请输入验证码')
        driver.find_elements.return_value = [captcha, password, order]
        with patch.object(runtime, 'visible_control', return_value=Mock()):
            self.assertEqual(runtime.manager_login_fields(driver), (order, password, captcha))

    def test_partial_form_is_not_ready(self):
        driver = Mock()
        driver.find_elements.return_value = [self.field('XCUIElementTypeTextField', 100)]
        self.assertIsNone(runtime.manager_login_fields(driver))

    def test_existing_form_selects_manager_tab_before_input(self):
        driver = Mock()
        fields = [Mock(), Mock(), Mock()]
        for field, value in zip(fields, ('id', 'password', 'captcha')):
            field.get_attribute.side_effect = ['', value, value]
        with patch.object(runtime, 'manager_login_fields', return_value=fields), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'scene_navigation', return_value=dict(ready=True)), \
             patch.object(runtime, 'visible_control', return_value=Mock()), \
             patch.object(runtime, 'wait_control', return_value=Mock()) as control:
            runtime.login_manager(driver, 1, 'id', 'password', 'captcha')
        self.assertEqual([call.args[1] for call in control.call_args_list], ['客户经理登录', '登录'])
        for field, value in zip(fields, ('id', 'password', 'captcha')):
            field.send_keys.assert_called_once_with(value)

    def test_customer_form_with_both_tabs_is_not_manager_form(self):
        driver = Mock(page_source='''<App><Text name="客户经理登录"/><Text name="客户登录"/>
        <XCUIElementTypeTextField value="请输入身份证号"/>
        <XCUIElementTypeSecureTextField/><XCUIElementTypeTextField value="请输入验证码"/>
        <XCUIElementTypeButton name="登录"/></App>''')
        state = runtime.startup_snapshot(driver)
        self.assertFalse(state['form'])
        self.assertTrue(state['entry'])

    def test_bulk_login_matches_actual_fields_despite_different_xml_order(self):
        driver = Mock()
        order = self.field('XCUIElementTypeTextField', 100, '请输入工号')
        password = self.field('XCUIElementTypeSecureTextField', 200)
        captcha = self.field('XCUIElementTypeTextField', 300, '请输入验证码')
        driver.find_elements.return_value = [captcha, order, password]
        state = dict(form=True, fields=[
            dict(kind='XCUIElementTypeTextField', hint='请输入工号', x=0, y=1),
            dict(kind='XCUIElementTypeSecureTextField', hint='', x=0, y=2),
            dict(kind='XCUIElementTypeTextField', hint='请输入验证码', x=0, y=3)])
        driver.__dict__['_scene_login_snapshot'] = (runtime.time.monotonic(), state)
        with patch.object(runtime, 'startup_snapshot') as snapshot:
            self.assertEqual(runtime.manager_login_fields(driver, bulk=True), (order, password, captcha))
        snapshot.assert_not_called()
        driver.find_elements.assert_called_once()
        for field in (order, password, captcha):
            self.assertTrue(field.get_attribute.called)
            field.is_displayed.assert_not_called()

    def test_bulk_login_rejects_changed_field_count(self):
        driver = Mock()
        driver.find_elements.return_value = [Mock()]
        with patch.object(runtime, 'startup_snapshot', return_value=dict(form=True, fields=[{}, {}, {}])):
            self.assertIsNone(runtime.manager_login_fields(driver, bulk=True))

    def test_prefilled_manager_uses_dom_role_without_work_id_hint(self):
        driver = Mock(contexts=['NATIVE_APP', 'WEBVIEW_1'])
        driver.execute_script.return_value = True
        fields = [self.field('XCUIElementTypeTextField', 100),
                  self.field('XCUIElementTypeSecureTextField', 200),
                  self.field('XCUIElementTypeTextField', 300, '请输入验证码')]
        driver.find_elements.return_value = fields
        state = dict(form=False, formLayout=True, fields=[
            dict(kind='XCUIElementTypeTextField', hint='', x=0, y=1, empty=False),
            dict(kind='XCUIElementTypeSecureTextField', hint='', x=0, y=2),
            dict(kind='XCUIElementTypeTextField', hint='请输入验证码', x=0, y=3)])
        with patch.object(runtime, 'startup_snapshot', return_value=state):
            self.assertEqual(runtime.manager_login_fields(driver, bulk=True), tuple(fields))
        driver.execute_script.assert_called_once_with(runtime.MANAGER_FORM_SCRIPT)
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_unverified_role_never_resolves_inputs(self):
        driver = Mock(contexts=['WEBVIEW_1'])
        driver.execute_script.return_value = False
        with patch.object(runtime, 'startup_snapshot', return_value=dict(
                form=False, formLayout=True, fields=[{}, {}, {}])):
            self.assertIsNone(runtime.manager_login_fields(driver, bulk=True))
        driver.find_elements.assert_not_called()

    def test_role_probe_failure_restores_native_and_propagates(self):
        driver = Mock(contexts=['WEBVIEW_1'])
        driver.execute_script.side_effect = RuntimeError('probe failed')
        with self.assertRaisesRegex(RuntimeError, 'probe failed'):
            runtime.manager_form_role(driver)
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_login_ignores_cached_empty_and_clears_every_input(self):
        driver = Mock()
        fields = [Mock(), Mock(), Mock()]
        for field, value in zip(fields, ('id', 'password', 'captcha')):
            field.get_attribute.side_effect = ['', value, value]
        def form(*args, **kwargs):
            driver.__dict__['_scene_login_empty'] = {fields[0].id: True, fields[2].id: True}
            return fields
        with patch.object(runtime, 'manager_login_fields', side_effect=form), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'scene_navigation', return_value=dict(ready=True)), \
             patch.object(runtime, 'wait_control', return_value=Mock()):
            runtime.login_manager(driver, 1, 'id', 'password', 'captcha')
        for field in fields:
            field.clear.assert_called_once()
            field.send_keys.assert_called_once()

    def test_clear_failure_never_appends(self):
        field = Mock()
        field.get_attribute.return_value = 'old-account'
        with self.assertRaisesRegex(RuntimeError, '清空失败'):
            runtime.replace_login_value(field, 'new-account', '工号')
        field.send_keys.assert_not_called()

    def test_wrong_focus_or_append_is_rejected(self):
        field = Mock()
        field.get_attribute.side_effect = ['', '100010000']
        with self.assertRaisesRegex(RuntimeError, '输入结果不匹配'):
            runtime.replace_login_value(field, '0000', '验证码')
        field.send_keys.assert_called_once_with('0000')

    def test_secure_mask_can_be_verified_without_logging_password(self):
        field = Mock()
        field.get_attribute.side_effect = ['', '••••']
        runtime.replace_login_value(field, 'test', '密码')

    def test_transition_waits_until_page_ready(self):
        driver = Mock(contexts=['NATIVE_APP', 'WEBVIEW_1'])
        driver.execute_script.side_effect = [dict(completed=False), dict(completed=True)]
        with patch.object(runtime.time, 'sleep') as sleep:
            self.assertTrue(runtime.wait_scene_transition(driver, 'completed'))
        sleep.assert_called_once()
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_transition_timeout_does_not_count_as_success(self):
        driver = Mock(contexts=['WEBVIEW_1'])
        driver.execute_script.return_value = dict(confirm=False)
        with patch.object(runtime.time, 'sleep'), \
             patch.object(runtime.time, 'monotonic', side_effect=range(30)):
            with self.assertRaisesRegex(RuntimeError, '后置页面未就绪'):
                runtime.wait_scene_transition(driver, 'confirm', timeout=4)
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_loading_page_does_not_trigger_back(self):
        driver = Mock(page_source='<App><Text name="正在加载"/></App>')
        driver.query_app_state.return_value = 4
        with patch.object(runtime, 'terminate_previous_app'), \
             patch.object(runtime, 'clear_broadcast'), \
             patch.object(runtime, 'scene_navigation', return_value=dict(ready=False)), \
             patch.object(runtime, 'manager_login_fields', return_value=None), \
             patch.object(runtime, 'visible_control', return_value=None), \
             patch.object(runtime.time, 'sleep'), \
             patch.object(runtime.time, 'monotonic', side_effect=range(100)):
            with self.assertRaisesRegex(RuntimeError, '启动清理超时'):
                runtime.prepare_manager(driver, 1, 'bundle', Mock())
        driver.back.assert_not_called()

    def reset_with_rows(self, rows):
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.side_effect = rows
        return conn, cursor

    def test_reset_only_target_and_verify_before_commit(self):
        conn, cursor = self.reset_with_rows([((3,),), ((0,),)])
        with patch.object(runtime.pymysql, 'connect', return_value=conn):
            runtime.reset_scene_order('scene-test')
        self.assertEqual(len(cursor.execute.call_args_list), 3)
        for call in cursor.execute.call_args_list:
            self.assertEqual(call.args[1], ('scene-test',))
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_missing_order_rolls_back_and_never_updates(self):
        conn, cursor = self.reset_with_rows([()])
        with patch.object(runtime.pymysql, 'connect', return_value=conn):
            with self.assertRaisesRegex(RuntimeError, '匹配 0 条'):
                runtime.reset_scene_order('missing')
        self.assertEqual(cursor.execute.call_count, 1)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_failed_verification_rolls_back(self):
        conn, cursor = self.reset_with_rows([((2,),), ((2,),)])
        with patch.object(runtime.pymysql, 'connect', return_value=conn):
            with self.assertRaisesRegex(RuntimeError, '核验失败'):
                runtime.reset_scene_order('scene-test')
        conn.rollback.assert_called_once()

    @patch.object(runtime.time, 'sleep')
    def test_ai_upload_error_fails_without_waiting(self, sleep):
        driver = Mock(page_source='<root><label visible="true" name="文件上传失败（Unknown error）"/></root>')
        with self.assertRaisesRegex(RuntimeError, '文件上传失败'):
            runtime.wait_upload_success(driver, fail_fast=True)
        sleep.assert_not_called()

    @patch.object(runtime.time, 'sleep')
    def test_hidden_upload_error_does_not_override_success(self, sleep):
        driver = Mock(page_source='<root><label visible="false" name="上传失败"/><label name="上传成功"/></root>')
        self.assertTrue(runtime.wait_upload_success(driver, fail_fast=True))
        sleep.assert_not_called()

    @patch.object(runtime.time, 'sleep')
    def test_ai_native_upload_pending_then_success_has_no_post_success_wait(self, sleep):
        driver = Mock()
        type(driver).page_source = unittest.mock.PropertyMock(side_effect=[
            '<root><label name="正在上传"/></root>',
            '<root><label name="上传成功" visible="true"/></root>'])
        self.assertTrue(runtime.wait_upload_success(driver, fail_fast=True))
        sleep.assert_called_once_with(.3)
        driver.execute_script.assert_not_called()

    @patch.object(runtime.time, 'sleep')
    def test_ai_hidden_success_cannot_pass_upload_verification(self, sleep):
        driver = Mock(page_source='<root><label name="上传成功" visible="false"/></root>')
        with patch.object(runtime.time, 'monotonic', side_effect=range(100)):
            with self.assertRaisesRegex(RuntimeError, '上传超时'):
                runtime.wait_upload_success(driver, timeout=3, fail_fast=True)

    @patch.object(runtime.time, 'sleep')
    def test_upload_timeout_is_failure(self, sleep):
        driver = Mock(page_source='正在上传')
        with patch.object(runtime.time, 'monotonic', side_effect=range(100)):
            with self.assertRaisesRegex(RuntimeError, '上传超时'):
                runtime.wait_upload_success(driver, timeout=3)

    @patch.object(runtime.time, 'sleep')
    def test_return_must_confirm_order_list(self, sleep):
        driver = Mock()
        driver.page_source = '业务办理完成'
        with patch.object(runtime.time, 'monotonic', side_effect=range(100)), \
             patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'scene_navigation', return_value=dict(onSite=False, clicked=False)), \
             patch.object(runtime, 'visible_control', return_value=Mock()):
            with self.assertRaisesRegex(RuntimeError, '未确认现场订单列表'):
                runtime.return_scene_list(driver, 1, timeout=3)

    def test_already_returned_list_does_not_click_return_again(self):
        driver = Mock()
        with patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'scene_navigation', return_value=dict(onSite=True)) as navigation:
            self.assertTrue(runtime.return_scene_list(driver, 1))
        navigation.assert_called_once_with(driver)
        driver.find_elements.assert_not_called()

    def test_return_click_is_not_success_until_list_visible(self):
        with patch.object(runtime, 'require_foreground'), \
             patch.object(runtime.time, 'sleep'), \
             patch.object(runtime, 'scene_navigation', side_effect=[
                 dict(onSite=False), dict(clicked=True), dict(onSite=True)]) as navigation:
            self.assertTrue(runtime.return_scene_list(Mock(), 1))
        self.assertEqual(navigation.call_count, 3)


    def test_main_resets_each_round_before_creating_session(self):
        import test_manager_pure_recording_ios as manager
        driver = Mock()
        driver.get_settings.return_value = {}
        events = []
        with patch.object(manager.sys, 'argv', ['script', 'scene_manual', '2']), \
             patch.object(manager, 'reset_scene_order', side_effect=lambda order: events.append(('reset', order))), \
             patch.object(manager.webdriver, 'Remote', side_effect=lambda *a, **k: events.append(('session', None)) or driver), \
             patch.object(manager, 'run_scene_record_cycle'), \
             patch.object(manager.time, 'sleep'):
            manager.main()
        self.assertEqual(events, [('reset', manager.SCENE_ORDER_ID), ('session', None)] * 2)

    def test_reset_failure_prevents_device_session(self):
        import test_manager_pure_recording_ios as manager
        with patch.object(manager.sys, 'argv', ['script', 'scene_manual', '1']), \
             patch.object(manager, 'reset_scene_order', side_effect=RuntimeError('重置失败')), \
             patch.object(manager.webdriver, 'Remote') as remote:
            with self.assertRaises(SystemExit):
                manager.main()
        remote.assert_not_called()

    def test_stopped_process_is_reported_before_touch(self):
        driver = Mock()
        driver.query_app_state.return_value = 1
        with self.assertRaisesRegex(RuntimeError, '已停止运行'):
            runtime.require_foreground(driver, 'bundle')
        driver.terminate_app.assert_not_called()

    def test_navigation_click_waits_for_actual_scene_list(self):
        states = [dict(ready=True, onSite=False, clicked=False),
                  dict(ready=True, onSite=False, clicked=True),
                  dict(ready=True, onSite=False, clicked=False),
                  dict(ready=True, onSite=True, clicked=False)]
        with patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'scene_navigation', side_effect=states) as nav, \
             patch.object(runtime.time, 'sleep'):
            self.assertTrue(runtime.open_scene_navigation(Mock(), 1))
        self.assertEqual(sum(call.kwargs.get('click', False) for call in nav.call_args_list), 1)

    def test_navigation_does_not_pass_after_click_only(self):
        with patch.object(runtime, 'require_foreground'), \
             patch.object(runtime, 'scene_navigation', return_value=dict(ready=True, onSite=False, clicked=True)), \
             patch.object(runtime.time, 'sleep'), \
             patch.object(runtime.time, 'monotonic', side_effect=range(100)):
            with self.assertRaisesRegex(RuntimeError, '未确认现场订单列表'):
                runtime.open_scene_navigation(Mock(), 1, timeout=5)

    def test_navigation_returns_to_native_context(self):
        driver = Mock()
        driver.contexts = ['NATIVE_APP', 'WEBVIEW_1']
        driver.execute_script.return_value = dict(ready=True, clicked=False, onSite=True)
        self.assertTrue(runtime.scene_navigation(driver)['onSite'])
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_navigation_handles_whitespace_labels_in_dom(self):
        import subprocess
        import json
        harness = r"""
const assert=require('node:assert/strict');let source='';
process.stdin.on('data',s=>source+=s);process.stdin.on('end',()=>{
 const script=new Function(JSON.parse(source));
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 let clicked=0;
 const elements=['现 场','我 的','远 程','纯录制'].map(text=>({textContent:text,children:[],
 getBoundingClientRect:()=>({x:1,y:1,width:10,height:10}),contains:e=>false,
 closest:()=>null,click:()=>clicked++}));
 global.document={body:{innerText:'远程双录 订单'},querySelectorAll:()=>elements,
 elementFromPoint:()=>elements[0]};
 assert.equal(script(false).ready,true);
 assert.equal(script(true).clicked,true);assert.equal(clicked,1);
 assert.equal(script(false).onSite,false);
 document.body.innerText='现场双录 订单';assert.equal(script(false).onSite,true);
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(runtime.SCENE_NAV_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_background_is_distinguished_from_crash(self):
        driver = Mock()
        driver.query_app_state.return_value = 3
        with self.assertRaisesRegex(RuntimeError, '离开前台'):
            runtime.require_foreground(driver, 'bundle')

    def test_failure_diagnostics_never_terminates_app(self):
        driver = Mock()
        driver.query_app_state.return_value = 4
        driver.execute_script.return_value = {'bundleId': 'business-app'}
        runtime.capture_failure(driver, 'bundle', '.', 1)
        driver.save_screenshot.assert_called_once()
        driver.terminate_app.assert_not_called()


if __name__ == '__main__':
    unittest.main()
