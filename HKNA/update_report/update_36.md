---
Phase 6T-Q same-region acceptance finalization

本次收口内容

1. 将临时 HTTP acceptance 收口为正式脚本 `backend/scripts/company_v2_financial_fusion_phase6tq_acceptance.py`。
2. 去掉对 `/tmp` 历史脚本和开发者本机绝对路径的依赖。
3. 固化 same-region runner 环境 artifact。
4. 固化 same-region acceptance artifact 与 final gate artifact。
5. 补充正式运行手册中的 Phase 6T-Q 章节。

真实验收结果

1. runner: Alibaba Cloud, `ap-northeast-2`
2. hermetic: `3065 passed, 9 deselected`
3. live Supabase: `9 passed`
4. same-region HTTP samples: `50`
5. steady-state create p50: `27.873 ms`
6. steady-state create p95: `29.707 ms`
7. active_jobs_after_cleanup: `0`

说明

1. 跨区域 Mac 测量不能代替 same-region acceptance。
2. 5 个验收前遗留 queued jobs 已通过正式 cancel API 清理。
3. 当前仍为 `auto_run=false`、`rollout_percent=0`。
4. Stage 3 仍未授权。
5. 本次不改变 Fusion / RAG / job admission 的业务语义。
