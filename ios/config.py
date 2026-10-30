# iOS 双录 App 测试配置

# ====================== 设备配置 ======================
WDA_URL = "http://172.16.2.134:8100"
APPIUM_URL = "http://172.16.2.134:4723"
UDID = "7720cc4ebea57931c047c2cdc0a9fbc5f6cf0c5c"
PLATFORM_VERSION = "17"

# ====================== App配置 ======================
BUNDLE_ID = "com.juphoon.record.ios"

# ====================== 客户账号 ======================
CUSTOMER_ID = "411525200006040977"
CUSTOMER_PASSWORD = "Record123456"
CUSTOMER_CAPTCHA = "0000"

# ====================== 客户经理账号 ======================
MANAGER_ID = "10001"
MANAGER_PASSWORD = "Aa123456"
MANAGER_CAPTCHA = "0000"



# ======================分界线==========================#
# 上面部分：可调整                                       #
# 下面部分：不需要调整                                   #
# =====================================================#

# ====================== 按钮文本常量 ======================
TEXT_CUSTOMER_LOGIN = "客户登录"
TEXT_MANAGER_LOGIN = "客户经理登录"
TEXT_LOGIN_BTN = "登录"
TEXT_MY = "我的"
TEXT_LOGOUT = "退出登录"
TEXT_CAPTCHA_PLACEHOLDER = "请输入验证码"
TEXT_ID_PLACEHOLDER = "请输入身份证号码"
TEXT_PASSWORD_PLACEHOLDER = "请输入登录密码"
TEXT_MANAGER_ID_PLACEHOLDER = "请输入客户经理工号"

# ====================== 超时配置(秒) ======================
APP_LAUNCH_TIMEOUT = 8
LOGIN_FORM_TIMEOUT = 9
LOGIN_BTN_TIMEOUT = 10
PAGE_LOAD_TIMEOUT = 10
LOGOUT_CONFIRM_TIMEOUT = 5

# ====================== 轮询配置 ======================
POLL_INTERVAL_FAST = 0.2      # 快速轮询间隔(秒)
POLL_INTERVAL_NORMAL = 0.3     # 普通轮询间隔(秒)
POLL_INTERVAL_SLOW = 0.5      # 慢速轮询间隔(秒)

# ====================== Appium 配置 ======================
WEBDRIVER_AGENT_URL = WDA_URL
NEW_COMMAND_TIMEOUT = 300
WDA_CONNECTION_TIMEOUT = 60000
AUTO_ACCEPT_ALERTS = True
SKIP_LOG_CAPTURE = True
ENABLE_WEBVIEW_DETAILS = True
AUTO_WEBVIEW = False
ENSURE_WEBVIEWS_HAVE_PAGES = True
WEBVIEW_CONNECT_TIMEOUT = 30000
WEBKIT_DEBUG_PROXY_PORT = 9221
SHOW_XCODE_LOG = True
NEW_COMMAND_TIMEOUT_SHORT = 60
WEBVIEW_CONNECT_RETRIES = 30
NATIVE_WEB_TAP = True

# ====================== 截图配置 ======================
SCREENSHOT_DIR = "screenshots"
ENABLE_SCREENSHOT = False  # 默认关闭，可通过环境变量 SCREENSHOT=1 开启
