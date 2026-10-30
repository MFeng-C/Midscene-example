import copy
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

import self_service_signature as signature


def state(ink='blank', text='请客户进行签字', controls=('确定',)):
    rect = dict(x=50, y=100, width=200, height=200)
    return dict(text=text, width=414, height=716,
                view=dict(x=0, y=20, width=414, height=716),
                canvas=dict(rect=rect, ink=ink) if ink is not None else None,
                controls=[dict(text=t, enabled=True, rect=rect) for t in controls])


class SignatureTest(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.driver.get_settings.return_value = {'waitForIdleTimeout': 4}
        self.shot = Mock()

    def test_each_character_confirm_submit_and_exact_completion(self):
        sequence = [state(), state('ink1'), state(), state('ink2'),
                    state(None, '提交签名', ('提交签名',)),
                    state(None, '业务办理完成', ('返回',))]
        with patch.object(signature, 'signature_snapshot', side_effect=sequence), \
                patch.object(signature, 'draw_test_signature') as draw, \
                patch.object(signature.time, 'sleep'):
            self.assertTrue(signature.wait_self_service_completion(
                self.driver, 1, self.shot, '郇伟'))
        self.assertEqual(draw.call_count, 2)
        self.assertEqual(self.driver.tap.call_count, 3)
        self.assertFalse(any('signature_before' in c.args[1] or 'signature_ink' in c.args[1]
                             for c in self.shot.call_args_list))
        self.assertEqual(self.driver.update_settings.call_args.args[0],
                         {'waitForIdleTimeout': 4, 'animationCoolOffTimeout': 2})

    def test_no_ink_must_not_confirm(self):
        with patch.object(signature, 'signature_snapshot', return_value=state()), \
                patch.object(signature, 'draw_test_signature'):
            with self.assertRaisesRegex(RuntimeError, '未在画布生成笔迹'):
                signature.wait_self_service_completion(self.driver, 1, self.shot, '郇伟')
        self.driver.tap.assert_not_called()
        self.assertEqual(self.driver.update_settings.call_args.args[0],
                         {'waitForIdleTimeout': 4, 'animationCoolOffTimeout': 2})

    def test_unchanged_canvas_must_not_sign_twice(self):
        clock = Mock()
        clock.monotonic.side_effect = range(500)
        sequence = [state(), state('ink')] + [state('ink')] * 20
        with patch.object(signature, 'signature_snapshot', side_effect=sequence), \
                patch.object(signature, 'draw_test_signature') as draw, \
                patch.object(signature, 'time', clock):
            with self.assertRaisesRegex(RuntimeError, '未清空或切换'):
                signature.wait_self_service_completion(self.driver, 1, self.shot, '郇伟')
        self.assertEqual(draw.call_count, 1)
        self.assertEqual(self.driver.tap.call_count, 1)

    def test_generic_complete_word_cannot_pass(self):
        clock = Mock()
        clock.monotonic.side_effect = range(500)
        with patch.object(signature, 'signature_snapshot',
                          return_value=state(None, '请完成签字', ())), \
                patch.object(signature, 'time', clock):
            with self.assertRaisesRegex(RuntimeError, '未出现业务办理完成'):
                signature.wait_self_service_completion(self.driver, 1, self.shot, '郇伟', timeout=3)

    def test_coordinates_account_for_webview_offset_and_scale(self):
        s = state()
        s['view'] = dict(x=10, y=20, width=828, height=1432)
        self.assertEqual(signature.native_point(s, s['canvas']['rect']), (310, 420))

    def test_submission_gets_fresh_budget_after_slow_signature_and_screenshot(self):
        now = [0]
        clock = Mock()
        clock.monotonic.side_effect = lambda: now[0]
        def snapshot(driver, **kwargs):
            if now[0] == 0:
                now[0] = 179
                return state(None, '提交签名', ('提交签名',))
            now[0] += 1
            return state(None, '业务办理完成', ('返回',))
        def screenshot(driver, name):
            if 'submitted' in name:
                now[0] = 190  # 旧的总超时已到，但还没检查提交后的完成页。
        with patch.object(signature, 'signature_snapshot', side_effect=snapshot), \
                patch.object(signature, 'time', clock):
            self.assertTrue(signature.wait_self_service_completion(
                self.driver, 5, screenshot, '郇伟'))
        self.assertEqual(self.driver.tap.call_count, 1)

    def test_slow_final_read_of_completed_page_is_not_discarded(self):
        clock = Mock()
        clock.monotonic.side_effect = [0, 100]
        with patch.object(signature, 'signature_snapshot',
                          return_value=state(None, '业务办理完成', ('返回',))), \
                patch.object(signature, 'time', clock):
            self.assertTrue(signature.wait_self_service_completion(
                self.driver, 5, self.shot, '郇伟', timeout=3))

    def test_recording_finished_is_not_business_completion(self):
        clock = Mock()
        clock.monotonic.side_effect = range(500)
        with patch.object(signature, 'signature_snapshot',
                          return_value=state(None, '录制已完成', ())), \
                patch.object(signature, 'time', clock):
            with self.assertRaisesRegex(RuntimeError, '录制完成后.*未出现业务办理完成'):
                signature.wait_self_service_completion(
                    self.driver, 5, self.shot, '郇伟', completion_timeout=3)

    def test_out_of_view_canvas_is_rejected(self):
        s = copy.deepcopy(state())
        s['canvas']['rect']['x'] = -10
        with self.assertRaisesRegex(RuntimeError, '边界无效'):
            signature.draw_test_signature(self.driver, s)

    def test_snapshot_reuses_webview_discovery_within_one_flow(self):
        self.driver.contexts = ['NATIVE_APP', 'WEBVIEW_1']
        view = Mock()
        view.rect = state()['view']
        view.is_displayed.return_value = True
        self.driver.find_elements.return_value = [view]
        self.driver.execute_script.side_effect = [state(), state('ink')]
        cache = {}
        signature.signature_snapshot(self.driver, cache)
        signature.signature_snapshot(self.driver, cache)
        self.driver.find_elements.assert_called_once()
        self.assertEqual(cache['context'], 'WEBVIEW_1')

    def test_failed_context_query_invalidates_cached_geometry(self):
        cache = dict(view=state()['view'], context='WEBVIEW_1', dimensions=(414,716))
        self.driver.execute_script.side_effect = RuntimeError('stale WebView')
        with self.assertRaisesRegex(RuntimeError, 'stale WebView'):
            signature.signature_snapshot(self.driver, cache)
        self.assertEqual(cache, {})
        self.assertEqual(self.driver.switch_to.context.call_args.args[0], 'NATIVE_APP')

    def test_animation_wait_is_disabled_only_during_signature_and_restored(self):
        self.driver.get_settings.return_value = {'waitForIdleTimeout': 4,
                                                 'animationCoolOffTimeout': .8}
        with patch.object(signature, 'signature_snapshot',
                          return_value=state(None, '业务办理完成', ('返回',))):
            self.assertTrue(signature.wait_self_service_completion(self.driver, 1, self.shot, '郇伟'))
        self.assertEqual([c.args[0] for c in self.driver.update_settings.call_args_list],
                         [{'waitForIdleTimeout': 0, 'animationCoolOffTimeout': 0},
                          {'waitForIdleTimeout': 4, 'animationCoolOffTimeout': .8}])

    def test_pixel_fingerprint_detects_ink_and_clearing_without_png_encoding(self):
        harness = r"""
const assert=require('node:assert/strict');
let source='';process.stdin.on('data',s=>source+=s);
process.stdin.on('end',()=>{
 const snapshot=new Function(JSON.parse(source));
 global.innerWidth=414;global.innerHeight=716;
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 const pixels=new Uint8ClampedArray(16);
 const button={innerText:'确定',disabled:false,getAttribute:()=>null,
  getBoundingClientRect:()=>({x:50,y:310,width:200,height:40})};
 const canvas={width:2,height:2,clientWidth:200,clientHeight:200,
  getBoundingClientRect:()=>({x:50,y:100,width:200,height:200}),
  getContext:()=>({getImageData:()=>({data:pixels})}),
  toDataURL:()=>{throw Error('不应进行 PNG 编码');}};
 global.document={body:{innerText:'请客户进行签字'},
  querySelectorAll:s=>s==='canvas'?[canvas]:[button]};
 const blank=snapshot().canvas.ink;
 pixels[3]=255;
 assert.notEqual(snapshot().canvas.ink,blank);
 pixels[3]=0;
 assert.equal(snapshot().canvas.ink,blank);
 // 现场客户经理提示不能使用客户默认文案来定位画布。
 document.body.innerText='请客户经理进行签字';
 assert.equal(snapshot().canvas,null);
 assert.ok(snapshot('请客户经理进行签字').canvas);
 document.body.innerText='请 客户经理 进行签字';
 assert.ok(snapshot('请客户经理进行签字').canvas);
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(signature.SNAPSHOT_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
