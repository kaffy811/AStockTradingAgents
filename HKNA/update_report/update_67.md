---
目前完成的工作汇总：

已完成

1. 新增 Company V2 财务字段来源审计工具
- 新增 `backend/scripts/audit_company_financial_metric_provenance.py`。
- 支持按 market/symbol/metric/report_year/period_type 输出字段链路：
  - raw value / raw unit / source_key / payload path
  - period_end / period_type / report_year / value_type
  - normalization rule / warnings
  - service / repository / provider or source path
  - validation status / conflict audit
- 脚本不输出 DB URL、token、provider secret 或用户信息。
- 脚本落盘 JSON 已验证可被 `python -m json.tool` 解析。

2. 新增 canonical 财务字段字典
- 新增 `backend/docs/artifacts/company_financial_metric_dictionary.json`。
- 覆盖 revenue、operating_revenue、net_profit、parent_net_profit、operating_cashflow、total_assets、parent_equity、eps、roe、weighted_average_roe、gross_margin、net_margin、debt_ratio 等字段。
- 字典按 source_system + source_key 定义 raw_unit、normalized_unit、period_semantics、value_type、accounting_scope 和 normalization_rule。
- 明确禁止用数值大小启发式把 unknown unit 标记为 verified。

3. 收紧 CompanyChatDataService period 选择
- `get_financial_metrics()` 现在支持：
  - requested_metrics
  - target_period_type
  - target_report_year
  - allow_fallback
- 财报比较场景传入 `target_period_type=annual` 和共同 report_year。
- 若没有精确年度候选且 `allow_fallback=false`，返回 unavailable/unverified，不再拿 latest semiannual/quarter/TTM 冒充年报值。
- 财务快照场景仍可使用 latest fallback，但会保留真实 period metadata。

4. 页面与 Chat 使用同一来源链路
- Company 页面链路：controller -> `company_v2_history_service.build_company_history_dashboard`。
- Chat fallback 链路：`ReportComparisonSkill` -> `CompanyChatDataService` -> 同一 `build_company_history_dashboard`。
- 输出字段统一进入 `MetricNormalizer` 和 `FinancialMetricComparabilityService`。

5. 修复比较 fallback 的 verified 口径
- `ReportComparisonSkill` 在年报比较中不再让 Company fallback 继承 selected annual report title。
- 每个指标按自身 period_end / period_type / raw_unit / source_key 判定是否可比。
- `common_metric_count` 只统计 comparability=true 的指标。
- period/unit 不明的字段不会计入 verified common metrics。

6. 000858 本地审计结果
- 本地环境无法解析 Eastmoney/Tencent DNS，Sina proxy 被 sandbox 拒绝，BaoStock socket 不可用。
- 因本地没有命中可用 Company 财务缓存，000858 revenue 和 ROE 审计均输出：
  - validation.status=unverified
  - reason_codes=[METRIC_UNAVAILABLE]
  - financial_snapshot=unavailable
  - financial_history=unavailable
- 因此本地未确认 `405.29亿元` 的真实期间，也未确认 `0.07` 的真实 raw_unit；代码路径已保证这类值在无法追溯时不会被标记为 verified annual metric。

7. 测试与验证
- Targeted backend tests passed：11 passed。
- Adjacent backend tests passed：32 passed。
- Backend default full passed：3282 passed, 15 skipped。
- Frontend Vitest passed：679 passed。
- Frontend build passed。

未完成 / 受限

- 受当前本地外部网络限制，无法从真实 provider/cache 读取 000858 的 `405.29亿元` 与 `0.07` 记录。
- 需要在能访问真实 Company 缓存/数据库的服务器环境运行审计脚本，才能输出这两个值的最终 source_key、period_end、period_type 和 raw_unit。

---
下一步：你需要操作

第一步：在真实可访问环境运行：
`python backend/scripts/audit_company_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025 --period-type annual --metric revenue`

第二步：再运行：
`python backend/scripts/audit_company_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025 --period-type annual --metric roe`

第三步：浏览器回归：
1. 贵州茅台最新财报表现如何？
2. 那它和五粮液比呢

重点检查：
- `405.29亿元` 是否显示真实 period，若不是 annual 不计入年度 common count。
- `0.07` 是否依据 source_system + source_key 映射归一化；若 raw_unit unknown，则显示单位待确认。
- verified_common_count 是否只统计 period/unit/scope 全部对齐的字段。
