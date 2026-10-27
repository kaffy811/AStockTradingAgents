---
目前完成的工作汇总：

已完成

1. 生产运行身份与资源只读检查
- 记录服务器 Git HEAD/tree、backend/frontend 镜像和容器 ID、健康状态、重启次数、OOM 状态、内存、Swap 与磁盘。
- 两个容器均在运行，restart count 为 0，未发生 OOM；backend 为 healthy。

2. Company 公共接口 smoke
- `/health`、京东方 A profile、annual history 均返回 HTTP 200。
- profile 返回完整公司名；history 为 6/6 模块可用且无 `AUTH_REQUIRED`。
- 按部署代码的正向 allowlist 验证 history 顶层、模块和记录字段，违规数为 0；Token、raw payload、trace、Provider URL 和内部异常标记命中数为 0。

3. 站点与日志只读检查
- 服务器本地前端与公开 `aastock.cloud` 均返回 HTTP 200。
- 部署后日志及内核日志的 5xx、健康失败、OOM、磁盘 I/O、Tushare 失败/超时、未批准 Provider 和公开泄漏标记计数均为 0。

4. 24 小时观察登记
- 登记窗口为 `2026-09-10T00:59:53Z` 至 `2026-09-11T00:59:53Z`。
- 未创建 cron、定时抓取或自动轮询任务；只登记指定异常类别。

5. 浏览器验收阻断
- 浏览器运行时原文为 `No browser is available`，可用浏览器列表为空。
- 未用 curl/API 冒充人工页面验收，因此最终状态为 `PRODUCTION_MONITORING_REQUIRED`。

---
下一步：你需要操作

第一步：连接一个可用浏览器后，人工打开 `https://aastock.cloud/`，逐条验证京东方公司页、贵州茅台 EOD/来源标注和 exact Q4 fail-closed 展示。

第二步：在 24 小时窗口结束时仅汇总已登记的 5xx、健康、重启、Tushare、空数据、资源和用户可见错误；不要创建定时抓取任务。

第三步：若页面验收通过且观察窗口无异常，再关闭 monitoring gate；若出现健康失败、连续重启或用户可见安全问题，单独评估是否需要 rollback。
