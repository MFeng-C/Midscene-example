import unittest
import json
import subprocess
from unittest.mock import Mock, patch

import ios_customer_logout as logout


def state(**updates):
    result = dict(clicked=False, loggedOut=False, my=False, logout=False,
                  confirm=False, confirmAlt=False)
    result.update(updates)
    return result


class LogoutTest(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.driver.contexts = ['NATIVE_APP', 'WEBVIEW_1']
        self.driver.get_settings.return_value = {'waitForIdleTimeout': 7}
        self.shot = Mock()
        cleanup = patch.object(logout, 'stop_logout_confirmation')
        self.cleanup = cleanup.start()
        self.addCleanup(cleanup.stop)

    def test_my_logout_confirmation_and_login_verified(self):
        self.driver.execute_script.side_effect = [state(my=True),
            state(clicked=True, logout=True), state(clicked=True, confirm=True),
            state(clicked=True), state(loggedOut=True)]
        with patch.object(logout.time, 'sleep'):
            self.assertTrue(logout.logout_customer_ios(self.driver, 1, self.shot))
        self.assertEqual([c.args[1] for c in self.driver.execute_script.call_args_list],
                         [None, '我的', '退出登录', '确认', None])
        self.assertEqual(self.shot.call_count, 1)
        self.assertEqual(self.driver.update_settings.call_args.args[0], {'waitForIdleTimeout': 7})
        self.assertEqual(self.driver.switch_to.context.call_args.args[0], 'NATIVE_APP')

    def test_accepting_popup_without_login_page_is_failure(self):
        clock = Mock()
        clock.monotonic.side_effect = range(500)
        self.driver.execute_script.side_effect = [state(logout=True),
            state(clicked=True, confirm=True), state(clicked=True)] + [state()] * 30
        with patch.object(logout, 'time', clock):
            with self.assertRaisesRegex(RuntimeError, '未确认返回客户登录页'):
                logout.logout_customer_ios(self.driver, 1, self.shot, timeout=12)
        self.assertEqual(sum(c.args[1] == '确认' for c in self.driver.execute_script.call_args_list), 1)
        self.assertEqual(self.driver.update_settings.call_args.args[0], {'waitForIdleTimeout': 7})

    def test_resume_my_page_and_alternate_confirm(self):
        self.driver.execute_script.side_effect = [state(logout=True),
            state(clicked=True, confirmAlt=True), state(clicked=True, loggedOut=True)]
        self.assertTrue(logout.logout_customer_ios(self.driver, 1, self.shot))
        self.assertEqual([c.args[1] for c in self.driver.execute_script.call_args_list],
                         [None, '退出登录', '确定'])

    def test_already_logged_out_does_not_click(self):
        self.driver.execute_script.return_value = state(loggedOut=True)
        self.assertTrue(logout.logout_customer_ios(self.driver, 1, self.shot))
        self.driver.execute_script.assert_called_once_with(logout.LOGOUT_SCRIPT, None)

    def run_timed_states(self, responses, timeout=20):
        now = [0.0]

        def execute(script, action):
            elapsed, result = next(responses)
            now[0] += elapsed
            return result

        self.driver.execute_script.side_effect = execute
        with patch.object(logout.time, 'monotonic', side_effect=lambda: now[0]), \
                patch.object(logout.time, 'sleep'):
            return logout.logout_customer_ios(self.driver, 1, self.shot, timeout)

    def test_slow_logout_query_still_clicks_confirmation(self):
        self.assertTrue(self.run_timed_states(iter([
            (1, state(logout=True)),
            (53, state(clicked=True, confirm=True)),
            (30, state(clicked=True)),
            (1, state(loggedOut=True)),
        ])))
        self.assertEqual([c.args[1] for c in self.driver.execute_script.call_args_list],
                         [None, '退出登录', '确认', None])

    def test_delayed_confirmation_observed_after_deadline_is_clicked(self):
        self.assertTrue(self.run_timed_states(iter([
            (1, state(logout=True)), (1, state(clicked=True)),
            (25, state(confirm=True)), (1, state(clicked=True)),
            (1, state(loggedOut=True)),
        ])))

    def test_final_read_accepts_async_login_transition(self):
        self.assertTrue(self.run_timed_states(iter([
            (1, state(logout=True)), (1, state(clicked=True, confirm=True)),
            (53, state(clicked=True)), (21, state()),
            (1, state(loggedOut=True)),
        ])))
        self.assertEqual(self.driver.execute_script.call_args_list[-1].args[1], None)

    def test_stuck_confirmation_is_bounded_and_not_clicked_twice(self):
        with self.assertRaisesRegex(RuntimeError, '等待客户登录页'):
            self.run_timed_states(iter([
                (1, state(logout=True)), (1, state(clicked=True, confirm=True)),
                (1, state(clicked=True)), (21, state(confirm=True)),
                (1, state(confirm=True)),
            ]))
        self.assertEqual(sum(c.args[1] == '确认' for c in self.driver.execute_script.call_args_list), 1)

    def test_missing_entry_gets_one_final_read_then_fails(self):
        with self.assertRaisesRegex(RuntimeError, '查找登出入口'):
            self.run_timed_states(iter([(21, state()), (1, state())]))
        self.assertEqual(self.driver.execute_script.call_count, 2)

    def test_page_confirmation_does_not_need_another_remote_click(self):
        self.driver.execute_script.side_effect = [state(logout=True),
            state(clicked=True, confirm=True, autoConfirmed='确认'),
            state(loggedOut=True, autoConfirmed='确认')]
        with patch.object(logout.time, 'sleep'):
            self.assertTrue(logout.logout_customer_ios(self.driver, 1, self.shot))
        self.assertEqual([c.args[1] for c in self.driver.execute_script.call_args_list],
                         [None, '退出登录', None])
        self.cleanup.assert_called_once_with(self.driver)

    def test_page_confirmation_still_requires_login_page_and_cleans_up(self):
        with self.assertRaisesRegex(RuntimeError, '未确认返回客户登录页'):
            self.run_timed_states(iter([
                (1, state(logout=True)),
                (1, state(clicked=True, autoConfirmed='确定')),
                (21, state(autoConfirmed='确定')), (1, state(autoConfirmed='确定')),
            ]))
        self.cleanup.assert_called_once_with(self.driver)


class PageConfirmationTest(unittest.TestCase):
    def test_observer_only_confirms_logout_dialog_once_and_disconnects(self):
        harness = r"""
const assert=require('node:assert/strict');
let source=''; process.stdin.on('data',s=>source+=s);
process.stdin.on('end',()=>{
 const script=new Function(JSON.parse(source));
 for(const label of ['确认','确定']) {
  let observe, clicks=0, stopped=0, dialogText='删除订单吗';
  global.window={};
  global.getComputedStyle=()=>({display:'block',visibility:'visible',opacity:'1'});
  global.setInterval=()=>1; global.clearInterval=()=>{};
  global.setTimeout=()=>2; global.clearTimeout=()=>{};
  global.MutationObserver=class {
    constructor(callback){observe=callback;} observe(){} disconnect(){stopped++;}
  };
  const node=text=>({textContent:text,innerText:text,children:[],disabled:false,
    getBoundingClientRect:()=>({x:0,y:0,width:100,height:40}),
    contains:()=>true,closest:()=>null});
  const confirm=node(label); confirm.click=()=>clicks++;
  const logout=node('退出登录'); logout.click=()=>{};
  const dialog=node(''); dialog.querySelectorAll=()=>[confirm];
  Object.defineProperty(dialog,'textContent',{get:()=>dialogText});
  global.document={body:{innerText:''},elementFromPoint:()=>confirm,
    querySelectorAll:s=>s.includes('.van-dialog')?[dialog]:[logout,confirm]};
  script('退出登录');
  observe(); assert.equal(clicks,0,'不得点击其他业务确认弹窗');
  dialogText='确认退出登录？';
  observe(); observe();
  assert.equal(clicks,1); assert.equal(stopped,1);
  const state=script(label);
  assert.equal(clicks,1,'Python 兜底不得重复确认');
  assert.equal(state.autoConfirmed,label);
 }
});
"""
        result = subprocess.run(['node', '-e', harness], input=json.dumps(logout.LOGOUT_SCRIPT),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
