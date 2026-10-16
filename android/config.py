# Android 双录 App 测试配置

# ====================== 设备配置 ======================
DEVICE_ID = "b76086c1"

# ====================== App配置 ======================
PACKAGE_NAME = "com.juphoon.hybridrecord"
ACTIVITY_NAME = "com.juphoon.hybrid.record.webhybrid.WebHybridActivity"
APP_NAME = "智能双录"
SYSTEM_INPUT_METHOD = "com.sohu.inputmethod.sogou.xiaomi/.SogouIME"

# ====================== 客户账号 ======================
CUSTOMER_ID = "330212198508192621"
CUSTOMER_PASSWORD = "Record123456"
CUSTOMER_CAPTCHA = "0000"

# ====================== 客户经理账号 ======================
MANAGER_ID = "10001"
MANAGER_PASSWORD = "Aa123456"
MANAGER_CAPTCHA = "0000"

# ====================== 订单配置 ======================
ORDER_ID_PURE_RECORD = "OD2100856414927859712"  # 客户经理纯录制订单号
ORDER_ID_CUSTOMER_PURE_RECORD = "OD2100856414927859712"  # 客户纯录制订单号
CUSTOMER_NAME_PURE_RECORD = "郇伟"  # 客户纯录制客户名称
ORDER_ID_SELF_SERVICE = "OD2102934122029674496"  # 自助双录订单号
CUSTOMER_NAME_SELF_SERVICE = "郇伟"  # 自助双录客户名称
ORDER_ID_SCENE = "OD2104818769953079296"  # 现场双录订单号
CUSTOMER_NAME_SCENE = "郇伟"  # 现场双录客户名称

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
TEXT_PURE_RECORD = "纯录制"
TEXT_SELF_SERVICE = "自助"
TEXT_SELF_RECORD = "自助"
TEXT_SCENE = "现场"
TEXT_MY = "我的"
TEXT_LOGIN_BTN = "登录"
TEXT_RECORD_BTN = "录制"
TEXT_CONFIRM = "确认"
TEXT_AGREE_AND_START = "同意并开始双录"
TEXT_AGREE_AND_START_RECORD = "同意并开始录制"
TEXT_IMMEDIATELY_START = "立即开始"
TEXT_AGREE_CHECK = "同意检测"
TEXT_START_RECORD = "开始录制"
TEXT_PAUSE_RECORD = "暂停"
TEXT_CONTINUE_RECORD = "继续录制"
TEXT_SCREENSHOT = "截图"
TEXT_END_RECORD = "结束录制"
TEXT_CONFIRM_COMPLETE = "确认完成"
TEXT_ABORT_RECORD = "放弃录制"
TEXT_SKIP = "跳过"
TEXT_RETURN = "返回"
TEXT_END = "结束"
TEXT_LOGOUT = "退出登录"
TEXT_NEXT_STEP = "下一步"
TEXT_FINISH_RECORD = "完成录制"
TEXT_START_AI = "开始（AI）"
TEXT_START_MANUAL = "开始（人工）"
TEXT_SELECT_ALL = "全选"

# ====================== UI元素定位符 ======================
INPUT_ID_CARD = "van-field-4-input"
INPUT_PASSWORD = "van-field-5-input"
INPUT_CAPTCHA = "van-field-6-input"

# ====================== 超时配置(秒) ======================
LOGIN_TIMEOUT = 10
FORM_TIMEOUT = 15
CAPTCHA_INPUT_TIMEOUT = 5
LOGIN_BTN_TIMEOUT = 5
RECORD_BTN_TIMEOUT = 10
AGREE_TIMEOUT = 10
CHECK_TIMEOUT = 10
DETECTION_TIMEOUT = 120
UPLOAD_TIMEOUT = 120
MY_MENU_TIMEOUT = 10
RETURN_TIMEOUT = 10
END_TIMEOUT = 10
LOGOUT_TIMEOUT = 10
CONFIRM_TIMEOUT = 5

# ====================== 等待时间配置(秒) ======================
WAIT_APP_LAUNCH = 5
WAIT_PAGE_LOAD = 3
WAIT_ELEMENT = 0.5
WAIT_INPUT = 0.3
WAIT_CLEAR_TEXT = 0.2
WAIT_LONG_CLICK = 0.5
WAIT_BACK = 1
WAIT_SWIPE = 1.5
WAIT_POPUP = 2
WAIT_RECORDING = 2
WAIT_SCREENSHOT_BEFORE_END = 3
WAIT_COUNTDOWN = 3
WAIT_DETECTION_PASSED = 3
WAIT_UPLOAD = 5
WAIT_STABLE = 5
WAIT_ORDER_LOAD = 3
WAIT_BUSINESS_DONE = 3
WAIT_RECORD_END = 2
WAIT_FINISH_PAGE = 2
WAIT_END_PAGE = 3
WAIT_RETURN_PAGE = 2
WAIT_LOGOUT_PAGE = 2

# ====================== 截图文件名常量 ======================
SCREENSHOT_STEP_LAUNCH = "step1_after_launch"
SCREENSHOT_STEP_LOGIN = "step2_after_customer_login"
SCREENSHOT_ERROR_PREFIX = "error_step"
SCREENSHOT_CUSTOMER_RECORD_PREFIX = "customer_record"
SCREENSHOT_CUSTOMER_SELF_PREFIX = "customer_self"
SCREENSHOT_MANAGER_PREFIX = "manager"
SCREENSHOT_SCENE_AI_PREFIX = "scene_ai"
SCREENSHOT_SCENE_MANUAL_PREFIX = "scene_manual"
