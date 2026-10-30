import json
import subprocess
import unittest
from unittest.mock import Mock, patch

import scene_ai_pages as pages
import scene_ai_ocr as ocr
import scene_ai_runtime as runtime


class AIFastPagesTest(unittest.TestCase):
    def test_node_polls_reuse_context_until_invalidated(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.return_value = dict(node=dict(progress=[2, 4], clicked=False))
        read = ocr.AINodeReader()
        read(driver)
        read(driver)
        driver.switch_to.context.assert_called_once_with('WEBVIEW_1')
        read.invalidate()
        read(driver)
        self.assertEqual(driver.switch_to.context.call_count, 2)
        self.assertEqual(read.reads, 3)

    def test_ocr_native_action_invalidates_cached_context(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.side_effect = [dict(ocr=dict(present=True)),
                                             dict(node=dict(progress=[3, 4], clicked=False))]
        with patch.object(ocr, 'skip_ocr_confirmations') as skip:
            result = ocr.AINodeReader()(driver)
        self.assertEqual(result['progress'], (3, 4))
        skip.assert_called_once()
        self.assertEqual([c.args[0] for c in driver.switch_to.context.call_args_list],
                         ['WEBVIEW_1', 'NATIVE_APP', 'WEBVIEW_1'])

    def test_failed_reader_restores_native_without_repeating_click(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.side_effect = RuntimeError('lost context')
        read = ocr.AINodeReader()
        with self.assertRaisesRegex(RuntimeError, 'lost context'):
            read(driver, click=True, progress=(3, 4))
        self.assertFalse(read.active)
        self.assertIsNone(read.context)
        driver.switch_to.context.assert_called_with('NATIVE_APP')
        driver.execute_script.assert_called_once()

    def test_upload_fails_fast_and_restores_native(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.return_value = dict(upload='failed', clicked=False)
        with patch.object(pages.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, '上传失败'):
                pages.wait_ai_upload(driver)
        sleep.assert_not_called()
        driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_upload_pending_then_success_reuses_context(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.side_effect = [dict(upload='pending'), dict(upload='success')]
        with patch.object(pages.time, 'sleep'):
            self.assertTrue(pages.wait_ai_upload(driver))
        self.assertEqual([c.args[0] for c in driver.switch_to.context.call_args_list],
                         ['WEBVIEW_1', 'NATIVE_APP'])

    def test_upload_timeout_is_still_failure(self):
        driver = Mock()
        driver.contexts = ['WEBVIEW_1']
        driver.execute_script.return_value = dict(upload='pending')
        with patch.object(pages.time, 'monotonic', side_effect=range(100)), \
             patch.object(pages.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, '上传超时'):
                pages.wait_ai_upload(driver, timeout=3)

    def test_finish_uses_exact_dom_control_and_verifies_review(self):
        driver = Mock()
        with patch.object(runtime, 'node_snapshot', side_effect=[dict(review=False, finish=True),
                                                               dict(review=True)]), \
             patch.object(runtime, 'click_ai_control') as click:
            self.assertTrue(runtime.finish_ai_recording(driver, 1))
        click.assert_called_once_with(driver, '完成录制')

    def test_dom_confirm_is_scoped_unique_enabled_and_unobscured(self):
        harness = r"""
const assert=require('node:assert/strict');let code='';
process.stdin.on('data',s=>code+=s);process.stdin.on('end',()=>{
 const read=new Function(JSON.parse(code));let clicks=0;
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 const rect={x:0,y:0,width:40,height:20};
 const b={textContent:'确认',disabled:false,closest:()=>null,
 getBoundingClientRect:()=>rect,contains:e=>e===b,click:()=>clicks++};
 let buttons=[b];const dialog={getBoundingClientRect:()=>rect,querySelectorAll:()=>buttons};
 global.document={body:{innerText:'正在上传',querySelectorAll:()=>[b]},
 querySelectorAll:()=>[dialog],elementFromPoint:()=>b};
 assert.equal(read('确认',true).clicked,true);assert.equal(clicks,1);
 document.elementFromPoint=()=>({});assert.equal(read('确认',true).clicked,false);
 document.elementFromPoint=()=>b;b.disabled=true;assert.equal(read('确认',true).clicked,false);
 b.disabled=false;buttons=[];assert.equal(read('确认',true).clicked,false);
 const other={...b};buttons=[b,other];assert.equal(read('确认',true).clicked,false);
 document.body.innerText='文件上传失败 Unknown error';assert.equal(read(null,false).upload,'failed');
 document.body.innerText='上传成功';assert.equal(read(null,false).upload,'success');
 assert.equal(clicks,1);
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(pages.PAGE_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
