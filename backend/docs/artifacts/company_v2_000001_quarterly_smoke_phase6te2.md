# Phase 6T-E1 跨股票真实验收报告（mode=deep）

生成日期：2026-07-11

## Gates

- history_gate_passed: **True**
- chart_gate_passed: **True**
- cninfo_gate_passed: **None**
- performance_gate_passed: **True**
- phase_gate_passed: **True**

symbols: 0 passed / 1 warning / 0 failed / 0 timeout

## Per-symbol

| symbol | list_date | modules_ok | annual rows(max) | quarterly rows(max) | provider_calls | logins | cache | elapsed ms | range label | cninfo | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 000001 | 1991-04-03 | 6 | 2 | 11 | 120 | 3 | cold | 33291 | 当前数据源覆盖 2021—2025 年 | skipped | warning |

## Blocking issues / warnings

### 000001
- warning: history_audit_warning:profitability
- warning: history_audit_warning:growth
- warning: history_audit_warning:solvency
- warning: history_audit_warning:operation_capability
- warning: history_audit_warning:cashflow_quality
- warning: history_audit_warning:dupont

> 本报告为真实数据验收结果，不构成投资建议。