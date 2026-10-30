"""AI 共性控件的 DOM 快速路径：精确文本、可见性、唯一性和遮挡核验。"""
import time

PAGE_SCRIPT = r"""
const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
const text=document.body.innerText.replace(/\s/g,'');
const dialogs=Array.from(document.querySelectorAll('.van-dialog,[role="dialog"],.el-dialog')).filter(visible);
let clicked=false;
if(arguments[0]){
 const scope=arguments[1]?dialogs:[document.body];
 const buttons=[...new Set(scope.flatMap(p=>Array.from(p.querySelectorAll('button,[role="button"],a'))))]
 .filter(e=>e.textContent.replace(/\s/g,'')===arguments[0]&&visible(e)&&!e.disabled&&
 !e.closest('[disabled],[aria-disabled="true"],.van-button--disabled'));
 if(buttons.length===1){const b=buttons[0],r=b.getBoundingClientRect();
 const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
 if(top&&(top===b||b.contains(top))){b.click();clicked=true;}}
}
return {clicked,upload:text.includes('上传失败')?'failed':
 (text.includes('上传成功')||text.includes('上传文件成功'))?'success':'pending'};
"""


def run_page_action(driver, label=None, dialog=False, timeout=30, upload=False):
    started = time.monotonic()
    reads = 0
    try:
        context = next((c for c in driver.contexts if 'WEBVIEW' in c), None)
        if context is None:
            raise RuntimeError('AI 共性节点未找到 WebView')
        driver.switch_to.context(context)
        while True:
            state = driver.execute_script(PAGE_SCRIPT, label, dialog)
            reads += 1
            if upload and state['upload'] == 'failed':
                raise RuntimeError('现场 AI 录制文件上传失败，停止等待上传成功')
            if (upload and state['upload'] == 'success') or (not upload and state['clicked']):
                return True
            if time.monotonic() - started >= timeout:
                raise RuntimeError('现场录制上传超时，未出现上传成功提示' if upload
                                   else f'AI 共性控件未就绪或被遮挡：{label}')
            time.sleep(.2)
    finally:
        driver.switch_to.context('NATIVE_APP')
        print(f'    [AI共性节点] {"上传核验" if upload else label}：'
              f'{time.monotonic()-started:.2f}s，DOM读取 {reads} 次')


def click_ai_control(driver, label, dialog=False, timeout=30):
    return run_page_action(driver, label=label, dialog=dialog, timeout=timeout)


def wait_ai_upload(driver, timeout=120):
    return run_page_action(driver, timeout=timeout, upload=True)
