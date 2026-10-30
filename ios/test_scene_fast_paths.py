import unittest
from unittest.mock import Mock, patch

import scene_fast_paths as fast
import scene_manual_nodes as nodes
import scene_manual_runtime as runtime


class FastPathsTest(unittest.TestCase):
    def test_progress_does_not_merge_adjacent_score(self):
        import json
        import subprocess
        harness = r"""
const assert=require('node:assert/strict');let source='';
process.stdin.on('data',s=>source+=s);process.stdin.on('end',()=>{
 const snapshot=new Function(JSON.parse(source));
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 let parts=[];
 global.document={body:{innerText:''},querySelectorAll:()=>parts};
 const element=text=>({innerText:text,textContent:text,children:[],
  getBoundingClientRect:()=>({x:0,y:0,width:50,height:20}),closest:()=>null});
 // 即使整页文字紧连，优先取独立的进度元素。
 parts=[element('进度 1/4'),element('95/100')];
 document.body.innerText='进度1/495/100';
 assert.deepEqual(snapshot(false,null).progress,[1,4]);
 parts=[element('进度： 4 / 12'),element('100/100')];
 document.body.innerText='进度：4/12100/100';
 assert.deepEqual(snapshot(false,null).progress,[4,12]);
 // 没有独立元素时保留原始空白作为数字边界。
 parts=[];document.body.innerText='进度 2/4\n95/100';
 assert.deepEqual(snapshot(false,null).progress,[2,4]);
 document.body.innerText='正在录制 95/100';
 assert.equal(snapshot(false,null).progress,null);
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(fast.NODE_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_search_dom_path_does_not_open_keyboard_or_run_fallback(self):
        driver = Mock()
        driver.is_keyboard_shown.return_value = False
        driver.execute_script.side_effect = [dict(opened=True), dict(ready=True), True, True]
        fallback, result = Mock(), Mock(return_value=True)
        self.assertTrue(fast.search_scene_order(driver, 1, 'order', 'name', Mock(return_value=True), fallback, result))
        fallback.assert_not_called()
        driver.hide_keyboard.assert_not_called()
        result.assert_called_once_with(driver)

    def test_search_without_entry_uses_compatible_fallback(self):
        driver = Mock()
        driver.execute_script.return_value = dict(opened=False)
        fallback = Mock(return_value=True)
        self.assertTrue(fast.search_scene_order(driver, 1, 'order', 'name', Mock(return_value=False), fallback, Mock()))
        fallback.assert_called_once_with(driver, 1, fast_search=True, dom_search=True,
                                         order_id='order', customer_name='name')

    def test_icon_coordinate_recovery_keeps_dom_input(self):
        driver = Mock()
        driver.get_window_size.return_value = dict(width=400, height=800)
        driver.is_keyboard_shown.return_value = False
        driver.execute_script.side_effect = [dict(opened=False), dict(ready=True), True, True]
        fallback = Mock()
        self.assertTrue(fast.search_scene_order(driver, 1, 'order', 'name',
                        Mock(return_value=True), fallback, Mock(return_value=True)))
        driver.tap.assert_called_once_with([(360, 56)])
        fallback.assert_not_called()
        driver.hide_keyboard.assert_not_called()

    def test_search_icon_script_skips_obscured_candidate(self):
        import json
        import subprocess
        harness = r"""
const assert=require('node:assert/strict');let source='';
process.stdin.on('data',s=>source+=s);process.stdin.on('end',()=>{
 const open=new Function(JSON.parse(source));let clicks=0;
 global.innerWidth=400;global.innerHeight=800;
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 const icon=(x,attrs)=>({tagName:'svg',textContent:'',
  getBoundingClientRect:()=>({x,y:20,width:24,height:24}),
  getAttribute:k=>attrs[k]||null,contains:()=>false,closest:()=>null,
  click:()=>clicks++});
 const blocked=icon(310,{'class':'filter'}),valid=icon(360,{});
 global.document={body:{innerText:'现场双录'},querySelector:()=>null,
  querySelectorAll:s=>s==='input'?[]:[blocked,valid],
  elementFromPoint:x=>x<350?{contains:()=>false}:valid};
 assert.equal(open().opened,true);assert.equal(clicks,1);
 // 已展开表单时不能再次点击入口，将表单收起。
 document.querySelectorAll=s=>s==='input'?[{...valid,placeholder:'订单号'}]:[valid];
 assert.equal(open().opened,true);assert.equal(clicks,1);
 // 实际导航栏筛选容器使用原生触摸，不能把装饰图标 click 视为已打开。
 const nav={...valid,querySelector:()=>valid,contains:()=>true};
 document.querySelector=()=>nav;document.querySelectorAll=()=>[];
 assert.equal(open().nativeTap,true);assert.equal(clicks,1);
 // 实际表单 placeholder 是“请输入”，通过字段名识别已展开，避免再次点击收起。
 document.querySelectorAll=s=>s==='input'?[{...valid,name:'orderId',placeholder:'请输入'}]:[];
 assert.equal(open().opened,true);assert.equal(clicks,1);
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(fast.OPEN_SEARCH_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_search_failed_query_does_not_submit_twice_or_click_record(self):
        driver = Mock()
        driver.is_keyboard_shown.return_value = False
        driver.execute_script.side_effect = [dict(opened=True), dict(ready=True), False]
        fallback, result = Mock(), Mock()
        with self.assertRaisesRegex(RuntimeError, '查询按钮'):
            fast.search_scene_order(driver, 1, 'order', 'name', Mock(return_value=True), fallback, result)
        fallback.assert_not_called()
        result.assert_not_called()

    def test_batch_node_progress_is_verified_before_next_click(self):
        def state(progress, **kwargs):
            return dict(progress=progress, signature=False, finish=False, review=False,
                        next=True, clicked=False) | kwargs
        sequence = [state((1, 4)), state((1, 4), clicked=True), state((1, 4)),
                    state((2, 4)), state((2, 4), clicked=True), state((3, 4), finish=True)]
        with patch.object(nodes, 'node_snapshot', side_effect=sequence) as snapshot, \
             patch.object(nodes.time, 'sleep'), patch.object(nodes, 'visible_control') as native:
            self.assertTrue(nodes.advance_manual_nodes(Mock(), 1, batch=True))
        native.assert_not_called()
        self.assertEqual(sum(c.kwargs.get('click', False) for c in snapshot.call_args_list), 2)

    def test_batch_signature_dispatches_three_characters(self):
        with patch.object(nodes, 'node_snapshot', side_effect=[dict(signature=True),
                          dict(signature=False, review=True)]), \
             patch.object(nodes, 'sign_scene_name') as sign:
            self.assertTrue(nodes.advance_manual_nodes(Mock(), 1, batch=True))
        sign.assert_called_once_with(unittest.mock.ANY, 1, character_count=3)

    def test_cleanup_quits_even_if_settings_restore_fails(self):
        driver = Mock()
        driver.update_settings.side_effect = RuntimeError('restore failed')
        runtime.cleanup_session(driver, {})
        driver.quit.assert_called_once()

    def test_manual_start_waits_for_node_without_fixed_sleep(self):
        with patch.object(runtime, 'wait_control', return_value=Mock()) as button, \
             patch.object(fast, 'node_snapshot', return_value=dict(progress=(1, 4))), \
             patch.object(runtime.time, 'sleep') as sleep:
            self.assertTrue(runtime.start_manual_recording(Mock(), 1))
        sleep.assert_not_called()
        button.return_value.click.assert_called_once()


if __name__ == '__main__':
    unittest.main()
