---
目前完成的工作汇总：

已完成

1. Phase 6T-E3 多报告索引与隔离问答
- 在 Phase 6T-D 单报告 RAG 基础上扩展为同一股票多份报告独立索引。
- 普通问答继续强制单 report_id，不做跨报告 fallback，不自动搜索其他年份。
- 查询结果新增 `selected_report_id`、`retrieved_report_ids`、`cross_report_leakage_detected`。
- wrong-year 问题和季度报告问全年问题直接返回 `insufficient_evidence`。

2. 修改文件清单
- Backend:
  - `backend/app/models/company_v2_report_rag.py`
  - `backend/app/routers/company_v2_report_rag.py`
  - `backend/app/services/company_v2_report_rag_index_service.py`
  - `backend/app/services/company_v2_report_rag_index_manager.py`
  - `backend/app/services/company_v2_report_rag_index_queue.py`
  - `backend/app/services/company_v2_report_rag_retriever.py`
  - `backend/app/services/company_v2_report_rag_answer_service.py`
  - `backend/scripts/company_v2_multi_report_rag_eval.py`
  - `backend/tests/fundamental/phase6te3_helpers.py`
  - `backend/tests/fundamental/test_phase6te3_rag_index_manager.py`
  - `backend/tests/fundamental/test_phase6te3_rag_index_queue.py`
  - `backend/tests/fundamental/test_phase6te3_multi_report_isolation.py`
  - `backend/tests/fundamental/test_phase6te3_rag_refresh_atomic_switch.py`
  - `backend/tests/fundamental/test_phase6te3_rag_soft_delete.py`
  - `backend/tests/fundamental/test_phase6te3_rag_index_api.py`
- Frontend:
  - `frontend/src/api/companyV2.js`
  - `frontend/src/components/company-v2/CompanyV2ReportDocuments.vue`
  - `frontend/src/components/company-v2/CompanyV2ReportTimeline.vue`
  - `frontend/src/components/company-v2/reports/CompanyV2ReportQaPanel.vue`
  - `frontend/src/components/company-v2/reports/CompanyV2ReportRagIndexManager.vue`
  - `frontend/src/tests/companyV2ReportRagIndexManager.test.js`
- Artifacts / report:
  - `backend/docs/artifacts/company_v2_601686_multi_report_index_phase6te3.json`
  - `backend/docs/artifacts/company_v2_601686_multi_report_rag_eval_phase6te3.json`
  - `backend/docs/artifacts/company_v2_601686_multi_report_rag_eval_phase6te3.md`
  - `backend/docs/artifacts/company_v2_phase6te3_final_gate.json`
  - `backend/docs/artifacts/company_v2_phase6te3_final_gate.md`
  - `HKNA/update_report/update_21.md`

3. 索引唯一性与管理
- `ReportRagDocument` 增加唯一索引身份字段组合：report_id、symbol、report_year、report_type、pdf_hash、parse_version、embedding_version。
- 增加 `active_index`、`supersedes_rag_document_id`、`stale_reason`、`indexed_at`、`deleted_at`、`index_generation`。
- 新增 `company_v2_report_rag_index_manager.py`：
  - list_indexes
  - get_index
  - create_index
  - refresh_index
  - delete_index
  - mark_stale
  - rebuild_stale_index
  - get_index_progress
- refresh 失败不覆盖旧可用索引。
- delete 为 soft delete，不删除 PDF 和 page sidecar。

4. 轻量索引队列
- 新增 `company_v2_report_rag_index_queue.py`。
- job 状态：queued、running、succeeded、failed、cancelled。
- 同一 report_id 同时只允许一个 active job。
- job progress 返回 pages_processed、chunks_created、chunks_embedded、total_pages、percent。
- API 的 index/refresh 返回 job_id，不在请求线程中长时间阻塞。

