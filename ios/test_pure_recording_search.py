import unittest
import json
import subprocess
from unittest.mock import Mock, patch

import pure_recording_search as search


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.switch = Mock(return_value=True)

    def test_open_once_then_fill_verified_form(self):
        self.driver.execute_script.side_effect = [dict(ready=False, opened=True), dict(ready=True, opened=False)]
        with patch.object(search.time, 'sleep'):
            self.assertTrue(search.prepare_search(self.driver, 'order', 'name', self.switch))
        self.assertEqual([c.args[-1] for c in self.driver.execute_script.call_args_list], [True, False])
        self.driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_form_timeout_returns_to_native_for_fallback(self):
        self.driver.execute_script.return_value = dict(ready=False, opened=False)
        self.assertFalse(search.prepare_search(self.driver, 'order', 'name', self.switch, timeout=0))
        self.driver.switch_to.context.assert_called_with('NATIVE_APP')

    def test_failed_webview_read_uses_fallback(self):
        self.driver.execute_script.side_effect = RuntimeError('stale context')
        self.assertFalse(search.prepare_search(self.driver, 'order', 'name', self.switch))

    def test_keyboard_not_shown_avoids_slow_hide(self):
        self.driver.is_keyboard_shown.return_value = False
        fallback = Mock()
        self.assertTrue(search.confirm_keyboard_hidden(self.driver, fallback))
        fallback.assert_not_called()

    def test_visible_keyboard_still_requires_hiding(self):
        self.driver.is_keyboard_shown.return_value = True
        fallback = Mock(return_value=False)
        self.assertFalse(search.confirm_keyboard_hidden(self.driver, fallback))
        fallback.assert_called_once_with(self.driver)

    def test_unknown_keyboard_state_does_not_mean_hidden(self):
        self.driver.is_keyboard_shown.side_effect = RuntimeError('unsupported')
        fallback = Mock(return_value=True)
        self.assertTrue(search.confirm_keyboard_hidden(self.driver, fallback))
        fallback.assert_called_once_with(self.driver)

    def test_dom_search_sets_named_fields_dispatches_events_and_blurs(self):
        harness = r"""
const assert=require('node:assert/strict');let source='';
process.stdin.on('data',s=>source+=s);process.stdin.on('end',()=>{
 const script=new Function(JSON.parse(source));
 global.getComputedStyle=()=>({display:'block',visibility:'visible'});
 global.HTMLInputElement=class {
  constructor(placeholder){this.placeholder=placeholder;this.events=[];this.v='old';}
  get value(){return this.v;} set value(v){this.v=v;}
  getAttribute(){return null;} closest(){return null;}
  getBoundingClientRect(){return {width:100,height:30};}
  dispatchEvent(e){this.events.push(e.type);}
 };
 const order=new HTMLInputElement('订单号'),customer=new HTMLInputElement('客户名称');
 let fields=[order,customer],blurs=0;
 global.document={querySelectorAll:s=>s==='input'?fields:[],activeElement:{blur:()=>blurs++}};
 assert.equal(script('order-123','customer',false).ready,true);
 assert.equal(order.value,'order-123');assert.equal(customer.value,'customer');
 assert.deepEqual(order.events,['input','change']);assert.equal(blurs,1);
 const unrelated=new HTMLInputElement('不相关字段');fields=[unrelated];
 assert.equal(script('order-123','customer',false).ready,false);
 assert.equal(unrelated.value,'old');
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(search.SEARCH_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
