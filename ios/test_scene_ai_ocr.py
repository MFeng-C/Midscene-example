import unittest
from unittest.mock import Mock, patch
import scene_ai_ocr as ocr


def panel(key, side):
    return dict(present=True, ready=True, key=key, side=side, width=100, height=100,
                rect=dict(x=10, y=20, width=20, height=20))


class OCRTest(unittest.TestCase):
    def test_dom_only_selects_skip_inside_ocr_dialog(self):
        import json
        import subprocess
        harness = r"""
const assert=require('node:assert/strict');let code='';
process.stdin.on('data',s=>code+=s);process.stdin.on('end',()=>{
 const read=new Function(JSON.parse(code));global.innerWidth=100;global.innerHeight=100;
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 let clicks=0;
 const skip={textContent:'跳过',click:()=>clicks++,getBoundingClientRect:()=>({x:10,y:20,width:20,height:20}),
  closest:()=>null,contains:e=>e===skip};
 const panel={innerText:'OCR识别人工确认 国徽面 签发机关 跳过 重新识别',querySelectorAll:()=>[skip]};
 const title={...skip,textContent:'OCR识别人工确认',closest:()=>panel};
 global.document={body:{innerText:'OCR识别人工确认'},querySelectorAll:()=>[title],elementFromPoint:()=>skip};
 assert.equal(read().side,'国徽面');assert.equal(read().ready,true);
 assert.equal(read(true,'wrong-key').clicked,false);assert.equal(clicks,0);
 assert.equal(read(true,panel.innerText.replace(/\s/g,'')).clicked,true);assert.equal(clicks,1);
 panel.innerText='OCR识别人工确认 姓名 身份证号码 跳过 重新识别';
 assert.equal(read().side,'人像面');
 document.elementFromPoint=()=>({contains:()=>false});assert.equal(read().ready,false);
 assert.equal(read(true,panel.innerText.replace(/\s/g,'')).clicked,false);assert.equal(clicks,1);
 document.querySelectorAll=()=>[skip];assert.equal(read().present,false);
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(ocr.OCR_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_combined_script_blocks_node_click_while_ocr_is_visible(self):
        import json
        import subprocess
        harness = r"""
const assert=require('node:assert/strict');let code='';
process.stdin.on('data',s=>code+=s);process.stdin.on('end',()=>{
 const read=new Function(JSON.parse(code));global.innerWidth=100;global.innerHeight=100;
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 let clicks=0;
 const next={innerText:'下一步',textContent:'下一步',children:[],closest:()=>null,
 getBoundingClientRect:()=>({x:0,y:0,width:50,height:20}),click:()=>clicks++};
 const progress={...next,innerText:'进度 3/4',textContent:'进度 3/4'};
 global.document={body:{innerText:'进度 3/4'},querySelectorAll:()=>[next,progress],elementFromPoint:()=>next};
 assert.deepEqual(read(true,[3,4]).node.progress,[3,4]);assert.equal(clicks,1);
 assert.equal(read(false,null,true).node.clicked,true);assert.equal(clicks,2);
 document.body.innerText='请客户经理进行签字 进度 3/4';
 assert.equal(read(false,null,true).node.clicked,false);assert.equal(clicks,2);
 const title={...next,textContent:'OCR识别人工确认',closest:()=>null};
 document.body.innerText='OCR识别人工确认 进度 3/4';document.querySelectorAll=()=>[title,next,progress];
 assert.equal(read(true,[3,4]).ocr.present,true);assert.equal(clicks,2);
 assert.equal(read(false,null,true).ocr.present,true);assert.equal(clicks,2);
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(ocr.AI_NODE_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def driver(self):
        driver = Mock()
        view = Mock(rect=dict(x=0, y=0, width=200, height=100))
        driver.find_elements.return_value = [view]
        return driver

    def test_both_faces_are_skipped_once_and_transition_verified(self):
        driver = self.driver()
        back, front = panel('back', '国徽面'), panel('front', '人像面')
        with patch.object(ocr, 'read_ocr', side_effect=[back, back, front, front, dict(present=False)]), \
             patch.object(ocr.time, 'sleep'):
            self.assertEqual(ocr.skip_ocr_confirmations(driver), 2)
        self.assertEqual(driver.tap.call_count, 2)
        driver.tap.assert_called_with([(40, 30)])

    def test_separate_popups_are_detected_on_each_poll(self):
        driver = self.driver()
        with patch.object(ocr, 'read_ocr', side_effect=[panel('back', '国徽面'), dict(present=False),
                         panel('front', '人像面'), dict(present=False)]), \
             patch.object(ocr.time, 'sleep'):
            self.assertEqual(ocr.skip_ocr_confirmations(driver), 1)
            self.assertEqual(ocr.skip_ocr_confirmations(driver), 1)
        self.assertEqual(driver.tap.call_count, 2)

    def test_unchanged_dialog_fails_without_repeated_tap(self):
        driver = self.driver()
        with patch.object(ocr, 'read_ocr', return_value=panel('back', '国徽面')), \
             patch.object(ocr.time, 'sleep'), \
             patch.object(ocr.time, 'monotonic', side_effect=range(50)):
            with self.assertRaisesRegex(RuntimeError, '未关闭或切换'):
                ocr.skip_ocr_confirmations(driver)
        driver.tap.assert_called_once()

    def test_unrelated_skip_is_not_clicked(self):
        driver = self.driver()
        with patch.object(ocr, 'read_ocr', return_value=dict(present=False)):
            self.assertEqual(ocr.skip_ocr_confirmations(driver), 0)
        driver.tap.assert_not_called()

    def test_dom_skip_revalidates_dialog_key_and_still_verifies_closure(self):
        driver = self.driver()
        initial = panel('back', '国徽面')
        with patch.object(ocr, 'read_ocr', side_effect=[dict(initial, clicked=True), dict(present=False)]) as read, \
             patch.object(ocr.time, 'sleep'):
            self.assertEqual(ocr.skip_ocr_confirmations(driver, initial_state=initial, dom_click=True), 1)
        self.assertEqual(read.call_args_list[0].kwargs, dict(click=True, key='back'))
        driver.find_elements.assert_not_called()
        driver.tap.assert_not_called()

    def test_node_click_is_checked_after_ocr(self):
        driver = Mock()
        driver.contexts = ['NATIVE_APP', 'WEBVIEW_1']
        popup = panel('back', '国徽面')
        driver.execute_script.side_effect = [dict(ocr=popup),
                                             dict(node=dict(progress=[3, 4], clicked=True))]
        with patch.object(ocr, 'skip_ocr_confirmations') as skip:
            state = ocr.ai_node_snapshot(driver, click=True, progress=(3, 4))
        skip.assert_called_once_with(driver, initial_state=popup)
        self.assertEqual(state['progress'], (3, 4))
        self.assertTrue(state['clicked'])
        self.assertEqual(driver.execute_script.call_count, 2)

    def test_normal_poll_uses_single_script_and_no_separate_ocr_read(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.return_value = dict(node=dict(progress=[2, 4], clicked=False))
        with patch.object(ocr, 'read_ocr') as read:
            self.assertEqual(ocr.ai_node_snapshot(driver)['progress'], (2, 4))
        read.assert_not_called()
        driver.execute_script.assert_called_once_with(ocr.AI_NODE_SCRIPT, False, None)
        driver.switch_to.context.assert_any_call('NATIVE_APP')


if __name__ == '__main__':
    unittest.main()
