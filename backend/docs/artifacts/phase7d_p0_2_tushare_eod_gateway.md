# Phase 7D-P0.2 — Grounded Tushare EOD Gateway

## 结论

候选实现已建立统一 Tushare EOD Gateway，并通过受控 live 验收。Gateway 仅允许 `stock_basic`、`daily`、`daily_basic`、`fina_indicator`，以及调用方显式提供指数映射时的 `index_daily`。本阶段没有调用 `news` 或任何网页抓取 Provider。

## 数据契约

每个可见事实均包含 `value`、`unit`、`as_of`、`source=tushare`、`source_status`、`freshness`、`field_availability` 与 `reason_code`。空值不会转换为 `0` 或推测值。

模块错误按 `credential`、`permission`、`network`、`http`、`schema`、`empty_result` 分类。任一 endpoint 失败只将对应模块标记为 `unavailable`，不会清空其他成功模块。

## 安全边界

- Token 只传给 Tushare SDK 初始化；初始化日志不再输出 Token 前缀。
- 错误响应不包含原始异常、请求头、SDK payload 或内部 trace。
- 普通公司页不再请求旧 `debug/full` 聚合；该请求仅在显式 debug 模式使用。
- 公开 EOD 响应的 `fallback_providers_used=[]`，不会回退 Eastmoney、AKShare、Sina 或 Tencent。
- `daily` 始终标注为最近可得 EOD/盘后数据，不称实时行情。
- 未修改全局鉴权、全局 timeout、全局缓存 TTL、Docker、依赖、migration 或 RAG。

## 缓存

复用 `company_v2_snapshot_cache_service` 的 SWR 隔离键 `tushare_eod:{market}:{symbol}:v1`。缓存故障不会阻断 endpoint 调用；缓存内容仍为标准化安全响应。

## 验证摘要

- 受控 live：`000725.SZ` 与 `600519.SH` 的四个白名单 endpoint 全部成功。
- 最近交易日：`2026-09-03`。
- 最近财务报告期：`2026-06-30`。
- 后端相关回归：143 passed。
- 完整前端低并发回归：69 files / 763 passed / 0 failed / 0 worker timeout。
- production build：971 modules transformed，通过。
- Python compile 与 `git diff --check`：通过。

详细公共运行结果见 `phase7d_p0_2_tushare_eod_runtime.json`。
