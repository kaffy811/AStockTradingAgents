---
目前完成的工作汇总：

已完成

1. Stock EOD 请求级数值证据
- 新增 `backend/app/services/stock_eod_numeric_validation.py`。
- 为每条展示事实保留 metric、canonical/display value、unit、as_of、财务 report_period、source 与 request-local evidence id。
- 显式记录恒等显示、ROUND_HALF_UP 舍入和受控货币单位换算规则。

2. stock_eod_research 安全校验
- 回答中的行情和财务数字逐项绑定到本次请求的 Tushare/CNINFO 结构化事实。
- 股票代码和日期只通过专门 metadata 规则放行，不提供全整数豁免。
- 校验失败时返回 partial，并移除未经验证的数字展示。

3. 定向测试
- 覆盖收盘价、PE、PB、ROE、报告期、百分比、舍入和亿元换算。
- 覆盖编造数字、错误期间、错误单位、无来源、metadata 边界和安全 partial。
- P0.6 未修改 Report RAG numeric validator、Provider、缓存或 timeout。

---
下一步：你需要操作

第一步：从 P0.6 独立候选提交构建 backend/frontend 纯镜像，并核对 OCI revision、Mounts 与镜像秘密扫描。
第二步：在同一纯镜像环境逐条、串行、无重试执行 Q1–Q4。
第三步：若全部门禁通过，可请求审查此独立提交；不要 push、merge、部署、migration 或扩流。
