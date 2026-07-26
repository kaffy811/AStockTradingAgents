# Phase 6T-E Cold Run Blocker — HISTORY_PROVIDER_N_PLUS_ONE_REQUESTS

生成日期：2026-07-11
状态：**phase6te_passed=false / performance_gate_passed=false**
处置：**action=optimize_history_fetch_before_rerun**（进入 Phase 6T-E1）

## 中断事实（真实记录，未伪造）

- 8 股 cold acceptance 于 600519 完成、000725 开始时被人工中断；
- 600519：elapsed **1611120 ms（约 26.9 分钟）**，completed=true，modules_ok=2；
- 期间 BaoStock 多次返回「接收数据异常，请稍后再试」（长会话逐季查询导致）；
- 其余 7 只未运行，不生成任何伪造结果；
- 601686 独立冒烟：cold 411595 ms（当时 history dashboard 无缓存）。

## 根因：N+1 逐季请求

调用图（修复前）：

```
Company /history request (1)
└─ build_company_history_dashboard
   └─ fetch_all_modules_history          ← aggregate_calls = 1（表面）
      └─ BaoStockClient.get_all_financial_indicators(n_quarters = (末年-上市年+1)*4+4)
         └─ _sync_fetch_all（单次 login/logout ✅）
            └─ for table in 6 张表:
               └─ for (year, quarter) in n_quarters:   ← ❌ 逐季串行网络查询
                  └─ bs.query_*_data(code, year, quarter)
```

- 600519（2001 上市）：n_quarters≈104 → **6 × 104 ≈ 624 次外部查询**；
- login 只有 1 次、模块间共享 aggregate ✅ —— 问题不在 session/模块复用，而在**逐季循环本身**；
- BaoStock query_*_data API 只支持按 (year, quarter) 查询，因此必须：年度批量 + 并发上限 + 分年缓存 + singleflight，而不是无限串行。

## 修复门槛（Phase 6T-E1）

| 指标 | 门槛 |
|---|---|
| annual full-history 外部调用 | 目标 <= 10（API 限制下：年度批量 + 并发 3 + 分年缓存） |
| quarterly 最近 5 年 | 目标 <= 25 |
| BaoStock login / 请求 | <= 1 |
| 普通 page 默认 | period=annual，不默认拉全部季度 |

> 本文档为真实性能阻断记录，不构成投资建议。
