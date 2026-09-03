---
目前完成的工作汇总：

已完成

1. Company V2 公开历史财务摘要授权修复
- 将 `GET /api/v2/company/{market}/{symbol}/history` 从 debug/admin 门禁中拆出，匿名调用不再返回 `AUTH_REQUIRED`。
- 匿名调用无法使用 `force_refresh` 触发强制刷新；全局鉴权和其他 debug、管理路由保持不变。
- history 响应仅保留公开财务历史值、模块状态、source、as_of、coverage、field_availability、warnings 和 reason_code，并过滤 raw payload、trace、内部 ID 与性能诊断字段。

2. 公司页模块级容错
- profile、history 与 quote/debug 请求独立结算，debug 或 history 失败不再清空已成功加载的公司资料。
- profile 数据现在计入页面可展示状态，公司名称、交易所、行业和上市日期可在其他模块失败时继续显示。
- history 无数据或失败时显示“暂缺历史财务数据”；quote/debug 失败只显示对应模块提示。

3. 自动化验证
- 后端 history、Company V2 与鉴权相关回归：98 passed。
- 完整前端低并发套件：68 files、759 passed、0 failed、0 worker startup timeout。
- 前端 production build：通过，971 modules transformed。
- `git diff --check` 与 Python 编译检查：通过。

---
下一步：你需要操作

第一步：审阅独立分支 `phase7d-p0-1-public-history` 的最小提交及公开响应字段范围。
第二步：如 Owner 批准，再将该独立提交合入受控 release 分支；当前阶段不要部署。
第三步：继续将 Phase 7D-P0.2 作为独立工作项处理；Tushare EOD 只能补充个股行情/财务事实，不能替代行业或主题新闻授权。
