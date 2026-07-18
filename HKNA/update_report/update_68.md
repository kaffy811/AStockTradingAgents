---
目前完成的工作汇总：

已完成

1. 建立 Provider Field Registry
- 新增 `backend/app/services/provider_field_registry.py`。
- 字段映射按 `provider + endpoint + field` 定义，不再按字段名或数值大小推断单位。
- 已覆盖当前 Company V2 核心 BaoStock 字段：
  - `query_profit_data`
  - `query_growth_data`
  - `query_balance_data`
  - `query_cash_flow_data`
  - `query_operation_data`
  - `query_dupont_data`
- 新增 artifact：`backend/docs/artifacts/company_financial_provider_field_registry.json`。

2. 补齐 provider → cache/dashboard 的 persisted provenance
- 更新 `backend/app/datasource/history_financial_provider.py`。
- 每条 normalized history row 现在会写入：
  - `financial_metric_schema_version=financial_metric_v1`
  - `field_provenance`
  - source_system / source_endpoint / source_key
  - raw_unit / normalized_unit
  - period_start / period_end / period_type / report_year
  - disclosed_at
  - accounting_scope / value_type / normalization_rule
- 不保存完整 provider raw payload，避免放大 Chat metadata。

3. 收紧 CompanyChatDataService 的 verified 判定
- 更新 `backend/app/services/company_chat_data_service.py`。
- Chat fallback 优先读取 persisted `field_provenance`。
- 旧缓存缺少 provenance 时标记：
  - `LEGACY_PROVENANCE_MISSING`
  - `legacy_unverified=true`
  - `validation_status=unverified`
- `allow_fallback=true` 的财务快照仍可展示 latest/interim 值，但不会作为 annual comparison 的 verified metric。
- `allow_fallback=false` 的年报比较继续只接受精确 annual + report_year + verified provenance。

4. 增加 coverage summary
- `get_financial_metrics()` 返回：
  - requested_metrics
  - available_metrics
  - verified_metrics
  - annual_exact_metrics
  - unit_unknown
  - period_unknown
  - conflicts
  - coverage_rate
- 用于后续比较 coverage before/after 和全市场聚合。

5. 新增 provenance backfill dry-run 脚本
- 新增 `backend/scripts/backfill_financial_metric_provenance.py`。
- 默认 dry-run，不写入。
- 支持：
  - `--market`
  - `--symbol`
  - `--report-year`
  - `--dry-run`
  - `--limit`
  - `--force-refresh`
- 只有显式 `--write --force-refresh` 才委托现有 dashboard refresh/cache 路径。

6. 更新审计脚本
- `backend/scripts/audit_company_financial_metric_provenance.py` 增加 `metric_coverage` 输出。
- 本地 000858 revenue 审计输出为 unavailable/unverified，未把无来源值升级为 verified。

7. 测试与验证
- 新增 `backend/tests/fundamental/test_phase6u_e1_3_4_financial_provenance.py`。
- 覆盖：
  - provider registry key
  - provider → dashboard provenance
  - persisted provenance verified unit
  - legacy value remains unverified
  - backfill dry-run no writes
  - annual request ignores legacy latest value
- Targeted tests passed：17 passed。
- Adjacent tests passed：52 passed。
- Backend default full passed：3288 passed, 15 skipped。
- Frontend Vitest passed：679 passed。
- Frontend build passed。

未完成 / 受限

- 当前本地环境仍无法访问真实 Eastmoney/Tencent/BaoStock 数据源，因此未能确认 000858 的 `405.29亿元` 与 `ROE 0.07` 的真实 source/period/raw_unit。
- 本轮保证：无法追溯时保持 unavailable/unverified，不会用启发式升级为 verified。

---
下一步：你需要操作

第一步：在可访问真实数据源的服务器运行 dry-run：
`cd backend && python scripts/backfill_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025 --dry-run --limit 20`

第二步：确认 dry-run 输出后再显式刷新单只股票：
`cd backend && python scripts/backfill_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025 --write --force-refresh --limit 20`

第三步：审计 000858 两个问题字段：
`cd backend && python scripts/audit_company_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025 --period-type annual --metric revenue`
`cd backend && python scripts/audit_company_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025 --period-type annual --metric roe`

第四步：浏览器回归：
1. 贵州茅台最新财报表现如何？
2. 那它和五粮液比呢

检查：
- 405.29 是否有真实 period/source。
- ROE 0.07 是否有 registry 或 persisted raw_unit。
- latest interim 值是否不会计入 annual verified common metric。
