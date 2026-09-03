# Phase 6T-J 结构化核验 Seed 人工审核材料（2026-07-12）

生成方式：`scripts/company_v2_run_phase6tj_seed_verify.py`（薄封装，复用 Phase 6T-C `verify_with_ai` 真实 LLM + `build_full` 真实结构化数据 + sanitizer）。
每只 seed：`company_v2_{symbol}_ai_official_verification_phase6tj.json` + 对应 human_review_queue 文件。

| symbol | report_id | loader 兼容 | fields | verified | def_mismatch | conflict | struct_missing | official_not_found | skipped | queue | 泄漏 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 600519 | 2 | ✅ | 10 | 2 | 2 | 1 | 4 | 1 | 0 | 3 | 否 |
| 300750 | 3 | ✅ | 10 | 3 | 2 | 0 | 3 | 1 | 1 | 2 | 否 |
| 000725 | 4 | ✅ | 10 | 2 | 2 | 0 | 4 | 2 | 0 | 2 | 否 |
| 000001 | 5 | ✅ | 10 | 2 | 2 | 0 | 3 | 2 | 1 | 2 | 否 |

## Human Review Queue 明细

### 600519
- field=`revenue` page=6 reason=VALUE_DIFF_EXCEEDS_TOLERANCE
- field=`net_profit_parent` page=6 reason=field definition text indicates a different financial concept
- field=`roe_weighted` page=6 reason=field definition text indicates a different financial concept

### 300750
- field=`net_profit_parent` page=117 reason=field definition text indicates a different financial concept
- field=`roe_weighted` page=232 reason=field definition text indicates a different financial concept

### 000725
- field=`net_profit_parent` page=101 reason=field definition text indicates a different financial concept
- field=`roe_weighted` page=12 reason=field definition text indicates a different financial concept

### 000001
- field=`net_profit_parent` page=288 reason=field definition text indicates a different financial concept
- field=`roe_weighted` page=18 reason=field definition text indicates a different financial concept

## Readiness 复核

4/4 `readiness=ready`、`fusion_readiness=ready`、`next_manual_action=run_fusion`。

## 审核点

**fusion audit 未自动重跑**。请审核以上 seed 分类与 review queue，确认后授权重跑 `scripts/company_v2_financial_fusion_stage2_audit.py`。