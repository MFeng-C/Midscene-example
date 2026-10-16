# iOS 纯录制业务测试配置

# ====================== 设备配置 ======================
WDA_URL = "http://172.16.1.39:8100"
APPIUM_URL = "http://172.16.1.39:4723"
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

# ====================== 订单配置 ======================
ORDER_ID = "OD2054126084278943744"  # 测试用订单号

# ====================== 数据库配置 ======================
DB_HOST = "192.168.18.223"
DB_PORT = 3306
DB_USER = "kiwi"
DB_PASSWORD = "juphoon419708"
DB_NAME = "test"
DB_TABLE = "dual_record_order_ex"
DB_STATE_FIELD = "state"



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
TEXT_SELF_SERVICE = "自助"
TEXT_PURE_RECORD = "纯录制"
TEXT_RECORD_BTN = "录制"
TEXT_CONFIRM = "确认"
TEXT_AGREE_AND_START = "同意并开始录制"
TEXT_AGREE_AND_START_DUAL = "同意并开始双录"
TEXT_START_LIVE = "开始直播"
TEXT_AGREE_CHECK = "同意检测"
TEXT_START_RECORD = "开始录制"
TEXT_END_RECORD = "结束录制"
TEXT_CONFIRM_COMPLETE = "确认完成"
TEXT_SKIP = "跳过"
TEXT_RECHECK = "重新检测"
TEXT_NEXT_STEP = "下一步"
TEXT_FINISH_RECORD = "完成录制"
TEXT_RETURN = "返回"
TEXT_END = "结束"
TEXT_UPLOAD_SUCCESS = "文件上传成功"
TEXT_UPLOAD_SUCCESS2 = "上传成功"
TEXT_END_SERVICE = "结束办理"
TEXT_END_SERVICE2 = "结束服务"
TEXT_SERVICE_ENDED = "本次服务已结束"

# 输入框占位符文本
TEXT_ID_PLACEHOLDER = "请输入身份证号码"
TEXT_PASSWORD_PLACEHOLDER = "请输入登录密码"
TEXT_CAPTCHA_PLACEHOLDER = "请输入验证码"

# ====================== 超时配置(秒) ======================
APP_LAUNCH_TIMEOUT = 8
LOGIN_FORM_TIMEOUT = 9
LOGIN_BTN_TIMEOUT = 10
PAGE_LOAD_TIMEOUT = 6
POPUP_TIMEOUT = 3
AGREE_BTN_TIMEOUT = 15
START_LIVE_TIMEOUT = 5
AGREE_CHECK_TIMEOUT = 15
DETECTION_TIMEOUT = 15
RECORD_BTN_TIMEOUT = 15
END_RECORD_TIMEOUT = 15
CONFIRM_TIMEOUT = 15
UPLOAD_TIMEOUT = 30
END_TIMEOUT = 10
RETURN_TIMEOUT = 9
LOGOUT_TIMEOUT = 10
CONFIRM_LOGOUT_TIMEOUT = 5

# 播报/朗读等待
BROADCAST_TIMEOUT = 30
BROADCAST_READING_TIMEOUT = 24
BUSINESS_COMPLETE_TIMEOUT = 30

# ====================== 轮询配置 ======================
POLL_INTERVAL_FAST = 0.2
POLL_INTERVAL_NORMAL = 0.3
POLL_INTERVAL_SLOW = 0.5

# ====================== 倒计时配置 ======================
COUNTDOWN_SECONDS = 3
COUNTDOWN_BUFFER = 0.5

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
SCREENSHOT_DIR = "ios/screenshots_pure_recording"
ENABLE_SCREENSHOT = False  # 默认关闭，可通过环境变量 SCREENSHOT=1 开启

# ====================== WebView CSS选择器 ======================
CSS_DIALOG_CONFIRM = '.van-dialog__confirm'
CSS_DIALOG_CONFIRM_BTN = 'button.van-dialog__confirm'
CSS_AGREE_BTN = 'button.agree-btn'
