# Update 29 - Phase 6T-M Job Admission Latency Isolation and Warm Snapshot Read Optimization

## 本次更新概览

Phase 6T-M 已完成真实 acceptance、计时边界校准和热路径优化，但 steady-state job create 仍未进入 300ms gate：

- connection pool 从 `NullPool` 切换为 Postgres 下的 `AsyncAdaptedQueuePool`；
- `pool_pre_ping` 已移除，减少每次 checkout 额外 SQL；
- job admission 由 ORM `add()` 改为 direct `INSERT`；
- warm profile 不再在计时前预取 RAG status；
- acceptance 现在区分 connection-cold create 与 steady-state create；
- warm snapshot 真实命中已降到亚毫秒级；
- backend full suite 继续通过：3052 passed；
- frontend full suite 继续通过：56 files / 639 tests passed；
- frontend build 继续通过；
- 但 steady-state job create p50 仍为 `400.88ms`，高于 `300ms` gate。

## 主要变更

- `backend/app/core/database.py`
  - Postgres 环境改用小型可复用 `AsyncAdaptedQueuePool`。
  - 去掉 `pool_pre_ping`，降低 admission checkout 开销。

- `backend/app/services/company_v2_report_rag_db_repository.py`
  - RAG DB repository 也切换到同类连接池配置。

- `backend/app/services/company_v2_financial_fusion_job_service.py`
  - fresh create 由 ORM `add()` 改为 direct `INSERT`。
  - 仍保留 duplicate path 的查重语义。

- `backend/scripts/company_v2_financial_fusion_phase6tk_profile.py`
  - warm profile 不再在计时前预取 `company_v2_report_rag_index_service.status()`。

- `backend/scripts/company_v2_financial_fusion_phase6tl_acceptance.py`
  - 接受测试输出改为区分 connection-cold create 和 steady-state create。

- 新增 Phase 6T-M 测试：
  - connection pool reuse
  - warm snapshot prefetch boundary

## 已验证结果

- backend targeted tests: passed
- backend full tests: 3052 passed
- frontend full tests: 56 files / 639 tests passed
- frontend build: passed
- real acceptance executed: yes

## 主要性能结果

- connection-cold create: `2740.98ms`
- steady-state create p50: `400.88ms`
- steady-state create p95: `405.57ms`
- warm p50: `0.52ms`
- warm p95: `1.04ms`
- warm speedup: effectively far above `3x`

## 当前阻塞

- steady-state job create p50 is still above gate

## 结论

Phase 6T-M improved warm path correctness and latency, but the admission path still does not meet the `300ms` steady-state target. Final gate remains `hold`.
