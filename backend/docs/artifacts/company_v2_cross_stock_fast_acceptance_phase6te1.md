# Phase 6T-E1 跨股票真实验收报告（mode=fast）

生成日期：2026-07-11

## Gates

- history_gate_passed: **True**
- chart_gate_passed: **True**
- cninfo_gate_passed: **None**
- performance_gate_passed: **True**
- phase_gate_passed: **True**

symbols: 6 passed / 2 warning / 0 failed / 0 timeout

## Per-symbol

| symbol | list_date | modules_ok | annual rows(max) | quarterly rows(max) | provider_calls | logins | cache | elapsed ms | range label | cninfo | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 600519 | 2001-08-27 | 6 | 17 | — | 120 | 3 | cold | 145877 | 当前数据源覆盖 2007—2025 年 | skipped | passed |
| 000725 | 2001-01-12 | 6 | 19 | — | 120 | 3 | cold | 110498 | 当前数据源覆盖 2007—2025 年 | skipped | passed |
| 601686 | 2020-12-04 | 6 | 5 | — | 42 | 3 | cold | 76412 | 最近 5 期 | skipped | warning |
| 300750 | 2018-06-11 | 6 | 8 | — | 54 | 3 | cold | 87126 | 最近 8 期 | skipped | passed |
| 688981 | 2020-07-16 | 6 | 6 | — | 42 | 3 | cold | 58015 | 上市以来 | skipped | passed |
| 601318 | 2007-03-01 | 6 | 19 | — | 120 | 3 | cold | 136910 | 当前数据源覆盖 2007—2025 年 | skipped | passed |
| 000001 | 1991-04-03 | 6 | 18 | — | 120 | 3 | cold | 120181 | 当前数据源覆盖 2007—2024 年 | skipped | warning |
| 601728 | 2021-08-20 | 6 | 5 | — | 36 | 3 | cold | 53059 | 最近 5 期 | skipped | passed |

## Blocking issues / warnings

### 601686
- warning: history_audit_warning:dupont

### 000001
- warning: history_audit_warning:profitability
- warning: history_audit_warning:growth
- warning: history_audit_warning:solvency
- warning: history_audit_warning:operation_capability
- warning: history_audit_warning:cashflow_quality
- warning: history_audit_warning:dupont

> 本报告为真实数据验收结果，不构成投资建议。

## Regeneration Metadata

- artifact_regenerated_after_chart_fix: true
- retry_count_by_symbol.000725: 1
- 601686 chart_reaudit: chart_contract_valid=true; invalid_chart_contracts=[]
