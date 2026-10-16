# H5 单端与 Android 客户角色覆盖对照

## 对照结果

| H5 客户用例 | Android 原有覆盖 | 本次处理 |
| --- | --- | --- |
| 客户登录、进入“我的”、退出登录 | `test_jdualrecord_app.py customer` | 保留原用例 |
| 客户登录页必填/非法证件号校验、密码显隐 | 无独立覆盖 | 新增 `login-validation` |
| 客户远程列表字段、状态/产品组合筛选、高级搜索、重置和空结果 | 无覆盖 | 新增 `remote-filter-search` |
| 客户纯录制完整业务 | `test_jdualrecord_app.py customer_record` | 保留原用例 |
| 客户自助双录完整业务 | `test_jdualrecord_app.py customer_self` | 保留原用例 |
| 办理提示页可见、进入业务页 | 已包含在纯录制和自助双录流程 | 不重复新增 |

H5 的 `h5-business-ready` 和 `h5-remind-ready` 使用带运行参数的浏览器直达
URL。Android App 没有等价的外部路由测试入口，因此不单独迁移；对应页面已由现有
Android 业务流程从订单列表进入并覆盖。

## 新增脚本

新增用例位于 `test_customer_h5_coverage.py`，不导入、不修改
`test_jdualrecord_app.py`，因此不会改变现有 Android 测试命令和业务流程。

```powershell
# 登录表单校验
python test_customer_h5_coverage.py login-validation

# 远程筛选与高级搜索
python test_customer_h5_coverage.py remote-filter-search

# 依次执行全部新增用例
python test_customer_h5_coverage.py all
```

运行截图统一写入 `customer_h5_coverage_artifacts/`。测试失败时脚本返回非零退出码，
并额外保存失败现场截图。

## 覆盖边界

- Android 与 H5 使用同一业务页面，但 Android 通过 WebView 可访问性节点定位控件。
- 订单状态 Picker 选项为“待处理”，选中后 Android 顶部展示为“待质检”；脚本兼容两个文案。
- 高级搜索按钮优先使用无障碍描述定位，旧版本页面无描述时才使用右上角相对坐标。
- 远程列表用例只查询不存在的订单，不启动录制，也不修改订单状态。
- 账号、密码、验证码和设备编号继续读取现有 `config.py`。
