"""AI 循环失败后限制诊断开销，结束当前 App 并释放会话。"""
from appium.webdriver.client_config import AppiumClientConfig


def ai_client_config(server):
    # 客户端上限高于 WDA 的30秒，给代理响应及网络传输留出余量。
    return AppiumClientConfig(server, timeout=40,
        init_args_for_pool_manager={'init_args_for_pool_manager': {'retries': 0}})


def limit_failure_requests(driver):
    # 失败后的诊断/清理请求使用独立短期限，避免每个请求耗尽正常上限。
    driver.command_executor._client_config.timeout = 3


def end_failed_ai_cycle(driver, bundle_id):
    limit_failure_requests(driver)
    for label, action in [('结束本轮 App', lambda: driver.terminate_app(bundle_id)),
                          ('释放本轮 Appium 会话', driver.quit)]:
        try:
            action()
            print(f'    [AI失败收尾] {label}完成')
        except Exception as error:
            print(f'    [AI失败收尾] {label}失败：{type(error).__name__}；下一轮重新建会话并清理')
