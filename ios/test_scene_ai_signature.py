import json
import subprocess
import unittest
from unittest.mock import Mock, patch

import scene_ai_signature as ai
import scene_manual_nodes as nodes
import self_service_signature as shared
from test_scene_manual_signature import state


class AISignatureTest(unittest.TestCase):
    def test_slow_three_characters_and_submit_get_independent_completion_budget(self):
        driver = Mock()
        driver.get_settings.return_value = {}
        snapshots = iter([state('b1'), state('i1'), state('b2'), state('i2'),
                          state('b3'), state('i3'), state(text='提交签名', label='提交签名'),
                          state(text='请客户经理确认签字 进度4/4', label='下一步')])
        clock = [0]

        def read(*args, **kwargs):
            s = next(snapshots)
            clock[0] += 35 if '确认签字' in s['text'] else 1
            return s

        def draw(*args):
            clock[0] += 28

        def execute(script, *args):
            if script == ai.CONFIRM_SCRIPT:
                clock[0] += 3
                return True
            return dict(node=dict(progress=[4, 4], next=True, clicked=bool(args[0])))

        driver.execute_script.side_effect = execute
        with patch.object(ai, 'signature_snapshot', side_effect=read), \
             patch.object(ai, 'draw_test_signature', side_effect=draw), \
             patch.object(ai.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(ai.time, 'sleep'):
            result = ai.sign_ai_name(driver, 1)
        self.assertGreater(clock[0], 90)
        self.assertTrue(result['clicked'])
        confirms = [c.args[1] for c in driver.execute_script.call_args_list
                    if c.args[0] == ai.CONFIRM_SCRIPT]
        self.assertEqual(confirms, ['确定', '确定', '确定', '提交签名'])

    def test_submitted_page_stuck_times_out_without_repeated_submission(self):
        driver = Mock()
        driver.get_settings.return_value = {}
        snapshots = iter([state('b1'), state('i1'), state('b2'), state('i2'),
                          state('b3'), state('i3')])
        clock = [0]

        def read(*args, **kwargs):
            clock[0] += 5
            return next(snapshots, state(text='提交签名', label='提交签名'))

        def execute(script, *args):
            if script == ai.CONFIRM_SCRIPT:
                return True
            clock[0] += 5
            return dict(node=dict(progress=[4, 4], next=False, clicked=False))

        driver.execute_script.side_effect = execute
        with patch.object(ai, 'signature_snapshot', side_effect=read), \
             patch.object(ai, 'draw_test_signature'), \
             patch.object(ai.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(ai.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, '未能点击下一步'):
                ai.sign_ai_name(driver, 1)
        confirms = [c.args[1] for c in driver.execute_script.call_args_list if c.args[0] == ai.CONFIRM_SCRIPT]
        self.assertEqual(confirms, ['确定', '确定', '确定', '提交签名'])
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_post_signature_retries_readiness_and_revalidates_blocked_next(self):
        driver = Mock()
        driver.get_settings.return_value = {}
        snapshots = [state('b1'), state('i1'), state('b2'), state('i2'),
                     state('b3'), state('i3'), state(text='提交签名', label='提交签名')]
        waiting = dict(progress=[4, 4], next=False, clicked=False)
        ready = dict(waiting, next=True)
        driver.execute_script.side_effect = [True, True, True, True,
                                             dict(node=waiting), dict(node=ready), dict(node=ready),
                                             dict(node=ready), dict(node=dict(ready, clicked=True))]
        with patch.object(ai, 'signature_snapshot', side_effect=snapshots) as read, \
             patch.object(ai, 'draw_test_signature'), patch.object(ai.time, 'sleep'):
            result = ai.sign_ai_name(driver, 1)
        self.assertTrue(result['clicked'])
        self.assertEqual(read.call_count, 7)  # 提交后不再读取签名字形画布。
        submits = [c for c in driver.execute_script.call_args_list
                   if c.args[0] == ai.CONFIRM_SCRIPT and c.args[1] == '提交签名']
        self.assertEqual(len(submits), 1)

    def test_three_real_draws_dom_confirms_and_guarded_next(self):
        driver = Mock()
        driver.get_settings.return_value = {}
        snapshots = [state('b1'), state('i1'), state('b2'), state('i2'),
                     state('b3'), state('i3'), state(text='进度 4/4', label='下一步')]
        node = dict(progress=[4, 4], next=True, clicked=False)
        driver.execute_script.side_effect = [True, True, True, dict(node=node),
                                             dict(node=dict(node, clicked=True))]
        with patch.object(ai, 'signature_snapshot', side_effect=snapshots) as read, \
             patch.object(ai, 'draw_test_signature') as draw, \
             patch('scene_manual_signature.time.sleep'):
            result = ai.sign_ai_name(driver, 1)
        self.assertTrue(result['clicked'])
        self.assertEqual(result['progress'], (4, 4))
        self.assertEqual(draw.call_count, 3)
        self.assertTrue(all(call.kwargs['keep_webview'] for call in read.call_args_list))
        driver.tap.assert_not_called()
        driver.execute_script.assert_called_with(ai.AI_NODE_SCRIPT, True, [4, 4])
        driver.switch_to.context.assert_called_with('NATIVE_APP')
        driver.update_settings.assert_called_with({'waitForIdleTimeout': 10, 'animationCoolOffTimeout': 2})

    def test_no_ink_cannot_confirm_or_advance(self):
        driver = Mock()
        driver.get_settings.return_value = {}
        with patch.object(ai, 'signature_snapshot', side_effect=[state('blank'), state('blank')]), \
             patch.object(ai, 'draw_test_signature'):
            with self.assertRaisesRegex(RuntimeError, '未生成笔迹'):
                ai.sign_ai_name(driver, 1)
        driver.execute_script.assert_not_called()

    def test_blocked_confirmation_fails_without_native_fallback(self):
        driver = Mock()
        driver.get_settings.return_value = {}
        driver.execute_script.return_value = False
        with patch.object(ai, 'signature_snapshot', side_effect=[state('b'), state('i')]), \
             patch.object(ai, 'draw_test_signature'):
            with self.assertRaisesRegex(RuntimeError, '被遮挡'):
                ai.sign_ai_name(driver, 1)
        driver.tap.assert_not_called()

    def test_handoff_waits_for_transition_without_reclicking(self):
        driver = Mock()
        reader = Mock(side_effect=[dict(signature=True),
                                  dict(signature=False, review=False, finish=False,
                                       next=True, progress=(4, 4)),
                                  dict(signature=False, review=False, finish=True)])
        handler = Mock(return_value=dict(progress=(4, 4), clicked=True))
        with patch.object(nodes.time, 'sleep'):
            self.assertTrue(nodes.advance_manual_nodes(driver, 1, batch=True,
                            snapshot_reader=reader, signature_handler=handler))
        self.assertEqual(reader.call_count, 3)
        self.assertTrue(all(not call.kwargs.get('click') for call in reader.call_args_list))

    def test_eager_node_click_is_not_repeated_and_pending_disables_auto_advance(self):
        driver = Mock()
        initial = dict(signature=False, review=False, finish=False,
                       next=True, progress=(3, 4), clicked=True)
        waiting = dict(initial, clicked=False)
        reader = Mock(side_effect=[initial, waiting,
                                  dict(signature=False, review=False, finish=True)])
        with patch.object(nodes.time, 'sleep'):
            self.assertTrue(nodes.advance_manual_nodes(driver, 1, batch=True,
                            snapshot_reader=reader, eager_advance=True))
        self.assertEqual([c.kwargs for c in reader.call_args_list],
                         [dict(advance=True), dict(advance=False), dict(advance=False)])

    def test_snapshot_keeps_webview_only_when_opted_in(self):
        for keep in (False, True):
            driver = Mock()
            driver.execute_script.return_value = dict(width=100, height=100, text='请客户经理进行签字')
            shared.signature_snapshot(driver, cache=dict(view={}, context='WEBVIEW_1'),
                                      signature_prompt='请客户经理进行签字', keep_webview=keep)
            self.assertEqual(driver.switch_to.context.call_args.args[0],
                             'WEBVIEW_1' if keep else 'NATIVE_APP')

    def test_confirmation_js_checks_hit_bounds_disabled_and_uniqueness(self):
        harness = r"""
const assert=require('node:assert/strict');let code='';
process.stdin.on('data',s=>code+=s);process.stdin.on('end',()=>{
 const click=new Function(JSON.parse(code)),rect={x:0,y:0,width:100,height:40};let clicks=0;
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 const b={innerText:'确定',disabled:false,getAttribute:()=>null,
 getBoundingClientRect:()=>rect,contains:e=>e===b,click:()=>clicks++};
 global.document={querySelectorAll:()=>[b],elementFromPoint:()=>b};
 assert.equal(click('确定',rect),true);assert.equal(clicks,1);
 document.elementFromPoint=()=>({});assert.equal(click('确定',rect),false);
 document.elementFromPoint=()=>b;b.disabled=true;assert.equal(click('确定',rect),false);
 b.disabled=false;assert.equal(click('确定',{...rect,x:50}),false);
 document.querySelectorAll=()=>[b,b];assert.equal(click('确定',rect),false);
 assert.equal(clicks,1);
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(ai.CONFIRM_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
