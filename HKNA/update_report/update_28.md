# Update 28 - Phase 6T-L Fast Path Correction, Job Admission Decoupling, and Live Acceptance

## 本次更新概览

Phase 6T-L 已完成代码层面的关键修复，并完成真实 live acceptance 核验，但性能 gate 仍未通过：

- job admission 从重型 readiness / structured load 中解耦；
- warm cache hit 改为先读持久化快照，不再在 cache lookup 之前重算 structured seed；
- `601686` 的 readiness 归一化测试补齐，RAG 状态回退到持久化 `ReportDocument.rag_status`；
- 新增 Phase 6T-L 回归测试与 acceptance 脚本；
- 前端面板继续保持手动触发、status/result 分离轮询；
- 真实 acceptance 已在可连接数据库环境执行；
- 601686 永久 RAG 已恢复并可由独立进程读取；
- backend full suite 已通过：3052 passed；
- frontend full suite 已通过：56 files / 639 tests passed；
- frontend build 已通过；
- 但 job create p95、job create p50、warm p50、warm speedup 仍未达到 Phase 6T-L gate。

## 主要变更

- `backend/app/services/company_v2_financial_fusion_job_service.py`
  - `create_job()` 变成轻量 admission。
  - 删除 admission 阶段对 structured seed / RAG status 的强依赖。
  - `run_job()` 在 worker 内再做 readiness 校验。
  - `RAG_NOT_INDEXED` 判断增加持久化 `ReportDocument.rag_status` 回退。
  - 阶段进度补回兼容的 `eligibility` / `readiness` 别名。

- `backend/app/services/company_v2_financial_evidence_fusion_service.py`
  - warm hit 先走 repository snapshot / cache entry，不再先加载 structured seed。
  - cache context 增加 `seed_path` / `selected_fields` 元数据。
  - cache hit 仍保留真实 metrics 统计。

- `backend/app/models/company_v2_financial_evidence_fusion.py`
  - snapshot 增加 `selected_fields`、`cache_context`、`seed_path`。

- `frontend/src/components/company-v2/reports/CompanyV2FinancialEvidenceFusionPanel.vue`
  - job stage 文案补齐 `validating_readiness` / terminal states。

- `backend/scripts/company_v2_financial_fusion_phase6tl_acceptance.py`
  - 已在真实数据库环境执行 acceptance。

- 新增 Phase 6T-L 测试：
  - job admission lightweight
  - no readiness on create
  - job create query count
  - warm cache before readiness
  - warm no provider
  - status no result hydration
  - 601686 RAG reconciliation
  - no auto run

## 已验证结果

- backend Phase 6T-L targeted tests: 9 passed
- backend full tests: 3052 passed
- frontend targeted tests: 4 passed
- frontend full tests: 56 files / 639 tests passed
- frontend build: passed
- live acceptance executed: yes

## 主要结果

- 601686 permanent RAG restored in PostgreSQL:
  - `repository_backend=database`
  - `persistent=true`
  - `active_rag_document_id=71`
  - `active_generation=1`
  - `persisted_chunk_count=296`
- job admission is lightweight and no longer triggers warm-path recomputation.
- warm hit reads persisted snapshot directly.
- singleflight and cancel checks passed.

## 当前阻塞

- `job_create_p95` exceeds gate
- `job_create_p50` exceeds gate
- `warm_result_p50` exceeds gate
- warm speedup is only about `1.07x`, below the required `3x`

## 结论

真实 acceptance 已完成，但 Phase 6T-L 仍应保持 `hold`，不写入通过 gate。