5. API
- 新增/扩展：
  - `GET /api/v2/company/{market}/{symbol}/reports/rag/indexes`
  - `POST /api/v2/company/{market}/{symbol}/reports/{report_id}/rag/index`
  - `POST /api/v2/company/{market}/{symbol}/reports/{report_id}/rag/refresh`
  - `DELETE /api/v2/company/{market}/{symbol}/reports/{report_id}/rag/index`
  - `GET /api/v2/company/{market}/{symbol}/reports/{report_id}/rag/job`
  - `POST /api/v2/company/{market}/{symbol}/reports/{report_id}/rag/query`
- symbol/report_id 强校验保留。
- query 不接受无 report_id 的跨报告问答。

6. Frontend
- Report QA 面板新增报告选择器。
- 用户展开某份报告时默认选中当前报告。
- 切换报告会清空旧答案、旧 citation 和旧问题。
- 新增 `CompanyV2ReportRagIndexManager.vue`，默认不挂载，由“索引管理”按钮展开。
- 索引管理支持显示年份、报告类型、状态、chunk_count、indexed_at/stale_reason，并提供建立、刷新、删除入口。
- 删除前确认，不显示 local_path，不自动批量索引。

7. 真实 601686 三报告索引结果
- 2024 annual：
  - report_id=1
  - page_count=265
  - chunk_count=296
  - status=indexed
- 2024 q3：
  - report_id=2
  - page_count=13
  - chunk_count=14
  - status=indexed
- 2023 annual：
  - report_id=3
  - page_count=244
  - chunk_count=282
  - status=indexed
- 2024 Q3 与 2023 annual PDF 仅在本阶段真实验收中按指定报告从 CNINFO 官方下载/解析，不做全市场批量下载。

8. 幂等与 stale/refresh
- 重复创建 2024 annual 索引：
  - same_rag_document_id=true
  - repeated_generation=1
  - active_index_preserved=true
- stale/refresh：
  - stale_status=stale
  - stale_reason=phase6te3_stale_refresh_smoke
  - refresh_status=indexed
  - new_generation=2
  - supersedes_rag_document_id=1
  - history_count=2

9. 多报告隔离评估
- retrieval_hit_rate=1.00。
- citation_page_accuracy=1.00。
- cross_report_leakage=0。
- wrong_year_answer_rate=0.00。
- insufficient_evidence_correctness=1.00。
- 选中 2023 annual 问 2024 年营业收入：返回 insufficient_evidence，不跳到 2024 annual。
- 选中 2024 q3 问全年净利润：返回 insufficient_evidence，不跳到 2024 annual。

10. Tests / Build
- Backend targeted：25 passed。
- Backend full：2904 passed, 1 skipped。
- Frontend targeted：3 files / 28 tests passed。
- Frontend full：50 files / 623 tests passed。
- Frontend build：成功。
- 环境 warning：`pyenv: cannot rehash`，不影响测试/build。

11. Phase 6T-E3 Gate
- multi_index_gate_passed=true。
- index_idempotency_gate_passed=true。
- report_isolation_gate_passed=true。
- stale_refresh_gate_passed=true。
- citation_gate_passed=true。
- safety_gate_passed=true。
- frontend_gate_passed=true。
- tests_gate_passed=true。
- phase6te3_passed=true。
- blocking_issues=[]。
- recommendation_for_phase6tf=proceed。

12. Limitations
- 当前仍不支持普通问答自由跨报告综合。
- 当前不支持多股票比较。
- 当前不支持全市场批量索引。
- 当前索引 repository 仍是轻量抽象实现，后续若进入生产持久化，应迁移到 PostgreSQL/pgvector 或明确的持久化 job 表。

---
下一步：你需要操作

第一步：在页面中打开 601686 报告区域，展开“索引管理”，确认三份报告索引状态和删除/刷新交互符合预期。

第二步：在 Report QA 中切换 2024 annual、2024 q3、2023 annual 分别提问，确认切换报告会清空旧答案和 citation。

第三步：如继续推进，可进入 Phase 6T-F：Explicit Cross-Report Comparison。该阶段必须显式选择多个报告，不能复用普通单报告问答接口做隐式跨报告检索。
