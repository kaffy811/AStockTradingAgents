# Phase 6U-P4 Production Regression Summary

## Fixture

Added `backend/tests/fixtures/phase6u_production_regression_cases.json` with 30 fixed production smoke cases:

- 财报与基本面: 8
- 多轮追问: 6
- 综合分析: 4
- 技术面: 4
- 新闻面: 4
- 数据缺失与安全: 4

Each case records expected route, skill, agent, required tools, entity, market, report context, prohibited content, required limitations, and expected output shape.

## Test Coverage

`backend/tests/fundamental/test_phase6u_production_regression.py` covers fixture loading, routing contracts, multi-turn entity/report context, narrow output shape, comprehensive numeric whitelist, limitation retention, conflict labeling, partial handling, all-missing no-synthesis behavior, safety filtering, source scope, duplicate removal, and schema compatibility.

## Results

- Targeted: `49 passed, 1282 deselected, 1 warning`
- Hermetic: `3139 passed, 15 deselected, 206 warnings`
- New skip count: 0
- Schema regression count: 0
- External provider/RAG/Fusion calls: 0

No deployment, Stage 3, auto-run rollout, or Canary action was performed.
