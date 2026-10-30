import unittest
import json
import shutil
import subprocess
from unittest.mock import Mock, patch, PropertyMock

import scene_ai_upload_failure as recovery
import test_manager_pure_recording_ios as manager
from contextlib import ExitStack


class UploadFailureTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'DOM fixture requires Node.js')
    def test_custom_div_dialog_and_exact_scoped_actions(self):
        # 执行真实定位脚本，复现无组件类名、div 按钮的弹窗。
        fixture = r'''
const script=JSON.parse(require('fs').readFileSync(0,'utf8'));
class E {
 constructor(text='',children=[]){this.text=text;this.children=children;this.hidden=false;
  for(const c of children)c.parentElement=this;}
 get textContent(){return this.text+this.children.map(c=>c.textContent).join('');}
 get innerText(){return this.textContent;}
 getBoundingClientRect(){return this.rect||{x:1,y:1,width:this.hidden?0:100,height:40};}
 contains(e){return e===this||this.children.some(c=>c.contains(e));}
 closest(){return null;}
 click(){this.clicked=true;}
}
const cancel=new E('取消'),confirm=new E('确认');
const dialog=new E('',[new E('文件上传失败'),new E('Unknown error'),cancel,confirm]);
const unrelated=new E('取消'),end=new E('结束');
const body=new E('',[unrelated,end,dialog]);
const all=e=>[e,...e.children.flatMap(all)];
let hit=cancel;
const document={body,documentElement:{clientWidth:1000,clientHeight:500},
 querySelectorAll:s=>s.startsWith('.van-dialog')?[]:all(body),
 elementFromPoint:()=>hit};
const run=new Function('document','getComputedStyle','phase',
 'return (function(){'+script+'}).call(null,phase)');
const style=()=>({display:'block',visibility:'visible'});
let state=run(document,style,'cancel');
if(!state.clicked||!cancel.clicked||confirm.clicked||unrelated.clicked)throw Error('wrong cancel');
state=run(document,style,'end');
if(state.clicked||end.clicked)throw Error('clicked behind modal');
cancel.clicked=false;cancel.disabled=true;
cancel.closest=()=>({});
state=run(document,style,'cancel');
if(state.clicked)throw Error('disabled cancel');
cancel.closest=()=>null;cancel.disabled=false;
// 文字不接收指针事件时命中外层白底按钮，仍应精确点击同一个按钮。
const caption=new E('取消');caption.parentElement=cancel;
cancel.text='';cancel.children=[caption];
cancel.tagName='BUTTON';caption.tagName='SPAN';
cancel.rect={x:100,y:100,width:360,height:50};
caption.rect={x:250,y:110,width:40,height:25};
state=run(document,style,'cancel');
if(!state.clicked||state.candidateCount!==1||state.targetTag!=='BUTTON')throw Error('wide button caption rejected');
// 不带标准标签的自定义弹窗按钮也不能受顶部控件的宽度比限制。
cancel.tagName='DIV';
state=run(document,style,'cancel');
if(!state.clicked||state.targetTag!=='DIV')throw Error('wide custom button rejected');
cancel.tagName='BUTTON';
// 背景按钮、遮罩和真正禁用的按钮仍不能绕过。
hit=unrelated;cancel.clicked=false;
state=run(document,style,'cancel');
if(state.clicked||state.reason!=='blocked'||cancel.clicked)throw Error('overlay bypassed');
const duplicate=new E('取消');duplicate.parentElement=dialog;dialog.children.push(duplicate);
hit=cancel;
state=run(document,style,'cancel');
if(state.clicked||state.reason!=='ambiguous_candidates')throw Error('ambiguous cancel');
dialog.children.pop();
caption.closest=()=>({});
state=run(document,style,'cancel');
if(state.clicked||state.reason!=='no_candidate')throw Error('disabled nested caption');
// 取消后同文案有两个可见节点，按截图中的右上方位置确定目标。
body.children.pop();
end.rect={x:880,y:5,width:100,height:40};
const oldEnd=new E('结束');oldEnd.rect={x:880,y:400,width:100,height:40};
oldEnd.parentElement=body;body.children.push(oldEnd);
hit=end;
state=run(document,style,'end');
if(state.clicked||!state.tapTarget||end.clicked||oldEnd.clicked||state.rawCandidateCount!==2||
 state.candidateCount!==1)throw Error('top right end not selected');
// 即使文案和位置相同，被遮挡的旧节点也不应制造歧义。
oldEnd.rect=end.rect;end.clicked=false;
state=run(document,style,'end');
if(state.clicked||!state.tapTarget||oldEnd.clicked)throw Error('covered duplicate end');
// 顶部目标被其他层遮挡时仍不得点击。
hit=unrelated;end.clicked=false;
state=run(document,style,'end');
if(state.clicked||state.tapTarget||end.clicked)throw Error('covered end clicked');
'''
        result = subprocess.run(['node', '-e', fixture], input=json.dumps(recovery.STATE_SCRIPT),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_end_uses_native_touch_with_scaled_webview_coordinates(self):
        driver = Mock()
        driver.page_source = '<App><XCUIElementTypeWebView visible="true" x="10" y="20" width="2000" height="1000"/></App>'
        target = dict(width=1000, height=500, rect=dict(x=880, y=5, width=100, height=40))
        with patch.object(recovery, 'ActionBuilder') as builder:
            recovery.tap_end_control(driver, target, 'WEBVIEW_1')
        actions = builder.return_value
        actions.pointer_action.move_to_location.assert_called_once_with(1870, 70)
        actions.pointer_action.pointer_down.assert_called_once()
        actions.pointer_action.pointer_up.assert_called_once()
        actions.perform.assert_called_once()
        driver.find_elements.assert_not_called()
        driver.switch_to.context.assert_called_with('WEBVIEW_1')

    def test_ambiguous_webviews_never_receive_touch(self):
        driver = Mock()
        driver.page_source = '<App><XCUIElementTypeWebView x="0" y="0" width="1000" height="500"/><XCUIElementTypeWebView x="0" y="50" width="1000" height="450"/></App>'
        target = dict(width=1000, height=500, rect=dict(x=880, y=5, width=100, height=40))
        with patch.object(recovery, 'ActionBuilder') as builder:
            with self.assertRaisesRegex(RuntimeError, '唯一 WebView 区域'):
                recovery.tap_end_control(driver, target, 'WEBVIEW_1')
        builder.assert_not_called()
        driver.switch_to.context.assert_called_with('WEBVIEW_1')

    def test_three_nested_webviews_with_identical_bounds_share_one_touch_region(self):
        driver = Mock()
        node = '<XCUIElementTypeWebView visible="true" x="0" y="0" width="736" height="414">'
        driver.page_source = '<App>' + node * 3 + '</XCUIElementTypeWebView>' * 3 + '</App>'
        target = dict(width=736, height=414, rect=dict(x=670, y=5, width=50, height=30))
        with patch.object(recovery, 'ActionBuilder') as builder:
            recovery.tap_end_control(driver, target, 'WEBVIEW_1')
        builder.return_value.pointer_action.move_to_location.assert_called_once_with(695, 20)
        builder.return_value.perform.assert_called_once()
        driver.switch_to.context.assert_called_with('WEBVIEW_1')

    def test_single_source_read_ignores_hidden_parent_and_zero_size(self):
        driver = Mock()
        source = '''<App><Panel visible="false"><XCUIElementTypeWebView width="10" height="20"/></Panel>
        <XCUIElementTypeWebView width="0" height="20"/>
        <XCUIElementTypeWebView x="0" y="0" width="1000" height="500"/></App>'''
        target = dict(width=1000, height=500, rect=dict(x=880, y=5, width=100, height=40))
        with patch.object(type(driver), 'page_source', new_callable=PropertyMock, create=True,
                          return_value=source) as page, patch.object(recovery, 'ActionBuilder'):
            recovery.tap_end_control(driver, target, 'WEBVIEW_1')
        page.assert_called_once()
        driver.find_elements.assert_not_called()

    def test_cancel_disappearance_and_end_target_share_one_query(self):
        driver = Mock(contexts=['WEBVIEW_1'])
        driver.execute_script.side_effect = [
            dict(clicked=True, failed=False, failureDialog=True),
            dict(clicked=False, failed=False, failureDialog=False, endingDialog=False,
                 tapTarget={'target': True}),
            dict(clicked=False, failed=False, endingDialog=True),
            dict(clicked=True, failed=False, endingDialog=False),
            dict(clicked=False, failed=True)]
        with patch.object(recovery, 'tap_end_control') as tap, patch.object(recovery.time, 'sleep'):
            recovery.close_failed_upload(driver, 1, Mock(), Mock())
        tap.assert_called_once_with(driver, {'target': True}, 'WEBVIEW_1')
        self.assertEqual([c.args[1] for c in driver.execute_script.call_args_list],
                         ['cancel', 'end', 'observe', 'confirm', 'failed'])

    def test_end_touch_once_then_observe_until_confirmation(self):
        driver = Mock(contexts=['WEBVIEW_1'])
        driver.execute_script.side_effect = [
            dict(clicked=True, failed=False, failureDialog=False),
            dict(clicked=False, failed=False, endingDialog=False, tapTarget={'target': True}),
            dict(clicked=False, failed=False, endingDialog=False),
            dict(clicked=False, failed=False, endingDialog=True),
            dict(clicked=True, failed=False, endingDialog=False),
            dict(clicked=False, failed=True)]
        with patch.object(recovery, 'tap_end_control') as tap, patch.object(recovery.time, 'sleep'):
            recovery.close_failed_upload(driver, 1, Mock(), Mock())
        tap.assert_called_once_with(driver, {'target': True}, 'WEBVIEW_1')
        self.assertEqual([c.args[1] for c in driver.execute_script.call_args_list],
                         ['cancel', 'end', 'observe', 'observe', 'confirm', 'failed'])

    def test_click_once_and_wait_for_each_transition(self):
        driver = Mock(contexts=['WEBVIEW_1'])
        driver.execute_script.side_effect = [
            dict(clicked=True, failed=False, failureDialog=True, endingDialog=False),
            dict(clicked=False, failed=False, failureDialog=False, endingDialog=False),
            dict(clicked=True, failed=False, failureDialog=False, endingDialog=False),
            dict(clicked=False, failed=False, failureDialog=False, endingDialog=True),
            dict(clicked=True, failed=False, failureDialog=False, endingDialog=True),
            dict(clicked=False, failed=False, failureDialog=False, endingDialog=False),
            dict(clicked=False, failed=True, failureDialog=False, endingDialog=False)]
        with patch.object(recovery.time, 'sleep'):
            recovery.close_failed_upload(driver, 1, Mock(), Mock())
        self.assertEqual([c.args[1] for c in driver.execute_script.call_args_list],
                         ['cancel', 'end', 'end', 'observe', 'confirm', 'observe', 'failed'])

    def check_flow_remains_failed_after_orderly_exit(self, mode):
        names = ('prepare_manager login_manager open_scene_navigation search_scene_order '
                 'step5_scene_confirm_popup step6_scene_click_agree_and_start '
                 'step7_scene_click_start_now step8_scene_click_agree_detection '
                 'step11_scene_wait_countdown start_ai_recording exercise_scene_controls '
                 'advance_ai_nodes finish_ai_recording step16_scene_review_and_confirm '
                 'step17_scene_confirm_popup step19_scene_upload_confirm '
                 'return_scene_list logout_customer_ios step24_scene_home screenshot '
                 'start_manual_recording step14_scene_manual_qa_node '
                 'step15_scene_manual_reading_node').split()
        with ExitStack() as stack:
            mocks = {name: stack.enter_context(patch.object(manager, name)) for name in names}
            stack.enter_context(patch.object(manager, 'step9_scene_wait_detection_result', return_value='passed'))
            stack.enter_context(patch.object(manager, 'wait_upload_success',
                side_effect=manager.SceneUploadFailed('upload failed')))
            def close(driver, cycle, back, logout):
                back()
                logout()
            closer = stack.enter_context(patch.object(manager, 'close_failed_upload', side_effect=close))
            with self.assertRaisesRegex(manager.SceneUploadFailed, 'upload failed'):
                manager.run_scene_record_cycle(Mock(), 1, record_type=mode)
            closer.assert_called_once()
            mocks['return_scene_list'].assert_called_once()
            mocks['logout_customer_ios'].assert_called_once()
            mocks['step19_scene_upload_confirm'].assert_not_called()

    def test_ai_flow_remains_failed_after_orderly_exit(self):
        self.check_flow_remains_failed_after_orderly_exit('ai')

    def test_manual_flow_remains_failed_after_orderly_exit(self):
        self.check_flow_remains_failed_after_orderly_exit('manual')

    def test_order_and_failed_page_before_list_and_logout(self):
        events = []
        driver = Mock()
        driver.contexts = ['NATIVE_APP', 'WEBVIEW_1']
        def execute(script, phase):
            events.append(phase)
            return dict(clicked=phase != 'failed', failed=phase == 'failed')
        driver.execute_script.side_effect = execute
        recovery.close_failed_upload(driver, 2,
            lambda: events.append('list'), lambda: events.append('logout'))
        self.assertEqual(events, ['cancel', 'end', 'confirm', 'failed', 'list', 'logout'])
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_missing_failed_page_does_not_return_or_logout(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.side_effect = lambda script, phase: dict(
            clicked=phase != 'failed', failed=False)
        back, logout = Mock(), Mock()
        with self.assertRaisesRegex(RuntimeError, 'failed'):
            recovery.close_failed_upload(driver, 1, back, logout, timeout=0)
        back.assert_not_called()
        logout.assert_not_called()
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_list_verification_failure_prevents_logout(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.return_value = dict(clicked=True, failed=True)
        logout = Mock()
        with self.assertRaisesRegex(RuntimeError, 'list missing'):
            recovery.close_failed_upload(driver, 1,
                Mock(side_effect=RuntimeError('list missing')), logout)
        logout.assert_not_called()


if __name__ == '__main__':
    unittest.main()
