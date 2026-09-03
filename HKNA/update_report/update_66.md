---
目前完成的工作汇总：

已完成

1. 建立财务比较指标口径 DTO
- 新增 `financial_metric_comparability.py`，统一 FinancialMetric 字段：
  - raw_value / raw_unit
  - normalized_value / normalized_unit
  - currency / scale
  - period_end / period_type / report_year
  - accounting_scope / value_type
  - source_id / source_type / as_of
  - validation_status / warnings
- 旧字段仍保留，属于向后兼容增量，无 migration。

2. 增加确定性 MetricNormalizer
- `percentage_fraction` 来源字段按 Company V2 metadata 归一化：
  - ratio `0.07` → `7.0%`
  - percent `7.0` → `7.0%`
- unknown unit 标记 `UNIT_UNKNOWN` / `unverified`，不计入可靠共同可比指标。
- 不使用 “value < 1 就乘 100” 的数值大小启发式。

3. 增加 FinancialMetricComparabilityService
- 只有 metric、unit、currency、period_type、period_end、accounting_scope、value_type、validation_status 全部一致，且无 unresolved conflict，才计为 comparable。
- common count 不再按双方 non-null 计算，改为：
  - candidate_common_count：双方均有值
  - verified_common_count / common_metric_count：通过期间与单位校验
  - excluded_metrics：记录 PERIOD_TYPE_MISMATCH、UNIT_UNKNOWN 等原因

4. 修复 Company fallback 指标口径
- `CompanyChatDataService` 现在保留 source_key、raw_unit、period_type、report_year、value_type、accounting_scope。
- fallback 指标不再被 selected report title 覆盖期间。
- `405.29亿元` 若来自 2025-06-30，会显示为 `2025年中报口径`，并不会计入与 2025 年报的 verified common metric。

5. 修复比较输出
- 指标值展示自己的真实期间，例如 `405.29 亿元（2025年中报口径）`。
- 来源列拆成左右两侧来源：
  - 年报字段
  - Company缓存
  - Company缓存·期间
  - Company缓存·单位待确认
- 当 verified common count 为 0 时，不生成“谁更强/谁更稳健”等横向比较结论，只提示暂时无法形成可靠年度横向比较。

6. 测试与验证
- 新增 E1.3.2 专项测试：
  - ratio 0.07 → 7%
  - percent 7 → 7%
  - unknown unit excluded
  - annual vs semiannual not comparable
  - point-in-time date mismatch
  - non-null but mismatched metrics not counted
  - source labels and zero-common presentation
- Targeted backend tests passed。
- Backend default full passed：3280 passed, 15 skipped。
- Frontend Vitest passed：679 passed。
- Frontend build passed。

未完成 / 受限

- 本地直接调用 000858 CompanyChatDataService 时，外部 quote/BaoStock 网络不可达，未能在本机确认真实 `405.29亿元` 的 period 和 `0.07` 的 raw unit。
- 代码已保证真实数据进入后按原始 period/source schema 展示和校验，不再把 fallback metric 自动挂到 selected annual report title 下。

---
下一步：你需要操作

第一步：在可访问真实 Company 缓存/数据库的浏览器环境重跑：
1. 贵州茅台最新财报表现如何？
2. 那它和五粮液比呢

第二步：重点检查输出：
- 五粮液 `405.29亿元` 后是否标注真实期间。
- 五粮液 ROE `0.07` 是否按 source schema 归一化为 `7.00%`，或在 source unit unknown 时被标记为单位待确认。
- `verified_common_count` 是否只统计 period/unit/scope 全部对齐的指标。
- 当 verified common count 为 0 时，不输出横向强弱结论。

第三步：若真实环境仍显示 `0.07%`，优先检查该字段是否缺失 `source_key` / Company V2 metadata 映射，不能用数值大小规则兜底。
